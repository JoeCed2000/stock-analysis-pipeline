"""§3 Report Period Consistency — tests for ReportPeriodContext, builder, and gate.

covers corrections.txt §3 requirements:
- ReportPeriodContext model creation and validation
- _parse_fiscal_quarter / _try_parse_quarter parsing
- _build_report_period_context integration
- SA_REPORT_PERIOD_CONSISTENCY_GATE rules (11a-11e)
"""

import pytest
from datetime import datetime, timezone


# ── ReportPeriodContext model ──────────────────────────────────────────────


class TestReportPeriodContextModel:
    """Test the ReportPeriodContext Pydantic model."""

    def test_valid_context(self):
        from backend.earnings_deep_dive.report_model import ReportPeriodContext
        ctx = ReportPeriodContext(
            ticker="NVDA",
            company_name="NVIDIA Corp",
            fiscal_year=2026,
            fiscal_quarter=1,
            filing_period="FY2026 Q1",
            report_title_period_label="Q1 2026",
            display_period_label="FY2026 Q1 (Period ended 2026-04-27)",
        )
        assert ctx.is_valid
        assert ctx.ticker == "NVDA"
        assert ctx.fiscal_year == 2026
        assert ctx.fiscal_quarter == 1

    def test_minimal_context_is_invalid(self):
        from backend.earnings_deep_dive.report_model import ReportPeriodContext
        ctx = ReportPeriodContext(ticker="NVDA", company_name="NVDA")
        assert not ctx.is_valid

    def test_context_without_title_label_is_invalid(self):
        from backend.earnings_deep_dive.report_model import ReportPeriodContext
        ctx = ReportPeriodContext(
            ticker="NVDA", company_name="NVDA",
            fiscal_year=2026, fiscal_quarter=1,
        )
        assert not ctx.is_valid

    def test_period_context_in_report_model(self):
        from backend.earnings_deep_dive.report_model import (
            EarningsDeepDiveReport,
            ReportPeriodContext,
        )
        ctx = ReportPeriodContext(
            ticker="NVDA", company_name="NVDA",
            fiscal_year=2026, fiscal_quarter=1,
            report_title_period_label="Q1 2026",
        )
        report = EarningsDeepDiveReport(
            ticker="NVDA", company="NVDA", quarter="FY2026 Q1",
            language="en", generated_at="2026-01-01T00:00:00Z",
            title="NVDA (NVDA) - Earnings Deep-Dive (FY2026 Q1)",
            sections=[],
            period_context=ctx,
        )
        assert report.period_context is not None
        assert report.period_context.is_valid
        assert report.period_context.fiscal_year == 2026


# ── Quarter parsing ────────────────────────────────────────────────────────


class TestQuarterParsing:
    """Test _parse_fiscal_quarter (mapper) and _try_parse_quarter (validator)."""

    @pytest.mark.parametrize("label,expected", [
        ("FY2026 Q1", (2026, 1)),
        ("FY2025 Q4", (2025, 4)),
        ("2026Q1", (2026, 1)),
        ("2025Q3", (2025, 3)),
        ("Q1 2026", (2026, 1)),
        ("Q4 2025", (2025, 4)),
        ("FY 2027 Q2", (2027, 2)),  # extra space
    ])
    def test_parse_valid_labels(self, label, expected):
        from backend.earnings_deep_dive.mapper import _parse_fiscal_quarter
        assert _parse_fiscal_quarter(label) == expected

    @pytest.mark.parametrize("label", [
        "",
        "garbage",
        "latest quarter",
        "FY2026",       # no quarter
        "Q1",           # no year
        "2026-Q1",      # wrong separator
    ])
    def test_parse_invalid_returns_none(self, label):
        from backend.earnings_deep_dive.mapper import _parse_fiscal_quarter
        assert _parse_fiscal_quarter(label) == (None, None)

    def test_try_parse_matches_parse(self):
        """_try_parse_quarter (validator) should produce same results as _parse_fiscal_quarter (mapper)."""
        from backend.earnings_deep_dive.mapper import _parse_fiscal_quarter
        from backend.earnings_deep_dive.pre_render_validator import _try_parse_quarter
        labels = ["FY2026 Q1", "2026Q3", "Q4 2025", "", "garbage"]
        for label in labels:
            assert _try_parse_quarter(label) == _parse_fiscal_quarter(label), \
                f"Mismatch for '{label}': try={_try_parse_quarter(label)} parse={_parse_fiscal_quarter(label)}"


