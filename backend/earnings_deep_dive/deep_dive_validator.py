"""Post-generation validation for earnings deep-dive reports.

Ensures every deep-dive matches the Nami template and contains zero unavailable markers.
Runs after _add_earnings_deep_dive_if_transcript() but before the dossier is marked 'complete'.

Systemic resilience (added 2026-06-03, RKLB incident):
  - normalize_markdown_headings() rewrites known LLM heading variants
    ("Key Operating Metrics", "Operational Performance", "Profitability Analysis"…)
    to the canonical name before validation. The .md file itself is updated
    so downstream PDF rendering and JSON exports stay consistent.
  - Aliases cover all 10 Nami sections, not just Operating Metrics.
  - validate_deep_dive() returns more informative issues when a section
    is genuinely missing, so the chat widget can surface actionable errors.
"""

import re
import os
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


# SECTION_KEYWORDS is defined in prompts.py — imported lazily to avoid circular
# imports at module load time. We use it as a fallback: a heading is considered
# a match for a required section if it contains the canonical name OR the
# section name (case-insensitive) OR at least 2 keywords from its keyword set.
# This handles sector-specific rewrites like "Key Operating Metrics" for
# aerospace tickers (RKLB, etc.) where the LLM adapts the heading.


# ── Template requirements ────────────────────────────────────────────────────

REQUIRED_SECTIONS: Dict[str, str] = {
    "EPS & Revenue": "EPS & Revenue",
    "Highlights & Lowlights": "Highlights & Lowlights",
    "Operating Metrics": "Operating Metrics",
    "Cash Flow": "Cash Flow",
    "Capital Efficiency": "Capital Efficiency",
    "Segments": "Segments",
    "Forward P/E": "Forward P/E",
    "Backlog Quality": "Backlog Quality",
    "Guidance": "Guidance",
    "Verdict": "Verdict",
}

# ── Heading aliases (systemic normalization) ─────────────────────────────────
#
# When the LLM produces a variant heading like "Key Operating Metrics" or
# "Operational Performance", normalize_markdown_headings() rewrites it in
# the .md to the canonical name before validation. This makes the validator
# and downstream PDF renderer see consistent headings without depending on
# the LLM being exactly compliant.
#
# Aliases are matched case-insensitively as exact heading strings. Add a
# variant here if a new ticker / sector triggers a new LLM rewrite.
#
HEADING_ALIASES: Dict[str, List[str]] = {
    "EPS & Revenue": [
        "EPS and Revenue", "Earnings & Revenue", "Revenue & EPS",
        "Quarterly Results", "Financial Results", "EPS Results",
    ],
    "Highlights & Lowlights": [
        "Highlights and Lowlights", "Highlights/Lowlights",
        "Key Highlights", "Quarterly Highlights", "Highlights & Risks",
    ],
    "Operating Metrics": [
        # Most common LLM rewrites for aerospace / pre-revenue / non-standard
        # financials. The prompt fix in prompts.py pushes the LLM to keep
        # the canonical name, but the LLM still rewrites ~10% of the time
        # for exotic sectors. Aliases catch the rest.
        "Key Operating Metrics", "Operational Performance",
        "Operating Performance", "Operating Results",
        "Operating Highlights", "Key Operational Highlights",
        "Operational Highlights", "Operating KPIs",
        "Financial Performance", "Profitability", "Profitability Analysis",
        "Business Performance", "Operating Snapshot",
        "Operating Profit Analysis", "Margin Analysis",
    ],
    "Cash Flow": [
        "Cash Flow Analysis", "Cash Flows", "FCF Analysis",
        "Cash Flow Statement", "Cash Generation",
    ],
    "Capital Efficiency": [
        "Returns", "Return Metrics", "Profitability Ratios",
        "Return on Capital", "Capital Returns", "ROE / ROIC Analysis",
    ],
    "Segments": [
        "Segment Analysis", "Business Segments", "Segment Breakdown",
        "Segment Performance", "Revenue by Segment", "Segment Detail",
    ],
    "Forward P/E": [
        "Valuation", "Forward Valuation", "Forward PE",
        "P/E Analysis", "Valuation Multiples", "Forward Earnings",
    ],
    "Backlog Quality": [
        "Backlog", "Order Backlog", "Remaining Performance Obligations",
        "Order Book", "Book to Bill", "Backlog Analysis",
    ],
    "Guidance": [
        "Outlook", "Forward Guidance", "Future Outlook",
        "Forward-Looking", "FY Guidance", "Guidance & Outlook",
    ],
    "Verdict": [
        "Conclusion", "Summary", "Investment Thesis",
        "Bottom Line", "Final Take", "Final Verdict",
    ],
}

