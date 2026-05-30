"""
Tests for V2.4 Valuation Context Engine.

Covers all 7 functions from services.valuation_context with
edge cases for N/A, negative values, zero growth, and
partial data scenarios.

Growth rates are passed as decimals (0.15 = 15%) and converted
internally to percentage points for ratio computation.

Acceptance criteria tests:
  1. test_peg_ttm_calculable / test_peg_ttm_na_if_eps_growth_zero
  2. test_ps_vs_growth_strong / test_ps_vs_growth_weak
  3. test_ev_ebitda_vs_growth_supported
  4. test_p_fcf_vs_growth / test_p_fcf_na_if_negative
  5. test_fcf_yield_context
  6. test_valuation_summary_card_all_signals
  7. test_valuation_summary_card_partial_data
  8. test_no_recommendation_wording
"""

import pytest
from services.valuation_context import (
    calculate_peg_ttm,
    calculate_sales_multiple_vs_growth,
    calculate_ev_ebitda_vs_ebitda_growth,
    calculate_price_to_fcf_vs_fcf_growth,
    calculate_fcf_yield_context,
    calculate_valuation_support,
    calculate_valuation_context_summary,
)


# ═══════════════════════════════════════════════════════════════
#  1. PEG TTM
# ═══════════════════════════════════════════════════════════════


class TestPegTtm:
    def test_peg_ttm_calculable(self):
        """PE=20, EPS growth=15% → PEG = 20/15 = 1.33 → fair_range."""
        result = calculate_peg_ttm(pe_ttm=20.0, eps_growth=0.15)
        assert result["peg_ratio"] == pytest.approx(1.33, abs=0.01)
        assert result["level"] == "fair_range"
        assert "fairly valued" in result["label"].lower()

    def test_peg_ttm_below_1(self):
        """PE=12, EPS growth=25% → PEG = 12/25 = 0.48 → below_1."""
        result = calculate_peg_ttm(pe_ttm=12.0, eps_growth=0.25)
        assert result["peg_ratio"] == pytest.approx(0.48, abs=0.01)
        assert result["level"] == "below_1"
        assert "growth supports" in result["label"].lower()

    def test_peg_ttm_above_2(self):
        """PE=50, EPS growth=8% → PEG = 50/8 = 6.25 → above_2."""
        result = calculate_peg_ttm(pe_ttm=50.0, eps_growth=0.08)
        assert result["peg_ratio"] == pytest.approx(6.25, abs=0.01)
        assert result["level"] == "above_2"
        assert "exceeds growth" in result["label"].lower()

    def test_peg_ttm_na_if_eps_growth_zero(self):
        """EPS growth = 0 → N/A."""
        result = calculate_peg_ttm(pe_ttm=20.0, eps_growth=0.0)
        assert result["peg_ratio"] is None
        assert result["level"] == "n/a"
        assert "zero" in result["label"].lower()

    def test_peg_ttm_na_if_eps_growth_negative(self):
        """EPS growth negative → N/A."""
        result = calculate_peg_ttm(pe_ttm=20.0, eps_growth=-0.05)
        assert result["peg_ratio"] is None
        assert result["level"] == "n/a"
        assert "negative" in result["label"].lower()

    def test_peg_ttm_na_if_missing(self):
        """Missing pe_ttm or eps_growth → N/A."""
        assert calculate_peg_ttm(None, 0.15)["level"] == "n/a"
        assert calculate_peg_ttm(20.0, None)["level"] == "n/a"
        assert calculate_peg_ttm(None, None)["level"] == "n/a"

    def test_peg_ttm_nvda_like(self):
        """NVDA-like: PE=32.38, EPS growth=214.5% → PEG = 32.38/214.5 = 0.15 → below_1.
        
        Regression test for Nami's correction: PEG was showing 0.66 (Yahoo Finance
        forward-looking pegRatio using 5yr expected growth). The correct trailing
        PEG uses trailing P/E and trailing EPS growth for internal consistency.
        """
        result = calculate_peg_ttm(pe_ttm=32.38, eps_growth=2.145)
        assert result["peg_ratio"] == pytest.approx(0.15, abs=0.01)
        assert result["level"] == "below_1"
        assert "growth supports" in result["label"].lower()


