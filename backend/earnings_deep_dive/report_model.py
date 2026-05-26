"""Structured render model for earnings deep-dive reports."""

from typing import Literal

from pydantic import BaseModel, Field

ReportLanguage = Literal["en", "jp"]
GroundingLevel = Literal["direct_metric", "derived", "estimated", "unknown", "missing"]


# ── Shared primitives ─────────────────────────────────────────────────────


class SourceRef(BaseModel):
    label: str
    url: str | None = None
    note: str | None = None


class RenderedTableRow(BaseModel):
    label: str
    cells: list[str]


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


# ═══════════════════════════════════════════════════════════════════════════
# V2.7 — Structured PDF sections
# ═══════════════════════════════════════════════════════════════════════════


class ExecutiveSnapshot(BaseModel):
    """Top-level summary card for the report's first page."""

    ticker: str | None = None
    company_name: str | None = None
    quarter: str | None = None
    price: float | None = None
    price_currency: str = "USD"
    market_cap: int | None = None
    market_cap_display: str | None = None
    market_cap_currency: str = "USD"
    verdict: str | None = None
    decision_score: int | None = None
    decision_max: int = 40
    sector: str | None = None
    industry: str | None = None
    next_earnings_date: str | None = None
    generated_at: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class FinancialMetrics(BaseModel):
    """Structured financial data tables for the PDF."""

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
    eps_grounding: str | None = None

    # ── Revenue ──
    revenue_actual: int | None = None
    revenue_actual_display: str | None = None
    revenue_estimate: int | None = None
    revenue_estimate_display: str | None = None
    revenue_beat_pct: float | None = None
    revenue_beat_pct_display: str | None = None
    revenue_currency: str = "USD"
    revenue_source: str | None = None
    revenue_as_of_date: str | None = None
    revenue_grounding: str | None = None

    # ── Margins ──
    gross_margin: float | None = None
    gross_margin_display: str | None = None
    operating_margin: float | None = None
    operating_margin_display: str | None = None
    net_margin: float | None = None
    net_margin_display: str | None = None

    # ── Growth ──
    revenue_growth_yoy: float | None = None
    revenue_growth_yoy_display: str | None = None
    eps_growth_yoy: float | None = None
    eps_growth_yoy_display: str | None = None

    # ── Cash flow ──
    fcf: int | None = None
    fcf_display: str | None = None
    fcf_currency: str = "USD"

    # ── Provenance ──
    sources: list[SourceRef] = Field(default_factory=list)


class ValuationSection(BaseModel):
    """Multiples and valuation ratios for the PDF."""

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
    fcf_yield: float | None = None
    fcf_yield_display: str | None = None
    dividend_yield: float | None = None
    dividend_yield_display: str | None = None
    currency: str = "USD"
    generated_at: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)


class ValuationContextSection(BaseModel):
    """7 context signals from V2.4 endpoint."""

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
    valuation_support: str | None = None
    context_summary: str | None = None
    generated_at: str | None = None
    currency: str = "USD"


class PeerBenchmarkSection(BaseModel):
    """Peer-relative benchmarks from V2.5 endpoint."""

    peer_group: str | None = None
    peer_tickers: list[str] = Field(default_factory=list)
    relative_valuation_label: str | None = None
    relative_valuation_detail: str | None = None
    relative_growth_label: str | None = None
    relative_growth_detail: str | None = None
    relative_quality_label: str | None = None
    relative_quality_detail: str | None = None
    benchmark_summary: str | None = None
    valuation_metrics: dict[str, float] = Field(default_factory=dict)
    quality_metrics: dict[str, float] = Field(default_factory=dict)
    currency: str = "USD"
    generated_at: str | None = None


class DataQualitySection(BaseModel):
    """Source freshness and data completeness for audit trail."""

    yfinance_freshness: str | None = None
    yfinance_source_label: str | None = None
    finnhub_freshness: str | None = None
    finnhub_source_label: str | None = None
    sec_edgar_freshness: str | None = None
    sec_edgar_source_label: str | None = None
    transcript_freshness: str | None = None
    transcript_source_label: str | None = None
    overall_confidence: str | None = None
    completeness_score: int | None = None
    completeness_max: int = 100
    missing_fields: list[str] = Field(default_factory=list)
    data_currency: str = "USD"
    generated_at: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Main report model
# ═══════════════════════════════════════════════════════════════════════════


class EarningsDeepDiveReport(BaseModel):
    ticker: str
    company: str
    quarter: str
    language: ReportLanguage
    generated_at: str
    title: str
    sections: list[RenderedSection]
    sources: list[SourceRef] = Field(default_factory=list)

    # ── V2.7 structured sections (all optional) ──
    executive_snapshot: ExecutiveSnapshot | None = None
    financial_metrics: FinancialMetrics | None = None
    valuation: ValuationSection | None = None
    valuation_context: ValuationContextSection | None = None
    peer_benchmark: PeerBenchmarkSection | None = None
    data_quality: DataQualitySection | None = None