# ── Report period context builder ──────────────────────────────────────────


class TestBuildReportPeriodContext:
    """Test _build_report_period_context in mapper."""

    def test_builds_from_resolved_quarter(self):
        from backend.earnings_deep_dive.mapper import _build_report_period_context
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics()
        ctx = _build_report_period_context(
            ticker="NVDA",
            company_name="NVIDIA Corp",
            resolved_quarter="FY2026 Q1",
            metrics=metrics,
        )
        assert ctx.ticker == "NVDA"
        assert ctx.company_name == "NVIDIA Corp"
        assert ctx.fiscal_year == 2026
        assert ctx.fiscal_quarter == 1
        assert ctx.filing_period == "FY2026 Q1"
        assert ctx.report_title_period_label == "FY2026 Q1"
        assert ctx.comparison_prior_year_period == "FY2025 Q1"
        assert "FY2026 Q1" in ctx.display_period_label

    def test_comparison_prior_year_different_quarter(self):
        from backend.earnings_deep_dive.mapper import _build_report_period_context
        from backend.earnings_deep_dive.schemas import FinancialMetrics
        metrics = FinancialMetrics()
        ctx = _build_report_period_context(
            ticker="AAPL", company_name="Apple Inc.",
            resolved_quarter="FY2025 Q4", metrics=metrics,
        )
        assert ctx.fiscal_year == 2025
        assert ctx.fiscal_quarter == 4
        assert ctx.comparison_prior_year_period == "FY2024 Q4"

    def test_builds_with_metrics_fields(self):
        from backend.earnings_deep_dive.mapper import _build_report_period_context
        from backend.earnings_deep_dive.schemas import FinancialMetrics

        # Create metrics with extra period-related fields
        metrics = FinancialMetrics()
        # Use model_copy to add custom fields
        metrics_dict = metrics.model_dump()
        metrics_dict["filing_date"] = "2026-04-27"
        metrics_dict["earnings_release_date"] = "2026-05-15"
        metrics_dict["guidance_period"] = "FY2027 Q2"
        enriched = FinancialMetrics(**metrics_dict)

        ctx = _build_report_period_context(
            ticker="MSFT", company_name="Microsoft Corp",
            resolved_quarter="FY2026 Q3", metrics=enriched,
        )
        assert ctx.calendar_period is not None
        assert ctx.guidance_period == "FY2027 Q2"
        # Guidance is forward (2027 Q2 > 2026 Q3) — gate should pass


# ── Period consistency gate (RULE 11) ──────────────────────────────────────