# ═══════════════════════════════════════════════════════════════
#  2. P/S vs Revenue Growth
# ═══════════════════════════════════════════════════════════════


class TestPsVsGrowth:
    def test_ps_vs_growth_strong(self):
        """P/S=3.0, revenue_growth=40% → 3.0/40=0.075 → strong (< 1.5)."""
        result = calculate_sales_multiple_vs_growth(ps_ttm=3.0, revenue_growth=0.40)
        assert result["level"] == "strong"
        assert result["ratio"] == 0.1

    def test_ps_vs_growth_moderate(self):
        """P/S=15.0, revenue_growth=8% → 15/8=1.875 → moderate."""
        result = calculate_sales_multiple_vs_growth(ps_ttm=15.0, revenue_growth=0.08)
        assert result["level"] == "moderate"
        assert result["ratio"] == 1.9

    def test_ps_vs_growth_weak(self):
        """P/S=20.0, revenue_growth=5% → 20/5=4.0 → weak (> 3.0)."""
        result = calculate_sales_multiple_vs_growth(ps_ttm=20.0, revenue_growth=0.05)
        assert result["level"] == "weak"
        assert result["ratio"] == 4.0
        assert "weakly supports" in result["label"].lower()

    def test_ps_vs_growth_na_zero_growth(self):
        """Revenue growth = 0 → N/A."""
        result = calculate_sales_multiple_vs_growth(ps_ttm=5.0, revenue_growth=0.0)
        assert result["level"] == "n/a"

    def test_ps_vs_growth_na_missing(self):
        """Missing data → N/A."""
        assert calculate_sales_multiple_vs_growth(None, 0.10)["level"] == "n/a"
        assert calculate_sales_multiple_vs_growth(5.0, None)["level"] == "n/a"


# ═══════════════════════════════════════════════════════════════
#  3. EV/EBITDA vs EBITDA Growth
# ═══════════════════════════════════════════════════════════════


class TestEvEbitdaVsGrowth:
    def test_ev_ebitda_vs_growth_strong(self):
        """EV/EBITDA=10, growth=30% → 10/30=0.33 → strong."""
        result = calculate_ev_ebitda_vs_ebitda_growth(
            ev_ebitda=10.0, ebitda_growth=0.30
        )
        assert result["level"] == "strong"
        assert result["ratio"] == 0.3

    def test_ev_ebitda_vs_growth_moderate(self):
        """EV/EBITDA=20, growth=8% → 20/8=2.5 → moderate."""
        result = calculate_ev_ebitda_vs_ebitda_growth(
            ev_ebitda=20.0, ebitda_growth=0.08
        )
        assert result["level"] == "moderate"
        assert result["ratio"] == 2.5

    def test_ev_ebitda_vs_growth_weak(self):
        """EV/EBITDA=30, growth=5% → 30/5=6.0 → weak."""
        result = calculate_ev_ebitda_vs_ebitda_growth(
            ev_ebitda=30.0, ebitda_growth=0.05
        )
        assert result["level"] == "weak"
        assert result["ratio"] == 6.0

    def test_ev_ebitda_vs_growth_na_missing(self):
        """Missing data → N/A."""
        assert (
            calculate_ev_ebitda_vs_ebitda_growth(None, 0.10)["level"] == "n/a"
        )
        assert (
            calculate_ev_ebitda_vs_ebitda_growth(10.0, None)["level"] == "n/a"
        )


# ═══════════════════════════════════════════════════════════════
#  4. P/FCF vs FCF Growth
# ═══════════════════════════════════════════════════════════════


