"""§§19-21,14 Verdict/Valuation/DataQuality/Segments gates — RULES 21-24."""

import pytest
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


def _errors_for(result, check_prefix: str) -> list:
    return [e for e in result.errors if e.check == check_prefix]


# ═══════════════════════════════════════════════════════════════════════════
# RULE 21 — §20 Verdict consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestVerdict:
    """RULE 21: score/commentary, beat but negative, no red flags paradox."""

    def test_high_score_with_strong_negative_language_blocked(self):
        sections = {"Verdict": "Score: 8/10. Sell immediately. This stock will crash. Avoid."}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "verdict_score_negative_contradiction")
        assert len(errs) == 1

    def test_beat_but_verdict_says_sell_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50, eps_estimate=6.20)
        sections = {
            "EPS & Revenue": "EPS beat consensus by 5%.",
            "Verdict": "Sell immediately. Downgrade to underperform. Negative outlook."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "verdict_beat_but_too_negative")
        assert len(errs) == 1

    def test_clean_verdict_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50, eps_estimate=6.20)
        sections = {
            "EPS & Revenue": "EPS beat consensus by 5%.",
            "Verdict": "Score: 7/10. Strong quarter with some valuation concerns. HOLD."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        for prefix in ["verdict_score_", "verdict_beat_", "verdict_no_red"]:
            assert len(_errors_for(result, prefix)) == 0

    def test_no_red_flags_with_many_risks_blocked(self):
        sections = {
            "Verdict": (
                "No major red flags for this quarter. "
                "Key risks: regulatory overhang, supply chain pressure, "
                "geopolitical uncertainty in Taiwan, margin compression from Blackwell ramp. "
                "Competition from AMD is intensifying."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "verdict_no_red_flags_paradox")
        assert len(errs) == 1


# ═══════════════════════════════════════════════════════════════════════════
# RULE 22 — §19 Valuation sanity
# ═══════════════════════════════════════════════════════════════════════════


class TestValuation:
    """RULE 22: FCF yield threshold, high P/FCF flagging."""

    def test_low_fcf_yield_but_attractive_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(fcf_yield=1.5)
        sections = {
            "Verdict": "Valuation remains attractive at current levels. BUY."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "valuation_fcf_yield_warning")
        assert len(errs) == 1

    def test_low_fcf_yield_flagged_appropriately_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(fcf_yield=1.5)
        sections = {
            "Valuation": (
                "FCF yield is low at 1.5%, which is a valuation risk. "
                "However, growth-adjusted metrics remain reasonable."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "valuation_fcf_yield_warning")
        assert len(errs) == 0

    def test_high_pfcf_not_flagged_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(price_to_fcf=65.0)
        sections = {"Verdict": "Valuation is reasonable. BUY."}
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "valuation_pfcf_not_flagged")
        assert len(errs) == 1

    def test_high_pfcf_flagged_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(price_to_fcf=65.0)
        sections = {
            "Verdict": "P/FCF is elevated at 65x, reflecting growth premium. HOLD."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "valuation_pfcf_not_flagged")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RULE 23 — §21 Data Quality truthfulness
# ═══════════════════════════════════════════════════════════════════════════


class TestDataQuality:
    """RULE 23: false completeness, source usage truthfulness."""

    def test_completeness_100_but_critical_missing_blocked(self):
        sections = {
            "Data Quality": "Completeness: 98/100. All sources available."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "data_quality_false_completeness")
        assert len(errs) == 1  # eps_actual, revenue_actual, etc. all None

    def test_completeness_100_with_all_metrics_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            eps_actual=6.50, revenue_actual=22.1e9,
            free_cash_flow=14.9e9, gross_margin=72.4,
        )
        sections = {
            "Data Quality": "Completeness: 98/100. All critical metrics present."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "data_quality_false_completeness")
        assert len(errs) == 0

    def test_all_sources_used_but_transcript_missing_blocked(self):
        sections = {
            "Data Quality": (
                "All sources used and verified. "
                "Transcript not available for this quarter."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "data_quality_sources_inaccurate")
        assert len(errs) == 1


# ═══════════════════════════════════════════════════════════════════════════
# RULE 24 — §14 Segments hierarchy
# ═══════════════════════════════════════════════════════════════════════════


class TestSegments:
    """RULE 24: Total N/A contradiction, parent/child mixing."""

    def test_total_na_but_revenue_exists_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_quarterly=22.1e9)
        sections = {"Segments": "Data Center: $18.4B. Gaming: $3.1B. Total: Not available."}
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "segments_total_na_contradiction")
        assert len(errs) == 1

    def test_normal_segments_passes(self):
        sections = {
            "Segments": (
                "Data Center: $18.4B (+22% YoY). Gaming: $3.1B (+8%). "
                "Total: $22.1B (+18%)."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "segments_total_na_contradiction")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestMultiRuleIntegration:
    """All rules 21-24 together."""

    def test_fully_clean_report_passes_all(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            eps_actual=6.50, eps_estimate=6.20,
            revenue_actual=22.1e9, revenue_quarterly=22.1e9,
            free_cash_flow=14.9e9, gross_margin=72.4,
            operating_margin=64.8, fcf_yield=2.5,
            price_to_fcf=35.0,
            roe=85.5, roic=42.3,
        )
        sections = {
            "EPS & Revenue": "EPS $6.50 beat consensus $6.20 by 4.8%. Revenue $22.1B.",
            "Verdict": "Score: 7/10. Solid execution with balanced risks. HOLD.",
            "Valuation": "P/FCF at 35x is elevated but supported by 45% growth. FCF yield 2.5%.",
            "Data Quality": "Completeness: 92/100. EPS and Revenue: available. Transcript available.",
            "Segments": "Data Center: $18.4B. Gaming: $3.1B. Total: $22.1B.",
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        rule21_24_errors = [
            e for e in result.errors
            if e.check.startswith((
                "verdict_", "valuation_", "data_quality_", "segments_"
            ))
        ]
        assert len(rule21_24_errors) == 0, \
            f"Clean report should pass all rules, got: {[(e.check, e.detail[:60]) for e in rule21_24_errors]}"
