"""Pydantic models for Stock Analysis Pipeline."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class TickerRequest(BaseModel):
    """Request to analyze one or more tickers."""
    tickers: List[str] = Field(..., min_length=1, max_length=10)
    deep_dive: bool = Field(default=False, description="Also generate earnings deep-dive PDF")


class FinancialData(BaseModel):
    """Extracted financial metrics."""
    revenue_quarterly: Optional[float] = None
    revenue_yoy_growth: Optional[float] = None
    revenue_annual: Optional[float] = None
    revenue_annual_growth: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_income: Optional[float] = None
    free_cash_flow: Optional[float] = None
    net_debt: Optional[float] = None
    guidance_official: Optional[float] = None


class SegmentInfo(BaseModel):
    """Business segment breakdown."""
    primary_segment: Optional[str] = None
    revenue_share_pct: Optional[float] = None
    segment_growth: Optional[float] = None
    excessive_dependency: Optional[str] = None


class ManagementTone(BaseModel):
    """Management discourse analysis."""
    tone: Optional[str] = None
    confidence: Optional[str] = None
    visibility: Optional[str] = None
    concrete_promises: Optional[List[str]] = None
    defensive_signals: Optional[List[str]] = None


class RiskItem(BaseModel):
    """A single identified risk."""
    category: str
    description: str
    severity: str  # high / medium / low
    source: str


class ValuationData(BaseModel):
    """Valuation metrics."""
    pe_current: Optional[float] = None
    pe_forward: Optional[float] = None
    peg_ratio: Optional[float] = None
    expected_growth: Optional[float] = None
    margin_of_safety: Optional[str] = None


class Scoring(BaseModel):
    """8-criterion scoring out of 5 each, total /40."""
    growth: int = 0
    profitability: int = 0
    financial_strength: int = 0
    moat: int = 0
    management: int = 0
    valuation_risk: int = 0
    geopolitical_risk: int = 0
    business_momentum: int = 0

    @property
    def total(self) -> int:
        return sum([
            self.growth, self.profitability, self.financial_strength,
            self.moat, self.management, self.valuation_risk,
            self.geopolitical_risk, self.business_momentum
        ])

    def decision(self) -> str:
        t = self.total
        if t >= 32:
            return "BUY"
        elif t >= 26:
            return "HOLD / BUY ON PULLBACK"
        elif t >= 18:
            return "HOLD fragile"
        else:
            return "SELL or AVOID"


class Source(BaseModel):
    """A single source reference."""
    id: str
    category: str
    title: str
    url: str
    local_path: Optional[str] = None
    retrieved_at: str
    source_type: str
    publisher: str
    period: Optional[str] = None
    used_for: List[str] = []
    reliability: str = "medium"


class Claim(BaseModel):
    """A traceable claim linking to a source."""
    claim_id: str
    claim: str
    source_id: str
    file_path: Optional[str] = None
    page_or_section: Optional[str] = None
    confidence: str = "high"
    used_in_report: bool = True
    sha256: Optional[str] = None  # Cryptographic hash of claim+source for verification


class AnalysisResult(BaseModel):
    """Complete analysis result for one ticker."""
    ticker: str
    company_name: str
    retrieved_at: str
    price_native: Optional[float] = None
    price_eur: Optional[float] = None
    currency: str = "USD"
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    financials: FinancialData = Field(default_factory=FinancialData)
    segments: SegmentInfo = Field(default_factory=SegmentInfo)
    management_tone: ManagementTone = Field(default_factory=ManagementTone)
    risks: List[RiskItem] = Field(default_factory=list)
    valuation: ValuationData = Field(default_factory=ValuationData)
    scoring: Scoring = Field(default_factory=Scoring)
    decision: str = ""
    conviction: str = ""
    key_phrase: str = ""
    report_path: Optional[str] = None
    sources_manifest_path: Optional[str] = None


class AnalysisJobResponse(BaseModel):
    """Response when analysis is submitted."""
    job_id: str
    tickers: List[str]
    status: str = "processing"


class AnalysisJobStatus(BaseModel):
    """Polling status for an analysis job."""
    job_id: str
    status: str  # processing / completed / partial / failed
    results: List[AnalysisResult] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