class TestPFcfVsGrowth:
    def test_p_fcf_vs_growth_strong(self):
        """P/FCF=15, growth=25% → 15/25=0.6 → strong."""
        result = calculate_price_to_fcf_vs_fcf_growth(
            p_fcf=15.0, fcf_growth=0.25
        )
        assert result["level"] == "strong"
        assert result["ratio"] == 0.6

    def test_p_fcf_vs_growth_weak(self):
        """P/FCF=40, growth=5% → 40/5=8.0 → weak."""
        result = calculate_price_to_fcf_vs_fcf_growth(
            p_fcf=40.0, fcf_growth=0.05
        )
        assert result["level"] == "weak"
        assert result["ratio"] == 8.0

    def test_p_fcf_na_if_negative_fcf(self):
        """P/FCF <= 0 → N/A (negative FCF, not meaningful)."""
        result = calculate_price_to_fcf_vs_fcf_growth(
            p_fcf=-5.0, fcf_growth=0.10
        )
        assert result["level"] == "n/a"
        assert "FCF is negative" in result["label"]

    def test_p_fcf_na_if_zero_growth(self):
        """FCF growth = 0 → N/A."""
        result = calculate_price_to_fcf_vs_fcf_growth(
            p_fcf=20.0, fcf_growth=0.0
        )
        assert result["level"] == "n/a"

    def test_p_fcf_na_missing(self):
        """Missing data → N/A."""
        assert (
            calculate_price_to_fcf_vs_fcf_growth(None, 0.10)["level"] == "n/a"
        )
        assert (
            calculate_price_to_fcf_vs_fcf_growth(20.0, None)["level"] == "n/a"
        )


# ═══════════════════════════════════════════════════════════════
#  5. FCF Yield Context
# ═══════════════════════════════════════════════════════════════


class TestFcfYieldContext:
    def test_fcf_yield_strong(self):
        """FCF Yield = 7% → strong."""
        result = calculate_fcf_yield_context(0.07)
        assert result["level"] == "strong"
        assert result["fcf_yield"] == 0.07
        assert "strong" in result["label"].lower()

    def test_fcf_yield_moderate(self):
        """FCF Yield = 4% → moderate."""
        result = calculate_fcf_yield_context(0.04)
        assert result["level"] == "moderate"
        assert "moderate" in result["label"].lower()

    def test_fcf_yield_weak(self):
        """FCF Yield = 1% → weak."""
        result = calculate_fcf_yield_context(0.01)
        assert result["level"] == "weak"
        assert "weak" in result["label"].lower()

    def test_fcf_yield_negative(self):
        """FCF Yield = -3% → negative."""
        result = calculate_fcf_yield_context(-0.03)
        assert result["level"] == "negative"
        assert "negative" in result["label"].lower()

    def test_fcf_yield_na(self):
        """FCF Yield = None → n/a."""
        result = calculate_fcf_yield_context(None)
        assert result["level"] == "n/a"
        assert result["fcf_yield"] is None

    def test_fcf_yield_boundary_5pct(self):
        """FCF Yield = 5% exactly — boundary case."""
        result = calculate_fcf_yield_context(0.05)
        # 0.05 is NOT > FCF_YIELD_STRONG (0.05), so falls to moderate
        assert result["level"] == "moderate"

    def test_fcf_yield_boundary_2pct(self):
        """FCF Yield = 2% exactly — boundary case."""
        result = calculate_fcf_yield_context(0.02)
        assert result["level"] == "moderate"


# ═══════════════════════════════════════════════════════════════
#  6. Valuation Support (aggregate)
# ═══════════════════════════════════════════════════════════════


