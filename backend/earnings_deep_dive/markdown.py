"""Markdown assembly for earnings call deep-dive reports."""
import re
from typing import Dict, Iterable, List, Optional

from backend.earnings_deep_dive.prompts import SECTION_ORDER


# ── Post-processing patterns ─────────────────────────────────────────────────

# Pattern: "yfinance — field_name" or "yfinance — field_name=VALUE"
# Goal: strip raw field names, preserve values when present
# "yfinance — eps_yoy=$2.14" → "yfinance ($2.14)"
# "yfinance — quarterly data" → "yfinance"
_YFINANCE_FIELD = re.compile(
    r"yfinance\s*[—–-]\s*([a-z_]+)(?:=(\S+))?",
    re.IGNORECASE,
)

# Pattern: "yfinance field_name" or "yfinance field_name=VALUE" (no dash, running text)
# Must come after a non-word boundary to avoid matching "from yfinance." natural text
_YFINANCE_SPACE = re.compile(
    r"(?<=\s)yfinance\s+([a-z_]+)(?:=(\S+))?",
    re.IGNORECASE,
)

# Pattern: "Metrics — field1, field2" in source references (inside parens/brackets)
# Goal: strip raw field names, keep "company metrics"
_METRICS_FIELD = re.compile(r"Metrics\s*[—–-]\s*[a-z_, ]+(?=[)\]])", re.IGNORECASE)


def _clean_yfinance(match: re.Match) -> str:
    """Substitution callback: preserve value if present, strip field name."""
    value = match.group(2)
    if value:
        # Strip trailing punctuation that got captured with the value
        clean_value = value.rstrip(",.)};:")
        return f"yfinance ({clean_value})"
    return "yfinance"


def post_process_markdown(markdown: str) -> str:
    """Clean up LLM artifacts from generated deep-dive markdown.

    Runs after section assembly, before PDF rendering.
    Strips raw internal field names that the LLM regurgitates from prompt metrics,
    while preserving source labels and data values for auditability.
    """
    cleaned = markdown

    # 1. "yfinance — field_name=VALUE" → "yfinance (VALUE)"
    #    "yfinance — field_name" → "yfinance"
    cleaned = _YFINANCE_FIELD.sub(_clean_yfinance, cleaned)

    # 2. "(source: Metrics — field1, field2)" → "(source: company metrics)"
    cleaned = _METRICS_FIELD.sub("company metrics", cleaned)

    # 3. "yfinance field_name=VALUE" (no dash, running text) → "yfinance (VALUE)"
    cleaned = _YFINANCE_SPACE.sub(_clean_yfinance, cleaned)

    return cleaned


def _placeholder(section: str) -> str:
    return f"## {section}\n\n- Unavailable from reviewed sources."


def assemble_final_report(
    sections: Dict[str, str],
    warnings: Optional[Iterable[str]] = None,
    company_website: Optional[str] = None,
) -> str:
    """Assemble section markdown in deterministic report order."""
    lines: List[str] = ["# Earnings Call Deep-Dive", ""]
    warning_list = [w for w in (warnings or []) if w]

    if company_website:
        lines.extend([f"**Official Website:** {company_website}", ""])

    if warning_list:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warning_list)
        lines.append("")

    for section in SECTION_ORDER:
        body = (sections.get(section) or "").strip() or _placeholder(section)
        lines.append(body)
        lines.append("")

    lines.extend([
        "## Source Discipline",
        "",
        "- Analysis is limited to supplied metrics and transcript excerpts.",
        "- Missing or unavailable data is marked as Not disclosed.",
    ])
    return "\n".join(lines).rstrip() + "\n"
