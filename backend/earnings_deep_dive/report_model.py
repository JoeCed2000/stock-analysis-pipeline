"""Structured render model for earnings deep-dive reports.

CompanyOverview section — see company_overview.py for the service layer.
⚠️ LANGUAGE SEPARATION: CompanyClaim and CompetitorRef store bilingual
text in SEPARATE fields (text_en + text_jp). Never mix languages.
CompanyOverview itself is per-language (EN or JP from cache).
"""
from datetime import date as DateType
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


ReportLanguage = Literal["en", "jp"]
MetricPeriodType = Literal[
    "Quarterly",
    "Annual",
    "TTM",
    "Market Snapshot",
    "Guidance",
    "Consensus",
    "Calculated",
]
MetricSourceStatus = Literal[
    "used",
    "candidate",
    "available_not_used",
    "failed",
    "fallback_used",
    "unavailable",
]
MetricValidationStatus = Literal["verified", "unverified", "warning", "blocked", "unavailable", "flagged"]
MetricConfidence = Literal["high", "medium", "low"]

_METRIC_PERIOD_ALIASES: dict[str, MetricPeriodType] = {
    "quarterly": "Quarterly",
    "quarter": "Quarterly",
    "q": "Quarterly",
    "annual": "Annual",
    "yearly": "Annual",
    "fy": "Annual",
    "ttm": "TTM",
    "ltm": "TTM",
    "market_data": "Market Snapshot",
    "market snapshot": "Market Snapshot",
    "market_snapshot": "Market Snapshot",
    "market": "Market Snapshot",
    "guidance": "Guidance",
    "consensus": "Consensus",
    "calculated": "Calculated",
    "computed": "Calculated",
}

_BLOCKED_INTERNAL_PERIODS = {"annual_or_ttm", "unknown", "mixed", "provider_default"}

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
    revenue_model: str | None = None
    business_segments: list[str] = Field(default_factory=list)
    growth_drivers: list[str] = Field(default_factory=list)
    moats: list[str] = Field(default_factory=list)
    key_kpis: list[str] = Field(default_factory=list)
    business_risks: list[str] = Field(default_factory=list)
    key_financials: KeyFinancials | None = None
    recent_developments: list[RecentDevelopment] = Field(default_factory=list)
    competitive_position: str | None = None
    strengths_vs_competitors: str | None = None
    weaker_areas_vs_competitors: str | None = None
    ceo_leadership_style: str | None = None
    long_term_vision: str | None = None
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


class EarningsDocumentsChecklist(BaseModel):
    """Pre-generation checklist of required earnings documents — §6 corrections.txt.

    Tracks which documents are expected, retrieved, and their status.
    Used by the validator to ensure no section fabricates data from a missing source.
    """
    # ── Transcript ──
    transcript_status: str | None = None          # "retrieved" | "unavailable" | "not_applicable"
    transcript_source_id: str | None = None
    transcript_period_match: bool = False

    # ── Earnings Presentation ──
    presentation_status: str | None = None         # "retrieved" | "unavailable" | "not_applicable"
    presentation_source_id: str | None = None
    presentation_period_match: bool = False

    # ── Press Release ──
    press_release_status: str | None = None        # "retrieved" | "unavailable" | "not_applicable"
    press_release_source_id: str | None = None
    press_release_period_match: bool = False

    # ── SEC Filing (10-Q/10-K) ──
    sec_filing_status: str | None = None           # "retrieved" | "unavailable" | "not_applicable"
    sec_filing_source_id: str | None = None
    sec_filing_period_match: bool = False

    # ── Consensus Estimates ──
    consensus_status: str | None = None            # "retrieved" | "unavailable" | "not_applicable"
    consensus_source_id: str | None = None
    consensus_period_match: bool = False

    # ── Overall ──
    all_documents_match_period: bool = False
    missing_document_public_note: str | None = None
    missing_document_internal_reason: str | None = None

    # ── Metadata ──
    generated_at: str | None = None

    @property
    def critical_sources_available(self) -> bool:
        """At minimum, SEC filing and consensus must be available."""
        return (
            self.sec_filing_status == "retrieved"
            and self.consensus_status == "retrieved"
        )

    @property
    def transcript_available(self) -> bool:
        return self.transcript_status == "retrieved"

    @property
    def presentation_available(self) -> bool:
        return self.presentation_status == "retrieved"

    @property
    def press_release_available(self) -> bool:
        return self.press_release_status == "retrieved"


