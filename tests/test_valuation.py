"""Unit tests for backend/valuation.py — pure arithmetic, no network.

All tests run with the project venv so yfinance and other deps are available.
Run:  cd /home/ced/codex-projects/stock-analysis-pipeline && .venv/bin/python -m pytest tests/test_valuation.py -v
"""

from __future__ import annotations

import math

import pytest

from backend.valuation import (
    calculate_all_ratios,
    calculate_enterprise_value,
    calculate_ev_ebitda,
    calculate_ev_sales,
    calculate_fcf_yield,
    calculate_pe_ttm,
    calculate_price_to_fcf,
    calculate_ps_ttm,
)


# ═════════════════════════════════════════════════════════════
#  P/E TTM
# ═════════════════════════════════════════════════════════════


class TestCalculatePE:
    def test_normal(self):
        assert calculate_pe_ttm(150.0, 5.0) == pytest.approx(30.0)

    def test_price_none(self):
        assert calculate_pe_ttm(None, 5.0) is None

    def test_eps_none(self):
        assert calculate_pe_ttm(150.0, None) is None

    def test_eps_zero(self):
        assert calculate_pe_ttm(150.0, 0.0) is None

    def test_eps_negative(self):
        assert calculate_pe_ttm(150.0, -2.0) is None

    def test_price_zero_eps_positive(self):
        # Price 0 with positive EPS → P/E = 0 (valid edge case)
        assert calculate_pe_ttm(0.0, 5.0) == 0.0


# ═════════════════════════════════════════════════════════════
#  P/S TTM
# ═════════════════════════════════════════════════════════════


class TestCalculatePS:
    def test_normal(self):
        assert calculate_ps_ttm(150.0, 30.0) == pytest.approx(5.0)

    def test_revenue_per_share_none(self):
        assert calculate_ps_ttm(150.0, None) is None

    def test_revenue_zero(self):
        assert calculate_ps_ttm(150.0, 0.0) is None


# ═════════════════════════════════════════════════════════════
#  Price / FCF
# ═════════════════════════════════════════════════════════════


class TestCalculatePriceToFCF:
    def test_normal(self):
        assert calculate_price_to_fcf(200.0, 10.0) == pytest.approx(20.0)

    def test_fcf_none(self):
        assert calculate_price_to_fcf(200.0, None) is None

    def test_fcf_zero(self):
        assert calculate_price_to_fcf(200.0, 0.0) is None

    def test_price_zero(self):
        assert calculate_price_to_fcf(0.0, 10.0) == 0.0


# ═════════════════════════════════════════════════════════════
#  FCF Yield
# ═════════════════════════════════════════════════════════════


class TestCalculateFCFYield:
    def test_normal(self):
        # $10 FCF/share on $200 stock → 5% yield
        result = calculate_fcf_yield(10.0, 200.0)
        assert result == pytest.approx(0.05)

    def test_fcf_none(self):
        assert calculate_fcf_yield(None, 200.0) is None

    def test_price_none(self):
        assert calculate_fcf_yield(10.0, None) is None

    def test_price_zero(self):
        assert calculate_fcf_yield(10.0, 0.0) is None

    def test_fcf_zero(self):
        assert calculate_fcf_yield(0.0, 200.0) == 0.0


# ═════════════════════════════════════════════════════════════
#  Enterprise Value
# ═════════════════════════════════════════════════════════════


class TestCalculateEnterpriseValue:
    def test_all_provided(self):
        # Market cap 500B, debt 50B, cash 30B → EV = 520B
        assert calculate_enterprise_value(500e9, 50e9, 30e9) == pytest.approx(520e9)

    def test_debt_none_defaults_to_zero(self):
        assert calculate_enterprise_value(500e9, None, 30e9) == pytest.approx(470e9)

    def test_cash_none_defaults_to_zero(self):
        assert calculate_enterprise_value(500e9, 50e9, None) == pytest.approx(550e9)

    def test_market_cap_none(self):
        assert calculate_enterprise_value(None, 50e9, 30e9) is None

    def test_market_cap_zero(self):
        # Unusual but valid — EV can be negative (cash > market cap + debt)
        assert calculate_enterprise_value(0.0, 10e9, 0.0) == pytest.approx(10e9)

    def test_negative_ev(self):
        # Company with more cash than market cap + debt
        ev = calculate_enterprise_value(100e6, 50e6, 200e6)
        assert ev == pytest.approx(-50e6)


