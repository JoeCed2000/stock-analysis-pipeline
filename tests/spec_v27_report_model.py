"""V2.7 Report Model Spec — 6 structured PDF sections.

Contract tests for the new Pydantic models added to report_model.py.
All fields must be nullable (Optional/None), USD-only, with source/timestamp tracking.
"""

import pytest
from datetime import date, datetime
from backend.earnings_deep_dive.report_model import (
    # ── V2.7 new models ──
    ExecutiveSnapshot,
    FinancialMetrics,
    ValuationSection,
    ValuationContextSection,
    PeerBenchmarkSection,
    DataQualitySection,
    # ── shared utilities ──
    SourceRef,
    GroundingLevel,
)


# ═══════════════════════════════════════════════════════════════════════════
# Executive Snapshot
# ═══════════════════════════════════════════════════════════════════════════

class TestExecutiveSnapshot:
    """Top-level summary card for the report's first page."""

    def test_all_fields_nullable(self):
        """All fields must accept None — snapshot may be partial."""
        snap = ExecutiveSnapshot()
        assert snap.ticker is None
        assert snap.company_name is None
        assert snap.quarter is None
        assert snap.price is None
        assert snap.market_cap is None
        assert snap.verdict is None
        assert snap.decision_score is None

    def test_full_construction(self):
        snap = ExecutiveSnapshot(
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            quarter="FY2026 Q1",
            price=145.32,
            price_currency="USD",
            market_cap=3_580_000_000_000,
            market_cap_display="$3.58T",
            market_cap_currency="USD",
            verdict="BUY",
            decision_score=32,
            decision_max=40,
            sector="Technology",
            industry="Semiconductors",
            next_earnings_date="2026-08-20",
            generated_at="2026-05-26T10:00:00Z",
            source_refs=[SourceRef(source_id="S1", label="yfinance NVDA")],
        )
        assert snap.ticker == "NVDA"
        assert snap.price == 145.32
        assert snap.price_currency == "USD"
        assert snap.verdict == "BUY"
        assert snap.decision_score == 32
        assert len(snap.source_refs) == 1

    def test_serialization_roundtrip(self):
        snap = ExecutiveSnapshot(
            ticker="AAPL",
            company_name="Apple Inc.",
            quarter="FY2026 Q2",
            price=225.0,
            market_cap=3_400_000_000_000,
            verdict="HOLD",
            decision_score=22,
            decision_max=40,
            generated_at="2026-05-26T10:00:00Z",
        )
        data = snap.model_dump()
        loaded = ExecutiveSnapshot(**data)
        assert loaded.ticker == "AAPL"
        assert loaded.price == 225.0
        assert loaded.verdict == "HOLD"

    def test_currency_is_usd_only(self):
        """price_currency and market_cap_currency must default to 'USD'."""
        snap = ExecutiveSnapshot(price=100.0, market_cap=1_000_000_000)
        assert snap.price_currency == "USD"
        assert snap.market_cap_currency == "USD"


# ═══════════════════════════════════════════════════════════════════════════
# Financial Metrics
# ═══════════════════════════════════════════════════════════════════════════

