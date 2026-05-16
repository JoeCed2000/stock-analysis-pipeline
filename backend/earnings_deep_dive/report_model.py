"""Structured render model for earnings deep-dive reports."""
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