# ═════════════════════════════════════════════════════════════
#  EV / Sales
# ═════════════════════════════════════════════════════════════


class TestCalculateEVSales:
    def test_normal(self):
        assert calculate_ev_sales(520e9, 100e9) == pytest.approx(5.2)

    def test_ev_none(self):
        assert calculate_ev_sales(None, 100e9) is None

    def test_revenue_none(self):
        assert calculate_ev_sales(520e9, None) is None

    def test_revenue_zero(self):
        assert calculate_ev_sales(520e9, 0.0) is None


# ═════════════════════════════════════════════════════════════
#  EV / EBITDA
# ═════════════════════════════════════════════════════════════


class TestCalculateEVEBITDA:
    def test_normal(self):
        assert calculate_ev_ebitda(520e9, 40e9) == pytest.approx(13.0)

    def test_ebitda_none(self):
        assert calculate_ev_ebitda(520e9, None) is None

    def test_ebitda_zero(self):
        assert calculate_ev_ebitda(520e9, 0.0) is None

    def test_ebitda_negative(self):
        assert calculate_ev_ebitda(520e9, -5e9) is None


# ═════════════════════════════════════════════════════════════
#  Batch — calculate_all_ratios
# ═════════════════════════════════════════════════════════════


class TestCalculateAllRatios:
    def test_all_present(self):
        result = calculate_all_ratios(
            price=150.0,
            eps_ttm=5.0,
            revenue_per_share=30.0,
            fcf_per_share=10.0,
            market_cap=500e9,
            total_debt=50e9,
            cash=30e9,
            revenue=100e9,
            ebitda=40e9,
        )
        assert result["pe_ttm"] == pytest.approx(30.0)
        assert result["ps_ttm"] == pytest.approx(5.0)
        assert result["price_to_fcf"] == pytest.approx(15.0)
        assert result["fcf_yield"] == pytest.approx(10.0 / 150.0)
        assert result["enterprise_value"] == pytest.approx(520e9)
        assert result["ev_sales"] == pytest.approx(5.2)
        assert result["ev_ebitda"] == pytest.approx(13.0)

    def test_all_none(self):
        result = calculate_all_ratios(price=None)
        for key in result:
            assert result[key] is None, f"Expected None for {key}, got {result[key]}"

    def test_partial(self):
        result = calculate_all_ratios(price=150.0, eps_ttm=5.0)
        assert result["pe_ttm"] == pytest.approx(30.0)
        assert result["ps_ttm"] is None  # no revenue_per_share
        assert result["price_to_fcf"] is None  # no fcf_per_share
        assert result["enterprise_value"] is None  # no market_cap

    def test_returns_dict_keys(self):
        result = calculate_all_ratios(price=100.0)
        expected_keys = {
            "pe_ttm", "ps_ttm", "price_to_fcf", "fcf_yield",
            "enterprise_value", "ev_sales", "ev_ebitda",
        }
        assert set(result.keys()) == expected_keys


# ═════════════════════════════════════════════════════════════
#  Edge Cases
# ═════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_very_small_numbers(self):
        # Penny stock ($0.01) with micro EPS ($0.001)
        pe = calculate_pe_ttm(0.01, 0.001)
        assert pe == pytest.approx(10.0)

    def test_very_large_numbers(self):
        # Trillion-dollar company
        pe = calculate_pe_ttm(300.0, 10.0)
        assert pe == pytest.approx(30.0)

    def test_float_precision(self):
        # Ensure float arithmetic doesn't introduce None
        result = calculate_pe_ttm(100.0, 3.33333)
        assert result is not None
        assert math.isfinite(result)