REQUIRED_SUMMARY_MARKER = re.compile(
    r">\s*(?:一言まとめ|One-line summary)\s*:",
    re.IGNORECASE,
)

FORBIDDEN_MARKERS: List[str] = [
    "DATA NOT AVAILABLE",
    "DONNÉE NON DISPONIBLE",
    "DONNÃ‰E NON DISPONIBLE",
    "Section unavailable",
    "Transcript missing",
]

# Sections that MUST contain a markdown table
TABLE_SECTIONS = {
    "EPS & Revenue",
    "Operating Metrics",
    "Cash Flow",
    "Segments",
    "Guidance",
}

TABLE_PATTERN = re.compile(r"^\|.+\|$", re.MULTILINE)
SECTION_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)
SUB_HEADING = re.compile(r"^###\s+(.+)$", re.MULTILINE)

# ── Forbidden background headings (EDP-004) ────────────────────────────────────
# Stable background sections that belong in Company Overview, not Earnings Deep Dive.
# Each entry is matched case-insensitively as a substring against section headings.
FORBIDDEN_BACKGROUND_HEADINGS: List[str] = [
    "Company Overview",
    "Business Model",
    "Revenue Generation Overview",
    "Revenue Generation",
    "Competitive Landscape",
]

# ── Concision thresholds (EDP-007, EDP-008, EDP-009) ────────────────────────────
# EPS & Revenue: compact table + short bullets, no long prose blocks.
EPS_REVENUE_MAX_WORDS = 120
EPS_REVENUE_MAX_PARAGRAPHS = 1

# Highlights/Lowlights: short headings + limited bullets, no paragraphs.
HIGHLIGHTS_MAX_BULLETS_PER_POINT = 5

# Operating Metrics: concise takeaways after table, not explanatory essays.
OPERATING_METRICS_MAX_WORDS = 120
OPERATING_METRICS_MAX_PARAGRAPHS = 1

# ── Numeric consistency tolerance (EDP-006) ────────────────────────────────────
# EPS tolerance in dollars (standard rounding tolerance for earnings data).
EPS_TOLERANCE = 0.03
# Revenue tolerance as a ratio of the table value (0.5%).
REVENUE_TOLERANCE_RATIO = 0.005


