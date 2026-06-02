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

    def test_revenue_beat_text_contradicts_metrics_warned(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=21.5e9, revenue_estimate=22.0e9)
        sections = {
            "EPS & Revenue": "Revenue exceeded consensus estimates."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        wrns = _warnings_for(result, "chart_revenue_contradiction")
        assert len(wrns) == 1

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
    """Rule 15 integration with other existing rules (Rule 14 removed)."""

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
        for prefix in ["chart_eps_", "chart_revenue_"]:
            errs = _errors_for(result, prefix)
            assert len(errs) == 0, \
                f"Clean sections should not trigger '{prefix}': {errs}"

    def test_multiple_rules_fire_on_bad_section(self):
        """A section with raw provider keys triggers the provider key rule."""
        sections = {
            "EPS & Revenue": (
                "| Metric | Estimate | Actual | Source |\n"
                "|---|---|---|---|\n"
                "| EPS | $6.20 | $6.50 | yfinance key: eps |\n"
                "Revenue beat consensus by 5%."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        provider_wrns = _warnings_for(result, "eps_revenue_raw_provider_key")
        assert len(provider_wrns) >= 1
