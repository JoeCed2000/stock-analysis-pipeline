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

    def test_score_ticker_returns_6_canonical_fields(self):
        """score_ticker() must return exactly 6 canonical fields with correct ranges."""
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
        # Exactly 6 canonical fields
        fields = {
            "financial_health": s.financial_health,
            "growth": s.growth,
            "valuation": s.valuation,
            "management": s.management,
            "moat": s.moat,
            "sentiment": s.sentiment,
        }
        assert len(fields) == 6, f"Expected 6 canonical fields, got {len(fields)}"
        for name, value in fields.items():
            assert isinstance(value, int), f"{name} is {type(value).__name__}, expected int"
        assert 0 <= s.financial_health <= 10, f"financial_health={s.financial_health}"
        assert 0 <= s.growth <= 10, f"growth={s.growth}"
        assert 0 <= s.valuation <= 8, f"valuation={s.valuation}"
        assert 0 <= s.management <= 5, f"management={s.management}"
        assert 0 <= s.moat <= 4, f"moat={s.moat}"
        assert 0 <= s.sentiment <= 3, f"sentiment={s.sentiment}"

    def test_total_is_40_for_msft(self):
        """MSFT-like data: verify total equals sum of 6 canonical fields and is within 40 cap."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.16,
                "revenue_annual_growth": 0.15,
                "gross_margin": 0.69,
                "operating_margin": 0.44,
                "net_income": 9e10,
                "free_cash_flow": 6e10,
                "net_debt": -5e9,  # net cash
                "guidance_official": 0.15,
            },
            "valuation": {
                "pe_current": 33,
                "pe_forward": 28,
                "peg_ratio": 2.1,
            },
            "sector": "Technology",
            "industry": "Software—Infrastructure",
            "market_cap": 3.2e12,
            "price": 430,
            "52w_high": 445,
        }
        s = score_ticker(data)
        expected_total = (
            s.financial_health + s.growth + s.valuation +
            s.management + s.moat + s.sentiment
        )
        assert s.total == expected_total, (
            f"total={s.total} != sum of 6 fields={expected_total}"
        )
        assert 0 <= s.total <= 40, f"total={s.total} exceeds 40 cap"
        assert s.total >= 20, "MSFT should score well"

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


class TestDecisionBoundaries:
    """T5.1 — Decision boundaries: 17→SELL, 18→HOLD, 27→HOLD, 28→BUY."""

    # ── Direct Scoring model tests (exact total via constructor) ──

    def test_total_17_is_sell(self):
        """Exact boundary: total=17 → SELL."""
        s = Scoring(
            financial_health=4, growth=4, valuation=4,
            management=2, moat=2, sentiment=1,
        )
        assert s.total == 17
        assert s.decision() == "SELL"

    def test_total_18_is_hold(self):
        """Exact boundary: total=18 → HOLD (first HOLD value)."""
        s = Scoring(
            financial_health=4, growth=4, valuation=4,
            management=3, moat=2, sentiment=1,
        )
        assert s.total == 18
        assert s.decision() == "HOLD"

    def test_total_27_is_hold(self):
        """Exact boundary: total=27 → HOLD (last HOLD value)."""
        s = Scoring(
            financial_health=7, growth=7, valuation=5,
            management=4, moat=3, sentiment=1,
        )
        assert s.total == 27
        assert s.decision() == "HOLD"

    def test_total_28_is_buy(self):
        """Exact boundary: total=28 → BUY (first BUY value)."""
        s = Scoring(
            financial_health=7, growth=7, valuation=5,
            management=4, moat=3, sentiment=2,
        )
        assert s.total == 28
        assert s.decision() == "BUY"

    # ── score_ticker real-data boundaries ──

    def test_score_ticker_produces_sell_below_18(self):
        """Realistic weak company: total should be < 18 → SELL."""
        data = {
            "financials": {
                "revenue_yoy_growth": -0.10,
                "revenue_annual_growth": -0.05,
                "gross_margin": 0.15,
                "operating_margin": -0.02,
                "net_income": -5e8,
                "free_cash_flow": -1e8,
                "net_debt": 5e10,
                "guidance_official": -0.05,
            },
            "valuation": {
                "pe_current": 80,
                "pe_forward": 70,
                "peg_ratio": None,
            },
            "sector": "Energy",
            "industry": "Oil & Gas",
            "market_cap": 5e9,
            "price": 10,
            "52w_high": 30,
        }
        s = score_ticker(data)
        assert s.total < 18, f"Expected total < 18, got {s.total}"
        assert s.decision() == "SELL"

    def test_score_ticker_produces_hold_in_range(self):
        """Moderate company: total should be 18–27 → HOLD."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.08,
                "revenue_annual_growth": 0.07,
                "gross_margin": 0.35,
                "operating_margin": 0.12,
                "net_income": 2e9,
                "free_cash_flow": 1e9,
                "net_debt": 8e9,
                "guidance_official": 0.06,
            },
            "valuation": {
                "pe_current": 28,
                "pe_forward": 25,
                "peg_ratio": 2.0,
            },
            "sector": "Consumer Cyclical",
            "industry": "Retail",
            "market_cap": 5e10,
            "price": 60,
            "52w_high": 70,
        }
        s = score_ticker(data)
        assert 18 <= s.total <= 27, f"Expected total 18–27, got {s.total}"
        assert s.decision() == "HOLD"

    def test_score_ticker_produces_buy_above_28(self):
        """Strong company: total should be ≥ 28 → BUY."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.60,
                "revenue_annual_growth": 0.55,
                "gross_margin": 0.70,
                "operating_margin": 0.50,
                "net_income": 8e10,
                "free_cash_flow": 5e10,
                "net_debt": -1e10,
                "guidance_official": 0.25,
            },
            "valuation": {
                "pe_current": 22,
                "pe_forward": 18,
                "peg_ratio": 0.6,
            },
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 2e12,
            "price": 200,
            "52w_high": 210,
        }
        s = score_ticker(data)
        assert s.total >= 28, f"Expected total ≥ 28, got {s.total}"
        assert s.decision() == "BUY"


class TestTotalMax40:
    """T5.2 — Verify total sums to 40 for known test cases."""

    def test_theoretical_maximum_total_is_40(self):
        """Perfect scoring scenario: all raw sub-scores = 5 → total = 40."""
        # Construct data that maximizes ALL 8 sub-scores to 5
        data = {
            "financials": {
                "revenue_yoy_growth": 0.80,    # _score_growth → 5
                "revenue_annual_growth": 0.75,
                "gross_margin": 0.70,           # _score_profitability op=0.70 > 0.30 → 5
                "operating_margin": 0.70,
                "net_income": 1e12,             # profitable → +1
                "free_cash_flow": 1e12,         # positive FCF → +1
                "net_debt": -5e11,              # net cash → +1 (base 3 + 1 + 1 + 1 = 6, clamped to 5)
                "guidance_official": 0.30,       # _score_management → 4 (not 5 achievable)
            },
            "valuation": {
                "pe_current": 5,                # pe < 15 → _score_valuation → 5
                "pe_forward": 5,
                "peg_ratio": 0.5,
            },
            "sector": "Software",               # low geopolitical risk → _score_geopolitical → 4
            "industry": "Software—Services",
            "market_cap": 2e12,                 # mega-cap → moat bonus
            "price": 100,
            "52w_high": 100,                    # at 52w high → momentum bonus
        }
        s = score_ticker(data)
        raw = s._raw_subscores

        # Verify raw sub-scores are maximized
        assert raw["growth"] == 5, f"growth={raw['growth']}"
        assert raw["profitability"] == 5, f"profitability={raw['profitability']}"
        assert raw["financial_strength"] == 5, f"financial_strength={raw['financial_strength']}"
        assert raw["moat"] >= 4, f"moat={raw['moat']}"
        assert raw["valuation_risk"] == 5, f"valuation_risk={raw['valuation_risk']}"
        assert raw["business_momentum"] >= 4, f"business_momentum={raw['business_momentum']}"

        # canonical: 10 + 9+ + 8 + 4 + 4 + 2+ ≈ 37–40
        assert 37 <= s.total <= 40, f"Expected near-max total, got {s.total}"
        assert s.decision() == "BUY"

    def test_max_total_via_direct_construction(self):
        """Directly construct a perfect Scoring to prove total=40 cap."""
        s = Scoring(
            financial_health=10,   # max 10
            growth=10,             # max 10
            valuation=8,           # max 8
            management=5,          # max 5
            moat=4,                # max 4
            sentiment=3,           # max 3
        )
        # Sum = 10+10+8+5+4+3 = 40
        assert s.total == 40
        assert s.decision() == "BUY"

    def test_total_is_sum_of_six_canonical_fields(self):
        """Total property must equal the sum of the 6 canonical fields."""
        test_cases = [
            Scoring(financial_health=10, growth=10, valuation=8, management=5, moat=4, sentiment=3),
            Scoring(financial_health=0, growth=0, valuation=0, management=0, moat=0, sentiment=0),
            Scoring(financial_health=5, growth=5, valuation=4, management=3, moat=2, sentiment=1),
        ]
        for sc in test_cases:
            expected = (sc.financial_health + sc.growth + sc.valuation +
                        sc.management + sc.moat + sc.sentiment)
            assert sc.total == expected, f"total={sc.total}, expected={expected}"

    def test_minimum_total(self):
        """Minimum possible total: all fields at 0."""
        s = Scoring(
            financial_health=0, growth=0, valuation=0,
            management=0, moat=0, sentiment=0,
        )
        assert s.total == 0
        assert s.decision() == "SELL"


class TestMappingCorrectness:
    """T5.3 — Mapping correctness: Financial Health = Profitability + Financial Strength."""

    def test_financial_health_equals_profitability_plus_strength(self):
        """Canonical: financial_health = raw profitability + raw financial_strength."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.12,
                "revenue_annual_growth": 0.11,
                "gross_margin": 0.55,     # _score_profitability: op=0.20 → 4
                "operating_margin": 0.20,
                "net_income": 3e9,         # profitable
                "free_cash_flow": 2e9,     # positive FCF
                "net_debt": -1e9,          # net cash
                "guidance_official": 0.10,
            },
            "valuation": {"pe_current": 30, "pe_forward": 28, "peg_ratio": 2.0},
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 5e11,
            "price": 100,
            "52w_high": 110,
        }
        s = score_ticker(data)
        raw = s._raw_subscores
        assert s.financial_health == raw["profitability"] + raw["financial_strength"], (
            f"financial_health={s.financial_health} != "
            f"profitability({raw['profitability']}) + financial_strength({raw['financial_strength']})"
        )

    def test_financial_health_extremes(self):
        """Financial Health mapping: min 0+1=1, max 5+5=10."""
        # Best case: profitability=5, financial_strength=5 → financial_health=10
        data_best = {
            "financials": {
                "revenue_yoy_growth": 0.05,
                "revenue_annual_growth": 0.05,
                "gross_margin": 0.70,
                "operating_margin": 0.50,   # op > 0.30 → profitability=5
                "net_income": 1e12,
                "free_cash_flow": 1e12,
                "net_debt": -5e11,          # net cash → strength+1 (base 3+1+1+1=6→5)
                "guidance_official": None,
            },
            "valuation": {"pe_current": None, "pe_forward": None, "peg_ratio": None},
            "sector": None, "industry": None,
            "market_cap": None, "price": None, "52w_high": None,
        }
        s = score_ticker(data_best)
        raw = s._raw_subscores
        assert raw["profitability"] == 5
        assert raw["financial_strength"] == 5
        assert s.financial_health == 10

        # Worst case: profitability=1, financial_strength=1 → financial_health=2
        data_worst = {
            "financials": {
                "revenue_yoy_growth": 0.0,
                "revenue_annual_growth": 0.0,
                "gross_margin": None,
                "operating_margin": -0.05,    # op ≤ 0 → profitability=1
                "net_income": -1e9,           # not profitable
                "free_cash_flow": -1e9,       # not positive FCF
                "net_debt": 1e12,             # heavy debt → strength-1 (base 3-1=2, min 1)
                "guidance_official": None,
            },
            "valuation": {"pe_current": None, "pe_forward": None, "peg_ratio": None},
            "sector": None, "industry": None,
            "market_cap": None, "price": None, "52w_high": None,
        }
        s = score_ticker(data_worst)
        raw = s._raw_subscores
        assert s.financial_health == raw["profitability"] + raw["financial_strength"]
        assert s.financial_health <= 4  # should be low

    def test_all_six_mappings_match_spec(self):
        """Verify each of the 6 canonical category mappings."""
        from backend.scorer import _scale_to_8, _scale_to_3

        # Use data that exercises all 8 raw scores with known values
        data = {
            "financials": {
                "revenue_yoy_growth": 0.30,
                "revenue_annual_growth": 0.25,
                "gross_margin": 0.65,
                "operating_margin": 0.45,
                "net_income": 2e9,
                "free_cash_flow": 1e9,
                "net_debt": -5e8,
                "guidance_official": 0.15,
            },
            "valuation": {"pe_current": 25, "pe_forward": 22, "peg_ratio": 1.5},
            "sector": "Technology",
            "industry": "Software—Infrastructure",
            "market_cap": 1e12,
            "price": 150,
            "52w_high": 155,
        }
        s = score_ticker(data)
        raw = s._raw_subscores

        # 1. Financial Health = profitability + financial_strength
        assert s.financial_health == raw["profitability"] + raw["financial_strength"]
        assert 0 <= s.financial_health <= 10

        # 2. Growth = growth + business_momentum
        assert s.growth == raw["growth"] + raw["business_momentum"]
        assert 0 <= s.growth <= 10

        # 3. Valuation = scaled valuation_risk (0–8)
        assert s.valuation == _scale_to_8(raw["valuation_risk"])
        assert 0 <= s.valuation <= 8

        # 4. Management = direct (0–5)
        assert s.management == raw["management"]
        assert 0 <= s.management <= 5

        # 5. Moat = capped at 4
        assert s.moat == min(raw["moat"], 4)
        assert 0 <= s.moat <= 4

        # 6. Sentiment = scaled geopolitical_risk (0–3)
        assert s.sentiment == _scale_to_3(raw["geopolitical_risk"])
        assert 0 <= s.sentiment <= 3