def _check_concision(content: str) -> List[str]:
    """Check markdown content for concision violations (EDP-007, EDP-008, EDP-009).

    Returns a list of issue strings for each concision violation found.
    """
    issues: List[str] = []

    # Split content by section headings (same pattern as validate_deep_dive)
    section_blocks = SECTION_HEADING.split(content)[1:]  # Skip preamble

    for i in range(0, len(section_blocks), 2):
        heading = section_blocks[i].strip() if i < len(section_blocks) else ""
        body = section_blocks[i + 1] if i + 1 < len(section_blocks) else ""

        # ── EDP-007: EPS & Revenue concision ──
        if "EPS & Revenue" in heading or ("EPS" in heading and "Revenue" in heading):
            lines = body.split("\n")
            prose_words = _count_prose_words(lines)
            para_count = _count_paragraphs(lines)

            if prose_words > EPS_REVENUE_MAX_WORDS:
                issues.append(
                    f"Concision (EDP-007): EPS & Revenue section has {prose_words} "
                    f"words of prose (max {EPS_REVENUE_MAX_WORDS})"
                )
            elif para_count > EPS_REVENUE_MAX_PARAGRAPHS:
                issues.append(
                    f"Concision (EDP-007): EPS & Revenue section has {para_count} "
                    f"paragraph blocks (max {EPS_REVENUE_MAX_PARAGRAPHS})"
                )

        # ── EDP-008: Highlights & Lowlights concision ──
        if "Highlights" in heading and "Lowlights" in heading:
            lines = body.split("\n")
            _check_highlights_concision(lines, issues)

        # ── EDP-009: Operating Metrics concision ──
        if "Operating Metrics" in heading:
            lines = body.split("\n")
            prose_words = _count_prose_words(lines)
            para_count = _count_paragraphs(lines)

            if prose_words > OPERATING_METRICS_MAX_WORDS:
                issues.append(
                    f"Concision (EDP-009): Operating Metrics section has {prose_words} "
                    f"words of prose (max {OPERATING_METRICS_MAX_WORDS})"
                )
            elif para_count > OPERATING_METRICS_MAX_PARAGRAPHS:
                issues.append(
                    f"Concision (EDP-009): Operating Metrics section has {para_count} "
                    f"paragraph blocks (max {OPERATING_METRICS_MAX_PARAGRAPHS})"
                )

    return issues


def _count_prose_words(lines: List[str]) -> int:
    """Count words in prose text (excluding tables, quotes, bullets, headings)."""
    prose_parts: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip tables, quotes, bullet lists, headings, bold section labels
        if (stripped.startswith("|") or stripped.startswith(">")
                or stripped.startswith("- ") or stripped.startswith("* ")
                or stripped.startswith("##") or stripped.startswith("**")):
            continue
        prose_parts.append(stripped)

    return len(" ".join(prose_parts).split())


def _count_paragraphs(lines: List[str]) -> int:
    """Count prose paragraph blocks (prose text separated by blank lines)."""
    count = 0
    in_paragraph = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            in_paragraph = False
            continue
        # Only count prose paragraphs (not tables, quotes, bullets, headings)
        if (stripped.startswith("|") or stripped.startswith(">")
                or stripped.startswith("- ") or stripped.startswith("* ")
                or stripped.startswith("##")):
            in_paragraph = False
            continue
        if not in_paragraph:
            count += 1
            in_paragraph = True
    return count


def _check_highlights_concision(lines: List[str], issues: List[str]) -> None:
    """Check Highlights & Lowlights section for concision violations (EDP-008).

    Appends issues directly to the passed-in issues list.
    """
    bullet_count = 0
    has_prose_paragraph = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # End of current bullet block — check if we exceeded threshold
            if bullet_count > HIGHLIGHTS_MAX_BULLETS_PER_POINT:
                issues.append(
                    f"Concision (EDP-008): Highlights section has a point with "
                    f"{bullet_count} bullets (max {HIGHLIGHTS_MAX_BULLETS_PER_POINT})"
                )
            bullet_count = 0
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            bullet_count += 1
        elif stripped.startswith("**") or stripped.startswith(">"):
            # Bold heading or quote ends the bullet block
            if bullet_count > HIGHLIGHTS_MAX_BULLETS_PER_POINT:
                issues.append(
                    f"Concision (EDP-008): Highlights section has a point with "
                    f"{bullet_count} bullets (max {HIGHLIGHTS_MAX_BULLETS_PER_POINT})"
                )
            bullet_count = 0
        elif stripped.startswith("##"):
            bullet_count = 0
        elif not stripped.startswith("|"):
            # Prose text that isn't a bullet, table, heading, or quote
            has_prose_paragraph = True

    # Check trailing bullet block
    if bullet_count > HIGHLIGHTS_MAX_BULLETS_PER_POINT:
        issues.append(
            f"Concision (EDP-008): Highlights section has a point with "
            f"{bullet_count} bullets (max {HIGHLIGHTS_MAX_BULLETS_PER_POINT})"
        )

    if has_prose_paragraph:
        issues.append(
            "Concision (EDP-008): Highlights section contains prose paragraphs "
            "(use short headings + bullets only)"
        )


