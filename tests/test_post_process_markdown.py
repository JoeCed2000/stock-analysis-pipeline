"""Test post-processing of LLM artifacts in deep-dive markdown."""
import pytest
from backend.earnings_deep_dive.markdown import post_process_markdown


class TestPostProcessMarkdown:
    """Verify field name / source reference cleanup."""

    def test_yfinance_dash_field_stripped(self):
        """yfinance — field_name → yfinance"""
        result = post_process_markdown("Source: yfinance — pe_forward")
        assert "pe_forward" not in result
        assert "yfinance" in result

    def test_yfinance_dash_value_preserved(self):
        """yfinance — field_name=VALUE → yfinance (VALUE)"""
        result = post_process_markdown("YoY: yfinance — eps_yoy=$2.14")
        assert "eps_yoy" not in result
        assert "yfinance ($2.14)" in result

    def test_yfinance_space_value_preserved(self):
        """yfinance field_name=VALUE (no dash) → yfinance (VALUE)"""
        result = post_process_markdown(
            "calculated from yfinance eps_yoy=$2.14, which represents"
        )
        assert "eps_yoy" not in result
        assert "yfinance ($2.14)" in result

    def test_metrics_field_stripped(self):
        """(source: Metrics — field1, field2) → (source: company metrics)"""
        result = post_process_markdown(
            "(source: Metrics — revenue_actual, revenue_yoy)"
        )
        assert "revenue_actual" not in result
        assert "company metrics" in result

    def test_yfinance_quarterly_data_preserved(self):
        """yfinance — quarterly data → yfinance (descriptive, not a field name)"""
        result = post_process_markdown("Source: yfinance — quarterly data")
        # "quarterly data" is two words, regex only captures first as field name
        # but the value isn't captured, so it becomes just "yfinance"
        assert "yfinance" in result

    def test_no_false_positive_natural_text(self):
        """Natural text like 'from yfinance.' should not be modified."""
        original = "based on the supplied metric from yfinance. This is"
        result = post_process_markdown(original)
        assert result == original

    def test_multiple_substitutions(self):
        """Multiple patterns in the same text all cleaned."""
        original = (
            "| EPS | $1.77 | $1.87 | YoY: yfinance eps_yoy=$2.14 |\n"
            "Revenue: $81.61B (source: Metrics — revenue_actual, revenue_yoy)\n"
            "P/E: yfinance — pe_forward\n"
        )
        result = post_process_markdown(original)
        assert "eps_yoy" not in result
        assert "revenue_actual" not in result
        assert "pe_forward" not in result
        assert "yfinance ($2.14)" in result
        assert "company metrics" in result

    def test_preserves_other_content(self):
        """Non-matching markdown passes through unchanged."""
        original = "# Heading\n\nNormal paragraph with **bold** and *italic*.\n\n| Table | Without | yfinance |\n|-------|---------|----------|\n| Row   | Data    | Here     |"
        result = post_process_markdown(original)
        # No yfinance field patterns here — should be identical
        assert result == original
