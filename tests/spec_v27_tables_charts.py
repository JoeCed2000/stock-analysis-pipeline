"""§24-25 Table Rendering & Charts — tests for RULE 14 (markdown) + RULE 15 (charts).

Covers corrections.txt §24 (table/PDF layout) and §25 (chart integrity).
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


def _errors_for(result, check_prefix: str) -> list:
    return [e for e in result.errors if e.check == check_prefix]


def _warnings_for(result, check_prefix: str) -> list:
    return [w for w in result.warnings if w.check == check_prefix]


# ═══════════════════════════════════════════════════════════════════════════
# RULE 14 — Raw Markdown rendering
# ═══════════════════════════════════════════════════════════════════════════


class TestRawMarkdownTable:
    """RULE 14a: raw Markdown pipe tables."""

    def test_pipe_table_blocked(self):
        sections = {
            "Segments": (
                "| Segment | Revenue | YoY | Source |\n"
                "|---|---|---|---|\n"
                "| Compute | $18.4B | +22% | Company |\n"
                "| Networking | $3.1B | +8% | Company |\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_table")
        assert len(errs) == 1

    def test_no_pipe_table_passes(self):
        sections = {
            "Segments": "Compute revenue was $18.4B (+22% YoY). Networking was $3.1B (+8%)."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_table")
        assert len(errs) == 0

    def test_single_pipe_line_not_blocked(self):
        """A single pipe line is not a table — could be a data row rendered correctly."""
        sections = {
            "Segments": "Segment breakdown: | Compute | $18.4B |"
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_table")
        assert len(errs) == 0


class TestRawMarkdownHeadings:
    """RULE 14b: raw heading markers (###, ##)."""

    def test_hash_heading_blocked(self):
        sections = {"Operating Metrics": "### Margin Analysis\n\nGross margin was 72.4%."}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_headings")
        assert len(errs) == 1

    def test_rendered_heading_passes(self):
        sections = {"Operating Metrics": "Margin Analysis\n\nGross margin was 72.4%."}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_headings")
        assert len(errs) == 0


class TestRawMarkdownBullets:
    """RULE 14c: raw bullet markers (*, -, +)."""

    def test_raw_star_bullets_blocked(self):
        sections = {
            "Highlights": (
                "* Revenue grew 18% YoY to $22.1B\n"
                "* Operating margin expanded 220bps\n"
                "* FCF reached $14.9B\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_bullets")
        assert len(errs) == 1

    def test_rendered_bullets_pass(self):
        sections = {
            "Highlights": (
                "• Revenue grew 18% YoY to $22.1B\n"
                "• Operating margin expanded 220bps\n"
                "• FCF reached $14.9B\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_bullets")
        assert len(errs) == 0

    def test_less_than_3_raw_bullets_passes(self):
        """1-2 raw bullets could be intentional. Gate fires at 3+."""
        sections = {
            "Highlights": (
                "* Revenue grew 18% YoY to $22.1B\n"
                "• Operating margin expanded 220bps\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "raw_markdown_bullets")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RULE 15 — Chart data consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestChartEPSContradiction:
    """RULE 15: text says beat but metrics say actual < estimate."""

    def test_eps_beat_text_contradicts_metrics_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.20, eps_estimate=6.50)  # actual < estimate = MISS
        sections = {
            "EPS & Revenue": "EPS beat consensus estimates by a wide margin."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "chart_eps_contradiction")
        assert len(errs) == 1

    def test_eps_actual_above_estimate_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50, eps_estimate=6.20)  # actual > estimate = BEAT
        sections = {
            "EPS & Revenue": "EPS beat consensus estimates by a wide margin."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "chart_eps_contradiction")
        assert len(errs) == 0

    def test_no_beat_language_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.20, eps_estimate=6.50)  # actual < estimate
        sections = {
            "EPS & Revenue": "EPS was $6.20 vs $6.50 estimate."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "chart_eps_contradiction")
        assert len(errs) == 0


class TestChartRevenueContradiction:
    """RULE 15: text says revenue beat but metrics say actual < estimate."""

    def test_revenue_beat_text_contradicts_metrics_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=21.5e9, revenue_estimate=22.0e9)
        sections = {
            "EPS & Revenue": "Revenue exceeded consensus estimates."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "chart_revenue_contradiction")
        assert len(errs) == 1

    def test_revenue_actual_above_estimate_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=22.1e9, revenue_estimate=22.0e9)
        sections = {
            "EPS & Revenue": "Revenue exceeded consensus estimates."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "chart_revenue_contradiction")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestRules1415Integration:
    """Rules 14 and 15 with other existing rules."""

    def test_clean_section_all_rules_pass(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            eps_actual=6.50, eps_estimate=6.20,
            revenue_actual=22.1e9, revenue_estimate=22.0e9,
        )
        sections = {
            "EPS & Revenue": (
                "EPS beat consensus by 4.8% to $6.50. "
                "Revenue exceeded estimates at $22.1B."
            ),
            "Operating Metrics": (
                "Gross margin was 72.4%, down 120bps sequentially "
                "due to Blackwell ramp costs."
            ),
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        for prefix in ["raw_markdown_", "chart_eps_", "chart_revenue_"]:
            errs = _errors_for(result, prefix)
            assert len(errs) == 0, \
                f"Clean sections should not trigger '{prefix}': {errs}"

    def test_multiple_rules_fire_on_bad_section(self):
        """A section with both raw markdown and provider keys triggers multiple rules."""
        sections = {
            "EPS & Revenue": (
                "| Metric | Estimate | Actual | Source |\n"
                "|---|---|---|---|\n"
                "| EPS | $6.20 | $6.50 | yfinance key: eps |\n"
                "Revenue beat consensus by 5%."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        # Both raw_markdown_table and raw_provider_key should fire
        table_errs = _warnings_for(result, "raw_markdown_table")
        provider_errs = _errors_for(result, "eps_revenue_raw_provider_key")
        assert len(table_errs) >= 1
        assert len(provider_errs) >= 1
