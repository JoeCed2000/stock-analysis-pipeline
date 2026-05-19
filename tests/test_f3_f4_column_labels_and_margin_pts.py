"""Tests for F3 (dynamic column labels) and F4 (margin change in percentage points)."""
import pytest
from backend.earnings_deep_dive.prompts import _parse_quarter, _base_prompt


class TestParseQuarter:
    def test_valid_quarters(self):
        assert _parse_quarter("2026Q1") == ("Q1 2026", "Q1 2025")
        assert _parse_quarter("2025Q4") == ("Q4 2025", "Q4 2024")
        assert _parse_quarter("2024Q2") == ("Q2 2024", "Q2 2023")
        assert _parse_quarter("2030Q3") == ("Q3 2030", "Q3 2029")

    def test_invalid_quarters(self):
        assert _parse_quarter("") is None
        assert _parse_quarter("abc") is None
        assert _parse_quarter("2026Q5") is None  # invalid quarter number
        assert _parse_quarter("2026Q0") is None  # invalid quarter number
        assert _parse_quarter(None) is None
        assert _parse_quarter(2026) is None
        assert _parse_quarter("2026-Q1") is None  # wrong format


class TestDynamicColumnLabels:
    def test_quarter_labels_replaced(self):
        """F3: 'Actual'/'Prior Year' → 'Q1 2026'/'Q1 2025'."""
        prompt = _base_prompt(
            section="Operating Metrics",
            language="en",
            ticker="NVDA",
            company="NVIDIA",
            quarter="2026Q1",
            metrics={},
            transcript_excerpt="test",
        )
        assert "Q1 2026" in prompt
        assert "Q1 2025" in prompt
        assert "Actual" not in prompt
        assert "Prior Year" not in prompt

    def test_fallback_when_quarter_unparseable(self):
        """When quarter can't be parsed, keep original labels."""
        prompt = _base_prompt(
            section="Operating Metrics",
            language="en",
            ticker="NVDA",
            company="NVIDIA",
            quarter="not-a-quarter",
            metrics={},
            transcript_excerpt="test",
        )
        assert "Actual" in prompt
        assert "Prior Year" in prompt

    def test_cash_flow_also_gets_labels(self):
        """Cash Flow section also uses Actual/Prior Year."""
        prompt = _base_prompt(
            section="Cash Flow",
            language="en",
            ticker="AAPL",
            company="Apple",
            quarter="2025Q4",
            metrics={},
            transcript_excerpt="test",
        )
        assert "Q4 2025" in prompt
        assert "Q4 2024" in prompt

    def test_eps_section_unchanged(self):
        """EPS & Revenue section (no 'Actual'/'Prior Year') should not break."""
        prompt = _base_prompt(
            section="EPS & Revenue",
            language="en",
            ticker="NVDA",
            company="NVIDIA",
            quarter="2026Q1",
            metrics={"eps_actual": 1.76, "eps_estimate": 1.62},
            transcript_excerpt="test",
        )
        # Should still render correctly
        assert "EPS & Revenue" in prompt or "EPS" in prompt


class TestMarginPoints:
    def test_positive_diff(self):
        from backend.earnings_deep_dive.mapper import _yoy_pts
        assert _yoy_pts(58.3, 55.6) == "+2.7 pts"

    def test_negative_diff(self):
        from backend.earnings_deep_dive.mapper import _yoy_pts
        assert _yoy_pts(55.6, 58.3) == "-2.7 pts"

    def test_zero_diff(self):
        from backend.earnings_deep_dive.mapper import _yoy_pts
        assert _yoy_pts(50.0, 50.0) == "0.0 pts"

    def test_missing_current(self):
        from backend.earnings_deep_dive.mapper import _yoy_pts, MISSING
        assert _yoy_pts(None, 55.6) == MISSING

    def test_missing_prior(self):
        from backend.earnings_deep_dive.mapper import _yoy_pts, MISSING
        assert _yoy_pts(58.3, None) == MISSING

    def test_string_inputs(self):
        from backend.earnings_deep_dive.mapper import _yoy_pts
        assert _yoy_pts("58.3", "55.6") == "+2.7 pts"