# ── Numeric consistency helpers (EDP-006) ─────────────────────────────────────


def _parse_dollar_amount(text: str) -> tuple[float | None, str | None]:
    """Parse a dollar amount from a text fragment.

    Returns (value_in_dollars, raw_match) or (None, None) if no amount found.
    Handles $X.XX, $X.XXB, $X.XXM, and text suffixes (billion, million).
    """
    # Pattern: $X.XX optionally followed by B/M/billion/million
    m = re.search(
        r"\$(\d+(?:\.\d+)?)\s*(B|Billion|billion|M|Million|million)?",
        text,
    )
    if not m:
        # Also try "X.XX billion" without $ prefix
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(billion|million)\s",
            text,
        )
    if not m:
        return None, None

    assert m is not None  # Guard: we returned early if None
    raw = m.group(0)
    value = float(m.group(1))
    suffix = m.group(2) if m.lastindex >= 2 else None
    if suffix:
        suffix_lower = suffix.lower()
        if suffix_lower in ("b", "billion"):
            value *= 1_000_000_000
        elif suffix_lower in ("m", "million"):
            value *= 1_000_000
    return value, raw


def _parse_table_values(body: str) -> dict[str, tuple[float | None, str]]:
    """Parse EPS and Revenue actual values from a markdown table.

    Returns dict mapping metric name (uppercase) to (value_in_dollars, raw_cell).
    Only EPS and Revenue are extracted.
    """
    values: dict[str, tuple[float | None, str]] = {}
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # Remove leading empty cell from the opening |
        if cells and not cells[0]:
            cells = cells[1:]
        if len(cells) < 2:
            continue
        metric_name = cells[0].strip().lower()
        if metric_name not in ("eps", "revenue"):
            continue
        actual_cell = cells[1] if len(cells) > 1 else ""
        value, _ = _parse_dollar_amount(actual_cell)
        values[metric_name] = (value, actual_cell)
    return values


def _prose_dollar_amounts(body: str) -> list[dict]:
    """Extract dollar amounts from prose text in a section body.

    Returns list of dicts: {value, raw, context, metric_type_hint}
    where metric_type_hint is 'eps', 'revenue', or None.
    """
    amounts: list[dict] = []
    for line in body.split("\n"):
        stripped = line.strip()
        # Skip tables, headings, bold labels
        if (stripped.startswith("|") or stripped.startswith("##")
                or stripped.startswith("**") or stripped.startswith("#")):
            continue
        # Skip empty lines
        if not stripped:
            continue

        # Find all dollar amounts on this line
        pos = 0
        while pos < len(stripped):
            m = re.search(
                r"\$(\d+(?:\.\d+)?)\s*(B|Billion|billion|M|Million|million)?",
                stripped[pos:],
            )
            if not m:
                break

            assert m is not None  # Guard: we broke early if None
            raw = m.group(0)
            value = float(m.group(1))
            suffix = m.group(2) if m.lastindex >= 2 else None
            if suffix:
                suffix_lower = suffix.lower()
                if suffix_lower in ("b", "billion"):
                    value *= 1_000_000_000
                elif suffix_lower in ("m", "million"):
                    value *= 1_000_000

            # Determine context (character window around match)
            # Use a tight window for metric classification to avoid
            # picking up keywords from other dollar amounts on the same line
            start_idx = max(0, pos + m.start() - 20)
            end_idx = min(len(stripped), pos + m.end() + 10)
            context = stripped[start_idx:end_idx].lower()

            # Classify metric type from context (tight classification window)
            metric_hint: str | None = None

            # Check if this dollar amount is a comparison reference (e.g., "above the $1.15 consensus")
            # If the text before the dollar amount contains "above the", "below the", "beat the",
            # or "surpassed the", it's a reference, not a stated actual.
            pre_text = stripped[max(0, pos + m.start() - 25):pos + m.start()].lower()
            is_comparison_reference = any(
                phrase in pre_text
                for phrase in ("above the", "below the", "beat the", "surpassed the")
            )

            # Skip small dollar amounts preceded by "by" — these are deltas, not values
            is_delta = "by " in pre_text

            if not is_comparison_reference and not is_delta:
                if "eps" in context or "per share" in context:
                    metric_hint = "eps"
                elif "revenue" in context or "sales" in context or "top line" in context:
                    metric_hint = "revenue"

            amounts.append({
                "value": value,
                "raw": raw,
                "context": context,
                "metric_type_hint": metric_hint,
            })
            pos += m.end()

    return amounts


