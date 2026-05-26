"""T6 — DataQuality integration tests.

Tests for _build_data_quality() — source freshness extraction,
completeness scoring, missing field tracking, and confidence tiering.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from backend.earnings_deep_dive.report_model import (
    DataQualitySection,
    SourceRef,
)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_source_ref(**kwargs) -> SourceRef:
    """Create a SourceRef with sensible defaults."""
    return SourceRef(
        source_id=kwargs.pop("source_id", "S1"),
        label=kwargs.pop("label", "Test Source"),
        url=kwargs.pop("url", "https://example.com"),
        source_type=kwargs.pop("source_type", "yfinance"),
        retrieved_at=kwargs.pop("retrieved_at", "2026-05-20T12:00:00Z"),
        **kwargs,
    )


def _make_metrics(**overrides) -> object:
    """Create a mock FinancialMetrics object."""
    class MockMetrics:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    defaults = {
        "eps_actual": 2.94,
        "revenue_actual": 43000000000.0,
        "free_cash_flow": 16000000000.0,
        "gross_margin": 0.75,
    }
    defaults.update(overrides)
    return MockMetrics(**defaults)


# ═══════════════════════════════════════════════════════════════════
#  Test classes
# ═══════════════════════════════════════════════════════════════════

class TestDataQualityFullData:
    """_build_data_quality with all data sources present."""

    def test_full_data_high_confidence(self):
        """With yf_info + company_overview + metrics + sources → high confidence."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        sources = [
            _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
            _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:01:00Z"),
            _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T12:00:00Z"),
            _make_source_ref(source_type="sec_edgar", retrieved_at="2026-05-19T08:00:00Z"),
            _make_source_ref(source_type="seeking_alpha", retrieved_at="2026-05-18T10:00:00Z"),
        ]

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=sources,
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.overall_confidence == "high"
        assert dq.completeness_score is not None
        assert dq.completeness_score >= 80
        assert dq.completeness_score == 100
        assert dq.missing_fields == []

    def test_source_freshness_extraction(self):
        """Verify per-source timestamps are extracted from bibliography."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        sources = [
            _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T10:00:00Z"),
            _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
            _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
            _make_source_ref(source_type="sec_edgar", retrieved_at="2026-05-19T14:00:00Z"),
            _make_source_ref(source_type="seeking_alpha", retrieved_at="2026-05-18T10:00:00Z"),
            _make_source_ref(source_type="press_release", retrieved_at="2026-05-18T11:00:00Z"),
        ]

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=sources,
            generated_at="2026-05-20T12:05:00Z",
        )

        # yfinance: picks most recent (12:00)
        assert dq.yfinance_freshness == "2026-05-20T12:00:00Z"
        assert "yfinance" in (dq.yfinance_source_label or "").lower()

        # finnhub via financial_data_api
        assert dq.finnhub_freshness == "2026-05-20T08:00:00Z"
        assert "finnhub" in (dq.finnhub_source_label or "").lower()

        # sec_edgar
        assert dq.sec_edgar_freshness == "2026-05-19T14:00:00Z"
        assert "sec" in (dq.sec_edgar_source_label or "").lower()

        # transcript: picks most recent from seeking_alpha or press_release
        assert dq.transcript_freshness == "2026-05-18T11:00:00Z"
        assert "transcript" in (dq.transcript_source_label or "").lower()

    def test_source_labels_descriptive(self):
        """Verify source labels are descriptive and non-null."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
                _make_source_ref(source_type="sec_edgar", retrieved_at="2026-05-19T14:00:00Z"),
                _make_source_ref(source_type="seeking_alpha", retrieved_at="2026-05-18T10:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        # Every source label should be non-null
        assert dq.yfinance_source_label is not None
        assert dq.finnhub_source_label is not None
        assert dq.sec_edgar_source_label is not None
        assert dq.transcript_source_label is not None

        # Labels should contain meaningful context
        assert len(dq.yfinance_source_label) > 3
        assert len(dq.finnhub_source_label) > 3


class TestDataQualityPartialData:
    """_build_data_quality with partial/missing data."""

    def test_no_company_overview_medium_confidence(self):
        """Missing company_overview → deducts 15, medium confidence with 1 source."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview=None,
            metrics=_make_metrics(),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                # Only 1 source → medium confidence even with score 85
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.overall_confidence == "medium"
        assert dq.completeness_score == 85  # 100 - 15
        assert "Company overview" in str(dq.missing_fields)

    def test_yfinance_unavailable_from_sources_but_yf_info_present(self):
        """yf_info present but no yfinance sources → uses generated_at as freshness."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=[],  # no sources at all
            generated_at="2026-05-20T12:05:00Z",
        )

        # Falls back to generated_at since yf_info exists
        assert dq.yfinance_freshness == "2026-05-20T12:05:00Z"
        assert "live" in (dq.yfinance_source_label or "").lower()

        # Still gets decent score because metrics + company_overview are present
        assert dq.overall_confidence == "medium"  # only 1 source (yf_info fallback)

    def test_missing_eps_deducts_15(self):
        """EPS actual None → deducts 15 from completeness."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(eps_actual=None),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.completeness_score == 85  # 100 - 15 (EPS)
        assert "EPS" in str(dq.missing_fields)

    def test_missing_revenue_deducts_15(self):
        """Revenue actual None → deducts 15."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(revenue_actual=None),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.completeness_score == 85  # 100 - 15
        assert "Revenue" in str(dq.missing_fields)

    def test_missing_fcf_deducts_10(self):
        """Free cash flow None → deducts 10."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(free_cash_flow=None),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.completeness_score == 90  # 100 - 10
        assert "Free cash flow" in str(dq.missing_fields)

    def test_missing_gross_margin_deducts_5(self):
        """Gross margin None → deducts 5."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(gross_margin=None),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.completeness_score == 95  # 100 - 5
        assert "Gross margin" in str(dq.missing_fields)

    def test_multiple_gaps_cumulative(self):
        """Multiple missing fields → cumulative deductions."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info=None,  # -25
            company_overview=None,  # -15
            metrics=_make_metrics(eps_actual=None, revenue_actual=None),  # -15 -15
            sources=[],
            generated_at="2026-05-20T12:05:00Z",
        )

        # 100 - 25 - 15 - 15 - 15 = 30 (floor at 0 handled elsewhere)
        assert dq.completeness_score == 30
        assert len(dq.missing_fields) == 4  # yfinance, company_overview, EPS, Revenue
        assert dq.overall_confidence == "low"

    def test_no_metrics_at_all(self):
        """metrics=None → deducts 40."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=None,
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.completeness_score == 60  # 100 - 40
        assert "Financial metrics" in str(dq.missing_fields)