class SourceRegistryEntry(BaseModel):
    """Per-source usage and capability tracking entry — §5 corrections.txt.

    Tracks whether a source was actually used as evidence (not just available).
    Declares what metric families it can support so later reconciliation can
    block unsupported attributions before rendering.
    """
    source_id: str
    human_label: str
    provider: str | None = None               # yfinance, finnhub, sec_edgar, seeking_alpha
    source_type: str | None = None             # transcript, press_release, SEC_filing, market_data, consensus
    url: str | None = None
    period_matched: bool = False               # Does the source period match the report period?
    status: MetricSourceStatus = "candidate"
    fields_used: list[str] = Field(default_factory=list)  # e.g. ["eps_actual", "revenue_estimate"]
    capability_families: list[str] = Field(default_factory=list)
    unsupported_metric_families: list[str] = Field(default_factory=list)
    retrieved_at: str | None = None
    confidence: MetricConfidence | None = None
    failure_reason_internal_only: str | None = None
    public_display_label: str | None = None    # Client-ready label, never raw provider key
    public_quality_note: str | None = None

    def supports_metric_family(self, family: str) -> bool:
        """Return True only when this source is usable evidence for a metric family."""
        normalized = family.strip().lower()
        if self.status != "used":
            return False
        unsupported = {f.strip().lower() for f in self.unsupported_metric_families}
        if normalized in unsupported:
            return False
        supported = {f.strip().lower() for f in self.capability_families}
        return normalized in supported


class SourceRegistry(BaseModel):
    """Source usage registry — §5 corrections.txt.

    Maps every source to its usage status. Ensures:
    - No source cited as evidence unless status = "used"
    - No raw provider keys in public-facing labels
    - Every S1/S2/etc. has a readable mapping
    - Data Quality reflects actual source usage
    """
    entries: list[SourceRegistryEntry] = Field(default_factory=list)
    generated_at: str | None = None

    @property
    def used_sources(self) -> list[SourceRegistryEntry]:
        return [e for e in self.entries if e.status == "used"]

    @property
    def used_count(self) -> int:
        return len(self.used_sources)

    @property
    def has_transcript(self) -> bool:
        return any(e.source_type == "transcript" and e.status == "used" for e in self.entries)

    @property
    def has_sec_filing(self) -> bool:
        return any(e.source_type == "SEC_filing" and e.status == "used" for e in self.entries)

    @property
    def has_consensus(self) -> bool:
        return any(e.source_type == "consensus" and e.status == "used" for e in self.entries)

    def get_label(self, source_id: str) -> str | None:
        """Get human-readable label for a source ID. Returns None if not found."""
        entry = self.get_entry(source_id)
        if entry is None:
            return None
        return entry.public_display_label or entry.human_label

    def get_entry(self, source_id: str) -> SourceRegistryEntry | None:
        """Return a source registry entry by ID."""
        for e in self.entries:
            if e.source_id == source_id:
                return e
        return None

    def source_supports(self, source_id: str, metric_family: str) -> bool:
        """Return whether a used source can support the requested metric family."""
        entry = self.get_entry(source_id)
        if entry is None:
            return False
        return entry.supports_metric_family(metric_family)


class MetricsLedgerEntry(BaseModel):
    """Single canonical row in the PDF metric truth table — §4 corrections.txt.

    Every displayed number in the PDF must derive from a ledger entry. Public
    period labels are normalized here so renderer layers never leak internal
    provider enums such as ``annual_or_ttm`` or ``market_data``.
    """
    metric_id: str                          # e.g. "EPS-001", "REV-002"
    canonical_metric_name: str              # "eps_actual", "revenue_ttm"
    display_name: str                       # "EPS (Actual)", "Revenue (TTM)"
    value: float | None = None
    unit: str | None = None                 # "USD", "shares", "ratio", "%"
    scale: str | None = None                # "billions", "millions", "units"
    period_type: MetricPeriodType | None = None
    fiscal_period: str | None = None        # "FY2026 Q1"
    calendar_period: str | None = None      # "2026-03-31"
    source_id: str | None = None
    source_type: str | None = None          # yfinance | sec_edgar | seeking_alpha | calculated
    source_status: MetricSourceStatus = "used"
    metric_family: str | None = None        # market_snapshot | consensus | management_guidance | historical_actuals | filing_facts | transcript_claims
    basis: str | None = None                # GAAP | non-GAAP | adjusted | consensus | market | calculated | provider_supplied
    formula: str | None = None              # "revenue_actual / shares_outstanding"
    inputs: list[str] = Field(default_factory=list)
    numerator: float | None = None
    denominator: float | None = None
    validation_status: MetricValidationStatus | None = None
    confidence: MetricConfidence | None = None
    allowed_sections: list[str] = Field(default_factory=list)  # ["EPS & Revenue", "Financials"]
    display_label: str | None = None
    quality_notes: list[str] = Field(default_factory=list)

    @field_validator("period_type", mode="before")
    @classmethod
    def _normalize_period_type(cls, value: object) -> object:
        if value is None:
            return None
        key = str(value).strip()
        normalized_key = key.lower().replace("-", "_")
        if normalized_key in _BLOCKED_INTERNAL_PERIODS:
            raise ValueError(f"unresolved internal period_type is not client-safe: {key}")
        if key in _METRIC_PERIOD_ALIASES.values():
            return key
        if normalized_key in _METRIC_PERIOD_ALIASES:
            return _METRIC_PERIOD_ALIASES[normalized_key]
        raise ValueError(f"unsupported metric period_type: {key}")

    @model_validator(mode="after")
    def _validate_calculated_metric_contract(self) -> "MetricsLedgerEntry":
        if self.period_type == "Calculated" or self.basis == "calculated" or self.source_type == "calculated":
            if not self.formula:
                raise ValueError("calculated metrics require formula")
        return self


