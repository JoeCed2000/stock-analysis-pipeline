"""Prompt templates for earnings call deep-dive sections."""
from typing import Any, Callable, Dict, List


class SectionName(str):
    """Canonical section key that renders as the report heading."""

    def __new__(cls, canonical: str, title: str) -> "SectionName":
        obj = str.__new__(cls, canonical)
        obj.title = title
        return obj

    def __str__(self) -> str:
        return self.title

    def __repr__(self) -> str:
        return repr(self.title)

    def __contains__(self, item: object) -> bool:
        return item in self.title

    def translate(self, table: Any) -> str:
        return self.title.translate(table)


SECTION_TITLES: Dict[str, str] = {
    "EPS & Revenue": "📊 EPS & Revenue",
    "Highlights": "🌟 Highlights & ⚠️ Lowlights",
    "Operating Metrics": "🧠 Operating Metrics",
    "Cash Flow": "💵 Cash Flow",
    "Capital Efficiency": "💰 Capital Efficiency",
    "Segments": "🎯 Segments",
    "Forward P/E": "📈 Forward P/E",
    "Backlog": "📦 Backlog Quality",
    "Guidance": "🧩 Guidance",
    "Verdict": "🏆 Verdict / 総合評価",
}

SECTION_ORDER: List[str] = [
    SectionName("EPS & Revenue", SECTION_TITLES["EPS & Revenue"]),
    SectionName("Highlights", SECTION_TITLES["Highlights"]),
    SectionName("Operating Metrics", SECTION_TITLES["Operating Metrics"]),
    SectionName("Cash Flow", SECTION_TITLES["Cash Flow"]),
    SectionName("Capital Efficiency", SECTION_TITLES["Capital Efficiency"]),
    SectionName("Segments", SECTION_TITLES["Segments"]),
    SectionName("Forward P/E", SECTION_TITLES["Forward P/E"]),
    SectionName("Backlog", SECTION_TITLES["Backlog"]),
    SectionName("Guidance", SECTION_TITLES["Guidance"]),
    SectionName("Verdict", SECTION_TITLES["Verdict"]),
]

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "EPS & Revenue": ["eps", "earnings per share", "revenue", "sales", "top line"],
    "Highlights": ["highlight", "record", "growth", "demand", "margin", "customer"],
    "Operating Metrics": ["operating", "utilization", "volume", "unit", "margin", "retention"],
    "Cash Flow": ["cash flow", "free cash flow", "operating cash", "capex", "liquidity"],
    "Capital Efficiency": ["roic", "roe", "roa", "return", "capital", "buyback", "dividend"],
    "Segments": ["segment", "division", "cloud", "data center", "geography", "product"],
    "Forward P/E": ["valuation", "forward", "earnings", "multiple", "pe", "p/e"],
    "Backlog": ["backlog", "remaining performance", "bookings", "orders", "pipeline"],
    "Guidance": ["guidance", "outlook", "forecast", "next quarter", "full year"],
    "Verdict": ["priority", "risk", "opportunity", "guidance", "demand", "margin"],
}

TABLE_SECTIONS = set(SECTION_ORDER)

TABLE_REQUIREMENTS: Dict[str, str] = {
    "EPS & Revenue": (
        "Include an estimate-vs-actual table with rows for EPS and Revenue. "
        "Columns: Metric | Estimate | Actual | Variance vs Estimate | YoY Change | Source."
    ),
    "Highlights": (
        "Include a table separating 🌟 Highlights and ⚠️ Lowlights. "
        "Columns: Type | Item | Evidence / Severity | Investor implication."
    ),
    "Operating Metrics": (
        "Include a YoY comparison table for 🧠 Revenue, Gross Profit/Margin, OpEx, "
        "Operating Income/Margin, and Net Income. Columns: Metric | Current | Prior Year | YoY Change | Source."
    ),
    "Cash Flow": (
        "Include a 💵 cash-flow table for OCF, CapEx, and FCF with YoY comparison. "
        "Columns: Metric | Current | Prior Year | YoY Change | Quality read-through."
    ),
    "Capital Efficiency": (
        "Include a 💰 capital-efficiency table for ROE, ROIC, and ROA. "
        "Columns: Metric | Current | Prior Year / Benchmark | Driver | Interpretation."
    ),
    "Segments": (
        "Include two 🎯 tables: product/category performance and geography performance. "
        "Columns for each: Segment | Revenue / KPI | YoY Change | Mix shift | Risk."
    ),
    "Forward P/E": (
        "Include a 📈 valuation table centered on forward P/E. "
        "Columns: Metric | Current | Comparison / Context | Evidence | Read-through."
    ),
    "Backlog": (
        "Include a 📦 backlog-quality table. "
        "Columns: Quantity | Coverage | Quality | Contract firmness | Source."
    ),
    "Guidance": (
        "Include a 🧩 guidance table. "
        "Columns: Metric | Next-period Guidance | QoQ Change | YoY / Medium-term Signal | Source."
    ),
    "Verdict": (
        "Include a 🏆 verdict table. "
        "Columns: Dimension | Positive evidence | Negative evidence | Net assessment."
    ),
}