class TestOrientation:
    """T5.4 — Higher score always means better across all categories."""

    def test_decision_monotonic_with_total(self):
        """As total increases, decision never regresses (SELL→HOLD→BUY)."""
        decisions = []
        for total in range(0, 41):
            # Distribute total proportionally across 6 fields
            # Simple distribution that respects per-field max
            fh = min(10, max(0, total * 10 // 40))
            gr = min(10, max(0, total * 10 // 40))
            va = min(8, max(0, total * 8 // 40))
            mg = min(5, max(0, total * 5 // 40))
            mo = min(4, max(0, total * 4 // 40))
            se = min(3, max(0, total * 3 // 40))
            s = Scoring(
                financial_health=fh, growth=gr, valuation=va,
                management=mg, moat=mo, sentiment=se,
            )
            decisions.append(s.decision())

        # Decision should only change SELL→HOLD→BUY, never regress
        decision_order = {"SELL": 0, "HOLD": 1, "BUY": 2}
        for i in range(1, len(decisions)):
            assert decision_order[decisions[i]] >= decision_order[decisions[i-1]], (
                f"Decision regressed at total={i}: {decisions[i-1]} → {decisions[i]}"
            )

    def test_improving_fundamentals_increases_or_preserves_scores(self):
        """When we improve underlying data, all canonical scores should be ≥."""
        base_data = {
            "financials": {
                "revenue_yoy_growth": 0.10,
                "revenue_annual_growth": 0.08,
                "gross_margin": 0.40,
                "operating_margin": 0.15,
                "net_income": 1e9,
                "free_cash_flow": 5e8,
                "net_debt": 1e9,
                "guidance_official": 0.05,
            },
            "valuation": {
                "pe_current": 35,
                "pe_forward": 30,
                "peg_ratio": 2.5,
            },
            "sector": "Consumer Cyclical",
            "industry": "Retail",
            "market_cap": 2e10,
            "price": 40,
            "52w_high": 60,
        }

        # Improved data: better growth, margins, valuation, momentum
        improved_data = {
            "financials": {
                "revenue_yoy_growth": 0.35,
                "revenue_annual_growth": 0.30,
                "gross_margin": 0.65,
                "operating_margin": 0.40,
                "net_income": 5e9,
                "free_cash_flow": 3e9,
                "net_debt": -1e9,           # net cash
                "guidance_official": 0.20,
            },
            "valuation": {
                "pe_current": 18,           # cheaper
                "pe_forward": 15,
                "peg_ratio": 1.0,
            },
            "sector": "Technology",         # lower geopolitical risk
            "industry": "Software",
            "market_cap": 1e12,            # larger
            "price": 80,
            "52w_high": 82,                # near 52w high
        }

        base = score_ticker(base_data)
        improved = score_ticker(improved_data)

        # Every canonical field must be >= base
        assert improved.financial_health >= base.financial_health, (
            f"financial_health: {improved.financial_health} < {base.financial_health}"
        )
        assert improved.growth >= base.growth, (
            f"growth: {improved.growth} < {base.growth}"
        )
        assert improved.valuation >= base.valuation, (
            f"valuation: {improved.valuation} < {base.valuation}"
        )
        assert improved.management >= base.management, (
            f"management: {improved.management} < {base.management}"
        )
        assert improved.moat >= base.moat, (
            f"moat: {improved.moat} < {base.moat}"
        )
        assert improved.sentiment >= base.sentiment, (
            f"sentiment: {improved.sentiment} < {base.sentiment}"
        )
        assert improved.total > base.total, (
            f"total: {improved.total} <= {base.total}"
        )
        assert improved.decision() != "SELL"  # improved should be at least HOLD

    def test_all_canonical_fields_are_non_negative(self):
        """All six canonical fields must be >= 0 for any input."""
        # Generate several different scenarios
        scenarios = [
            # Strong company
            {
                "financials": {"revenue_yoy_growth": 0.50, "revenue_annual_growth": 0.45,
                               "gross_margin": 0.70, "operating_margin": 0.50,
                               "net_income": 5e10, "free_cash_flow": 3e10,
                               "net_debt": -2e10, "guidance_official": 0.25},
                "valuation": {"pe_current": 20, "pe_forward": 18, "peg_ratio": 0.8},
                "sector": "Technology", "industry": "Software",
                "market_cap": 1e12, "price": 150, "52w_high": 152,
            },
            # Weak company
            {
                "financials": {"revenue_yoy_growth": -0.15, "revenue_annual_growth": -0.12,
                               "gross_margin": 0.15, "operating_margin": -0.05,
                               "net_income": -2e9, "free_cash_flow": -1e9,
                               "net_debt": 1e11, "guidance_official": None},
                "valuation": {"pe_current": None, "pe_forward": None, "peg_ratio": None},
                "sector": "Energy", "industry": "Oil & Gas",
                "market_cap": 1e9, "price": 5, "52w_high": 20,
            },
            # All None/missing
            {
                "financials": {}, "valuation": {},
                "sector": None, "industry": None,
                "market_cap": None, "price": None, "52w_high": None,
            },
        ]

        for i, data in enumerate(scenarios):
            s = score_ticker(data)
            fields = {
                "financial_health": s.financial_health,
                "growth": s.growth,
                "valuation": s.valuation,
                "management": s.management,
                "moat": s.moat,
                "sentiment": s.sentiment,
            }
            for name, value in fields.items():
                assert value >= 0, f"Scenario {i}: {name}={value} < 0"


class TestScoreTickerEdgeCases:
    """Edge case and robustness tests for score_ticker."""

    def test_empty_tone_data(self):
        """Empty dict for tone_data → falls back to _score_management()."""
        data = {
            "financials": {
                "revenue_yoy_growth": 0.10,
                "revenue_annual_growth": 0.10,
                "gross_margin": 0.40,
                "operating_margin": 0.15,
                "net_income": 1e9,
                "free_cash_flow": 5e8,
                "net_debt": 0,
                "guidance_official": 0.10,
            },
            "valuation": {"pe_current": 30, "pe_forward": 28, "peg_ratio": None},
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 1e11,
            "price": 50,
            "52w_high": 55,
        }
        s_empty = score_ticker(data, tone_data={})
        s_none = score_ticker(data, tone_data=None)
        # Empty dict and None should give same result (both skip _score_management_realtime)
        assert s_empty.total == s_none.total

    def test_fractional_scale_to_8(self):
        """Test _scale_to_8 rounding behavior at boundaries."""
        from backend.scorer import _scale_to_8
        assert _scale_to_8(0) == 0
        assert _scale_to_8(1) == 2   # 1*8/5 = 1.6 → 2
        assert _scale_to_8(2) == 3   # 2*8/5 = 3.2 → 3
        assert _scale_to_8(3) == 5   # 3*8/5 = 4.8 → 5
        assert _scale_to_8(4) == 6   # 4*8/5 = 6.4 → 6
        assert _scale_to_8(5) == 8   # 5*8/5 = 8.0 → 8

    def test_fractional_scale_to_3(self):
        """Test _scale_to_3 rounding behavior at boundaries."""
        from backend.scorer import _scale_to_3
        assert _scale_to_3(0) == 0
        assert _scale_to_3(1) == 1   # 1*3/5 = 0.6 → 1
        assert _scale_to_3(2) == 1   # 2*3/5 = 1.2 → 1
        assert _scale_to_3(3) == 2   # 3*3/5 = 1.8 → 2
        assert _scale_to_3(4) == 2   # 4*3/5 = 2.4 → 2
        assert _scale_to_3(5) == 3   # 5*3/5 = 3.0 → 3