class TestValuationSupport:
    def test_all_supportive(self):
        """All signals strong → dominant supportive."""
        result = calculate_valuation_support(
            peg_signal={"level": "below_1"},
            ps_vs_growth={"level": "strong"},
            ev_ebitda_vs_growth={"level": "strong"},
            p_fcf_vs_growth={"level": "strong"},
            fcf_yield_signal={"level": "strong"},
        )
        assert result["support"] == 5
        assert result["concern"] == 0
        assert result["dominant"] == "supportive"

    def test_mixed_signals(self):
        """Mix of support and concern → dominant mixed (tie between extremes)."""
        result = calculate_valuation_support(
            peg_signal={"level": "above_2"},
            ps_vs_growth={"level": "strong"},
            ev_ebitda_vs_growth={"level": "strong"},
            p_fcf_vs_growth={"level": "weak"},
            fcf_yield_signal={"level": "weak"},
        )
        # support: 2 (strong, strong), neutral: 0, concern: 3 (above_2, weak, weak)
        assert result["support"] == 2
        assert result["neutral"] == 0
        assert result["concern"] == 3
        assert result["dominant"] == "concerning"

    def test_dead_heat_mixed(self):
        """Tie between support and concern (2 each, 0 neutral) → mixed."""
        result = calculate_valuation_support(
            peg_signal={"level": "below_1"},
            ps_vs_growth={"level": "strong"},
            ev_ebitda_vs_growth={"level": "weak"},
            p_fcf_vs_growth={"level": "weak"},
        )
        # support: 2 (below_1, strong), neutral: 0, concern: 2 (weak, weak)
        assert result["support"] == 2
        assert result["concern"] == 2
        assert result["dominant"] == "mixed"

    def test_all_na(self):
        """No signals with data → insufficient_data."""
        result = calculate_valuation_support(
            peg_signal={"level": "n/a"},
            ps_vs_growth={"level": "n/a"},
        )
        assert result["total_signals"] == 0
        assert result["dominant"] == "insufficient_data"

    def test_some_none_some_na(self):
        """Mix of None and n/a → insufficient_data."""
        result = calculate_valuation_support(
            peg_signal=None,
            ps_vs_growth={"level": "n/a"},
            ev_ebitda_vs_growth=None,
        )
        assert result["total_signals"] == 0
        assert result["dominant"] == "insufficient_data"


# ═══════════════════════════════════════════════════════════════
#  7. Valuation Context Summary Card
# ═══════════════════════════════════════════════════════════════


class TestValuationContextSummary:
    def test_summary_all_signals_strong(self):
        """All 5 signals strong → growth_supported, high confidence."""
        summary = calculate_valuation_context_summary(
            peg_signal=calculate_peg_ttm(12.0, 0.25),          # PEG 0.48 below_1
            ps_vs_growth=calculate_sales_multiple_vs_growth(3.0, 0.40),  # strong
            ev_ebitda_vs_growth=calculate_ev_ebitda_vs_ebitda_growth(10.0, 0.30),  # strong
            p_fcf_vs_growth=calculate_price_to_fcf_vs_fcf_growth(15.0, 0.25),  # strong
            fcf_yield_signal=calculate_fcf_yield_context(0.07),  # strong
        )

        assert summary["valuation_level"] == "growth_supported"
        assert summary["growth_support"] == "strong"
        assert summary["profitability_support"] == "strong"
        assert summary["cashflow_support"] == "strong"
        assert summary["confidence"] == "high"
        assert summary["signals_available"] == 5
        assert summary["warnings"] == []

    def test_summary_all_signals_weak(self):
        """All signals weak → growth_lagging, warnings."""
        summary = calculate_valuation_context_summary(
            peg_signal=calculate_peg_ttm(80.0, 0.05),          # PEG 16.0 above_2
            ps_vs_growth=calculate_sales_multiple_vs_growth(20.0, 0.05),  # weak
            ev_ebitda_vs_growth=calculate_ev_ebitda_vs_ebitda_growth(30.0, 0.05),  # weak
            p_fcf_vs_growth=calculate_price_to_fcf_vs_fcf_growth(40.0, 0.05),  # weak
            fcf_yield_signal=calculate_fcf_yield_context(0.01),  # weak
        )

        assert summary["valuation_level"] == "growth_lagging"
        assert summary["growth_support"] == "weak"
        assert summary["profitability_support"] == "weak"
        assert summary["cashflow_support"] == "weak"
        assert summary["confidence"] == "high"
        assert len(summary["warnings"]) >= 4  # PEG, PS, EV/EBITDA, P/FCF

    def test_summary_partial_data(self):
        """Only 2 of 5 signals available → medium confidence."""
        summary = calculate_valuation_context_summary(
            peg_signal=calculate_peg_ttm(15.0, 0.20),          # PEG 0.75 below_1
            ps_vs_growth=calculate_sales_multiple_vs_growth(15.0, 0.08),  # 15/8=1.875 moderate
            ev_ebitda_vs_growth=None,
            p_fcf_vs_growth=None,
            fcf_yield_signal=None,
        )

        assert summary["valuation_level"] == "growth_supported"
        assert summary["growth_support"] == "moderate"
        assert summary["profitability_support"] == "strong"
        assert summary["cashflow_support"] == "n/a"
        assert summary["confidence"] == "medium"
        assert summary["signals_available"] == 2

    def test_summary_all_none(self):
        """No signals at all → insufficient_data, low confidence."""
        summary = calculate_valuation_context_summary(
            peg_signal=None,
            ps_vs_growth=None,
            ev_ebitda_vs_growth=None,
            p_fcf_vs_growth=None,
            fcf_yield_signal=None,
        )

        assert summary["valuation_level"] == "insufficient_data"
        assert summary["confidence"] == "low"
        assert summary["signals_available"] == 0
        assert len(summary["warnings"]) >= 1


