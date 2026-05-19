"""Tests for the scoring engine."""
import pytest
from backend.scorer import score_ticker, Scoring, _scale_to_8, _scale_to_3


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
        assert s.total >= 23  # strong but expensive
        # growth (growth + momentum) should be high
        assert s.growth >= 6
        # Financial health (profitability + financial_strength) should be high
        assert s.financial_health >= 6
        assert s.decision() in ("BUY", "HOLD")

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
        assert s.total >= 20
        # Financial health should be high (good margins + decent balance sheet)
        assert s.financial_health >= 6

    def test_struggling_value(self):
        """Legacy retailer: low growth, low margins, cheap.
        Cheap valuation (P/E=10→8) compensates for poor fundamentals, giving a low-HOLD."""
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
        # Low growth/margins but cheap valuation pushes it to ~24
        assert 20 <= s.total <= 28
        assert s.decision() == "HOLD"

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
        assert 8 <= s.total <= 22  # neutral-ish
        assert isinstance(s, Scoring)

    def test_raw_subscores_preserved(self):
        """score_ticker() must preserve all 8 raw sub-scores in _raw_subscores."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.30,
                "revenue_annual_growth": 0.25,
                "gross_margin": 0.60,
                "operating_margin": 0.40,
                "net_income": 1e9,
                "free_cash_flow": 5e8,
                "net_debt": -1e8,
                "guidance_official": 0.15,
            },
            "valuation": {
                "pe_current": 25,
                "pe_forward": 22,
                "peg_ratio": 1.5,
            },
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1e12,
            "price": 150,
            "52w_high": 155,
        }
        s = score_ticker(data)
        raw = s._raw_subscores
        assert len(raw) == 8
        for key in ("growth", "profitability", "financial_strength", "moat",
                     "management", "valuation_risk", "geopolitical_risk", "business_momentum"):
            assert key in raw, f"Missing raw sub-score: {key}"
            assert 1 <= raw[key] <= 5, f"{key} = {raw[key]}, expected 1-5"

    def test_canonical_mapping_consistency(self):
        """Verify the 8→6 mapping matches the spec."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.30,
                "revenue_annual_growth": 0.25,
                "gross_margin": 0.60,
                "operating_margin": 0.40,
                "net_income": 1e9,
                "free_cash_flow": 5e8,
                "net_debt": -1e8,
                "guidance_official": 0.15,
            },
            "valuation": {
                "pe_current": 25,
                "pe_forward": 22,
                "peg_ratio": 1.5,
            },
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1e12,
            "price": 150,
            "52w_high": 155,
        }
        s = score_ticker(data)
        raw = s._raw_subscores

        # Financial Health = profitability + financial_strength (0–10)
        assert s.financial_health == raw["profitability"] + raw["financial_strength"]
        assert 0 <= s.financial_health <= 10

        # Growth = growth + business_momentum (0–10)
        assert s.growth == raw["growth"] + raw["business_momentum"]
        assert 0 <= s.growth <= 10

        # Valuation = scaled val_risk (0–8)
        assert s.valuation == _scale_to_8(raw["valuation_risk"])
        assert 0 <= s.valuation <= 8

        # Management = direct (0–5)
        assert s.management == raw["management"]
        assert 0 <= s.management <= 5

        # Moat = capped at 4
        assert s.moat == min(raw["moat"], 4)
        assert 0 <= s.moat <= 4

        # Sentiment = scaled geo (0–3)
        assert s.sentiment == _scale_to_3(raw["geopolitical_risk"])
        assert 0 <= s.sentiment <= 3

        # Total = sum of 6 canonical
        assert s.total == s.financial_health + s.growth + s.valuation + s.management + s.moat + s.sentiment
        assert 0 <= s.total <= 40


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