class TestFinancialMetrics:
    """Structured financial data tables for the PDF."""

    def test_all_fields_nullable(self):
        fm = FinancialMetrics()
        assert fm.eps_actual is None
        assert fm.eps_estimate is None
        assert fm.eps_beat_pct is None
        assert fm.revenue_actual is None
        assert fm.revenue_estimate is None
        assert fm.revenue_beat_pct is None
        assert fm.gross_margin is None
        assert fm.operating_margin is None
        assert fm.net_margin is None
        assert fm.revenue_growth_yoy is None

    def test_full_construction(self):
        fm = FinancialMetrics(
            eps_actual=2.94,
            eps_actual_display="$2.94",
            eps_estimate=2.85,
            eps_estimate_display="$2.85",
            eps_beat_pct=3.16,
            eps_beat_pct_display="+3.2%",
            eps_currency="USD",
            eps_source="yfinance",
            eps_as_of_date="2026-05-20",
            eps_grounding="direct_metric",
            revenue_actual=22_400_000_000,
            revenue_actual_display="$22.4B",
            revenue_estimate=22_100_000_000,
            revenue_estimate_display="$22.1B",
            revenue_beat_pct=1.36,
            revenue_beat_pct_display="+1.4%",
            revenue_currency="USD",
            revenue_source="yfinance",
            revenue_as_of_date="2026-05-20",
            revenue_grounding="direct_metric",
            gross_margin=74.5,
            gross_margin_display="74.5%",
            operating_margin=58.2,
            operating_margin_display="58.2%",
            net_margin=52.3,
            net_margin_display="52.3%",
            revenue_growth_yoy=12.4,
            revenue_growth_yoy_display="+12.4%",
            eps_growth_yoy=15.2,
            eps_growth_yoy_display="+15.2%",
            fcf=8_500_000_000,
            fcf_display="$8.5B",
            fcf_currency="USD",
            sources=[
                SourceRef(source_id="S1", label="yfinance NVDA FY2026 Q1"),
                SourceRef(source_id="S2", label="SEC EDGAR 10-Q"),
            ],
        )
        assert fm.eps_actual == 2.94
        assert fm.eps_beat_pct == 3.16
        assert fm.revenue_actual == 22_400_000_000
        assert fm.gross_margin == 74.5
        assert fm.revenue_growth_yoy == 12.4
        assert fm.eps_currency == "USD"
        assert fm.revenue_currency == "USD"
        assert fm.fcf_currency == "USD"
        assert len(fm.sources) == 2
        assert fm.eps_grounding == "direct_metric"

    def test_serialization_roundtrip(self):
        fm = FinancialMetrics(
            eps_actual=2.94,
            revenue_actual=22_400_000_000,
            gross_margin=74.5,
        )
        data = fm.model_dump()
        loaded = FinancialMetrics(**data)
        assert loaded.eps_actual == 2.94
        assert loaded.revenue_actual == 22_400_000_000

    def test_all_currencies_default_usd(self):
        fm = FinancialMetrics(eps_actual=1.0, revenue_actual=100_000)
        assert fm.eps_currency == "USD"
        assert fm.revenue_currency == "USD"
        assert fm.fcf_currency == "USD"


# ═══════════════════════════════════════════════════════════════════════════
# Valuation
# ═══════════════════════════════════════════════════════════════════════════

class TestValuationSection:
    """Multiples and valuation ratios for the PDF."""

    def test_all_fields_nullable(self):
        val = ValuationSection()
        assert val.pe_trailing is None
        assert val.pe_forward is None
        assert val.peg_ratio is None
        assert val.price_to_sales is None
        assert val.price_to_book is None
        assert val.ev_to_ebitda is None
        assert val.fcf_yield is None
        assert val.dividend_yield is None

    def test_full_construction(self):
        val = ValuationSection(
            pe_trailing=52.3,
            pe_trailing_display="52.3",
            pe_forward=48.7,
            pe_forward_display="48.7",
            peg_ratio=1.8,
            peg_ratio_display="1.8",
            price_to_sales=28.5,
            price_to_sales_display="28.5",
            price_to_book=42.1,
            price_to_book_display="42.1",
            ev_to_ebitda=38.9,
            ev_to_ebitda_display="38.9",
            fcf_yield=0.8,
            fcf_yield_display="0.8%",
            dividend_yield=0.02,
            dividend_yield_display="0.02%",
            currency="USD",
            generated_at="2026-05-26T10:00:00Z",
            sources=[
                SourceRef(source_id="S1", label="yfinance"),
                SourceRef(source_id="S3", label="Finnhub"),
            ],
        )
        assert val.pe_trailing == 52.3
        assert val.pe_forward == 48.7
        assert val.peg_ratio == 1.8
        assert val.price_to_sales == 28.5
        assert val.ev_to_ebitda == 38.9
        assert val.fcf_yield == 0.8
        assert val.dividend_yield == 0.02
        assert val.currency == "USD"
        assert len(val.sources) == 2

    def test_serialization_roundtrip(self):
        val = ValuationSection(pe_trailing=20.0, pe_forward=18.5)
        data = val.model_dump()
        loaded = ValuationSection(**data)
        assert loaded.pe_trailing == 20.0
        assert loaded.pe_forward == 18.5


