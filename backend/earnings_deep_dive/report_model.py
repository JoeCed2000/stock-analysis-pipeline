"""Structured render model for earnings deep-dive reports.

CompanyOverview section — see company_overview.py for the service layer.
⚠️ LANGUAGE SEPARATION: CompanyClaim and CompetitorRef store bilingual
text in SEPARATE fields (text_en + text_jp). Never mix languages.
CompanyOverview itself is per-language (EN or JP from cache).
"""
from datetime import date as DateType
from typing import Literal, Optional

from pydantic import BaseModel, Field


ReportLanguage = Literal["en", "jp"]

# ── Source grounding levels ──
GroundingLevel = Literal[
    "direct_metric",   # exact field from yfinance/SEC/Finnhub
    "calculated",      # deterministic formula from direct metrics
    "direct_quote",    # transcript quote
    "document_fact",   # filing/press release fact
    "inference",       # analyst interpretation from sourced facts
    "unsupported",     # should be blocked or flagged
]

class SourceRef(BaseModel):
    """Report-level bibliography entry — answers 'what sources exist?'"""
    source_id: str | None = None  # e.g. "S1", "S2"
    label: str
    url: str | None = None
    note: str | None = None
    source_type: str | None = None  # "sec_edgar", "yfinance", "seeking_alpha", "ir_page", "press_release"
    publisher: str | None = None
    retrieved_at: str | None = None
    period: str | None = None  # "FY2026 Q1", "2026-03-15"


class ClaimSource(BaseModel):
    """Evidence link — answers 'what evidence supports this exact claim?'

    Machine-readable mapping from every analytical claim back to its data source.
    Designed for auditability: each claim can be traced to a specific field,
    value, date, and grounding level.
    """
    claim_id: str                 # e.g. "EPS-001"
    section: str                  # "EPS & Revenue", "Cash Flow", etc.
    claim_text: str | None = None # The actual claim text from the report
    source_type: str | None = None   # "yfinance", "sec_edgar", "seeking_alpha", "finnhub"
    source_name: str | None = None   # Human-readable source name (matches SourceRef.label)
    source_id: str                   # references SourceRef.source_id
    source_url: str | None = None    # Direct URL to the source if available
    source_field: str | None = None  # "eps_actual", "revenue_estimate"
    source_value: str | None = None  # "$2.94", "$22.4B"
    as_of_date: str | None = None    # ISO date when the data was retrieved
    grounding: GroundingLevel = "inference"  # Evidence quality tier
    confidence: str | None = None    # "high" / "medium" / "low" — qualitative confidence


class RenderedTableRow(BaseModel):
    label: str
    cells: list[str]
    # Row-level source provenance (optional — populated for tables)
    source_field: str | None = None
    source_value_raw: str | None = None
    grounding: GroundingLevel | None = None


class RenderedTable(BaseModel):
    columns: list[str]
    rows: list[RenderedTableRow] = Field(default_factory=list)


class RenderedSection(BaseModel):
    key: str
    title: str
    question: str
    table: RenderedTable
    analysis: list[str] = Field(default_factory=list)
    summary_label: str
    summary: str


class ChartData(BaseModel):
    """Pre-computed chart data extracted from metrics for PDF rendering."""
    eps_actual: float | None = None
    eps_estimate: float | None = None
    eps_vs_pct: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_vs_pct: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    pe_forward: float | None = None
    fcf: float | None = None
    roic: float | None = None
    sector: str | None = None
    industry: str | None = None
    # ── 6-category weighted scoring (total /40) ──
    scoring_financial_health: float | None = None   # /10
    scoring_growth: float | None = None              # /10
    scoring_valuation: float | None = None           # /8
    scoring_management: float | None = None          # /5
    scoring_moat: float | None = None                # /4
    scoring_sentiment: float | None = None           # /3
    scoring_total: int | None = None                 # total /40
    scoring_decision: str | None = None              # BUY/HOLD/SELL


# ── Company Overview models ───────────────────────────────────────────────
# These mirror the JSON shape produced by company_overview.py.
# CompanyOverview is per-language; bilingual fields are in CompetitorRef/CompanyClaim.


class CompanyProfile(BaseModel):
    """Basic company identity — mirrors yfinance Ticker.info fields."""
    name: str
    ticker: str
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    website: str | None = None
    employees: int | None = None
    founded: int | None = None
    headquarters: str | None = None


class KeyFinancials(BaseModel):
    """Snapshot financial metrics for CompanyOverview."""
    market_cap: float | None = None
    market_cap_display: str | None = None
    revenue: float | None = None
    revenue_display: str | None = None
    pe_ratio: float | None = None
    pe_forward: float | None = None
    dividend_yield: float | None = None
    beta: float | None = None
    window_52w_high: float | None = Field(default=None, alias="52w_high")
    window_52w_low: float | None = Field(default=None, alias="52w_low")

    model_config = {"populate_by_name": True}


