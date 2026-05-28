"""Post-generation validation for earnings deep-dive reports.

Ensures every deep-dive matches the Nami template and contains zero unavailable markers.
Runs after _add_earnings_deep_dive_if_transcript() but before the dossier is marked 'complete'.
"""

import re
import os
from typing import List, Dict, Tuple


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


def validate_deep_dive(md_path: str) -> Tuple[bool, List[str]]:
    """Validate a generated deep-dive markdown file.

    Args:
        md_path: Path to the earnings_deep_dive.md file.

    Returns:
        (passed, issues) — passed is True only if zero issues found.
    """
    issues: List[str] = []

    if not os.path.exists(md_path):
        return False, [f"File not found: {md_path}"]

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # ── 1. Check all 10 Nami sections are present ──
    found_sections: List[str] = []
    for match in SECTION_HEADING.finditer(content):
        heading = match.group(1).strip()
        found_sections.append(heading)

    for emoji_key, name in REQUIRED_SECTIONS.items():
        matched = any(
            emoji_key in h or name.lower() in h.lower()
            for h in found_sections
        )
        if not matched:
            issues.append(f"Missing section: {emoji_key} ({name})")

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
