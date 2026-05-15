"""Structured render model for earnings deep-dive reports."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


ReportLanguage = Literal["en", "jp"]


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
    next_earnings_date: Optional[str] = None
    earnings_audio_url: Optional[str] = None
    charts: ChartData | None = None