# ═══════════════════════════════════════════════════════════════════════════
# Valuation Context (V2.4)
# ═══════════════════════════════════════════════════════════════════════════

class TestValuationContextSection:
    """7 context signals from V2.4 endpoint."""

    def test_all_fields_nullable(self):
        ctx = ValuationContextSection()
        assert ctx.peg_signal is None
        assert ctx.ps_vs_growth_signal is None
        assert ctx.ev_ebitda_vs_growth_signal is None
        assert ctx.pfcf_vs_growth_signal is None
        assert ctx.fcf_yield_signal is None
        assert ctx.valuation_support is None
        assert ctx.context_summary is None

    def test_full_construction(self):
        ctx = ValuationContextSection(
            peg_signal=0.85,
            peg_signal_label="Reasonable",
            peg_signal_detail="PEG < 1.0: growth fairly priced",
            ps_vs_growth_signal=1.2,
            ps_vs_growth_label="Slightly Premium",
            ev_ebitda_vs_growth_signal=0.9,
            ev_ebitda_vs_growth_label="Fair Value",
            pfcf_vs_growth_signal=1.1,
            pfcf_vs_growth_label="Slightly Premium",
            fcf_yield_signal=0.8,
            fcf_yield_label="Below Threshold (<5%)",
            valuation_support="Moderate — PEG is reasonable (0.85), EV/EBITDA suggests fair value, but P/S and P/FCF ratios indicate slight premium relative to growth.",
            context_summary="Overall valuation is acceptable. PEG is reasonable and EV/EBITDA confirms fair value, though some premium metrics warrant monitoring.",
            generated_at="2026-05-26T10:00:00Z",
            currency="USD",
        )
        assert ctx.peg_signal == 0.85
        assert ctx.peg_signal_label == "Reasonable"
        assert ctx.valuation_support is not None
        assert "PEG is reasonable" in ctx.valuation_support
        assert ctx.context_summary is not None
        assert "acceptable" in ctx.context_summary
        assert ctx.currency == "USD"

    def test_serialization_roundtrip(self):
        ctx = ValuationContextSection(
            peg_signal=0.85,
            context_summary="Valuation is acceptable.",
        )
        data = ctx.model_dump()
        loaded = ValuationContextSection(**data)
        assert loaded.peg_signal == 0.85
        assert loaded.context_summary == "Valuation is acceptable."


# ═══════════════════════════════════════════════════════════════════════════
# Peer Benchmark (V2.5)
# ═══════════════════════════════════════════════════════════════════════════

class TestPeerBenchmarkSection:
    """Peer-relative benchmarks from V2.5 endpoint."""

    def test_all_fields_nullable(self):
        pb = PeerBenchmarkSection()
        assert pb.peer_group is None
        assert pb.peer_tickers == []  # default_factory=list (consistent with other models)
        assert pb.relative_valuation_label is None
        assert pb.relative_growth_label is None
        assert pb.relative_quality_label is None
        assert pb.benchmark_summary is None

    def test_full_construction(self):
        pb = PeerBenchmarkSection(
            peer_group="Semiconductors",
            peer_tickers=["NVDA", "AMD", "INTC", "AVGO", "QCOM"],
            relative_valuation_label="Above Average",
            relative_valuation_detail="P/E 52.3 vs peer median 28.1 (NVDA trades at premium)",
            relative_growth_label="Above Average",
            relative_growth_detail="Revenue growth 12.4% vs peer median 4.2%",
            relative_quality_label="Leader",
            relative_quality_detail="Gross margin 74.5% vs peer median 52.1%, ROIC 45% vs peer median 18%",
            benchmark_summary="NVDA leads peers across valuation premium, growth rate, and quality metrics. The premium valuation is supported by superior fundamentals.",
            valuation_metrics={
                "pe_peer_median": 28.1,
                "ps_peer_median": 8.2,
                "ev_ebitda_peer_median": 18.5,
            },
            quality_metrics={
                "gross_margin_peer_median": 52.1,
                "roic_peer_median": 18.0,
            },
            currency="USD",
            generated_at="2026-05-26T10:00:00Z",
        )
        assert pb.peer_group == "Semiconductors"
        assert len(pb.peer_tickers) == 5
        assert pb.relative_valuation_label == "Above Average"
        assert pb.relative_growth_label == "Above Average"
        assert pb.relative_quality_label == "Leader"
        assert pb.valuation_metrics["pe_peer_median"] == 28.1
        assert pb.quality_metrics["roic_peer_median"] == 18.0
        assert "NVDA" in pb.benchmark_summary
        assert pb.currency == "USD"

    def test_serialization_roundtrip(self):
        pb = PeerBenchmarkSection(
            peer_group="Semiconductors",
            peer_tickers=["NVDA", "AMD"],
            relative_valuation_label="Above Average",
            benchmark_summary="Summary.",
        )
        data = pb.model_dump()
        loaded = PeerBenchmarkSection(**data)
        assert loaded.peer_group == "Semiconductors"
        assert loaded.peer_tickers == ["NVDA", "AMD"]
        assert loaded.relative_valuation_label == "Above Average"

    def test_peer_tickers_defaults_empty(self):
        pb = PeerBenchmarkSection()
        assert pb.peer_tickers == []


