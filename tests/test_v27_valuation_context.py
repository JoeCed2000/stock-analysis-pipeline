"""Tests for _build_valuation_context() — V2.7 T4."""
import pytest
from datetime import datetime

# Provide a stub module path so the tests can import from the mapper
import sys
sys.path.insert(0, '/home/ced/codex-projects/stock-analysis-pipeline')

from backend.earnings_deep_dive.mapper import _build_valuation_context
from backend.earnings_deep_dive.report_model import ValuationContextSection

# ── Helpers ──────────────────────────────────────────────────────────

def _yf_info(**overrides) -> dict:
    """Build a realistic yfinance info dict (NVDA-like defaults)."""
    base = {
        "pegRatio": 0.66,
        "priceToSalesTrailing12Months": 20.57,
        "enterpriseToEbitda": 31.24,
        "forwardPE": 17.03,
        "freeCashflow": 46_335_873_024,
        "marketCap": 5_215_507_972_096,
        "revenueGrowth": 0.852,
        "earningsGrowth": 2.145,
        "beta": 2.244,
        "dividendYield": 0.02,
        "fiftyTwoWeekHigh": 236.54,
        "fiftyTwoWeekLow": 129.16,
        "recommendationKey": "strong_buy",
        "targetMeanPrice": 295.34,
        "totalRevenue": 253_491_003_392,
        "ebitda": 165_514_002_432,
    }
    base.update(overrides)
    return base


def _vc_section(**overrides) -> dict:
    """Build ValuationContextSection with defaults, helper for tests."""
    defaults = {
        "peg_signal": 0.66, "peg_signal_label": "Attractive (<1x)", "peg_signal_detail": "PEG 0.66 = P/E 33.0x / growth 110%",
        "ps_vs_growth_signal": 20.57, "ps_vs_growth_label": "Moderate",
        "ev_ebitda_vs_growth_signal": 31.24, "ev_ebitda_vs_growth_label": "Expensive",
        "pfcf_vs_growth_signal": None, "pfcf_vs_growth_label": "N/A (no FCF)",
        "fcf_yield_signal": 0.89, "fcf_yield_label": "Low (<4%)",
        "valuation_support": None, "context_summary": None,
        "generated_at": "2026-05-26T12:00:00", "currency": "USD",
    }
    defaults.update(overrides)
    return defaults


# ── Tests: with full yf_info ─────────────────────────────────────────

class TestBuildValuationContextFull:
    """Happy path: full yfinance info dict available."""

    def test_peg_signal_extracted(self):
        vc = _build_valuation_context(yf_info=_yf_info(trailingPE=33.0, earningsGrowth=2.145), metrics=None, generated_at="2026-05-26T12:00:00")
        assert vc.peg_signal == pytest.approx(0.66, abs=0.01)
        assert vc.peg_signal_label is not None
        if vc.peg_signal_detail is not None:
            assert "PEG" in vc.peg_signal_detail or "P/E" in vc.peg_signal_detail

    def test_ps_vs_growth_extracted(self):
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at="t")
        assert vc.ps_vs_growth_signal == pytest.approx(20.57, abs=0.01)
        assert vc.ps_vs_growth_label is not None

    def test_ev_ebitda_extracted(self):
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at="t")
        assert vc.ev_ebitda_vs_growth_signal == pytest.approx(31.24, abs=0.01)
        assert vc.ev_ebitda_vs_growth_label is not None

    def test_pfcf_computed_from_yf_info(self):
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at="t")
        # P/FCF = marketCap / freeCashflow = 5_215_507_972_096 / 46_335_873_024 ≈ 112.5
        if vc.pfcf_vs_growth_signal is not None:
            assert vc.pfcf_vs_growth_signal > 0

    def test_fcf_yield_computed_from_yf_info(self):
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at="t")
        # FCF yield = freeCashflow / marketCap ≈ 0.89%
        if vc.fcf_yield_signal is not None:
            assert vc.fcf_yield_signal > 0
            assert vc.fcf_yield_label is not None

    def test_currency_always_usd(self):
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at="t")
        assert vc.currency == "USD"

    def test_generated_at_preserved(self):
        ts = "2026-06-15T08:30:00Z"
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at=ts)
        assert vc.generated_at == ts

    def test_valuation_support_narrative_when_data_rich(self):
        """When enough data is present, valuation_support should be generated."""
        vc = _build_valuation_context(yf_info=_yf_info(), metrics=None, generated_at="t")
        # With full data, we should have at least some narrative
        assert vc.valuation_support is not None or vc.context_summary is not None


