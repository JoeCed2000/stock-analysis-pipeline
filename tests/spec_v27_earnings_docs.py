"""§6 Earnings Documents Checklist — spec tests.

Tests for EarningsDocumentsChecklist model, builder, and RULE 25 validator gate.
"""

import pytest
from backend.earnings_deep_dive.report_model import EarningsDocumentsChecklist, EarningsDeepDiveReport
from backend.earnings_deep_dive.pre_render_validator import (
    validate_pre_render,
    ValidationWarning,
    ValidationResult,
)


# ── Model tests ────────────────────────────────────────────────────────


class TestEarningsDocumentsChecklistModel:
    """Model creation, validation, and properties."""

    def test_creates_minimal_checklist(self):
        c = EarningsDocumentsChecklist()
        assert c.transcript_status is None
        assert c.sec_filing_status is None
        assert c.consensus_status is None
        assert c.critical_sources_available is False
        assert c.transcript_available is False

    def test_all_documents_retrieved(self):
        c = EarningsDocumentsChecklist(
            transcript_status="retrieved",
            transcript_source_id="S1",
            transcript_period_match=True,
            sec_filing_status="retrieved",
            sec_filing_source_id="S2",
            sec_filing_period_match=True,
            consensus_status="retrieved",
            consensus_source_id="S3",
            consensus_period_match=True,
            presentation_status="retrieved",
            press_release_status="retrieved",
            all_documents_match_period=True,
        )
        assert c.critical_sources_available is True
        assert c.transcript_available is True
        assert c.presentation_available is True
        assert c.press_release_available is True

    def test_critical_sources_unavailable(self):
        c = EarningsDocumentsChecklist(
            sec_filing_status="unavailable",
            consensus_status="unavailable",
        )
        assert c.critical_sources_available is False

    def test_transcript_unavailable(self):
        c = EarningsDocumentsChecklist(transcript_status="unavailable")
        assert c.transcript_available is False

    def test_presentation_unavailable(self):
        c = EarningsDocumentsChecklist(presentation_status="unavailable")
        assert c.presentation_available is False

    def test_press_release_unavailable(self):
        c = EarningsDocumentsChecklist(press_release_status="unavailable")
        assert c.press_release_available is False

    def test_missing_document_public_note_present(self):
        c = EarningsDocumentsChecklist(
            sec_filing_status="retrieved",
            consensus_status="unavailable",
            missing_document_public_note="Some documents were unavailable",
        )
        assert c.missing_document_public_note is not None
        assert "unavailable" in c.missing_document_public_note.lower()

    def test_period_match_flags(self):
        c = EarningsDocumentsChecklist(
            transcript_period_match=True,
            presentation_period_match=False,
            press_release_period_match=False,
            sec_filing_period_match=True,
            consensus_period_match=True,
        )
        assert c.transcript_period_match is True
        assert c.sec_filing_period_match is True
        assert c.consensus_period_match is True
        assert c.presentation_period_match is False

    def test_integration_in_report(self):
        """EarningsDocumentsChecklist can be attached to EarningsDeepDiveReport."""
        checklist = EarningsDocumentsChecklist(
            transcript_status="retrieved",
            sec_filing_status="retrieved",
            consensus_status="retrieved",
        )
        report = EarningsDeepDiveReport(
            ticker="NVDA",
            company="NVIDIA",
            quarter="Q1 FY2026",
            language="en",
            generated_at="2026-05-29T00:00:00Z",
            title="Test",
            sections=[],
            earnings_documents=checklist,
        )
        assert report.earnings_documents is not None
        assert report.earnings_documents.transcript_available is True


# ── RULE 25 validator gate tests ───────────────────────────────────────


