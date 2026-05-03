"""Tests for the scoring engine."""
import pytest
from backend.scorer import score_ticker, Scoring


class TestScoreTicker:
    """Integration-style tests for the scorer with realistic data."""

    def test_high_growth_buy(self):
        """NVDA-like: strong growth, high margins, expensive but high score."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.78,
                "revenue_annual_growth": 0.65,
                "gross_margin": 0.75,
                "operating_margin": 0.55,
                "net_income": 6e10,
                "free_cash_flow": 3e10,
                "net_debt": -5e9,  # net cash
                "guidance_official": 0.30,
            },
            "valuation": {
                "pe_current": 45,
                "pe_forward": 30,
                "peg_ratio": 0.8,
            },
            "sector": "Technology",
            "industry": "Semiconductors",
            "market_cap": 2.5e12,
            "price": 130,
            "52w_high": 150,
        }
        s = score_ticker(data)
        assert s.total >= 28  # strong but expensive
        assert s.growth == 5
        assert s.profitability == 5
        assert "BUY" in s.decision() or "HOLD" in s.decision()

    def test_stable_big_tech(self):
        """MSFT-like: steady growth, excellent margins, reasonable PE."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.16,
                "revenue_annual_growth": 0.15,
                "gross_margin": 0.69,
                "operating_margin": 0.44,
                "net_income": 7e10,
                "free_cash_flow": 5e10,
                "net_debt": 1e10,
                "guidance_official": 0.12,
            },
            "valuation": {
                "pe_current": 33,
                "pe_forward": 28,
                "peg_ratio": 2.1,
            },
            "sector": "Technology",
            "industry": "Software—Infrastructure",
            "market_cap": 3.0e12,
            "price": 420,
            "52w_high": 440,
        }
        s = score_ticker(data)
        assert s.total >= 25
        assert s.profitability == 5

    def test_struggling_value(self):
        """Legacy retailer: low growth, low margins, cheap."""
        data = {
            "financials": {
                "revenue_yoy_growth": -0.02,
                "revenue_annual_growth": -0.01,
                "gross_margin": 0.25,
                "operating_margin": 0.04,
                "net_income": 1e9,
                "free_cash_flow": 5e8,
                "net_debt": 2e10,
                "guidance_official": None,
            },
            "valuation": {
                "pe_current": 10,
                "pe_forward": 9,
                "peg_ratio": None,
            },
            "sector": "Consumer Cyclical",
            "industry": "Retail",
            "market_cap": 2e10,
            "price": 50,
            "52w_high": 80,
        }
        s = score_ticker(data)
        assert s.total < 25
        assert "SELL" in s.decision() or "HOLD fragile" in s.decision()

    def test_all_none_data_returns_neutral(self):
        """Completely missing data should not crash and return a neutral score."""
        data = {
            "financials": {},
            "valuation": {},
            "sector": None,
            "industry": None,
            "market_cap": None,
            "price": None,
            "52w_high": None,
        }
        s = score_ticker(data)
        assert 10 <= s.total <= 25  # neutral-ish
        assert isinstance(s, Scoring)


class TestIndividualScoreFunctions:
    """Tests imported from scorer module for direct function testing."""

    def test_all_scores_in_range(self):
        """Every score must be between 1 and 5 inclusive."""
        from backend.scorer import (
            _score_growth, _score_profitability, _score_financial_strength,
            _score_moat, _score_management, _score_valuation,
            _score_geopolitical, _score_momentum
        )
        for fn, args in [
            (_score_growth, (0.30, 0.25)),
            (_score_profitability, (0.60, 0.40)),
            (_score_financial_strength, (1e9, 5e9, 2e9)),
            (_score_moat, ("Technology", 1e12, 0.65)),
            (_score_management, (0.15, 0.20, 0.18)),
            (_score_valuation, (25, 22, 1.5)),
            (_score_geopolitical, ("Technology", "Semiconductors")),
            (_score_momentum, (0.35, 150, 155)),
        ]:
            result = fn(*args)
            assert 1 <= result <= 5, f"{fn.__name__} returned {result}, expected 1-5"