# ═══════════════════════════════════════════════════════════════
#  8. No recommendation wording
# ═══════════════════════════════════════════════════════════════


class TestNoRecommendationWording:
    """Ensure no buy/sell/cheap/expensive wording appears in any output."""

    FORBIDDEN = ["buy", "sell", "cheap", "expensive", "overvalued", "undervalued"]

    def _check_no_forbidden(self, result: dict):
        """Recursively check dict values for forbidden words (case-insensitive)."""
        for value in result.values():
            if isinstance(value, str):
                lowered = value.lower()
                for forbidden in self.FORBIDDEN:
                    assert forbidden not in lowered, (
                        f"Forbidden word '{forbidden}' found in: {value}"
                    )
            elif isinstance(value, dict):
                self._check_no_forbidden(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        lowered = item.lower()
                        for forbidden in self.FORBIDDEN:
                            assert forbidden not in lowered, (
                                f"Forbidden word '{forbidden}' found in: {item}"
                            )

    def test_peg_ttm_no_recommendation(self):
        result = calculate_peg_ttm(20.0, 0.15)
        self._check_no_forbidden(result)

    def test_ps_vs_growth_no_recommendation(self):
        result = calculate_sales_multiple_vs_growth(10.0, 0.10)
        self._check_no_forbidden(result)

    def test_fcf_yield_no_recommendation(self):
        result = calculate_fcf_yield_context(0.06)
        self._check_no_forbidden(result)

    def test_summary_no_recommendation(self):
        summary = calculate_valuation_context_summary(
            peg_signal=calculate_peg_ttm(20.0, 0.15),
            ps_vs_growth=calculate_sales_multiple_vs_growth(15.0, 0.08),
            ev_ebitda_vs_growth=calculate_ev_ebitda_vs_ebitda_growth(20.0, 0.08),
            p_fcf_vs_growth=calculate_price_to_fcf_vs_fcf_growth(15.0, 0.20),
            fcf_yield_signal=calculate_fcf_yield_context(0.04),
        )
        self._check_no_forbidden(summary)

    def test_labels_no_recommendation(self):
        """Every label string in context signals must not contain forbidden words."""
        # Test all functions exhaustively
        funcs = [
            ("peg", calculate_peg_ttm(20.0, 0.15)),
            ("ps", calculate_sales_multiple_vs_growth(10.0, 0.10)),
            ("ev", calculate_ev_ebitda_vs_ebitda_growth(10.0, 0.30)),
            ("fcf", calculate_price_to_fcf_vs_fcf_growth(15.0, 0.25)),
            ("yield", calculate_fcf_yield_context(0.07)),
            ("yield_neg", calculate_fcf_yield_context(-0.03)),
            ("peg_na", calculate_peg_ttm(20.0, 0.0)),
            ("fcf_na", calculate_fcf_yield_context(None)),
        ]

        for name, result in funcs:
            label = result.get("label", "")
            lowered = str(label).lower()
            for forbidden in self.FORBIDDEN:
                assert forbidden not in lowered, (
                    f"[{name}] Forbidden '{forbidden}' in label: {label}"
                )