class RecentDevelopment(BaseModel):
    """A recent news/development item synthesized from Tavily web search."""
    title: str
    summary: str
    date: str | None = None       # "YYYY-MM-DD" if known
    sentiment: str | None = None  # "positive" | "neutral" | "negative"


class CompetitorRef(BaseModel):
    """Bilingual competitor reference — text_en + text_jp, must have source.

    text_en is generated by the LLM. text_jp is filled by a separate
    translation step. Never mix languages in a single text field.
    """
    competitor_name: str
    text_en: str
    text_jp: str = ""
    source_id: str
    competitive_advantage: str | None = None


class CompanyClaim(BaseModel):
    """Bilingual analytical claim — text_en + text_jp, must have source_id.

    Every claim is traceable back to a source. text_en is LLM-generated;
    text_jp is populated by a separate translation step.
    """
    claim_id: str
    text_en: str
    text_jp: str = ""
    source_id: str
    section: str | None = None     # "competitive_position", "key_financials", etc.
    confidence: str = "medium"     # "high" | "medium" | "low"


class CompanyOverview(BaseModel):
    """Per-language structured company overview — mirrors company_overview.py output.

    Top-level fields match the LLM synthesis prompt in company_overview.py:
    company_profile + business_description + key_financials +
    recent_developments + competitive_position = 5 question fields.

    competitors and company_claims are optional lists of bilingual
    CompetitorRef / CompanyClaim models for source-backed analysis.
    """
    company_profile: CompanyProfile
    business_description: str | None = None
    key_financials: KeyFinancials | None = None
    recent_developments: list[RecentDevelopment] = Field(default_factory=list)
    competitive_position: str | None = None
    competitors: list[CompetitorRef] = Field(default_factory=list)
    company_claims: list[CompanyClaim] = Field(default_factory=list)


class ScoringCategory(BaseModel):
    """One scoring category with label, score, max, and JP label."""
    label: str
    score: int
    max_score: int = 10
    label_jp: str | None = None


class ScoringSummary(BaseModel):
    """6-category scoring summary (total /40). Rendered in PDF when available."""
    categories: list[ScoringCategory]
    total_score: int
    max_total: int = 40
    verdict: str  # BUY / HOLD / SELL
    ticker: str = ""
    quarter: str = ""


# ── V2.7 Structured PDF Section Models ───────────────────────────────────
# Each section is a standalone Pydantic model for PDF rendering.
# All fields are nullable (Optional/None) — partial data is valid.
# All monetary values are USD-only, with source/timestamp tracking.


class ExecutiveSnapshot(BaseModel):
    """Top-level summary card for the report's first page.

    High-level company identity + key stats + verdict.
    Designed to be rendered as a callout box at the top of the PDF.
    """
    ticker: str | None = None
    company_name: str | None = None
    quarter: str | None = None
    # ── Price & Market Cap (USD) ──
    price: float | None = None
    price_currency: str = "USD"
    market_cap: float | None = None
    market_cap_display: str | None = None
    market_cap_currency: str = "USD"
    # ── Verdict ──
    verdict: str | None = None          # BUY / HOLD / SELL
    decision_score: int | None = None    # /40
    decision_max: int = 40
    # ── Metadata ──
    sector: str | None = None
    industry: str | None = None
    next_earnings_date: str | None = None    # ISO date
    generated_at: str | None = None           # ISO timestamp
    source_refs: list[SourceRef] = Field(default_factory=list)


class FinancialMetrics(BaseModel):
    """Structured financial data tables for the PDF.

    EPS, Revenue, margins, growth rates, FCF — all in USD.
    Each metric carries its own display string, source, and grounding level.
    """
    # ── EPS ──
    eps_actual: float | None = None
    eps_actual_display: str | None = None
    eps_estimate: float | None = None
    eps_estimate_display: str | None = None
    eps_beat_pct: float | None = None
    eps_beat_pct_display: str | None = None
    eps_currency: str = "USD"
    eps_source: str | None = None
    eps_as_of_date: str | None = None
    eps_grounding: GroundingLevel | None = None

    # ── Revenue ──
    revenue_actual: float | None = None
    revenue_actual_display: str | None = None
    revenue_estimate: float | None = None
    revenue_estimate_display: str | None = None
    revenue_beat_pct: float | None = None
    revenue_beat_pct_display: str | None = None
    revenue_currency: str = "USD"
    revenue_source: str | None = None
    revenue_as_of_date: str | None = None
    revenue_grounding: GroundingLevel | None = None

    # ── Margins (%) ──
    gross_margin: float | None = None
    gross_margin_display: str | None = None
    operating_margin: float | None = None
    operating_margin_display: str | None = None
    net_margin: float | None = None
    net_margin_display: str | None = None

    # ── Growth (YoY %) ──
    revenue_growth_yoy: float | None = None
    revenue_growth_yoy_display: str | None = None
    eps_growth_yoy: float | None = None
    eps_growth_yoy_display: str | None = None

    # ── Free Cash Flow (USD) ──
    fcf: float | None = None
    fcf_display: str | None = None
    fcf_currency: str = "USD"

    # ── Sources ──
    sources: list[SourceRef] = Field(default_factory=list)


