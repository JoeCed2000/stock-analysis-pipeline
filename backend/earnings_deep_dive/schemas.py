"""Pydantic schemas for earnings call deep-dive generation."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


Language = Literal["en", "jp", "bilingual"]
SectionState = Literal["ok", "retry_ok", "failed", "placeholder"]


class FinancialMetrics(BaseModel):
    """Metrics passed into the earnings deep-dive prompts."""

    model_config = ConfigDict(extra="allow")

    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    eps_vs_estimate: Optional[float] = None
    eps_yoy: Optional[float] = None
    revenue_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    revenue_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    free_cash_flow: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    net_debt: Optional[float] = None
    roic: Optional[float] = None
    roe: Optional[float] = None
    # ── new yfinance-extracted fields (v2.5) ──
    gross_profit: Optional[float] = None
    opex: Optional[float] = None
    rotce: Optional[float] = None
    roa: Optional[float] = None
    total_assets: Optional[float] = None
    equity: Optional[float] = None
    buybacks: Optional[float] = None
    dividends: Optional[float] = None
    pe_forward: Optional[float] = None
    backlog: Optional[float] = None
    guidance: Optional[str] = None
    segments: Dict[str, Any] = Field(default_factory=dict)


class DeepDiveRequest(BaseModel):
    """Request for a single ticker earnings call deep-dive."""

    ticker: str = Field(..., min_length=1, max_length=16)
    company: Optional[str] = None
    quarter: str = "latest quarter"
    language: Language = "en"
    output_dir: str = Field(..., min_length=1)
    metrics: FinancialMetrics = Field(default_factory=FinancialMetrics)
    transcript_text: Optional[str] = None
    transcript_url: Optional[str] = None
    max_section_chars: int = Field(default=2400, ge=600, le=5000)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        clean = value.strip().upper()
        if not clean:
            raise ValueError("ticker is required")
        return clean

    @field_validator("company")
    @classmethod
    def strip_company(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if isinstance(value, str) and value.strip() else value


class SectionStatus(BaseModel):
    """Generation status for one report section."""

    name: str
    status: SectionState
    attempts: int = 0
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class DeepDiveResponse(BaseModel):
    """Generated earnings deep-dive response."""

    ticker: str
    company: str
    quarter: str
    language: Language
    transcript_url: Optional[str] = None
    markdown_path: str
    meta_path: str
    report_markdown: str
    sections: Dict[str, str]
    statuses: List[SectionStatus]
    warnings: List[str] = Field(default_factory=list)