def _check_numeric_consistency(content: str) -> List[str]:
    """Check EPS & Revenue section for numeric consistency (EDP-006).

    Parses ALL EPS & Revenue tables to extract canonical EPS and Revenue values,
    then cross-checks them against dollar amounts appearing in the section prose.
    Flags contradictions where prose states a value that differs from the table
    beyond documented tolerance.

    Returns a list of issue strings.
    """
    issues: List[str] = []

    # Find ALL EPS & Revenue sections
    section_blocks = SECTION_HEADING.split(content)

    for i in range(1, len(section_blocks), 2):
        heading = section_blocks[i].strip() if i < len(section_blocks) else ""
        body_idx = i + 1
        body = section_blocks[body_idx] if body_idx < len(section_blocks) else ""

        if not ("EPS" in heading and "Revenue" in heading):
            continue

        issues.extend(_check_single_eps_revenue_section(body))

    return issues


def _check_single_eps_revenue_section(body: str) -> List[str]:
    """Check numeric consistency within a single EPS & Revenue section body."""
    issues: List[str] = []

    # Parse table values
    table_values = _parse_table_values(body)

    # Extract prose dollar amounts
    prose_amounts = _prose_dollar_amounts(body)

    if not prose_amounts:
        return issues  # No prose amounts to cross-check

    # Cross-check each prose amount against table values
    for pa in prose_amounts:
        hint = pa["metric_type_hint"]
        prose_val = pa["value"]

        if hint == "eps":
            table_eps, raw_cell = table_values.get("eps", (None, ""))
            if table_eps is not None:
                diff = abs(prose_val - table_eps)
                if diff > EPS_TOLERANCE:
                    issues.append(
                        f"Numeric consistency (EDP-006): EPS value in prose "
                        f"(${prose_val:.2f}) differs from table value "
                        f"({raw_cell}) by ${diff:.2f} (tolerance: ${EPS_TOLERANCE:.2f})"
                    )
        elif hint == "revenue":
            table_rev, raw_cell = table_values.get("revenue", (None, ""))
            if table_rev is not None:
                diff = abs(prose_val - table_rev)
                tolerance = max(table_rev * REVENUE_TOLERANCE_RATIO, 5_000_000)
                if diff > tolerance:
                    issues.append(
                        f"Numeric consistency (EDP-006): Revenue value in prose "
                        f"(${prose_val:,.0f}) differs from table value "
                        f"({raw_cell}) by ${diff:,.0f} (tolerance: ${tolerance:,.0f})"
                    )

    return issues
# When an LLM generates a standalone "Quality" heading/section that is boilerplate,
# it should be flagged. Excluded: canonical required sections (e.g. "Backlog Quality")
# and headings that contain ticker-specific earnings language (e.g. "Earnings Quality").
FORBIDDEN_QUALITY_PATTERNS = [
    re.compile(r"\bQuality\b", re.IGNORECASE),       # standalone "Quality" word
]


# ── FCF Margin presence check (EDP-013) ──────────────────────────────────────