class TestRule25EarningsDocumentsGate:
    """RULE 25: No claims from missing documents."""

    def test_25a_missing_transcript_blocks_management_commentary(self):
        ed = EarningsDocumentsChecklist(
            transcript_status="unavailable",
            sec_filing_status="retrieved",
            consensus_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "Management & Tone": "The CEO said Q2 guidance would be strong. During the call, management guided higher."
            },
            earnings_documents=ed,
        )
        assert result.passed is False
        assert any("transcript" in e.check for e in result.errors)

    def test_25a_transcript_available_no_warning(self):
        ed = EarningsDocumentsChecklist(
            transcript_status="retrieved",
            sec_filing_status="retrieved",
            consensus_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "Management & Tone": "The CEO said Q2 guidance would be strong."
            },
            earnings_documents=ed,
        )
        # No error because transcript IS available
        assert not any("transcript" in e.check for e in result.errors)

    def test_25b_missing_presentation_blocks_presentation_claims(self):
        ed = EarningsDocumentsChecklist(
            presentation_status="unavailable",
            sec_filing_status="retrieved",
            consensus_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "Operating Metrics": "According to the earnings presentation, Data Center revenue grew 50% YoY."
            },
            earnings_documents=ed,
        )
        assert result.passed is False
        assert any("presentation" in e.check for e in result.errors)

    def test_25c_missing_consensus_blocks_beat_miss(self):
        ed = EarningsDocumentsChecklist(
            consensus_status="unavailable",
            sec_filing_status="retrieved",
            transcript_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "EPS & Revenue": "EPS of $2.94 beat consensus estimates by 5%."
            },
            earnings_documents=ed,
        )
        assert result.passed is False
        assert any("consensus" in e.check for e in result.errors)

    def test_25c_not_calculable_no_warning(self):
        """'not calculable' wording bypasses the beat/miss gate."""
        ed = EarningsDocumentsChecklist(
            consensus_status="unavailable",
            sec_filing_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "EPS & Revenue": "EPS beat/miss is not calculable from reviewed sources."
            },
            earnings_documents=ed,
        )
        assert not any("consensus" in e.check for e in result.errors)

    def test_25d_missing_sec_filing_blocks_sec_citations(self):
        ed = EarningsDocumentsChecklist(
            sec_filing_status="unavailable",
            consensus_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "Financials": "According to the SEC 10-Q filing, revenue was $22.4B."
            },
            earnings_documents=ed,
        )
        assert result.passed is False
        assert any("sec_filing" in e.check for e in result.errors)

    def test_25d_sec_available_no_warning(self):
        ed = EarningsDocumentsChecklist(
            sec_filing_status="retrieved",
            consensus_status="retrieved",
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "Financials": "According to the SEC 10-Q filing, revenue was $22.4B."
            },
            earnings_documents=ed,
        )
        assert not any("sec_filing" in e.check for e in result.errors)

    def test_null_earnings_documents_noop(self):
        """When earnings_documents is None, RULE 25 is a no-op."""
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=None,
            section_analysis={
                "Management & Tone": "The CEO said this on the call.",
                "EPS & Revenue": "Beat consensus by 5%.",
            },
            earnings_documents=None,
        )
        # Should not produce any RULE 25 errors
        assert not any("earnings_docs" in e.check for e in result.errors)

    def test_all_sources_available_no_errors(self):
        ed = EarningsDocumentsChecklist(
            transcript_status="retrieved",
            transcript_source_id="S1",
            presentation_status="retrieved",
            press_release_status="retrieved",
            sec_filing_status="retrieved",
            sec_filing_source_id="S2",
            consensus_status="retrieved",
            all_documents_match_period=True,
        )
        # Provide EPS/revenue metrics via FinancialMetrics so metric_map works
        from backend.earnings_deep_dive.report_model import FinancialMetrics
        metrics = FinancialMetrics(
            eps_actual=2.94,
            eps_estimate=2.80,
            revenue_actual=22400000000.0,
            revenue_estimate=22000000000.0,
            eps_actual_display='$2.94',
            eps_estimate_display='$2.80',
            revenue_actual_display='$22.4B',
            revenue_estimate_display='$22.0B',
        )
        result = validate_pre_render(
            ticker="NVDA",
            quarter="Q1 FY2026",
            metrics=metrics,
            section_analysis={
                "Management & Tone": "CEO stated on the call that demand is strong.",
                "EPS & Revenue": "EPS of $2.94 beat consensus of $2.80 by 5%.",
                "Financials": "SEC 10-Q shows revenue of $22.4B.",
            },
            earnings_documents=ed,
        )
        assert result.passed is True
