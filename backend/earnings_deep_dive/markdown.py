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

# Pattern: raw inline source citations emitted by the LLM, e.g.
# "(source: yfinance eps_actual; yfinance eps_estimate; formula: eps_actual - eps_estimate)".
# These are useful as model grounding instructions, but client PDFs must not expose
# provider names or internal key names.
_SOURCE_PAREN = re.compile(r"\(source:\s*([^)]*)\)", re.IGNORECASE)
_RAW_FIELD_TOKEN = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", re.IGNORECASE)
_YFINANCE_SOURCE_TOKEN = re.compile(r"\byfinance\b", re.IGNORECASE)
_COMPETITOR_ROW_ID = re.compile(r"(?m)(^|[|\n]\s*)S\d+\s+(?=[A-Z0-9])")
_RAW_METRIC_ASSIGNMENT = re.compile(r"\b([a-z][a-z0-9]*_[a-z0-9_]+)=([^\s,;).]+)", re.IGNORECASE)
_METRIC_LABELS = {
    "eps_actual": "reported EPS",
    "eps_estimate": "EPS estimate",
    "eps_surprise_pct": "EPS surprise",
    "revenue_actual": "reported revenue",
    "revenue_estimate": "revenue estimate",
    "revenue_yoy": "revenue YoY",
    "free_cash_flow": "free cash flow",
    "pe_forward": "forward P/E",
}


def _clean_yfinance(match: re.Match) -> str:
    """Substitution callback: preserve value if present, strip field name."""
    value = match.group(2)
    if value:
        # Strip trailing punctuation that got captured with the value
        clean_value = value.rstrip(",.)};:")
        return f"yfinance ({clean_value})"
    return "yfinance"


def _clean_source_parenthetical(match: re.Match) -> str:
    """Normalize raw source parentheticals into client-safe source labels.

    Keeps human-meaningful formula/provenance words, but removes raw provider
    names and internal snake_case metric keys from the final client PDF.
    """
    body = match.group(1)
    parts = [part.strip() for part in re.split(r"[;、]", body) if part.strip()]
    kept: list[str] = []
    saw_metric_source = False
    for part in parts:
        without_provider = _YFINANCE_SOURCE_TOKEN.sub("", part).strip(" ,;:")
        without_fields = _RAW_FIELD_TOKEN.sub("", without_provider).strip(" ,;:-")
        if part != without_fields:
            saw_metric_source = True
        if without_fields and without_fields.lower() not in {"source", "yfinance"}:
            kept.append(re.sub(r"\s{2,}", " ", without_fields))

    prefix = "source: company metrics" if saw_metric_source else "source: reviewed materials"
    if kept:
        return f"({prefix}; {'; '.join(kept)})"
    return f"({prefix})"


def _clean_raw_metric_assignment(match: re.Match) -> str:
    """Humanize raw snake_case metric assignments in prose."""
    field = match.group(1).lower()
    value = match.group(2)
    label = _METRIC_LABELS.get(field, field.replace("_", " "))
    return f"{label} {value}"


def post_process_markdown(markdown: str) -> str:
    """Clean up LLM artifacts from generated deep-dive markdown.

    Runs after section assembly, before PDF rendering. Strips raw internal field
    names, provider labels, and competitor row IDs that the LLM regurgitates
    from prompt metrics while preserving client-safe provenance.
    """
    cleaned = markdown

    # 1. Raw inline source parentheticals:
    #    "(source: yfinance eps_actual; yfinance eps_estimate; formula: ...)"
    #    → "(source: company metrics; formula: ...)"
    cleaned = _SOURCE_PAREN.sub(_clean_source_parenthetical, cleaned)

    # 2. "yfinance — field_name=VALUE" → "yfinance (VALUE)"
    #    "yfinance — field_name" → "yfinance"
    cleaned = _YFINANCE_FIELD.sub(_clean_yfinance, cleaned)

    # 3. "(source: Metrics — field1, field2)" → "(source: company metrics)"
    cleaned = _METRICS_FIELD.sub("company metrics", cleaned)

    # 4. "yfinance field_name=VALUE" (no dash, running text) → "yfinance (VALUE)"
    cleaned = _YFINANCE_SPACE.sub(_clean_yfinance, cleaned)

    # 5. Prose assignments like "eps_actual=2.01" → "reported EPS 2.01".
    cleaned = _RAW_METRIC_ASSIGNMENT.sub(_clean_raw_metric_assignment, cleaned)

    # 6. Competitor table/prose row IDs like "S1 Apple" are internal labels.
    cleaned = _COMPETITOR_ROW_ID.sub(lambda match: match.group(1), cleaned)

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