class _PC:
    """Lightweight period context for gate tests (mimics _LightPeriodContext)."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_ok_ctx():
    """Standard valid context: all periods match."""
    return _PC(
        ticker="NVDA", company_name="NVDA",
        fiscal_year=2026, fiscal_quarter=1,
        filing_period="FY2026 Q1",
        report_title_period_label="Q1 2026",
        transcript_period="FY2026 Q1",
        press_release_period="FY2026 Q1",
        comparison_prior_year_period="Q1 2025",
        guidance_period=None,
    )


class TestPeriodConsistencyGate:
    """RULE 11: SA_REPORT_PERIOD_CONSISTENCY_GATE"""

    def test_all_matching_passes(self):
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        period_errors = [e for e in result.errors if e.check.startswith("period_")]
        assert len(period_errors) == 0, \
            f"Expected 0 period errors, got: {[(e.check, e.detail) for e in period_errors]}"

    def test_title_filing_mismatch_blocked(self):
        """11a: Title period differs from filing period."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.report_title_period_label = "Q2 2026"  # Wrong quarter
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "period_title_filing_mismatch"]
        assert len(errors) == 1
        assert "Q2 2026" in errors[0].detail
        assert "FY2026 Q1" in errors[0].detail

    def test_guidance_not_forward_looking_blocked(self):
        """11b: Guidance not forward-looking vs current period."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.guidance_period = "FY2025 Q4"  # Before current period FY2026 Q1
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "guidance_not_forward_looking"]
        assert len(errors) == 1
        assert "FY2025 Q4" in errors[0].detail

    def test_guidance_same_period_blocked(self):
        """11b: Guidance same as current period — also blocked."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.guidance_period = "FY2026 Q1"  # Same as current
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "guidance_not_forward_looking"]
        assert len(errors) == 1

    def test_guidance_issued_before_current_release_blocked(self):
        """11f: Forward guidance cannot be stale/recycled from before current earnings release."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.guidance_period = "FY2026 Q2"
        ctx.earnings_release_date = "2026-05-22"
        ctx.guidance_issued_date = "2026-02-21"
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "guidance_stale_issue_date"]
        assert len(errors) == 1
        assert "2026-02-21" in errors[0].detail
        assert "2026-05-22" in errors[0].detail

    def test_guidance_issued_on_current_release_passes(self):
        """11f: Guidance issued on/after the current earnings release is fresh enough."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.guidance_period = "FY2026 Q2"
        ctx.earnings_release_date = "2026-05-22"
        ctx.guidance_issued_date = "2026-05-22"
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        assert not any(e.check == "guidance_stale_issue_date" for e in result.errors)

    def test_transcript_filing_mismatch_blocked(self):
        """11c: Transcript period differs from filing period."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.transcript_period = "FY2025 Q4"  # Wrong quarter
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "period_transcript_filing_mismatch"]
        assert len(errors) == 1

    def test_press_release_filing_mismatch_blocked(self):
        """11d: Press release from different quarter."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.press_release_period = "FY2026 Q2"  # Wrong quarter
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "period_press_release_filing_mismatch"]
        assert len(errors) == 1

    def test_prior_year_mismatch_blocked(self):
        """11e: Comparison prior year is wrong quarter/year."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _make_ok_ctx()
        ctx.comparison_prior_year_period = "Q1 2024"  # Should be Q1 2025 (fy-1)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=ctx)
        errors = [e for e in result.errors if e.check == "period_prior_year_mismatch"]
        assert len(errors) == 1
        assert "2025" in errors[0].detail  # Expected year mentioned

    def test_no_period_context_skips_gate(self):
        """With period_context=None, the gate is a no-op."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {}, period_context=None)
        period_errors = [e for e in result.errors if e.check.startswith("period_")]
        assert len(period_errors) == 0

    def test_unparseable_labels_graceful(self):
        """Unparseable period labels should NOT trigger false errors."""
        from backend.earnings_deep_dive.pre_render_validator import validate_pre_render
        ctx = _PC(
            ticker="NVDA", company_name="NVDA",
            filing_period="latest reported period",  # unparseable
            report_title_period_label="latest reported period",
            transcript_period="latest reported period",
            press_release_period="latest reported period",
            comparison_prior_year_period="Prior Year Quarter",
            guidance_period=None,
        )
        result = validate_pre_render("NVDA", "latest reported period", None, {}, period_context=ctx)
        period_errors = [e for e in result.errors if e.check.startswith("period_")]
        assert len(period_errors) == 0, \
            f"Unparseable labels should be skipped, got: {period_errors}"


# ── Integration: Report model carries period_context ────────────────────────


class TestReportModelIntegration:
    """Period context flows through the full report model."""

    def test_full_report_with_period_context(self):
        from backend.earnings_deep_dive.report_model import (
            EarningsDeepDiveReport,
            ReportPeriodContext,
        )
        ctx = ReportPeriodContext(
            ticker="NVDA",
            company_name="NVIDIA Corp",
            fiscal_year=2026,
            fiscal_quarter=1,
            calendar_period="2026-04-27",
            earnings_release_date="2026-05-22",
            transcript_period="FY2026 Q1",
            press_release_period="FY2026 Q1",
            filing_period="FY2026 Q1",
            comparison_prior_year_period="Q1 2025",
            report_title_period_label="Q1 2026",
            display_period_label="FY2026 Q1 (Period ended 2026-04-27)",
        )
        report = EarningsDeepDiveReport(
            ticker="NVDA", company="NVIDIA Corp", quarter="FY2026 Q1",
            language="en", generated_at="2026-06-01T00:00:00Z",
            title="NVIDIA Corp (NVDA) - Earnings Deep-Dive (FY2026 Q1)",
            sections=[],
            period_context=ctx,
        )
        assert report.period_context is not None
        assert report.period_context.is_valid
        assert report.period_context.fiscal_year == 2026
        assert report.period_context.comparison_prior_year_period == "Q1 2025"
        assert report.period_context.guidance_period is None
        # Backward compat: quarter field still works
        assert report.quarter == "FY2026 Q1"
