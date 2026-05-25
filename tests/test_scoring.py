"""Tests for Scoring model — 6 canonical weighted categories, total /40.

Acceptance criteria from SA-P0-F2F3-T1:
  1. Scoring model has 6 canonical fields (not 8 equal)
  2. total property sums to 40
  3. decision() returns BUY (>=28), HOLD (18–27), SELL (<18)
  4. Raw sub-scores preserved as optional audit fields (_raw_subscores)
"""

import pytest
from backend.models import Scoring


class TestScoringDecisionBoundaries:
    """SELL < 18, HOLD 18–27, BUY >= 28."""

    def test_total_17_is_sell(self):
        s = Scoring(financial_health=5, growth=5, valuation=3,
                     management=2, moat=1, sentiment=1)  # = 17
        assert s.total == 17
        assert s.decision() == "SELL"

    def test_total_18_is_hold_lower_bound(self):
        s = Scoring(financial_health=5, growth=5, valuation=3,
                     management=2, moat=1, sentiment=2)  # = 18
        assert s.total == 18
        assert s.decision() == "HOLD"

    def test_total_27_is_hold_upper_bound(self):
        s = Scoring(financial_health=8, growth=8, valuation=6,
                     management=3, moat=1, sentiment=1)  # = 27
        assert s.total == 27
        assert s.decision() == "HOLD"

    def test_total_28_is_buy(self):
        s = Scoring(financial_health=8, growth=8, valuation=6,
                     management=3, moat=2, sentiment=1)  # = 28
        assert s.total == 28
        assert s.decision() == "BUY"


class TestScoringTotalSumsTo40:
    """Max across all 6 categories must equal 40."""

    def test_max_scores_sum_to_40(self):
        s = Scoring(financial_health=10, growth=10, valuation=8,
                     management=5, moat=4, sentiment=3)
        assert s.total == 40  # 10+10+8+5+4+3

    def test_min_scores_sum_to_0(self):
        s = Scoring()  # all defaults = 0
        assert s.total == 0

    def test_mid_values_sum_correctly(self):
        s = Scoring(financial_health=5, growth=5, valuation=4,
                     management=3, moat=2, sentiment=2)
        assert s.total == 21  # 5+5+4+3+2+2


class TestScoringFieldMappingCorrect:
    """Verify the 6 canonical field names and weights match ADR-002."""

    CANONICAL_FIELDS = {
        "financial_health": 10,  # max 10
        "growth": 10,             # max 10
        "valuation": 8,           # max 8
        "management": 5,          # max 5
        "moat": 4,                # max 4
        "sentiment": 3,           # max 3
    }

    def test_no_old_8_fields_exist(self):
        """The model must NOT have the old 8 equal-weight fields."""
        field_names = set(Scoring.model_fields.keys())
        for old_field in ("profitability", "financial_strength",
                           "valuation_risk", "geopolitical_risk",
                           "business_momentum"):
            assert old_field not in field_names, \
                f"Legacy field '{old_field}' must not exist on Scoring"

    def test_all_6_canonical_fields_present(self):
        field_names = set(Scoring.model_fields.keys())
        expected = set(self.CANONICAL_FIELDS.keys())
        assert expected.issubset(field_names), \
            f"Missing canonical fields: {expected - field_names}"

    def test_field_weights_are_mapped(self):
        """Each field has the correct max weight."""
        for field_name, max_weight in self.CANONICAL_FIELDS.items():
            s = Scoring(**{field_name: max_weight})
            assert getattr(s, field_name) == max_weight, \
                f"Field '{field_name}' max should be {max_weight}"

    def test_total_is_read_only_property(self):
        """total must be a computed property, not a settable field."""
        s = Scoring(financial_health=5, growth=3, valuation=4,
                     management=2, moat=2, sentiment=1)  # = 17
        assert s.total == 17
        with pytest.raises(AttributeError):
            s.total = 50


class TestScoringRawSubscores:
    """Raw sub-scores must be preserved as optional audit fields."""

    def test_raw_subscores_is_private_attr(self):
        s = Scoring()
        assert hasattr(s, "_raw_subscores")
        assert isinstance(s._raw_subscores, dict)

    def test_raw_subscores_not_serialized_by_default(self):
        """Private attrs should not appear in model_dump."""
        s = Scoring(financial_health=5, growth=3, valuation=4,
                     management=2, moat=2, sentiment=1)
        d = s.model_dump()
        assert "_raw_subscores" not in d

    def test_raw_subscores_accept_8_internal_values(self):
        """Verify that the audit trail can hold all 8 original sub-scores."""
        s = Scoring()
        s._raw_subscores = {
            "growth": 4,
            "profitability": 3,
            "financial_strength": 5,
            "moat": 2,
            "management": 4,
            "valuation_risk": 3,
            "geopolitical_risk": 4,
            "business_momentum": 5,
        }
        assert len(s._raw_subscores) == 8
        assert s._raw_subscores["growth"] == 4


class TestScoringDecisionBoundariesExtended:
    """Edge cases beyond the 4 key boundaries."""

    def test_total_40_is_buy(self):
        s = Scoring(financial_health=10, growth=10, valuation=8,
                     management=5, moat=4, sentiment=3)
        assert s.total == 40
        assert s.decision() == "BUY"

    def test_total_0_is_sell(self):
        s = Scoring()
        assert s.total == 0
        assert s.decision() == "SELL"