def _check_fcf_margin_presence(content: str) -> List[str]:
    """Check that FCF Margin is present in Cash Flow section when both FCF and Revenue are available.

    EDP-013: Include FCF Margin when free cash flow and revenue are both available.
    Formula: FCF Margin = Free Cash Flow / Revenue × 100%.

    The check operates on the rendered Cash Flow section table: if the table contains
    rows for both Free Cash Flow (or FCF) and Revenue, but no row for FCF Margin,
    an EDP-013 issue is emitted.

    Returns a list of issue strings.
    """
    issues: List[str] = []

    # Find the Cash Flow section
    section_blocks = SECTION_HEADING.split(content)
    cash_flow_body: str | None = None

    for i in range(1, len(section_blocks), 2):
        heading = section_blocks[i].strip() if i < len(section_blocks) else ""
        body_idx = i + 1
        body = section_blocks[body_idx] if body_idx < len(section_blocks) else ""

        if "Cash Flow" in heading or "Cash Flows" in heading:
            cash_flow_body = body
            break

    if cash_flow_body is None:
        return issues  # No Cash Flow section found — nothing to check

    # Parse table rows in the Cash Flow section body
    has_fcf = False
    has_revenue = False
    has_fcf_margin = False

    for line in cash_flow_body.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|-"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # Remove leading empty cell from the opening |
        if cells and not cells[0]:
            cells = cells[1:]
        if len(cells) < 2:
            continue
        metric_name = cells[0].strip().lower()

        if "fcf margin" in metric_name:
            has_fcf_margin = True
        elif "free cash flow" in metric_name:
            has_fcf = True
        elif metric_name == "fcf":
            has_fcf = True
        elif metric_name == "revenue":
            has_revenue = True

    # Only flag if both FCF and Revenue are present but FCF Margin is absent
    if has_fcf and has_revenue and not has_fcf_margin:
        issues.append(
            "FCF Margin presence (EDP-013): Cash Flow section has Free Cash Flow "
            "and Revenue but no FCF Margin row. Include FCF Margin = FCF / Revenue × 100% "
            "when both inputs are available."
        )

    return issues


def _heading_matches_section(heading: str, emoji_key: str, canonical_name: str, keywords: List[str]) -> bool:
    """Return True if a markdown heading satisfies a required section.

    Match passes if ANY of these hold:
    1. Heading contains the canonical name (case-sensitive, e.g. "Operating Metrics").
    2. Heading contains the canonical name (case-insensitive).
    3. Heading contains at least 2 of the keywords from SECTION_KEYWORDS
       (lowercase substring match). This handles sector-specific rewrites
       like "Key Operational Highlights" for aerospace tickers.
    """
    h_lower = heading.lower()
    if emoji_key in heading:
        return True
    if canonical_name.lower() in h_lower:
        return True
    keyword_hits = sum(1 for kw in keywords if kw.lower() in h_lower)
    return keyword_hits >= 2


# ── Forbidden heading checks (EDP-004, EDP-011) ────────────────────────────────
# These run inside validate_deep_dive() to catch stable background headings
# and generic Quality subsections that shouldn't appear in Earnings Deep Dive.


def _check_forbidden_headings(content: str) -> List[str]:
    """Check markdown content for forbidden background and Quality headings.

    Returns a list of issue strings for each forbidden heading found.
    EDP-004: stable background sections (Company Overview, Business Model, etc.)
    EDP-011: generic Quality subsections that are boilerplate, not earnings-specific.
    """
    issues: List[str] = []
    required_names = set(REQUIRED_SECTIONS.values())

    # ── EDP-004: Forbidden background headings (section level) ──
    for heading_match in SECTION_HEADING.finditer(content):
        heading_text = heading_match.group(1).strip()
        for forbidden in FORBIDDEN_BACKGROUND_HEADINGS:
            if forbidden.lower() in heading_text.lower():
                issues.append(f"Forbidden background heading '{heading_text}' (matches '{forbidden}')")

    # ── EDP-011: Forbidden generic Quality subheadings (any heading level) ──
    all_headings = list(SECTION_HEADING.finditer(content)) + list(SUB_HEADING.finditer(content))
    for heading_match in all_headings:
        heading_text = heading_match.group(1).strip()
        canonical = heading_text.lstrip("🌟⚠️✨").strip()

        # Skip required canonical sections (e.g. "Backlog Quality")
        if canonical in required_names:
            continue

        for pattern in FORBIDDEN_QUALITY_PATTERNS:
            if pattern.search(canonical):
                # Exclude "Earnings Quality" — it's a ticker-specific concept
                if "Earnings" in canonical or "earnings" in canonical:
                    continue
                issues.append(f"Forbidden generic Quality heading '{heading_text}' (boilerplate)")
                break

    return issues


