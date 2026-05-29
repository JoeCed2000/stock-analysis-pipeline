"""§7-8 Company Overview gates — spec tests.

Tests RULE 31 (completeness) and RULE 32 (layer separation).
"""

import pytest
from backend.earnings_deep_dive.report_model import (
    CompanyOverview,
    CompanyProfile,
    CompetitorRef,
    CompanyClaim,
)
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


def _make_minimal_co(**kwargs):
    """Build a minimal CompanyOverview for testing."""
    return CompanyOverview(
        company_profile=CompanyProfile(name="NVIDIA", ticker="NVDA"),
        **kwargs,
    )


class TestRule31CompanyOverviewCompleteness:
    """RULE 31: CO must have competitors, segments, strengths/weaknesses."""

    def test_31a_no_competitors_blocked(self):
        co = _make_minimal_co(competitors=[])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=co,
        )
        assert result.passed is False
        assert any("no_competitors" in e.check for e in result.errors)

    def test_31a_with_competitors_passes(self):
        co = _make_minimal_co(competitors=[
            CompetitorRef(competitor_name="AMD", text_en="GPU competitor", source_id="S1"),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=co,
        )
        assert not any("no_competitors" in e.check for e in result.errors)

    def test_31b_no_segments_blocked(self):
        co = _make_minimal_co(business_segments=[])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=co,
        )
        assert result.passed is False
        assert any("no_segments" in e.check for e in result.errors)

    def test_31c_no_strengths_or_weaknesses_blocked(self):
        co = _make_minimal_co(
            strengths_vs_competitors="",
            weaker_areas_vs_competitors="",
        )
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=co,
        )
        assert result.passed is False
        assert any("no_strengths_weaknesses" in e.check for e in result.errors)

    def test_31d_unsourced_claims_blocked(self):
        co = _make_minimal_co(company_claims=[
            CompanyClaim(claim_id="C1", text_en="NVIDIA dominates AI", source_id=""),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=co,
        )
        assert result.passed is False
        assert any("unsourced_claims" in e.check for e in result.errors)

    def test_31d_sourced_claims_pass(self):
        co = _make_minimal_co(company_claims=[
            CompanyClaim(claim_id="C1", text_en="NVIDIA dominates AI", source_id="S1"),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=co,
        )
        assert not any("unsourced_claims" in e.check for e in result.errors)

    def test_null_company_overview_noop(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            company_overview=None,
        )
        assert not any("company_overview" in e.check for e in result.errors)


class TestRule32LayerSeparation:
    """RULE 32: Company Overview must not contain quarterly beat/miss."""

    def test_32_quarterly_beat_miss_in_co_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Company Overview": "NVIDIA beat consensus estimates in Q1 with strong Data Center growth.",
            },
        )
        assert result.passed is False
        assert any("quarterly_language_leak" in e.check for e in result.errors)

    def test_32_quarterly_metric_without_label_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Company Overview": "NVIDIA's Q1 revenue grew by 15% driven by AI demand.",
            },
        )
        assert result.passed is False
        assert any("unlabeled_quarterly_metric" in e.check for e in result.errors)

    def test_32_strategic_language_passes(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Company Overview": (
                    "NVIDIA is the global leader in GPU computing. "
                    "TTM revenue reached $120B driven by Data Center demand. "
                    "The company's annual growth rate exceeds 50%."
                ),
            },
        )
        assert not any("quarterly_language_leak" in e.check for e in result.errors)
        assert not any("unlabeled_quarterly_metric" in e.check for e in result.errors)

    def test_32_no_co_section_passes(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"EPS & Revenue": "EPS beat consensus."},
        )
        assert not any("company_overview" in e.check for e in result.errors)