class MetricsLedger(BaseModel):
    """Single source of truth for all displayed numbers — §4 corrections.txt.

    Rules enforced:
    - No number may appear in the PDF unless present in this ledger.
    - Tables, charts, callouts, narrative, and source appendix use the same values.
    - Quarterly and TTM revenue may coexist only if explicitly labeled.
    - Consensus estimates must not be labeled as SEC data.
    - Provider-supplied ratios must be labeled as provider-supplied.
    - Calculated ratios must store inputs, formula, and source IDs.
    """
    entries: list[MetricsLedgerEntry] = Field(default_factory=list)
    generated_at: str | None = None

    def get(self, metric_id: str) -> MetricsLedgerEntry | None:
        for e in self.entries:
            if e.metric_id == metric_id:
                return e
        return None

    def get_by_name(self, canonical_name: str) -> MetricsLedgerEntry | None:
        for e in self.entries:
            if e.canonical_metric_name == canonical_name:
                return e
        return None

    @property
    def metric_ids(self) -> set[str]:
        return {e.metric_id for e in self.entries}

    @property
    def canonical_names(self) -> set[str]:
        return {e.canonical_metric_name for e in self.entries}

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def verified_count(self) -> int:
        return len([e for e in self.entries if e.validation_status == "verified"])


class CompetitivePositioningEntry(BaseModel):
    """Single competitor entry — §17 corrections.txt.

    Distinct from CompetitorRef (which is bilingual, per-language).
    This is the structured competitive analysis data model.
    """
    competitor: str
    type: str | None = None  # direct | indirect | valuation_peer | supplier | customer_internal_alternative | ecosystem_competitor
    area_of_competition: str | None = None
    competitor_strength: str | None = None
    target_company_advantage: str | None = None
    target_company_weakness: str | None = None
    risk_to_target_company: str | None = None
    source_id: str | None = None
    investor_implication: str | None = None


class CompetitivePositioning(BaseModel):
    """Competitive positioning analysis — §17 corrections.txt.

    Rules:
    - Separate operating competitors from valuation peers.
    - Never mix peer valuation group with direct competitors without explanation.
    - No truncated text, no generic comparison, no unmapped S1/S2.
    """
    entries: list[CompetitivePositioningEntry] = Field(default_factory=list)
    generated_at: str | None = None

    @property
    def direct_competitors(self) -> list[CompetitivePositioningEntry]:
        return [e for e in self.entries if e.type == "direct"]

    @property
    def valuation_peers(self) -> list[CompetitivePositioningEntry]:
        return [e for e in self.entries if e.type == "valuation_peer"]

    @property
    def has_separated_types(self) -> bool:
        """True if operating competitors and valuation peers are both present but labeled."""
        types_present = {e.type for e in self.entries if e.type}
        if "direct" in types_present and "valuation_peer" in types_present:
            return True
        return len(types_present) <= 1  # Only one type = no mixing issue


class ManagementAnalysis(BaseModel):
    """Management strengths and weaknesses analysis — §18 corrections.txt.

    Client-requested: management assessment based on public evidence.
    No psychological speculation, no unsupported claims.
    """
    management_strengths: list[str] = Field(default_factory=list)
    management_weaknesses_or_risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source_id: str | None = None
    investor_implication: str | None = None
    what_to_monitor: str | None = None

    # ── Metadata ──
    generated_at: str | None = None


class ReportPeriodContext(BaseModel):
    """Single source of truth for report period — §3 corrections.txt.

    Every displayed period in the PDF must derive from this context.
    No section may independently compute or assume a period.
    """
    ticker: str
    company_name: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None           # 1-4
    calendar_period: str | None = None           # "2026-03-31"
    earnings_release_date: str | None = None     # ISO date
    transcript_period: str | None = None         # period label from transcript
    press_release_period: str | None = None      # period label from press release
    filing_period: str | None = None             # "FY2026 Q1" from SEC 10-Q
    guidance_period: str | None = None            # "FY2027 Q1" or "FY2027"
    guidance_issued_date: str | None = None       # ISO date when guidance was issued/confirmed
    comparison_prior_year_period: str | None = None  # "FY2025 Q1"
    report_title_period_label: str | None = None   # "Q1 FY2026"
    display_period_label: str | None = None        # "FY2026 Q1 (Filed 2026-05-15)"
    generated_at: str | None = None

    # Quick validity check
    @property
    def is_valid(self) -> bool:
        return bool(self.fiscal_year and self.fiscal_quarter and self.report_title_period_label)


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
    # ── §3 report period context ──
    period_context: ReportPeriodContext | None = None
    # ── §6 earnings documents checklist ──
    earnings_documents: EarningsDocumentsChecklist | None = None
    # ── §5 source registry ──
    source_registry: SourceRegistry | None = None
    # ── §4 metrics ledger ──
    metrics_ledger: MetricsLedger | None = None
    # ── §18 management analysis ──
    management_analysis: ManagementAnalysis | None = None
    # ── §17 competitive positioning ──
    competitive_positioning: CompetitivePositioning | None = None
