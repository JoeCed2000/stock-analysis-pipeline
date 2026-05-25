"""Pydantic models for Stock Analysis Pipeline."""
from datetime import datetime
from pydantic import BaseModel, Field, PrivateAttr
from typing import Optional, List, Dict, Any


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
    """6-category weighted scoring model. Total = /40.
    All 6 canonical fields are higher-is-better.
    Raw 8 sub-scores preserved in _raw_subscores for audit trail."""

    # ── 6 canonical categories (EXTERNALLY VISIBLE) ──
    financial_health: int = 0   # 0–10 (profitability + financial_strength)
    growth: int = 0             # 0–10 (growth + business_momentum)
    valuation: int = 0          # 0–8  (valuation_risk, scaled)
    management: int = 0         # 0–5  (management, direct)
    moat: int = 0               # 0–4  (moat, capped)
    sentiment: int = 0          # 0–3  (geopolitical_risk, scaled)

    # ── Audit trail (INTERNAL — not serialized by default) ──
    _raw_subscores: Dict[str, int] = PrivateAttr(default_factory=dict)

    @property
    def total(self) -> int:
        return sum([
            self.financial_health, self.growth, self.valuation,
            self.management, self.moat, self.sentiment,
        ])

    def decision(self) -> str:
        """BUY ≥ 28, HOLD 18–27, SELL < 18."""
        t = self.total
        if t >= 28:
            return "BUY"
        elif t >= 18:
            return "HOLD"
        else:
            return "SELL"


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
    used_for: List[str] = Field(default_factory=list)
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
    data_quality: str = "unknown"  # complete, partial, sparse
    company_overview: Optional[Dict[str, Any]] = None  # wired from get_company_overview() after scoring


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


class HealthResponse(BaseModel):
    """Response model for /api/health endpoint."""
    status: str
    service: str
    timestamp: str  # ISO 8601
    version: str
    commit: str = "unknown"


class MarketSnapshot(BaseModel):
    """Standardized real-time market data snapshot (V2.3).

    Single source of truth for market data consumed by the scorer,
    valuation module, and PDF renderer.  All fields are Optional
    because market data providers can return partial data.
    """
    ticker: str
    retrieved_at: str  # ISO 8601

    # ── Price ──
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None

    # ── Volume ──
    volume: Optional[int] = None
    avg_volume: Optional[int] = None

    # ── Market ──
    market_cap: Optional[float] = None
    beta: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    shares_outstanding: Optional[float] = None

    # ── Quick ratios (pulled from provider, not calculated) ──
    pe_ttm: Optional[float] = None
    ps_ttm: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None

    # ── Cache metadata ──
    cache_state: str = "unavailable"  # fresh / cached / stale / unavailable


class ValuationV2Response(BaseModel):
    """V2.3 Valuation endpoint response — market data (EUR disabled).

    Returns ticker, price, market cap, enterprise value, and
    valuation multiples computed from TTM fundamentals.
    EUR conversion is disabled in V2.3 (fx_status='unavailable').
    """
    ticker: str
    exchange: Optional[str] = None
    quote_currency: str = "USD"
    display_currency: str = "EUR"
    price: Optional[float] = None
    price_eur: Optional[float] = None
    market_cap: Optional[float] = None
    market_cap_eur: Optional[float] = None
    enterprise_value: Optional[float] = None
    enterprise_value_eur: Optional[float] = None
    ev_source: Optional[str] = None  # "reported" | "computed" | "unavailable"
    shares_outstanding: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    total_debt: Optional[float] = None
    quote_timestamp: Optional[str] = None   # ISO 8601
    fundamentals_timestamp: Optional[str] = None  # ISO 8601
    fx_rate_eur: Optional[float] = None
    fx_timestamp: Optional[str] = None      # ISO 8601
    fx_status: str = "unavailable"  # "available" | "unavailable"
    source: str = "unknown"  # finnhub / yfinance / twelvedata / eodhd
    served_from: str = "unknown"  # "live" | "cache" | "fallback"
    status: str = "unavailable"  # fresh | cached | stale | unavailable