class ValuationSection(BaseModel):
    """Multiples and valuation ratios for the PDF.

    Standard valuation multiples: PE, PEG, PS, PB, EV/EBITDA, FCF yield, dividend yield.
    All in USD context.
    """
    pe_trailing: float | None = None
    pe_trailing_display: str | None = None
    pe_forward: float | None = None
    pe_forward_display: str | None = None
    peg_ratio: float | None = None
    peg_ratio_display: str | None = None
    price_to_sales: float | None = None
    price_to_sales_display: str | None = None
    price_to_book: float | None = None
    price_to_book_display: str | None = None
    ev_to_ebitda: float | None = None
    ev_to_ebitda_display: str | None = None
    fcf_yield: float | None = None        # as decimal (0.008 = 0.8%)
    fcf_yield_display: str | None = None
    dividend_yield: float | None = None    # as decimal (0.0002 = 0.02%)
    dividend_yield_display: str | None = None

    currency: str = "USD"
    generated_at: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class ValuationContextSection(BaseModel):
    """7 context signals from V2.4 /api/valuation-context endpoint.

    Each signal has a numeric value + human-readable label + detail.
    """
    peg_signal: float | None = None
    peg_signal_label: str | None = None
    peg_signal_detail: str | None = None

    ps_vs_growth_signal: float | None = None
    ps_vs_growth_label: str | None = None

    ev_ebitda_vs_growth_signal: float | None = None
    ev_ebitda_vs_growth_label: str | None = None

    pfcf_vs_growth_signal: float | None = None
    pfcf_vs_growth_label: str | None = None

    fcf_yield_signal: float | None = None
    fcf_yield_label: str | None = None

    valuation_support: str | None = None      # narrative summary
    context_summary: str | None = None         # final verdict sentence

    generated_at: str | None = None
    currency: str = "USD"


class PeerBenchmarkSection(BaseModel):
    """Peer-relative benchmarks from V2.5 /api/peer-benchmark endpoint.

    Relative valuation, growth, quality vs curated peer group.
    """
    peer_group: str | None = None
    peer_tickers: list[str] = Field(default_factory=list)

    # ── Relative Labels (neutral wording: "Above Average" / "Below Average" / "In Line") ──
    relative_valuation_label: str | None = None
    relative_valuation_detail: str | None = None
    relative_growth_label: str | None = None
    relative_growth_detail: str | None = None
    relative_quality_label: str | None = None
    relative_quality_detail: str | None = None

    # ── Summary ──
    benchmark_summary: str | None = None

    # ── Detailed metrics (dict for flexibility) ──
    valuation_metrics: dict[str, float] = Field(default_factory=dict)
    quality_metrics: dict[str, float] = Field(default_factory=dict)

    currency: str = "USD"
    generated_at: str | None = None


class DataQualitySection(BaseModel):
    """Source freshness and data completeness for audit trail.

    Tracks when each data source was last refreshed and flags missing fields.
    """
    # ── Source Timestamps ──
    yfinance_freshness: str | None = None        # ISO date
    yfinance_source_label: str | None = None
    finnhub_freshness: str | None = None
    finnhub_source_label: str | None = None
    sec_edgar_freshness: str | None = None
    sec_edgar_source_label: str | None = None
    transcript_freshness: str | None = None
    transcript_source_label: str | None = None

    # ── Confidence ──
    overall_confidence: str | None = None          # "high" / "medium" / "low"
    completeness_score: int | None = None           # 0-100
    completeness_max: int = 100
    missing_fields: list[str] = Field(default_factory=list)

    # ── Metadata ──
    data_currency: str = "USD"
    generated_at: str | None = None


class EarningsDeepDiveReport(BaseModel):
    ticker: str
    company: str
    quarter: str
    language: ReportLanguage
    generated_at: str
    title: str
    sections: list[RenderedSection]
    sources: list[SourceRef] = Field(default_factory=list)
    claim_sources: list[ClaimSource] = Field(default_factory=list)
    next_earnings_date: Optional[str] = None
    earnings_audio_url: Optional[str] = None
    charts: ChartData | None = None
    company_overview: CompanyOverview | None = None
    scoring: Optional[ScoringSummary] = None
    # ── V2.7 structured section models (all optional, no breaking change) ──
    executive_snapshot: ExecutiveSnapshot | None = None
    financial_metrics: FinancialMetrics | None = None
    valuation: ValuationSection | None = None
    valuation_context: ValuationContextSection | None = None
    peer_benchmark: PeerBenchmarkSection | None = None
    data_quality: DataQualitySection | None = None
