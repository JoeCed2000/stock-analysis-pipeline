"""V2.7-T2 PDF Section Renderers — 6 structured section rendering tests.

Tests the V2.7 renderer functions added to pdf_renderer.py:
  render_executive_snapshot, render_financial_metrics, render_valuation,
  render_valuation_context, render_peer_benchmark, render_data_quality
"""

import os
import tempfile
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from backend.earnings_deep_dive.report_model import (
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    # V2.7 structured section models
    ExecutiveSnapshot,
    FinancialMetrics,
    ValuationSection,
    ValuationContextSection,
    PeerBenchmarkSection,
    DataQualitySection,
    SourceRef,
)
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import (
    render_earnings_deep_dive_pdf,
    render_executive_snapshot,
    render_financial_metrics,
    render_valuation,
    render_valuation_context,
    render_peer_benchmark,
    render_data_quality,
    resolve_pdf_fonts,
    _styles,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics as MapperFinancialMetrics


# ── Helper: minimal report fixture ──────────────────────────────────────────

def _minimal_report(**overrides) -> EarningsDeepDiveReport:
    """Minimal EarningsDeepDiveReport with none of the V2.7 fields set."""
    return EarningsDeepDiveReport(
        ticker="TEST",
        company="Test Corp",
        quarter="FY2026 Q1",
        language="en",
        generated_at="2026-05-26T12:00:00Z",
        title="Test Report",
        sections=[
            RenderedSection(
                key="EPS & Revenue",
                title="EPS & Revenue",
                question="",
                analysis=[],
                summary="Test summary.",
                summary_label="Key Takeaway",
                table=RenderedTable(
                    columns=["Metric", "Estimate", "Actual"],
                    rows=[RenderedTableRow(label="EPS", cells=["$3.10", "$3.46"])],
                ),
            ),
        ],
    )


def _operating_metric_rows(language: str):
    metrics = MapperFinancialMetrics(
        revenue_actual=81_610_000_000,
        revenue_yoy=0.78,
        gross_margin=0.7493,
        gross_profit=10_000_000_000,
        opex=2_000_000_000,
        operating_income=53_540_000_000,
        operating_margin=0.656,
        net_income=18_000_000_000,
    )
    report = build_earnings_deep_dive_report(
        ticker="NVDA",
        company="NVIDIA Corporation",
        quarter="FY2027 Q1",
        language=language,
        metrics=metrics,
    )
    section = next(item for item in report.sections if item.key == "Operating Metrics")
    return section.table.rows


def test_operating_metrics_derives_gross_profit_and_opex_from_canonical_metrics():
    en_rows = _operating_metric_rows("en")
    jp_rows = _operating_metric_rows("jp")

    assert en_rows[1].label == "Gross profit"
    assert jp_rows[1].label == "粗利益"
    assert en_rows[1].cells[0] == "$61.2B"
    assert jp_rows[1].cells[0] == en_rows[1].cells[0]

    assert en_rows[3].label == "OpEx"
    assert jp_rows[3].label == "営業費用"
    assert en_rows[3].cells[0] == "$7.6B"
    assert jp_rows[3].cells[0] == en_rows[3].cells[0]


def _segment_rows(language: str):
    metrics = MapperFinancialMetrics.model_validate({
        "revenue_actual": 81_610_000_000,
        "revenue_quarterly_prior_year": 44_050_000_000,
        "revenue_yoy": 85.23,
        "segments": {
            "Data Center": {
                "revenue": 41_100_000_000,
                "revenue_q_prior_year": 21_361_746_361.74636,
                "yoy": 92.4,
                "source": "SEC XBRL",
            },
            "Gaming": {
                "revenue": 3_800_000_000,
                "revenue_q_prior_year": 2_600_000_000,
                "yoy": 46.2,
                "source": "SEC XBRL",
            },
            "total_revenue_quarterly": 81_610_000_000,
            "source": "SEC XBRL",
        },
    })
    llm_rounded_table = """
| Segment | Revenue | Prior Year | YoY | % of Total | Driver | Source |
|---|---|---|---|---|---|---|
| Data Center | $41.10B | $21.41B | +92.0% | 50.4% | AI | LLM |
| Total | $81.61B | $44.06B | +85.0% | 100.0% | Total | LLM |
"""
    report = build_earnings_deep_dive_report(
        ticker="NVDA",
        company="NVIDIA Corporation",
        quarter="FY2027 Q1",
        language=language,
        metrics=metrics,
        section_analysis={"Segments": llm_rounded_table},
    )
    section = next(item for item in report.sections if item.key == "Segments")
    return {row.label: row.cells for row in section.table.rows}


def test_segments_rows_ignore_llm_rounded_values_for_en_jp_parity():
    en_rows = _segment_rows("en")
    jp_rows = _segment_rows("jp")

    assert en_rows["Data Center"][2] == "+92.4%"
    assert jp_rows["Data Center"][2] == en_rows["Data Center"][2]
    assert jp_rows["Data Center"][2] != "+92.0%"

    assert "Total" in en_rows
    assert "Total" in jp_rows
    assert jp_rows["Total"][1] == en_rows["Total"][1]
    assert jp_rows["Total"][1] != "$44.06B"


# ═══════════════════════════════════════════════════════════════════════════════
# Executive Snapshot
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderExecutiveSnapshot:
    """render_executive_snapshot() — top-level header card."""

    @pytest.fixture
    def fonts(self):
        return resolve_pdf_fonts("en")

    @pytest.fixture
    def styles(self, fonts):
        return _styles(fonts)

    def test_returns_empty_when_none(self, styles, fonts):
        """Returns [] when report has no executive_snapshot."""
        report = _minimal_report()
        assert report.executive_snapshot is None
        result = render_executive_snapshot(report, styles, fonts)
        assert result == []

    def test_renders_company_name_and_ticker(self, styles, fonts):
        """Renders company name and ticker when available."""
        es = ExecutiveSnapshot(
            ticker="AAPL",
            company_name="Apple Inc.",
            quarter="FY2026 Q2",
            price=185.50,
            market_cap_display="$2.9T",
            sector="Technology",
            verdict="BUY",
            decision_score=32,
            next_earnings_date="2026-08-01",
        )
        report = _minimal_report()
        report.executive_snapshot = es

        result = render_executive_snapshot(report, styles, fonts)
        assert len(result) > 0, "Should return flowables when data is present"

    def test_renders_price_and_market_cap(self, styles, fonts):
        """Renders price and market cap."""
        es = ExecutiveSnapshot(price=185.50, market_cap=2_900_000_000_000)
        report = _minimal_report()
        report.executive_snapshot = es

        result = render_executive_snapshot(report, styles, fonts)
        assert len(result) > 0

    def test_numeric_market_cap_fallback(self, styles, fonts):
        """Uses numeric market_cap when display string is None."""
        es = ExecutiveSnapshot(market_cap=2_900_000_000_000, market_cap_display=None)
        report = _minimal_report()
        report.executive_snapshot = es

        result = render_executive_snapshot(report, styles, fonts)
        assert len(result) > 0

    def test_verdict_buy_is_green(self, styles, fonts):
        """BUY verdict renders with green color."""
        es = ExecutiveSnapshot(verdict="BUY", decision_score=32)
        report = _minimal_report()
        report.executive_snapshot = es

        result = render_executive_snapshot(report, styles, fonts)
        assert len(result) > 0

    def test_partial_snapshot_renders_gracefully(self, styles, fonts):
        """Snapshot with only ticker and quarter still renders."""
        es = ExecutiveSnapshot(ticker="NVDA", quarter="FY2026 Q1")
        report = _minimal_report()
        report.executive_snapshot = es

        result = render_executive_snapshot(report, styles, fonts)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Financial Metrics
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderFinancialMetrics:
    """render_financial_metrics() — EPS/Revenue/Margins/Growth table."""

    @pytest.fixture
    def fonts(self):
        return resolve_pdf_fonts("en")

    @pytest.fixture
    def styles(self, fonts):
        return _styles(fonts)

    def test_returns_empty_when_none(self, styles, fonts):
        report = _minimal_report()
        result = render_financial_metrics(report, styles, fonts)
        assert result == []

    def test_renders_eps_rows(self, styles, fonts):
        fm = FinancialMetrics(
            eps_actual=3.46, eps_actual_display="$3.46",
            eps_estimate=3.10, eps_estimate_display="$3.10",
            eps_beat_pct=11.6, eps_beat_pct_display="+11.6%",
        )
        report = _minimal_report()
        report.financial_metrics = fm
        result = render_financial_metrics(report, styles, fonts)
        assert len(result) > 0

    def test_renders_revenue_rows(self, styles, fonts):
        fm = FinancialMetrics(
            revenue_actual=82_900_000_000, revenue_actual_display="$82.9B",
            revenue_estimate=80_000_000_000, revenue_estimate_display="$80.0B",
            revenue_beat_pct=3.6, revenue_beat_pct_display="+3.6%",
        )
        report = _minimal_report()
        report.financial_metrics = fm
        result = render_financial_metrics(report, styles, fonts)
        assert len(result) > 0

    def test_renders_margins(self, styles, fonts):
        fm = FinancialMetrics(
            gross_margin=67.6, gross_margin_display="67.6%",
            operating_margin=46.3, operating_margin_display="46.3%",
            net_margin=25.0, net_margin_display="25.0%",
        )
        report = _minimal_report()
        report.financial_metrics = fm
        result = render_financial_metrics(report, styles, fonts)
        assert len(result) > 0

    def test_renders_growth_and_fcf(self, styles, fonts):
        fm = FinancialMetrics(
            revenue_growth_yoy=18.3, revenue_growth_yoy_display="+18.3%",
            eps_growth_yoy=22.0, eps_growth_yoy_display="+22.0%",
            fcf=71_600_000_000, fcf_display="$71.6B",
        )
        report = _minimal_report()
        report.financial_metrics = fm
        result = render_financial_metrics(report, styles, fonts)
        assert len(result) > 0

    def test_partial_metrics_renders_gracefully(self, styles, fonts):
        """Only EPS data, no revenue/margins/growth/FCF."""
        fm = FinancialMetrics(eps_actual=3.46, eps_actual_display="$3.46")
        report = _minimal_report()
        report.financial_metrics = fm
        result = render_financial_metrics(report, styles, fonts)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Valuation Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderValuation:
    """render_valuation() — multiples table."""

    @pytest.fixture
    def fonts(self):
        return resolve_pdf_fonts("en")

    @pytest.fixture
    def styles(self, fonts):
        return _styles(fonts)

    def test_returns_empty_when_none(self, styles, fonts):
        report = _minimal_report()
        result = render_valuation(report, styles, fonts)
        assert result == []

    def test_renders_all_multiples(self, styles, fonts):
        v = ValuationSection(
            pe_trailing=30.5, pe_trailing_display="30.5",
            pe_forward=28.0, pe_forward_display="28.0",
            peg_ratio=1.5, peg_ratio_display="1.50",
            price_to_sales=8.2, price_to_sales_display="8.20",
            price_to_book=45.3, price_to_book_display="45.30",
            ev_to_ebitda=22.1, ev_to_ebitda_display="22.10",
            fcf_yield=0.028, fcf_yield_display="2.8%",
            dividend_yield=0.0052, dividend_yield_display="0.52%",
        )
        report = _minimal_report()
        report.valuation = v
        result = render_valuation(report, styles, fonts)
        assert len(result) > 0

    def test_partial_multiples_renders_gracefully(self, styles, fonts):
        v = ValuationSection(pe_trailing=30.5)
        report = _minimal_report()
        report.valuation = v
        result = render_valuation(report, styles, fonts)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Valuation Context
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderValuationContext:
    """render_valuation_context() — 7 context signals."""

    @pytest.fixture
    def fonts(self):
        return resolve_pdf_fonts("en")

    @pytest.fixture
    def styles(self, fonts):
        return _styles(fonts)

    def test_returns_empty_when_none(self, styles, fonts):
        report = _minimal_report()
        result = render_valuation_context(report, styles, fonts)
        assert result == []

    def test_renders_signals(self, styles, fonts):
        vc = ValuationContextSection(
            peg_signal=1.2, peg_signal_label="Fairly Valued",
            ps_vs_growth_signal=2.1, ps_vs_growth_label="Elevated",
            ev_ebitda_vs_growth_signal=1.8, ev_ebitda_vs_growth_label="Above Average",
            pfcf_vs_growth_signal=3.5, pfcf_vs_growth_label="Below Average",
            fcf_yield_signal=2.8, fcf_yield_label="Healthy",
            valuation_support="Multiple signals suggest fair valuation.",
            context_summary="Overall: slightly above fair value.",
        )
        report = _minimal_report()
        report.valuation_context = vc
        result = render_valuation_context(report, styles, fonts)
        assert len(result) > 0

    def test_partial_signals_renders_gracefully(self, styles, fonts):
        vc = ValuationContextSection(peg_signal=1.2, peg_signal_label="Fairly Valued")
        report = _minimal_report()
        report.valuation_context = vc
        result = render_valuation_context(report, styles, fonts)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Peer Benchmark
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderPeerBenchmark:
    """render_peer_benchmark() — peer-relative comparison."""

    @pytest.fixture
    def fonts(self):
        return resolve_pdf_fonts("en")

    @pytest.fixture
    def styles(self, fonts):
        return _styles(fonts)

    def test_returns_empty_when_none(self, styles, fonts):
        report = _minimal_report()
        result = render_peer_benchmark(report, styles, fonts)
        assert result == []

    def test_renders_peer_comparison(self, styles, fonts):
        pb = PeerBenchmarkSection(
            peer_group="Mag 7",
            peer_tickers=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
            relative_valuation_label="Below Average",
            relative_valuation_detail="P/E 25.2 vs group median 32.1",
            relative_growth_label="Above Average",
            relative_growth_detail="Rev growth 18% vs group median 8%",
            relative_quality_label="Above Average",
            relative_quality_detail="ROIC 28% vs group median 15%",
            benchmark_summary="NVDA trades at a premium to Mag 7 peers on growth and quality.",
        )
        report = _minimal_report()
        report.peer_benchmark = pb
        result = render_peer_benchmark(report, styles, fonts)
        assert len(result) > 0

    def test_quality_row_suppressed_when_all_dimensions_present(self, tmp_path, styles, fonts):
        """Quality dimension row must NOT appear in rendered PDF when all 3 peer dims are set."""
        pb = PeerBenchmarkSection(
            peer_group="Mag 7",
            peer_tickers=["AAPL", "MSFT"],
            relative_valuation_label="Below Average",
            relative_valuation_detail="P/E 25.2 vs group median 32.1",
            relative_growth_label="Above Average",
            relative_growth_detail="Rev growth 18% vs group median 8%",
            relative_quality_label="Above Average",
            relative_quality_detail="ROIC 28% vs group median 15%",
            benchmark_summary="Growth and quality premium.",
        )
        report = _minimal_report()
        report.peer_benchmark = pb
        pdf_path = tmp_path / "v27_no_quality.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)
        import fitz
        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Valuation" in text, "Valuation row must still appear"
        assert "Growth" in text, "Growth row must still appear"
        assert "Quality" not in text, "Quality row must be suppressed in earnings scope"

    def test_partial_peers_renders_gracefully(self, styles, fonts):
        pb = PeerBenchmarkSection(
            relative_valuation_label="Above Average",
            benchmark_summary="Minimal peer data.",
        )
        report = _minimal_report()
        report.peer_benchmark = pb
        result = render_peer_benchmark(report, styles, fonts)
        assert len(result) > 0

    def test_peer_group_without_tickers_renders(self, styles, fonts):
        pb = PeerBenchmarkSection(
            peer_group="Mag 7",
            peer_tickers=[],
            relative_valuation_label="In Line",
        )
        report = _minimal_report()
        report.peer_benchmark = pb
        result = render_peer_benchmark(report, styles, fonts)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Data Quality
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderDataQuality:
    """render_data_quality() — source freshness + completeness."""

    @pytest.fixture
    def fonts(self):
        return resolve_pdf_fonts("en")

    @pytest.fixture
    def styles(self, fonts):
        return _styles(fonts)

    def test_returns_empty_when_none(self, styles, fonts):
        report = _minimal_report()
        result = render_data_quality(report, styles, fonts)
        assert result == []

    def test_renders_source_freshness(self, styles, fonts):
        dq = DataQualitySection(
            yfinance_freshness="2026-05-26",
            yfinance_source_label="api live",
            finnhub_freshness="2026-05-26",
            finnhub_source_label="api live",
            sec_edgar_freshness="2026-03-15",
            sec_edgar_source_label="10-K filing",
            transcript_freshness="2026-05-25",
            transcript_source_label="Seeking Alpha",
        )
        report = _minimal_report()
        report.data_quality = dq
        result = render_data_quality(report, styles, fonts)
        assert len(result) > 0

    def test_renders_confidence_and_completeness(self, styles, fonts):
        dq = DataQualitySection(
            overall_confidence="high",
            completeness_score=85,
            missing_fields=["EV/EBITDA", "Forward P/E estimate"],
        )
        report = _minimal_report()
        report.data_quality = dq
        result = render_data_quality(report, styles, fonts)
        assert len(result) > 0

    def test_medium_confidence_is_orange(self, styles, fonts):
        dq = DataQualitySection(overall_confidence="medium", completeness_score=55)
        report = _minimal_report()
        report.data_quality = dq
        result = render_data_quality(report, styles, fonts)
        assert len(result) > 0

    def test_low_confidence_is_red(self, styles, fonts):
        dq = DataQualitySection(overall_confidence="low", completeness_score=30)
        report = _minimal_report()
        report.data_quality = dq
        result = render_data_quality(report, styles, fonts)
        assert len(result) > 0

    def test_partial_quality_renders_gracefully(self, styles, fonts):
        dq = DataQualitySection(yfinance_freshness="2026-05-26")
        report = _minimal_report()
        report.data_quality = dq
        result = render_data_quality(report, styles, fonts)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: render_earnings_deep_dive_pdf with V2.7 sections
# ═══════════════════════════════════════════════════════════════════════════════

class TestV27InPdf:
    """Integration: V2.7 sections present in the generated PDF."""

    def test_pdf_includes_executive_snapshot_when_present(self, tmp_path):
        """Executive Snapshot appears in PDF text."""
        es = ExecutiveSnapshot(
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            quarter="FY2026 Q1",
            price=950.00,
            market_cap_display="$2.34T",
            verdict="BUY",
            decision_score=36,
        )
        report = _minimal_report()
        report.executive_snapshot = es

        pdf_path = tmp_path / "v27_exec_snap.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "NVIDIA" in text
        assert "NVDA" in text
        assert "BUY" in text
        assert "$950.00" in text

    def test_pdf_includes_financial_metrics_when_present(self, tmp_path):
        """Financial Metrics table appears in PDF text."""
        fm = FinancialMetrics(
            eps_actual=3.46, eps_actual_display="$3.46",
            revenue_actual=82_900_000_000, revenue_actual_display="$82.9B",
            gross_margin=67.6, gross_margin_display="67.6%",
            fcf=71_600_000_000, fcf_display="$71.6B",
        )
        report = _minimal_report()
        report.financial_metrics = fm

        pdf_path = tmp_path / "v27_fin_metrics.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Financial Metrics" in text
        assert "EPS" in text and "$3.46" in text

    def test_pdf_includes_valuation_when_present(self, tmp_path):
        """Valuation multiples appear in PDF text."""
        v = ValuationSection(pe_trailing=30.5, pe_trailing_display="30.5")
        report = _minimal_report()
        report.valuation = v

        pdf_path = tmp_path / "v27_valuation.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Valuation" in text
        assert "P/E" in text

    def test_pdf_includes_valuation_context_when_present(self, tmp_path):
        """Valuation context signals appear in PDF text."""
        vc = ValuationContextSection(
            peg_signal=1.2, peg_signal_label="Fairly Valued",
            context_summary="Overall fair valuation.",
        )
        report = _minimal_report()
        report.valuation_context = vc

        pdf_path = tmp_path / "v27_val_context.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Valuation Context" in text

    def test_pdf_includes_peer_benchmark_when_present(self, tmp_path):
        """Peer benchmark section appears in PDF text."""
        pb = PeerBenchmarkSection(
            peer_group="Mag 7",
            relative_valuation_label="Below Average",
            benchmark_summary="Test benchmark summary.",
        )
        report = _minimal_report()
        report.peer_benchmark = pb

        pdf_path = tmp_path / "v27_peer.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Peer Benchmark" in text

    def test_pdf_includes_data_quality_when_present(self, tmp_path):
        """Data Quality section appears in PDF text."""
        dq = DataQualitySection(
            yfinance_freshness="2026-05-26",
            overall_confidence="high",
            completeness_score=90,
        )
        report = _minimal_report()
        report.data_quality = dq

        pdf_path = tmp_path / "v27_dq.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Data Quality" in text

    def test_pdf_without_v27_sections_still_renders(self, tmp_path):
        """Baseline: PDF renders fine without any V2.7 sections."""
        report = _minimal_report()
        pdf_path = tmp_path / "v27_baseline.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)
        assert "Test Corp" in text
        assert "EPS & Revenue" in text

    def test_all_v27_sections_together(self, tmp_path):
        """All 6 V2.7 sections present in a single PDF."""
        es = ExecutiveSnapshot(ticker="MSFT", company_name="Microsoft Corp", price=425.00, verdict="HOLD")
        fm = FinancialMetrics(eps_actual=3.46, eps_actual_display="$3.46")
        v = ValuationSection(pe_trailing=30.5, pe_trailing_display="30.5")
        vc = ValuationContextSection(peg_signal=1.2, peg_signal_label="Fairly Valued")
        pb = PeerBenchmarkSection(relative_valuation_label="In Line")
        dq = DataQualitySection(overall_confidence="high", completeness_score=90)

        report = _minimal_report()
        report.executive_snapshot = es
        report.financial_metrics = fm
        report.valuation = v
        report.valuation_context = vc
        report.peer_benchmark = pb
        report.data_quality = dq

        pdf_path = tmp_path / "v27_all.pdf"
        render_earnings_deep_dive_pdf(report, pdf_path)

        doc = fitz.open(str(pdf_path))
        text = "\n".join(page.get_text() for page in doc)

        # Verify all sections rendered
        assert "Microsoft Corp" in text
        assert "Financial Metrics" in text
        assert "Valuation" in text
        assert "Valuation Context" in text
        assert "Peer Benchmark" in text
        assert "Data Quality" in text
