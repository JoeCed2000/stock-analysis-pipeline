"""Prompt templates for earnings call deep-dive sections."""
from typing import Any, Callable, Dict, List


SECTION_ORDER: List[str] = [
    "EPS & Revenue",
    "Highlights",
    "Operating Metrics",
    "Cash Flow",
    "Capital Efficiency",
    "Segments",
    "Forward P/E",
    "Backlog",
    "Guidance",
    "Verdict",
]

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "EPS & Revenue": ["eps", "earnings per share", "revenue", "sales", "top line"],
    "Highlights": ["highlight", "record", "growth", "demand", "margin", "customer"],
    "Operating Metrics": ["operating", "utilization", "volume", "unit", "margin", "retention"],
    "Cash Flow": ["cash flow", "free cash flow", "operating cash", "capex", "liquidity"],
    "Capital Efficiency": ["roic", "roe", "return", "capital", "buyback", "dividend"],
    "Segments": ["segment", "division", "cloud", "data center", "geography", "product"],
    "Forward P/E": ["valuation", "forward", "earnings", "multiple", "pe", "p/e"],
    "Backlog": ["backlog", "remaining performance", "bookings", "orders", "pipeline"],
    "Guidance": ["guidance", "outlook", "forecast", "next quarter", "full year"],
    "Verdict": ["priority", "risk", "opportunity", "guidance", "demand", "margin"],
}

TABLE_SECTIONS = {"EPS & Revenue", "Forward P/E", "Guidance"}


def system_prompt(language: str) -> str:
    return (
        "You are a financial analyst. Output strict markdown. "
        f"Single language: {language}. No emojis. No persona. No bilingual output."
    )


def _fmt_metrics(metrics: Dict[str, Any]) -> str:
    if not metrics:
        return "Not disclosed"
    parts = []
    for key in sorted(metrics):
        value = metrics[key]
        if value is None or value == "":
            value = "Not disclosed"
        parts.append(f"{key}={value}")
    return " | ".join(parts) if parts else "Not disclosed"


def _base_prompt(
    *,
    section: str,
    language: str,
    ticker: str,
    company: str,
    quarter: str,
    metrics: Dict[str, Any],
    transcript_excerpt: str,
    task: str,
) -> str:
    table_rule = (
        "Include one concise markdown table before the analysis."
        if section in TABLE_SECTIONS
        else "Use concise bullets or short paragraphs only."
    )
    return f"""Required heading: ## {section}
Language: {language}
Ticker: {ticker}
Company: {company}
Quarter: {quarter}
Metrics: {_fmt_metrics(metrics)}
Transcript excerpt: {transcript_excerpt or "Not disclosed"}

Task: {task}

Output rules:
- Start with exactly: ## {section}
- Strict markdown only.
- Single language only: {language}.
- No emojis.
- No bilingual text.
- Maximum 3 bullets per subsection.
- Use "Not disclosed" for missing data.
- {table_rule}
"""


def eps_revenue_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="EPS & Revenue",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Generate a concise earnings summary table covering EPS and revenue, followed by 1-2 sentence analysis.",
    )


def highlights_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Highlights",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Summarize the main positive and negative call highlights with evidence from the excerpt.",
    )


def operating_metrics_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Operating Metrics",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Explain the operating metrics that moved the quarter and identify undisclosed metrics explicitly.",
    )


def cash_flow_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Cash Flow",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Analyze operating cash flow, free cash flow, capex, liquidity, and working-capital signals.",
    )


def capital_efficiency_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Capital Efficiency",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Evaluate ROIC, ROE, buybacks, dividends, and capital allocation discipline.",
    )


def segments_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Segments",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Summarize segment-level performance, mix shifts, and concentration risks.",
    )


def forward_pe_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Forward P/E",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Build a valuation table centered on forward P/E and explain whether the multiple is supported by disclosed growth signals.",
    )


def backlog_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Backlog",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Analyze backlog, bookings, remaining performance obligations, order pipeline, and visibility.",
    )


def guidance_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Guidance",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Create a guidance table and state what management disclosed or did not disclose for the next period.",
    )


def verdict_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Verdict",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
        task="Provide a balanced analyst verdict based only on the supplied metrics and excerpt. Do not give investment advice.",
    )


PROMPT_BUILDERS: Dict[str, Callable[[str, str, str, str, Dict[str, Any], str], str]] = {
    "EPS & Revenue": eps_revenue_prompt,
    "Highlights": highlights_prompt,
    "Operating Metrics": operating_metrics_prompt,
    "Cash Flow": cash_flow_prompt,
    "Capital Efficiency": capital_efficiency_prompt,
    "Segments": segments_prompt,
    "Forward P/E": forward_pe_prompt,
    "Backlog": backlog_prompt,
    "Guidance": guidance_prompt,
    "Verdict": verdict_prompt,
}


def build_prompt(section: str, language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    """Build a prompt for one earnings deep-dive section."""
    return PROMPT_BUILDERS[section](language, ticker, company, quarter, metrics, transcript_excerpt)