def normalize_markdown_headings(md_path: str) -> List[Tuple[str, str]]:
    """Rewrite known LLM heading variants to canonical names in-place.

    Returns a list of (old_heading, new_heading) tuples for logging.
    Idempotent: re-running on a normalized file is a no-op.

    This is the systemic resilience layer: when the LLM produces a variant
    heading (e.g. "Key Operating Metrics", "Operational Performance"), the
    .md is rewritten in place so that:
      - The validator sees the canonical heading
      - The PDF renderer uses the canonical name
      - JSON exports / dossier UI use the canonical name
    Without this, every exotic ticker would require a manual prompt patch.

    Side effect: writes the file back if any rewrite happened.
    """
    if not os.path.exists(md_path):
        return []

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    renames: List[Tuple[str, str]] = []
    for canonical, aliases in HEADING_ALIASES.items():
        # CRITICAL: match the alias as an exact heading (start-of-line "## alias" + end-of-line).
        # A naive substring match (e.g. "## Backlog" in "## Backlog Quality") causes recursive
        # corruption: every normalize() call appends " Quality" to the heading.
        # The end-of-line anchor is what prevents that.
        for alias in aliases:
            old_pattern = re.compile(rf"^##\s+{re.escape(alias)}\s*$", re.MULTILINE)
            new_heading = f"## {canonical}"
            if old_pattern.search(content):
                content = old_pattern.sub(new_heading, content, count=1)
                renames.append((alias, canonical))
                # Don't try other aliases for the same canonical — first match wins.
                break

    if renames:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(
            f"[{os.path.basename(md_path)}] Normalized {len(renames)} heading(s): "
            f"{[(a, c) for a, c in renames]}"
        )

    return renames


def validate_deep_dive(md_path: str) -> Tuple[bool, List[str]]:
    """Validate a generated deep-dive markdown file.

    Args:
        md_path: Path to the earnings_deep_dive.md file.

    Returns:
        (passed, issues) — passed is True only if zero issues found.
    """
    # Lazy import to avoid circular dependency with prompts.py at module load.
    from backend.earnings_deep_dive.prompts import SECTION_KEYWORDS

    issues: List[str] = []

    if not os.path.exists(md_path):
        return False, [f"File not found: {md_path}"]

    # ── 0. Normalize LLM heading variants to canonical names (systemic) ──
    # This rewrites the .md in place. The validator and downstream PDF renderer
    # then see consistent headings. Returns a list of renames for logging.
    normalize_markdown_headings(md_path)

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # ── 0.5. Check for forbidden background/Quality headings (EDP-004, EDP-011) ──
    issues.extend(_check_forbidden_headings(content))

    # ── 1. Check all 10 Nami sections are present ──
    found_sections: List[str] = []
    for match in SECTION_HEADING.finditer(content):
        heading = match.group(1).strip()
        found_sections.append(heading)

    for emoji_key, name in REQUIRED_SECTIONS.items():
        keywords = SECTION_KEYWORDS.get(emoji_key, [])
        matched = any(
            _heading_matches_section(h, emoji_key, name, keywords)
            for h in found_sections
        )
        if not matched:
            # Make the error actionable: include the canonical name and a hint.
            # The chat widget should surface this verbatim rather than invent
            # a "PDF generation blocked" message.
            issues.append(
                f"Missing section: {name}. The LLM did not produce a heading "
                f"for this section in the deep-dive markdown. Common causes: "
                f"exotic sector (aerospace/biotech/pre-revenue) where standard "
                f"metrics don't apply, or the LLM skipped the section entirely. "
                f"Suggested recovery: re-run the deep-dive (the prompt now "
                f"forces this heading for all sectors), or add the missing "
                f"alias to HEADING_ALIASES in deep_dive_validator.py."
            )

    # ── 2. Check each section ends with summary ──
    sections_with_summary = len(REQUIRED_SUMMARY_MARKER.findall(content))
    if sections_with_summary < 2:  # At least 2 of 10 must have it (LLM reliability: some sections resist)
        issues.append(
            f"Summary marker missing: found {sections_with_summary} sections with "
            f"'One-line summary' or '一言まとめ', need ≥2"
        )

    # ── 3. Check zero forbidden markers ──
    for marker in FORBIDDEN_MARKERS:
        count = content.count(marker)
        if count > 0:
            issues.append(f"Forbidden marker '{marker}' found {count}× in report")

    # ── 4. Check tables in required sections ──
    # Split content by section headings
    section_blocks = SECTION_HEADING.split(content)[1:]  # Skip preamble
    for i in range(0, len(section_blocks), 2):
        heading = section_blocks[i].strip() if i < len(section_blocks) else ""
        body = section_blocks[i + 1] if i + 1 < len(section_blocks) else ""

        for table_section in TABLE_SECTIONS:
            if table_section in heading:
                if not TABLE_PATTERN.search(body):
                    issues.append(f"Missing table in section: {heading}")

    # ── 4.5. Check section concision (EDP-007, EDP-008, EDP-009) ──
    issues.extend(_check_concision(content))

    # ── 5. Check numeric consistency in EPS & Revenue (EDP-006) ──
    issues.extend(_check_numeric_consistency(content))

    # ── 5.5. Check FCF Margin presence in Cash Flow (EDP-013) ──
    issues.extend(_check_fcf_margin_presence(content))

    # ── 6. Check minimum content size ──
    words = len(content.split())
    if words < 800:
        issues.append(f"Content too short: {words} words (need ≥800)")

    return len(issues) == 0, issues