def system_prompt(language: str) -> str:
    return (
        "You are a sell-side analyst producing earnings reports for an institutional investor. "
        "Use emojis as markers. Be concise but evidence-backed."
    )


def _fmt_metrics(metrics: Dict[str, Any]) -> str:
    if not metrics:
        return "DONNÉE NON DISPONIBLE"
    parts = []
    for key in sorted(metrics):
        value = metrics[key]
        if value is None or value == "":
            value = "DONNÉE NON DISPONIBLE"
        parts.append(f"{key}={value}")
    return " | ".join(parts) if parts else "DONNÉE NON DISPONIBLE"


def _section_title(section: str) -> str:
    return SECTION_TITLES.get(str.__str__(section) if isinstance(section, SectionName) else section, str(section))


def _language_rules(language: str) -> str:
    normalized = language.lower()
    if normalized in {"ja", "jp"}:
        return (
            "Output Japanese, including the section question. Keep important English financial terms in parentheses, "
            "for example 売上高 (Revenue), フリーキャッシュフロー (FCF), 投下資本利益率 (ROIC)."
        )
    if normalized == "bilingual":
        return (
            "Output the English question and analysis first, then add a concise Japanese summary for the same section. "
            "Do not introduce facts in the Japanese summary that were not stated in English."
        )
    return "Output English only, including the section question, except keep the required final label '> 一言まとめ:' exactly as written."


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
    title = _section_title(section)
    table_rule = TABLE_REQUIREMENTS[section]
    return f"""Required heading: ## {title}
Language: {language}
Language rule: {_language_rules(language)}
Ticker: {ticker}
Company: {company}
Quarter: {quarter}
Metrics: {_fmt_metrics(metrics)}
Transcript excerpt: {transcript_excerpt or "DONNÉE NON DISPONIBLE"}

Task: {task}

Output rules:
- Start with exactly: ## {title}
- Strict markdown only.
- Ask the section question before the answer, following the language rule above.
- Use emojis in the heading, table labels, and analysis bullets.
- Include markdown table(s) for this section: {table_rule}
- Maximum 3 bullets per subsection.
- Use direct transcript evidence when making a claim.
- Use "DONNÉE NON DISPONIBLE" for missing financial data.
- End the section with exactly one final blockquote line: > 一言まとめ: [one-line summary]
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
        task="Generate a concise 📊 EPS and revenue summary with estimate, actual, variance, YoY change, and evidence-backed analysis.",
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
        task=(
            "Summarize the main 🌟 positives and ⚠️ concerns. "
            "Format highlights exactly like: '1. 🌟 [highlight] — Evidence: [transcript quote]'. "
            "Format lowlights with severity, for example: '1. ⚠️ [lowlight] — Severity: [low/medium/high] — Evidence: [quote]'."
        ),
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
        task="Explain the 🧠 operating metrics that moved the quarter and compare each disclosed metric YoY.",
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
        task="Analyze 💵 OCF, CapEx, FCF, liquidity, working-capital signals, and cash-generation quality.",
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
        task="Evaluate 💰 ROE, ROIC, ROA, buybacks, dividends, and capital-allocation discipline.",
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
        task="Summarize 🎯 product/category and geography performance, mix shifts, and concentration risks.",
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
        task="Build a 📈 valuation table centered on forward P/E and explain whether the multiple is supported by disclosed growth signals.",
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
        task="Analyze 📦 backlog quantity, coverage, contract quality, bookings, RPO, order pipeline, and visibility.",
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
        task="Create a 🧩 guidance table covering next quarter, QoQ analysis, and medium-term directional signals.",
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
        task="Provide a balanced 🏆 sell-side analyst verdict using only supplied metrics and transcript evidence. Do not give investment advice.",
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