# ═══════════════════════════════════════════════════════════════════════════
# Data Quality
# ═══════════════════════════════════════════════════════════════════════════

class TestDataQualitySection:
    """Source freshness and data completeness for audit trail."""

    def test_all_fields_nullable(self):
        dq = DataQualitySection()
        assert dq.yfinance_freshness is None
        assert dq.finnhub_freshness is None
        assert dq.sec_edgar_freshness is None
        assert dq.transcript_freshness is None
        assert dq.overall_confidence is None
        assert dq.completeness_score is None

    def test_full_construction(self):
        dq = DataQualitySection(
            yfinance_freshness="2026-05-26",
            yfinance_source_label="yfinance Ticker.info + financials",
            finnhub_freshness="2026-05-26",
            finnhub_source_label="Finnhub Company News + Estimates",
            sec_edgar_freshness="2026-05-15",
            sec_edgar_source_label="SEC EDGAR 10-Q (FY2026 Q1)",
            transcript_freshness="2026-05-20",
            transcript_source_label="Seeking Alpha Earnings Call Transcript",
            overall_confidence="high",
            completeness_score=92,
            completeness_max=100,
            missing_fields=["short_interest", "insider_transactions"],
            data_currency="USD",
            generated_at="2026-05-26T10:00:00Z",
        )
        assert dq.yfinance_freshness == "2026-05-26"
        assert dq.finnhub_freshness == "2026-05-26"
        assert dq.sec_edgar_freshness == "2026-05-15"
        assert dq.transcript_freshness == "2026-05-20"
        assert dq.overall_confidence == "high"
        assert dq.completeness_score == 92
        assert dq.completeness_max == 100
        assert "short_interest" in dq.missing_fields
        assert dq.data_currency == "USD"

    def test_completeness_defaults(self):
        dq = DataQualitySection()
        assert dq.completeness_max == 100
        assert dq.data_currency == "USD"
        assert dq.missing_fields == []

    def test_serialization_roundtrip(self):
        dq = DataQualitySection(
            yfinance_freshness="2026-05-26",
            overall_confidence="high",
            completeness_score=90,
        )
        data = dq.model_dump()
        loaded = DataQualitySection(**data)
        assert loaded.yfinance_freshness == "2026-05-26"
        assert loaded.overall_confidence == "high"
        assert loaded.completeness_score == 90


# ═══════════════════════════════════════════════════════════════════════════
# Integration — EarningsDeepDiveReport extension
# ═══════════════════════════════════════════════════════════════════════════

