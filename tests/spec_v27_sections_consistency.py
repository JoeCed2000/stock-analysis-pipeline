"""§§11-16 Sections consistency gates — tests for RULES 16-20.

§11 Operating Metrics (RULE 16), §12 Cash Flow (RULE 17),
§13 Capital Efficiency (RULE 18), §15 Guidance (RULE 19),
§16 Backlog (RULE 20).
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


def _errors_for(result, check_prefix: str) -> list:
    return [e for e in result.errors if e.check == check_prefix]


def _warnings_for(result, check_prefix: str) -> list:
    return [w for w in result.warnings if w.check == check_prefix]


# ═══════════════════════════════════════════════════════════════════════════
# RULE 16 — §11 Operating Metrics
# ═══════════════════════════════════════════════════════════════════════════


class TestOperatingMetrics:
    """RULE 16: NOT available contradiction, margin % vs bps."""

    def test_not_available_with_margin_in_metrics_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(gross_margin=72.4, operating_margin=64.8)
        sections = {
            "Operating Metrics": "Gross margin: Not available. Operating margin: data not retrieved."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        warns = _warnings_for(result, "forbidden_marker_leak")
        assert len(warns) == 1

    def test_not_available_with_income_in_metrics_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(operating_income=14.3e9, net_income_quarterly=12.9e9)
        sections = {
            "Operating Metrics": "Operating income: Not available."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        warns = _warnings_for(result, "forbidden_marker_leak")
        assert len(warns) == 1

    def test_clean_metrics_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(gross_margin=72.4, operating_margin=64.8, operating_income=14.3e9)
        sections = {
            "Operating Metrics": (
                "Gross margin: 72.4% (+120bps YoY). "
                "Operating margin: 64.8% (+220bps YoY). "
                "Operating income: $14.3B."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "operating_metrics_not_available_contradiction")
        assert len(errs) == 0

    def test_margin_pct_growth_without_bps_blocked(self):
        sections = {
            "Operating Metrics": "Gross margin grew by 5% this quarter, reflecting improved pricing power."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "operating_metrics_margin_label")
        assert len(errs) == 1

    def test_margin_with_bps_passes(self):
        sections = {
            "Operating Metrics": "Gross margin expanded 500bps this quarter (+5 percentage points)."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "operating_metrics_margin_label")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RULE 17 — §12 Cash Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestCashFlow:
    """RULE 17: raw provider keys, FCF consistency."""

    @pytest.mark.parametrize("bad_text", [
        "Source: yfinance key operating_cash_flow",
        "capital_expenditure was -$2.1B",
        "free_cash_flow reached $14.9B",
    ])
    def test_raw_provider_key_warns(self, bad_text):
        sections = {"Cash Flow": bad_text}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        wrns = _warnings_for(result, "cash_flow_raw_provider_key")
        assert len(wrns) == 1

    def test_clean_labels_pass(self):
        sections = {
            "Cash Flow": (
                "Operating cash flow: $18.2B. CapEx: -$2.1B. "
                "Free cash flow: $14.9B (+45% YoY)."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "cash_flow_raw_provider_key")
        assert len(errs) == 0

    def test_fcf_mismatch_with_text_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(free_cash_flow=14.9e9)  # $14.9B
        sections = {
            "Cash Flow": "Free cash flow was $20.0B this quarter, a new record."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _warnings_for(result, "cash_flow_fcf_consistency")
        assert len(errs) == 1

    def test_fcf_matching_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(free_cash_flow=14.9e9)
        sections = {
            "Cash Flow": "Free cash flow reached $14.9B, up 45% YoY."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _warnings_for(result, "cash_flow_fcf_consistency")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RULE 18 — §13 Capital Efficiency
# ═══════════════════════════════════════════════════════════════════════════


class TestCapitalEfficiency:
    """RULE 18: NOT available contradiction, extreme ratios without label."""

    def test_not_available_with_roe_in_metrics_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(roe=85.5, roic=42.3)
        sections = {
            "Capital Efficiency": "ROE: Not available. ROIC: data not retrieved."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _warnings_for(result, "capital_efficiency_not_available_contradiction")
        assert len(errs) == 1

    def test_clean_efficiency_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(roe=85.5, roic=42.3)
        sections = {
            "Capital Efficiency": "ROE: 85.5%. ROIC: 42.3%. Both strong and sustainable."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _warnings_for(result, "capital_efficiency_not_available_contradiction")
        assert len(errs) == 0

    def test_extreme_roe_without_provider_label_blocked(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(roe=250.0)
        sections = {
            "Capital Efficiency": "ROE was 250% this quarter, driven by share buybacks."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "capital_efficiency_extreme_unlabeled")
        assert len(errs) == 1

    def test_extreme_roe_with_provider_label_passes(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(roe=250.0)
        sections = {
            "Capital Efficiency": "ROE: 250% (provider-supplied). Buyback-driven distortion possible."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        errs = _errors_for(result, "capital_efficiency_extreme_unlabeled")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RULE 19 — §15 Guidance
# ═══════════════════════════════════════════════════════════════════════════


class TestGuidance:
    """RULE 19: consensus ≠ guidance, current ≠ guidance, table/narrative."""

    def test_consensus_presented_as_guidance_blocked(self):
        sections = {
            "Guidance": "Analyst consensus estimates suggest revenue guidance of $25B next quarter."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _warnings_for(result, "guidance_consensus_conflated")
        assert len(errs) == 1

    def test_clean_guidance_passes(self):
        sections = {
            "Guidance": (
                "Management guidance: Revenue $24.5B ± 2% for Q2 FY2027. "
                "Analyst consensus: $25.0B (above guidance midpoint)."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs_consensus = _errors_for(result, "guidance_consensus_conflated")
        assert len(errs_consensus) == 0

    def test_current_as_guidance_blocked(self):
        sections = {
            "Guidance": "Current quarter guidance: Revenue was $22.1B."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "guidance_current_as_guidance")
        assert len(errs) == 1

    def test_explicit_no_guidance_for_current_quarter_passes(self):
        sections = {
            "Guidance": (
                "The lack of explicit next-quarter guidance adds uncertainty. "
                "For the investor, this quarter's no guidance posture underlines "
                "the challenge of modeling the company."
            )
        }
        result = validate_pre_render("AAPL", "FY2026 Q2", None, sections)
        errs = _errors_for(result, "guidance_current_as_guidance")
        assert len(errs) == 0

    def test_not_guided_but_narrative_has_guidance_warned(self):
        sections = {
            "Guidance": (
                "Revenue guidance: Not guided.\n\n"
                "Management guided for Q2 revenue of $24.5B, implying 11% sequential growth."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        warns = _warnings_for(result, "guidance_table_narrative_contradiction")
        assert len(warns) == 1

    def test_not_guided_without_narrative_passes(self):
        sections = {
            "Guidance": "Revenue: Not guided. The company does not provide quarterly guidance."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "guidance_table_narrative_contradiction")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# RULE 20 — §16 Backlog
# ═══════════════════════════════════════════════════════════════════════════


class TestBacklog:
    """RULE 20: no forced backlog, no 'Not available', no empty section."""

    def test_backlog_na_blocked(self):
        sections = {"Backlog": "Backlog is Not available for this quarter."}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "backlog_na_language")
        assert len(errs) == 1

    def test_professional_non_disclosure_passes(self):
        sections = {
            "Backlog": "The company does not publicly disclose backlog figures."
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "backlog_na_language")
        assert len(errs) == 0

    def test_empty_backlog_blocked(self):
        sections = {"Backlog": "• \n\n"}
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "backlog_empty_or_forced")
        assert len(errs) == 1

    def test_substantive_backlog_passes(self):
        sections = {
            "Backlog": (
                "Order backlog: $12.4B (+35% YoY). Coverage: 2.1 quarters of revenue. "
                "Contract firmness: High — 85% under non-cancellable purchase agreements."
            )
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs_empty = _errors_for(result, "backlog_empty_or_forced")
        errs_na = _errors_for(result, "backlog_na_language")
        assert len(errs_empty) == 0
        assert len(errs_na) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestMultiRuleIntegration:
    """Multiple rules fire correctly on various sections."""

    def test_all_sections_clean_pass(self):
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics(
            eps_actual=6.50, eps_estimate=6.20,
            revenue_actual=22.1e9, revenue_estimate=22.0e9,
            gross_margin=72.4, operating_margin=64.8, operating_income=14.3e9,
            net_income_quarterly=12.9e9,
            free_cash_flow=14.9e9,
            roe=85.5, roic=42.3, roa=32.1,
        )
        sections = {
            "EPS & Revenue": "EPS beat consensus by 4.8%. Revenue $22.1B.",
            "Operating Metrics": "Gross margin 72.4% (+120bps). Operating margin 64.8% (+220bps).",
            "Cash Flow": "OCF $18.2B. CapEx $2.1B. FCF $14.9B.",
            "Capital Efficiency": "ROE 85.5%. ROIC 42.3%. Strong and sustainable.",
            "Guidance": "Management guides Q2 revenue $24.5B ± 2%. Consensus sits at $25.0B.",
            "Backlog": "Order backlog $12.4B, covering 2.1 quarters of revenue.",
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", metrics, sections)
        rule16_20_errors = [
            e for e in result.errors
            if e.check.startswith((
                "operating_metrics_", "cash_flow_", "capital_efficiency_",
                "guidance_", "backlog_"
            ))
        ]
        assert len(rule16_20_errors) == 0, \
            f"All sections clean should have 0 errors, got: {[(e.check, e.detail[:50]) for e in rule16_20_errors]}"