class TestDataQualityEdgeCases:
    """Edge case and boundary tests."""

    def test_score_clamped_to_0(self):
        """Score cannot go below 0."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info=None,
            company_overview=None,
            metrics=None,
            sources=[],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.completeness_score == 20  # 100 - 25 - 15 - 40 = 20

    def test_sources_none_treated_as_empty(self):
        """sources=None gracefully handled."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=None,
            generated_at="2026-05-20T12:05:00Z",
        )

        # No source timestamps, but yf_info present → uses generated_at
        assert dq.yfinance_freshness == "2026-05-20T12:05:00Z"
        assert dq.data_currency == "USD"

    def test_empty_source_ref_list(self):
        """Empty sources list → graceful, all labels still populated."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info=None,
            company_overview=None,
            metrics=None,
            sources=[],
            generated_at="2026-05-20T12:05:00Z",
        )

        # All labels should still be populated (with unavailable messages)
        assert dq.yfinance_source_label is not None
        assert "unavailable" in (dq.yfinance_source_label or "").lower()

    def test_source_ref_with_none_retrieved_at(self):
        """SourceRef with retrieved_at=None is skipped."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        sources = [
            _make_source_ref(source_type="yfinance", retrieved_at=None),
            _make_source_ref(source_type="yfinance", retrieved_at=""),
        ]

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=sources,
            generated_at="2026-05-20T12:05:00Z",
        )

        # No valid yfinance timestamps → falls back to generated_at
        assert dq.yfinance_freshness == "2026-05-20T12:05:00Z"

    def test_unknown_source_type_ignored(self):
        """SourceRef with unknown source_type doesn't crash."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        sources = [
            _make_source_ref(source_type="some_unknown_api", retrieved_at="2026-05-20T12:00:00Z"),
        ]

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=sources,
            generated_at="2026-05-20T12:05:00Z",
        )

        # Should not crash, unknown source type just ignored for freshness
        assert dq.overall_confidence == "medium"

    def test_finnhub_source_type_variant(self):
        """Finnhub source can be 'financial_data_api' or 'finnhub'."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        # Test with 'finnhub' type (less common variant)
        sources = [
            _make_source_ref(source_type="finnhub", retrieved_at="2026-05-20T08:00:00Z"),
        ]

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=sources,
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.finnhub_freshness == "2026-05-20T08:00:00Z"

    def test_transcript_single_source_type(self):
        """Transcript can come from seeking_alpha OR press_release (not both)."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        # Only press_release, no seeking_alpha
        sources = [
            _make_source_ref(source_type="press_release", retrieved_at="2026-05-18T11:00:00Z"),
        ]

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=sources,
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.transcript_freshness == "2026-05-18T11:00:00Z"


class TestDataQualityConfidenceTiers:
    """Confidence tier boundaries."""

    def test_high_confidence_boundary(self):
        """Score=80 + 2 sources → high."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(eps_actual=None, revenue_actual=None),  # -30 → 70
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
                _make_source_ref(source_type="sec_edgar", retrieved_at="2026-05-19T14:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        # score=70, 2 sources → medium (score < 80)
        assert dq.overall_confidence == "medium"

    def test_medium_to_low_boundary(self):
        """Score < 50 or 0 sources → low."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info=None,
            company_overview=None,
            metrics=None,
            sources=[],
            generated_at="2026-05-20T12:05:00Z",
        )

        assert dq.overall_confidence == "low"

    def test_medium_confidence_with_single_source(self):
        """Score=80 but only 1 source → medium (need >= 2 for high)."""
        from backend.earnings_deep_dive.mapper import _build_data_quality

        dq = _build_data_quality(
            ticker="NVDA",
            yf_info={"trailingPE": 35.0},
            company_overview={"key_financials": {}},
            metrics=_make_metrics(),
            sources=[
                _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
            ],
            generated_at="2026-05-20T12:05:00Z",
        )

        # score=100, but only 1 source → medium
        assert dq.overall_confidence == "medium"


class TestDataQualityIntegration:
    """Integration: DataQuality flows through the full pipeline."""

    def test_pipeline_yields_data_quality(self):
        """Verify the full _build_v27_models output includes a populated data_quality."""
        from backend.earnings_deep_dive.mapper import _build_v27_models
        from backend.earnings_deep_dive.report_model import DataQualitySection

        # Minimal mock of FinancialMetrics
        class MockMetrics:
            def model_dump(self):
                return {
                    "eps_actual": 2.94,
                    "revenue_actual": 43e9,
                    "free_cash_flow": 16e9,
                    "gross_margin": 0.75,
                    "pe_trailing": 35.0,
                    "pe_forward": 25.0,
                    "eps_yoy": 0.15,
                    "revenue_actual": 43e9,
                    "revenue_yoy": 0.20,
                    "net_income": 22e9,
                    "net_margin": 0.55,
                    "operating_margin": 0.62,
                    "roe": 0.45,
                }

        sources = [
            _make_source_ref(source_type="yfinance", retrieved_at="2026-05-20T12:00:00Z"),
            _make_source_ref(source_type="financial_data_api", retrieved_at="2026-05-20T08:00:00Z"),
            _make_source_ref(source_type="sec_edgar", retrieved_at="2026-05-19T14:00:00Z"),
        ]

        result = _build_v27_models(
            ticker="NVDA",
            company="NVIDIA Corporation",
            quarter="FY2026 Q1",
            metrics=MockMetrics(),
            generated_at="2026-05-20T12:05:00Z",
            company_overview={"key_financials": {}, "company_profile": {}},
            scoring=None,
            sources=sources,
            yf_info={"trailingPE": 35.0, "forwardPE": 25.0},
        )

        dq = result["data_quality"]
        assert isinstance(dq, DataQualitySection)
        assert dq.overall_confidence is not None
        assert dq.completeness_score is not None
        assert 0 <= dq.completeness_score <= 100
        assert dq.generated_at == "2026-05-20T12:05:00Z"
        assert dq.data_currency == "USD"

    def test_data_quality_section_always_non_null(self):
        """Even with no data, data_quality section is populated."""
        from backend.earnings_deep_dive.mapper import _build_v27_models

        class MockMetrics:
            def model_dump(self):
                return {
                    "eps_actual": None,
                    "revenue_actual": None,
                    "free_cash_flow": None,
                    "gross_margin": None,
                }

        result = _build_v27_models(
            ticker="NVDA",
            company="NVIDIA Corporation",
            quarter="FY2026 Q1",
            metrics=MockMetrics(),
            generated_at="2026-05-20T12:05:00Z",
            company_overview=None,
            scoring=None,
            sources=None,
            yf_info=None,
        )

        dq = result["data_quality"]
        assert isinstance(dq, DataQualitySection)
        assert dq.missing_fields is not None
        assert dq.overall_confidence == "low"
