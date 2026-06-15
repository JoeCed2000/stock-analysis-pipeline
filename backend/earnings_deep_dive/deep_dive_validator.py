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

# ── Forbidden generic Quality subheadings (EDP-011) ────────────────────────────
# When an LLM generates a standalone "Quality" heading/section that is boilerplate,
# it should be flagged. Excluded: canonical required sections (e.g. "Backlog Quality")
# and headings that contain ticker-specific earnings language (e.g. "Earnings Quality").
FORBIDDEN_QUALITY_PATTERNS = [
    re.compile(r"\bQuality\b", re.IGNORECASE),       # standalone "Quality" word
]


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

    # ── 5. Check minimum content size ──
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
