"""Markdown assembly for earnings call deep-dive reports."""
from typing import Dict, Iterable, List, Optional

from backend.earnings_deep_dive.prompts import SECTION_ORDER


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
