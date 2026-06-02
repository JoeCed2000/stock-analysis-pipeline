"""§9 EPS & Revenue Reconciliation Gate — tests for RULE 13.

Covers corrections.txt §9 requirements:
- 13a: SEC should not be shown as source for consensus/estimates
- 13b: "Not available" shouldn't appear when metrics have the value
- 13c: No raw provider keys in output
- 13d: Beat/miss shouldn't be discussed when estimates are unavailable
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


def _errors_for(result, check_prefix: str) -> list:
    return [e for e in result.errors if e.check == check_prefix]


def _warnings_for(result, check_prefix: str) -> list:
    return [w for w in result.warnings if w.check == check_prefix]


# ═══════════════════════════════════════════════════════════════════════════
# 13a — SEC as consensus source
# ═══════════════════════════════════════════════════════════════════════════


class TestSECAsConsensusSource:
    """RULE 13a: SEC should not appear near estimate/consensus in Source column."""

    def test_sec_in_source_column_blocked(self):
        sections = {
            "EPS & Revenue": (
                "| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |\n"
                "| EPS | $6.20 | $6.50 | +4.8% | +18% | SEC |\n"
                "EPS beat consensus by 4.8%."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "eps_revenue_sec_as_consensus_source")
        assert len(errs) == 1

    def test_company_reported_passes(self):
        sections = {
            "EPS & Revenue": (
                "| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |\n"
                "| EPS | $6.20 | $6.50 | +4.8% | +18% | Company reported |\n"
                "EPS beat consensus by 4.8%."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "eps_revenue_sec_as_consensus_source")
        assert len(errs) == 0

    def test_analyst_consensus_passes(self):
        sections = {
            "EPS & Revenue": (
                "| EPS | Analyst consensus | $6.50 | +4.8% | +18% | Consensus |\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "eps_revenue_sec_as_consensus_source")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 13b — "Not available" contradiction with metrics
# ═══════════════════════════════════════════════════════════════════════════


class TestNotAvailableContradiction:
    """RULE 13b: "Not available" when metrics have the actual value."""

    def test_eps_not_available_but_metrics_have_it_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50)
        sections = {
            "EPS & Revenue": (
                "| EPS | $6.20 | Not available | — | +18% | Company |\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_not_available_contradiction")
        assert len(errs) == 1

    def test_revenue_not_available_but_metrics_have_it_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=22.1e9)
        sections = {
            "EPS & Revenue": (
                "| Revenue | $22.0B | Not retrieved | — | +18% | — |\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_not_available_contradiction")
        assert len(errs) == 1

    def test_not_available_but_no_metrics_passes(self):
        """If metrics are missing, Not available is legitimate."""
        sections = {
            "EPS & Revenue": "Revenue: Not available — company has not yet reported."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "eps_revenue_not_available_contradiction")
        assert len(errs) == 0

    def test_all_values_populated_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50, revenue_actual=22.1e9)
        sections = {
            "EPS & Revenue": (
                "| EPS | $6.20 | $6.50 | +4.8% | +18% | Company reported |\n"
                "| Revenue | $22.0B | $22.1B | +0.5% | +15% | Company reported |\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_not_available_contradiction")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 13c — Raw provider keys
# ═══════════════════════════════════════════════════════════════════════════


class TestRawProviderKeys:
    """RULE 13c: no raw provider keys or field names in output."""

    @pytest.mark.parametrize("bad_text", [
        "Source: yfinance key operating_cash_flow",
        "trailingPE of 35.2x",
        "earningsGrowth is 0.15",
        "pegRatio is 0.66",
        "raw provider field",
        "provider key: revenueGrowth",
    ])
    def test_raw_provider_key_warns(self, bad_text):
        sections = {"EPS & Revenue": bad_text}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        wrns = _warnings_for(result, "eps_revenue_raw_provider_key")
        assert len(wrns) >= 1, f"Should warn: '{bad_text}'"

    def test_clean_labels_pass(self):
        sections = {
            "EPS & Revenue": (
                "Source: Company reported 10-Q. Consensus from analyst estimates. "
                "P/E ratio is 35.2x based on trailing earnings."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "eps_revenue_raw_provider_key")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 13d — Beat/miss without estimate
# ═══════════════════════════════════════════════════════════════════════════


class TestBeatMissWithoutEstimate:
    """RULE 13d: beat/miss language when estimates are unavailable."""

    def test_beat_without_estimate_blocked(self):
        sections = {
            "EPS & Revenue": (
                "Revenue beat consensus estimates this quarter by a wide margin."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "eps_revenue_beat_miss_without_estimate")
        assert len(errs) == 1

    def test_beat_with_estimate_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_estimate=6.20, eps_actual=6.50)
        sections = {
            "EPS & Revenue": "EPS beat consensus estimates by 4.8%."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_beat_miss_without_estimate")
        assert len(errs) == 0

    def test_no_beat_miss_language_passes(self):
        sections = {
            "EPS & Revenue": "Revenue was $22.1B this quarter. No estimate available."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "eps_revenue_beat_miss_without_estimate")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestRule13Integration:
    """RULE 13 with other rules and realistic data."""

    def test_clean_eps_revenue_all_rules_pass(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            eps_actual=6.50,
            eps_estimate=6.20,
            revenue_actual=22.1e9,
            revenue_estimate=22.0e9,
        )
        sections = {
            "EPS & Revenue": (
                "| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |\n"
                "| EPS | $6.20 | $6.50 | +4.8% | +18% | Company reported (10-Q) |\n"
                "| Revenue | $22.0B | $22.1B | +0.5% | +15% | Company reported (10-Q) |\n\n"
                "EPS beat analyst consensus by 4.8%, driven by data center revenue growth. "
                "Revenue also exceeded estimates, confirming broad-based strength. "
                "This was a high-quality beat with both top and bottom line exceeding expectations."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        for prefix in ["eps_revenue_", "period_", "fy_label", "eps_direction"]:
            errs = _errors_for(result, prefix)
            assert len(errs) == 0, \
                f"Clean EPS & Revenue should not trigger '{prefix}': {errs}"

    def test_existing_rules_still_work_with_rule13(self):
        """RULE 3 (cross-section contradiction) + RULE 13 coexist."""
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50, eps_estimate=6.20)
        sections = {
            "EPS & Revenue": "EPS beat consensus by 4.8%. Source: Company reported.",
            "Verdict": "EPS missed consensus by 4.8%. SELL immediately."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        # RULE 13 should pass (no issues)
        errs_13 = [e for e in result.errors if e.check.startswith("eps_revenue_")]
        assert len(errs_13) == 0
        # RULE 3 should fire as warning (post-processing can repair/flag)
        wrns_3 = _warnings_for(result, "eps_direction_contradiction")
        assert len(wrns_3) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 13e — Estimate-Actual proximity suspicion
# ═══════════════════════════════════════════════════════════════════════════


class TestEstimateActualProximity:
    """RULE 13e: flag when estimate and actual are suspiciously close."""

    def test_revenue_estimate_near_actual_warns(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            revenue_actual=111.2e9,
            revenue_estimate=111.18e9,  # 0.02% difference
        )
        sections = {
            "EPS & Revenue": (
                "| Revenue | $111.18B | $111.2B | +0.02% | +16.6% | yfinance |\n"
            )
        }
        result = validate_pre_render("AAPL", "FY2026 Q1", metrics, sections)
        wrns = _warnings_for(result, "eps_revenue_estimate_actual_proximity")
        assert len(wrns) >= 1, "Estimate within 1% of actual should trigger proximity warning"

    def test_revenue_estimate_clearly_different_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            revenue_actual=22.1e9,
            revenue_estimate=20.8e9,  # ~6% difference
        )
        sections = {
            "EPS & Revenue": (
                "| Revenue | $20.8B | $22.1B | +6.3% | +15% | Company reported |\n"
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        wrns = _warnings_for(result, "eps_revenue_estimate_actual_proximity")
        assert len(wrns) == 0

    def test_no_estimate_skips_proximity_check(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=22.1e9)  # No estimate
        sections = {
            "EPS & Revenue": "| Revenue | — | $22.1B | — | +15% | Company |\n"
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        wrns = _warnings_for(result, "eps_revenue_estimate_actual_proximity")
        assert len(wrns) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 13f — YoY without prior-year data
# ═══════════════════════════════════════════════════════════════════════════


class TestYoYWithoutPriorData:
    """RULE 13f: YoY comparison when prior-year metric is missing."""

    def test_yoy_mentioned_but_no_prior_data_warned(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=111.2e9)  # No revenue_yoy!
        sections = {
            "EPS & Revenue": (
                "Revenue grew 16.6% YoY to $111.2B, a March quarter record.\n"
            )
        }
        result = validate_pre_render("AAPL", "FY2026 Q1", metrics, sections)
        wrns = _warnings_for(result, "eps_revenue_yoy_without_prior_data")
        assert len(wrns) >= 1

    def test_yoy_mentioned_with_revenue_yoy_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(revenue_actual=22.1e9, revenue_yoy=0.15)
        sections = {
            "EPS & Revenue": "Revenue grew 15% YoY to $22.1B.\n"
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_yoy_without_prior_data")
        assert len(errs) == 0

    def test_yoy_mentioned_with_eps_yoy_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(eps_actual=6.50, eps_yoy=0.18)
        sections = {
            "EPS & Revenue": "EPS grew 18% YoY to $6.50.\n"
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_yoy_without_prior_data")
        assert len(errs) == 0

    def test_no_yoy_mentioned_passes(self):
        sections = {
            "EPS & Revenue": "EPS was $6.50 this quarter. Revenue reached $22.1B.\n"
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "eps_revenue_yoy_without_prior_data")
        assert len(errs) == 0

    def test_yoy_with_revenue_yoy_passes(self):
        """If revenue_yoy exists in metrics, YoY is verifiable."""
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            revenue_actual=22.1e9,
            revenue_yoy=0.15,
        )
        sections = {
            "EPS & Revenue": "Revenue grew 15% YoY to $22.1B.\n"
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "eps_revenue_yoy_without_prior_data")
        assert len(errs) == 0
