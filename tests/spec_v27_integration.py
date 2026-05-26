"""V2.7-T3 Integration Tests — mapper → V2.7 models → PDF pipeline.

Verifies that build_earnings_deep_dive_report populates V2.7 structured section
models from available data (old metrics, company_overview, scoring).
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.earnings_deep_dive.mapper import (
    build_earnings_deep_dive_report,
    _build_v27_models,
)
from backend.earnings_deep_dive.report_model import (
    EarningsDeepDiveReport,
    ExecutiveSnapshot,
    FinancialMetrics as V27FinancialMetrics,
    ValuationSection,
    ValuationContextSection,
    PeerBenchmarkSection,
    DataQualitySection,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf


# ── Helpers ──────────────────────────────────────────────────────────────────


def _minimal_metrics(**overrides) -> FinancialMetrics:
    """Build a minimal old-style FinancialMetrics for testing."""
    defaults = {
        "eps_actual": 0.67,
        "eps_estimate": 0.59,
        "eps_vs_estimate": 13.6,
        "eps_yoy": 12.5,
        "revenue_actual": 44_200_000_000,
        "revenue_estimate": 42_900_000_000,
        "revenue_yoy": 15.3,
        "gross_margin": 47.2,
        "operating_margin": 28.8,
        "net_margin": 22.1,
        "free_cash_flow": 18_500_000_000,
        "operating_cash_flow": 21_200_000_000,
        "pe_forward": 28.4,
        "pe_trailing": 31.2,
    }
    defaults.update(overrides)
    return FinancialMetrics(**defaults)


def _minimal_company_overview(**overrides) -> dict:
    """Build a minimal company_overview dict."""
    return {
        "company_profile": {
            "sector": "Technology",
            "industry": "Software",
            **overrides.pop("profile", {}),
        },
        "key_financials": {
            "market_cap": 2_800_000_000_000,
            "market_cap_display": "$2.80T",
            **overrides.pop("key_financials", {}),
        },
        **overrides,
    }


# ── Tests: _build_v27_models ────────────────────────────────────────────────


class TestBuildV27Models:
    """Unit tests for the _build_v27_models function."""

    def test_returns_all_six_models(self):
        metrics = _minimal_metrics()
        result = _build_v27_models(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            generated_at="2026-05-26T12:00:00Z",
            company_overview=None,
            scoring=None,
        )
        assert set(result.keys()) == {
            "executive_snapshot",
            "financial_metrics",
            "valuation",
            "valuation_context",
            "peer_benchmark",
            "data_quality",
        }

    def test_executive_snapshot_from_company_overview(self):
        metrics = _minimal_metrics()
        ov = _minimal_company_overview()
        result = _build_v27_models(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            generated_at="2026-05-26T12:00:00Z",
            company_overview=ov,
            scoring=None,
        )
        es = result["executive_snapshot"]
        assert es.ticker == "TEST"
        assert es.company_name == "Test Corp"
        assert es.market_cap == 2_800_000_000_000
        assert es.market_cap_display == "$2.80T"
        assert es.sector == "Technology"
        assert es.industry == "Software"

    def test_executive_snapshot_without_company_overview(self):
        metrics = _minimal_metrics()
        result = _build_v27_models(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            generated_at="2026-05-26T12:00:00Z",
            company_overview=None,
            scoring=None,
        )
        es = result["executive_snapshot"]
        assert es.market_cap is None
        assert es.sector is None
        # Still has basic identity
        assert es.ticker == "TEST"

    def test_financial_metrics_maps_eps_revenue(self):
        metrics = _minimal_metrics(
            eps_actual=0.67, eps_estimate=0.59, eps_vs_estimate=13.6,
            revenue_actual=44_200_000_000, revenue_estimate=42_900_000_000,
        )
        result = _build_v27_models(
            ticker="TEST", company="Test Corp", quarter="FY2026 Q1",
            metrics=metrics, generated_at="2026-05-26T12:00:00Z",
            company_overview=None, scoring=None,
        )
        fm = result["financial_metrics"]
        assert fm.eps_actual == 0.67
        assert fm.eps_estimate == 0.59
        assert fm.eps_beat_pct == 13.6
        assert fm.revenue_actual == 44_200_000_000
        assert fm.revenue_beat_pct is not None  # computed
        assert fm.revenue_beat_pct > 0  # beat

    def test_financial_metrics_maps_margins_and_growth(self):
        metrics = _minimal_metrics(
            gross_margin=47.2, operating_margin=28.8,
            revenue_yoy=15.3, eps_yoy=12.5,
        )
        result = _build_v27_models(
            ticker="TEST", company="Test Corp", quarter="FY2026 Q1",
            metrics=metrics, generated_at="2026-05-26T12:00:00Z",
            company_overview=None, scoring=None,
        )
        fm = result["financial_metrics"]
        assert fm.gross_margin == 47.2
        assert fm.operating_margin == 28.8
        assert fm.revenue_growth_yoy == 15.3
        assert fm.eps_growth_yoy == 12.5
        # Display strings
        assert "47.2%" in str(fm.gross_margin_display or "")
        assert "15.3%" in str(fm.revenue_growth_yoy_display or "")

    def test_financial_metrics_fcf(self):
        metrics = _minimal_metrics(free_cash_flow=18_500_000_000)
        result = _build_v27_models(
            ticker="TEST", company="Test Corp", quarter="FY2026 Q1",
            metrics=metrics, generated_at="2026-05-26T12:00:00Z",
            company_overview=None, scoring=None,
        )
        fm = result["financial_metrics"]
        assert fm.fcf == 18_500_000_000
        assert fm.fcf_display == "$18.50B"

    def test_valuation_section_pe_multiples(self):
        metrics = _minimal_metrics(pe_forward=28.4, pe_trailing=31.2)
        result = _build_v27_models(
            ticker="TEST", company="Test Corp", quarter="FY2026 Q1",
            metrics=metrics, generated_at="2026-05-26T12:00:00Z",
            company_overview=None, scoring=None,
        )
        vs = result["valuation"]
        assert vs.pe_forward == 28.4
        assert vs.pe_forward_display == "28.4x"
        assert vs.pe_trailing == 31.2
        assert vs.pe_trailing_display == "31.2x"

    def test_all_models_with_none_metrics(self):
        """Graceful handling when metrics has no data."""
        metrics = _minimal_metrics(
            eps_actual=None, eps_estimate=None, eps_vs_estimate=None,
            eps_yoy=None, revenue_actual=None, revenue_estimate=None,
            revenue_yoy=None, gross_margin=None, operating_margin=None,
            net_margin=None, free_cash_flow=None, pe_forward=None,
            pe_trailing=None,
        )
        result = _build_v27_models(
            ticker="TEST", company="Test Corp", quarter="FY2026 Q1",
            metrics=metrics, generated_at="2026-05-26T12:00:00Z",
            company_overview=None, scoring=None,
        )
        # No exceptions
        fm = result["financial_metrics"]
        assert fm.eps_actual is None
        assert fm.revenue_actual is None
        assert fm.gross_margin is None


# ── Tests: build_earnings_deep_dive_report integration ───────────────────────


class TestBuildReportV27Integration:
    """Integration tests: build_earnings_deep_dive_report → V2.7 models."""

    def test_report_has_v27_fields_with_company_overview(self):
        metrics = _minimal_metrics()
        ov = _minimal_company_overview()
        report = build_earnings_deep_dive_report(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            language="en",
            section_analysis={},
            company_overview=ov,
        )
        assert report.executive_snapshot is not None
        assert report.financial_metrics is not None
        assert report.valuation is not None
        # These are minimal but present
        assert report.valuation_context is not None
        assert report.peer_benchmark is not None
        assert report.data_quality is not None

    def test_report_without_company_overview(self):
        metrics = _minimal_metrics()
        report = build_earnings_deep_dive_report(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            language="en",
            section_analysis={},
            company_overview=None,
        )
        # Models still created but with less data
        assert report.executive_snapshot is not None
        assert report.executive_snapshot.market_cap is None
        assert report.financial_metrics is not None
        assert report.financial_metrics.eps_actual == 0.67

    def test_report_with_ticker_uppercase_normalization(self):
        metrics = _minimal_metrics()
        report = build_earnings_deep_dive_report(
            ticker="test",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            language="en",
            section_analysis={},
            company_overview=None,
        )
        assert report.ticker == "TEST"
        assert report.executive_snapshot.ticker == "TEST"


# ── Tests: Full pipeline → V2.7 → PDF ───────────────────────────────────────


class TestV27PipelineToPdf:
    """End-to-end: report with V2.7 models → PDF rendering."""

    @pytest.fixture(autouse=True)
    def _check_fitz(self):
        pytest.importorskip("fitz")

    def test_pdf_renders_with_v27_models(self):
        """PDF generation succeeds with V2.7 models populated."""
        metrics = _minimal_metrics()
        ov = _minimal_company_overview()
        report = build_earnings_deep_dive_report(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            language="en",
            section_analysis={},
            company_overview=ov,
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "test_v27.pdf")
            result = render_earnings_deep_dive_pdf(report, pdf_path)
            assert result == pdf_path
            assert os.path.exists(pdf_path)
            assert os.path.getsize(pdf_path) > 1000  # non-trivial PDF

            # Verify PDF content
            import fitz
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text()
            doc.close()

            # Executive Snapshot content
            assert "Test Corp" in full_text
            assert "Technology" in full_text
            assert "$2.80T" in full_text
            # Financial Metrics content
            assert "EPS" in full_text
            assert "Revenue" in full_text
            # Valuation content
            assert "P/E" in full_text or "PE" in full_text

    def test_pdf_without_v27_company_overview(self):
        """PDF renders correctly even without company_overview."""
        metrics = _minimal_metrics()
        report = build_earnings_deep_dive_report(
            ticker="TEST",
            company="Test Corp",
            quarter="FY2026 Q1",
            metrics=metrics,
            language="en",
            section_analysis={},
            company_overview=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "test_v27_no_ov.pdf")
            result = render_earnings_deep_dive_pdf(report, pdf_path)
            assert result == pdf_path
            assert os.path.exists(pdf_path)
            assert os.path.getsize(pdf_path) > 1000

            import fitz
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text()
            doc.close()

            # Still has company name (from basic report data)
            assert "Test Corp" in full_text
            # Financial data still present
            assert "EPS" in full_text
            # Executive snapshot present but with less data
            assert report.executive_snapshot is not None
            assert report.executive_snapshot.market_cap is None