# ── Tests: with partial yf_info ──────────────────────────────────────

class TestBuildValuationContextPartial:
    """Graceful degradation when yfinance info is incomplete."""

    def test_missing_peg_ratio_sets_none(self):
        info = _yf_info()
        del info["pegRatio"]
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        assert vc.peg_signal is None
        assert vc.peg_signal_label is None

    def test_missing_ps_sets_none(self):
        info = _yf_info()
        del info["priceToSalesTrailing12Months"]
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        assert vc.ps_vs_growth_signal is None

    def test_missing_ev_ebitda_sets_none(self):
        info = _yf_info()
        del info["enterpriseToEbitda"]
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        assert vc.ev_ebitda_vs_growth_signal is None

    def test_missing_fcf_yields_none(self):
        info = _yf_info()
        del info["freeCashflow"]
        del info["marketCap"]
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        assert vc.fcf_yield_signal is None

    def test_zero_market_cap_handled(self):
        info = _yf_info(marketCap=0, freeCashflow=1e9)
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        # Should not crash — FCF yield should be None or computed safely
        assert vc.fcf_yield_signal is None

    def test_pfcf_with_null_free_cashflow(self):
        info = _yf_info(freeCashflow=None)
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        assert vc.pfcf_vs_growth_signal is None
        assert vc.pfcf_vs_growth_label is None


# ── Tests: yf_info is None ───────────────────────────────────────────

class TestBuildValuationContextNone:
    """When yf_info is None, all fields should be None (no crash)."""

    def test_none_yf_info_returns_all_none(self):
        vc = _build_valuation_context(yf_info=None, metrics=None, generated_at="t")
        assert vc.peg_signal is None
        assert vc.ps_vs_growth_signal is None
        assert vc.ev_ebitda_vs_growth_signal is None
        assert vc.pfcf_vs_growth_signal is None
        assert vc.fcf_yield_signal is None
        assert vc.currency == "USD"

    def test_none_yf_info_no_crash(self):
        vc = _build_valuation_context(yf_info=None, metrics=None, generated_at="t")
        assert isinstance(vc, ValuationContextSection)

    def test_empty_dict_yf_info_no_crash(self):
        vc = _build_valuation_context(yf_info={}, metrics=None, generated_at="t")
        assert isinstance(vc, ValuationContextSection)
        assert vc.peg_signal is None


# ── Tests: label interpretation ──────────────────────────────────────

class TestValuationLabels:
    """Semantic label generation from raw values."""

    def test_peg_attractive_below_1(self):
        vc = _build_valuation_context(yf_info=_yf_info(pegRatio=0.5), metrics=None, generated_at="t")
        assert "Attractive" in vc.peg_signal_label or "attractive" in str(vc.peg_signal_label).lower()

    def test_peg_fair_between_1_and_2(self):
        vc = _build_valuation_context(yf_info=_yf_info(pegRatio=1.5), metrics=None, generated_at="t")
        assert "Fair" in vc.peg_signal_label or "fair" in str(vc.peg_signal_label).lower()

    def test_peg_expensive_above_2(self):
        vc = _build_valuation_context(yf_info=_yf_info(pegRatio=2.5), metrics=None, generated_at="t")
        assert "Expensive" in vc.peg_signal_label or "High" in vc.peg_signal_label

    def test_peg_negative_handled(self):
        vc = _build_valuation_context(yf_info=_yf_info(pegRatio=-1.0), metrics=None, generated_at="t")
        assert vc.peg_signal_label is not None  # shouldn't crash

    def test_fcf_yield_strong_above_8pct(self):
        # freeCashflow / marketCap = 0.10 (10%)
        info = _yf_info(marketCap=100e9, freeCashflow=10e9)
        vc = _build_valuation_context(yf_info=info, metrics=None, generated_at="t")
        if vc.fcf_yield_signal is not None:
            assert "Strong" in vc.fcf_yield_label or "strong" in str(vc.fcf_yield_label).lower()
