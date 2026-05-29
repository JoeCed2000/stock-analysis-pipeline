"""§18 Management Analysis — spec tests."""

import pytest
from backend.earnings_deep_dive.report_model import (
    ManagementAnalysis,
    EarningsDeepDiveReport,
)
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


class TestManagementAnalysisModel:
    def test_creates_empty(self):
        m = ManagementAnalysis()
        assert m.management_strengths == []
        assert m.management_weaknesses_or_risks == []

    def test_with_strengths_and_evidence(self):
        m = ManagementAnalysis(
            management_strengths=["Strong capital allocation track record"],
            management_weaknesses_or_risks=["Key-person risk: founder-led"],
            evidence=["10-year ROIC above cost of capital", "SEC filings show insider sales"],
            source_id="S1",
            investor_implication="Monitor succession planning",
            what_to_monitor="Insider trading patterns, board composition changes",
        )
        assert len(m.management_strengths) == 1
        assert len(m.management_weaknesses_or_risks) == 1
        assert len(m.evidence) == 2
        assert m.source_id == "S1"

    def test_integration_in_report(self):
        ma = ManagementAnalysis(
            management_strengths=["Disciplined R&D investment"],
            evidence=["R&D efficiency ratio analysis"],
        )
        report = EarningsDeepDiveReport(
            ticker="NVDA", company="NVIDIA", quarter="Q1 FY2026",
            language="en", generated_at="2026-05-29T00:00:00Z",
            title="Test", sections=[],
            management_analysis=ma,
        )
        assert report.management_analysis is not None
        assert len(report.management_analysis.management_strengths) == 1


class TestRule28ManagementAnalysisGate:
    def test_28a_claims_without_evidence_blocked(self):
        ma = ManagementAnalysis(
            management_strengths=["Great leadership"],
            evidence=[],  # No evidence!
        )
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            management_analysis=ma,
        )
        assert result.passed is False
        assert any("no_evidence" in e.check for e in result.errors)

    def test_28a_claims_with_evidence_no_warning(self):
        ma = ManagementAnalysis(
            management_strengths=["Great leadership"],
            evidence=["Consistent ROIC above 20% for 5 years"],
        )
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            management_analysis=ma,
        )
        assert not any("no_evidence" in e.check for e in result.errors)

    def test_28a_empty_no_warning(self):
        ma = ManagementAnalysis()  # No claims = no evidence needed
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            management_analysis=ma,
        )
        assert not any("no_evidence" in e.check for e in result.errors)

    def test_28b_psychological_speculation_blocked(self):
        ma = ManagementAnalysis(
            management_strengths=["Visionary leader"],
            management_weaknesses_or_risks=["CEO is a narcissist who ignores critics"],
            evidence=["Board meeting minutes"],
        )
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            management_analysis=ma,
        )
        assert result.passed is False
        assert any("psychological_speculation" in e.check for e in result.errors)

    def test_28b_text_section_psych_blocked(self):
        ma = ManagementAnalysis(
            management_strengths=["Good track record"],
            evidence=["SEC filings"],
        )
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Management & Tone": "The CEO shows megalomaniac tendencies.",
            },
            management_analysis=ma,
        )
        assert result.passed is False
        assert any("psychological_speculation_in_text" in e.check for e in result.errors)

    def test_null_management_analysis_noop(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Management & Tone": "CEO is a narcissist.",
            },
            management_analysis=None,
        )
        assert not any("management_analysis" in e.check for e in result.errors)