class TestReportModelV27Integration:
    """Verify the 6 new sections can attach to the existing report model."""

    def test_new_sections_optional_on_report(self):
        """The 6 new sections are optional on EarningsDeepDiveReport."""
        from backend.earnings_deep_dive.report_model import EarningsDeepDiveReport

        report = EarningsDeepDiveReport(
            ticker="NVDA",
            company="NVIDIA Corporation",
            quarter="FY2026 Q1",
            language="en",
            generated_at="2026-05-26T10:00:00Z",
            title="NVDA FY2026 Q1 Earnings Deep Dive",
            sections=[],
        )
        # All V2.7 sections must be None by default (no breaking change)
        assert report.executive_snapshot is None
        assert report.financial_metrics is None
        assert report.valuation is None
        assert report.valuation_context is None
        assert report.peer_benchmark is None
        assert report.data_quality is None

    def test_full_report_with_v27_sections(self):
        """All 6 sections can be populated on a single report."""
        from backend.earnings_deep_dive.report_model import EarningsDeepDiveReport

        snap = ExecutiveSnapshot(
            ticker="AAPL",
            company_name="Apple Inc.",
            quarter="FY2026 Q2",
            price=225.0,
            market_cap=3_400_000_000_000,
            verdict="HOLD",
            decision_score=22,
            decision_max=40,
            generated_at="2026-05-26T10:00:00Z",
        )
        fm = FinancialMetrics(eps_actual=1.52, revenue_actual=95_800_000_000)
        val = ValuationSection(pe_trailing=30.5, pe_forward=28.2)
        ctx = ValuationContextSection(peg_signal=1.5, context_summary="Premium.")
        pb = PeerBenchmarkSection(peer_group="Consumer Electronics", peer_tickers=["AAPL", "SMSN"])
        dq = DataQualitySection(yfinance_freshness="2026-05-26", overall_confidence="high")

        report = EarningsDeepDiveReport(
            ticker="AAPL",
            company="Apple Inc.",
            quarter="FY2026 Q2",
            language="en",
            generated_at="2026-05-26T10:00:00Z",
            title="Apple FY2026 Q2 Earnings Deep Dive",
            sections=[],
            executive_snapshot=snap,
            financial_metrics=fm,
            valuation=val,
            valuation_context=ctx,
            peer_benchmark=pb,
            data_quality=dq,
        )
        assert report.executive_snapshot.ticker == "AAPL"
        assert report.executive_snapshot.verdict == "HOLD"
        assert report.financial_metrics.eps_actual == 1.52
        assert report.valuation.pe_trailing == 30.5
        assert report.valuation_context.peg_signal == 1.5
        assert report.peer_benchmark.peer_group == "Consumer Electronics"
        assert report.data_quality.overall_confidence == "high"

    def test_serialization_full_roundtrip(self):
        """Full report with V2.7 sections serializes and deserializes."""
        from backend.earnings_deep_dive.report_model import EarningsDeepDiveReport

        report = EarningsDeepDiveReport(
            ticker="NVDA",
            company="NVIDIA Corporation",
            quarter="FY2026 Q1",
            language="en",
            generated_at="2026-05-26T10:00:00Z",
            title="NVDA FY2026 Q1 Earnings Deep Dive",
            sections=[],
            executive_snapshot=ExecutiveSnapshot(
                ticker="NVDA", company_name="NVIDIA", price=145.32,
                verdict="BUY", decision_score=32, decision_max=40,
                generated_at="2026-05-26T10:00:00Z",
            ),
            financial_metrics=FinancialMetrics(eps_actual=2.94),
            valuation=ValuationSection(pe_trailing=52.3),
            valuation_context=ValuationContextSection(peg_signal=0.85),
            peer_benchmark=PeerBenchmarkSection(peer_group="Semiconductors", peer_tickers=["NVDA"]),
            data_quality=DataQualitySection(overall_confidence="high"),
        )
        data = report.model_dump()
        loaded = EarningsDeepDiveReport(**data)

        assert loaded.executive_snapshot.ticker == "NVDA"
        assert loaded.executive_snapshot.verdict == "BUY"
        assert loaded.financial_metrics.eps_actual == 2.94
        assert loaded.valuation.pe_trailing == 52.3
        assert loaded.valuation_context.peg_signal == 0.85
        assert loaded.peer_benchmark.peer_group == "Semiconductors"
        assert loaded.data_quality.overall_confidence == "high"