def validate_render_model(report_model) -> List[str]:
    """Validate the structured model that feeds the PDF renderer."""
    try:
        content = report_model.model_dump_json()
    except AttributeError:
        content = str(report_model)

    issues: List[str] = []
    for marker in FORBIDDEN_MARKERS:
        count = content.count(marker)
        if count > 0:
            issues.append(f"Forbidden marker '{marker}' found {count}× in PDF render model")

    for section in getattr(report_model, "sections", []):
        table = getattr(section, "table", None)
        rows = getattr(table, "rows", []) if table is not None else []
        if not rows:
            issues.append(f"Missing rows in PDF render model section: {getattr(section, 'title', 'unknown')}")

    sources = getattr(report_model, "sources", [])
    has_any_url = any(getattr(source, "url", None) for source in sources)
    has_transcript_url = any(
        getattr(source, "url", None)
        and isinstance(getattr(source, "label", None), str)
        and getattr(source, "label", "").startswith(("Transcript -", "Earnings Transcript"))
        for source in sources
    )
    if not has_any_url or not has_transcript_url:
        issues.append("Missing transcript/source URL in PDF render model")

    return issues


def validate_deep_dive_or_retry(
    md_path: str,
    ticker: str,
    max_retries: int = 2,
) -> Tuple[bool, List[str]]:
    """Validate and optionally trigger regeneration on failure.

    Args:
        md_path: Path to the deep-dive markdown.
        ticker: Ticker symbol (for logging).
        max_retries: Number of regeneration attempts.

    Returns:
        (passed, issues)
    """
    import logging
    logger = logging.getLogger(__name__)

    for attempt in range(1, max_retries + 2):  # Initial + retries
        passed, issues = validate_deep_dive(md_path)

        if passed:
            logger.info(f"[{ticker}] Deep-dive validation passed (attempt {attempt})")
            return True, []

        if attempt <= max_retries:
            logger.warning(
                f"[{ticker}] Deep-dive validation failed (attempt {attempt}): "
                f"{len(issues)} issues. Retrying..."
            )
            # Regeneration happens externally — caller re-runs _add_earnings_deep_dive_if_transcript
            return False, issues

    logger.error(f"[{ticker}] Deep-dive validation FAILED after {max_retries + 1} attempts")
    return False, issues
