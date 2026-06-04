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


# ═══════════════════════════════════════════════════════════════════════
# RULE 34: Content Completeness — all 10 required sections must be present
# ═══════════════════════════════════════════════════════════════════════

class TestRule34ContentCompleteness:
    """RULE 34: Every required section must have non-empty content."""

    def _full_co(self, **overrides):
        """Build a CompanyOverview with all required fields populated."""
        defaults = dict(
            company_profile=CompanyProfile(name="TestCo", ticker="TEST"),
            business_description="A leading technology company serving enterprise markets.",
            revenue_model="Generates revenue from subscription and service fees.",
            business_segments=["Cloud", "Enterprise"],
            growth_drivers=[
                "AI infrastructure demand driven by hyperscaler capex expansion — "
                "supporting data center growth over the next 3-5 years with CAGR >20%",
                "Cloud migration acceleration as enterprises shift workloads from on-premise, "
                "creating recurring subscription revenue streams",
                "International expansion into emerging markets with growing digital adoption",
                "Product cycle innovation with next-gen platform launches driving upgrade cycles",
            ],
            moats=[
                "Full-stack ecosystem integrating hardware, software, and developer tools — "
                "creates high switching costs and deep customer lock-in across the value chain",
                "Massive R&D investment ($8B+/year) maintaining 2-3 year technology lead "
                "with patent portfolio of 10,000+ granted patents",
            ],
            key_kpis=["Market Cap: $1.5T", "Revenue (TTM): $80B", "Gross Margin: 65%"],
            business_risks=[
                "Customer concentration risk: top 3 customers represent 40%+ of revenue, "
                "creating significant exposure to any single client reducing orders",
                "Export control regulations restricting sales to key markets, impacting "
                "revenue by $5-10B annually if fully enforced",
                "Supply chain dependency on single-source foundry with limited alternatives, "
                "creating production risk from geopolitical tension or natural disaster",
            ],
            competitive_position="Market leader in AI computing infrastructure.",
            strengths_vs_competitors="Full-stack platform integration with 15-year ecosystem lead vs nearest competitor at 3 years.",
            weaker_areas_vs_competitors="Higher total cost of ownership vs custom ASIC alternatives for single-workload deployments.",
            ceo_leadership_style="CEO Jane Smith combines technical depth with aggressive execution, prioritizing platform strategy over short-term revenue — evidenced by multi-year R&D commitments at investor days.",
            long_term_vision="Long-term vision focuses on becoming the computing platform for the AI era, expanding from training to inference to edge deployment across every major industry vertical.",
            competitors=[CompetitorRef(competitor_name="AMD", text_en="GPU competitor", source_id="S1")],
            company_claims=[CompanyClaim(claim_id="C1", text_en="Market leader", source_id="S1")],
        )
        defaults.update(overrides)
        return CompanyOverview(**defaults)

    def test_34_all_sections_present_passes(self):
        co = self._full_co()
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        missing = [e for e in result.errors if e.check == "company_overview_missing_section"]
        assert len(missing) == 0, f"Complete CO should not flag missing sections: {missing}"

    @pytest.mark.parametrize("field,label,empty_value", [
        ("business_description", "Company Overview", ""),
        ("revenue_model", "How It Makes Money", ""),
        ("growth_drivers", "Growth Drivers", []),
        ("moats", "Moats", []),
        ("key_kpis", "Key KPIs", []),
        ("business_risks", "Business Risks", []),
        ("strengths_vs_competitors", "Strengths vs Competitors", ""),
        ("weaker_areas_vs_competitors", "Weaknesses vs Competitors", ""),
        ("ceo_leadership_style", "CEO Leadership", ""),
        ("long_term_vision", "Long-Term Vision", ""),
    ])
    def test_34_missing_section_blocked(self, field, label, empty_value):
        co = self._full_co(**{field: empty_value})  # Empty the field
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        missing = [e for e in result.errors if e.check == "company_overview_missing_section"]
        # Find the specific one for this field
        field_errors = [e for e in missing if label in e.detail]
        assert len(field_errors) >= 1, f"Missing '{label}' should be blocked"

    def test_34_null_company_overview_noop(self):
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=None,
        )
        missing = [e for e in result.errors if e.check == "company_overview_missing_section"]
        assert len(missing) == 0


# ═══════════════════════════════════════════════════════════════════════
# RULE 35: Growth Drivers Quality
# ═══════════════════════════════════════════════════════════════════════

class TestRule35GrowthDriversQuality:
    """RULE 35: Growth drivers must be specific and substantive."""

    def test_35_generic_short_driver_blocked(self):
        co = _make_minimal_co(growth_drivers=["Revenue growth: 15% YoY"])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "growth_drivers" in e.check]
        assert len(errors) >= 1, "Short generic driver should be blocked"
        assert errors[0].severity == "error"

    def test_35_generic_pattern_blocked(self):
        co = _make_minimal_co(growth_drivers=[
            "Revenue growth driven by expanding enterprise footprint and market expansion across key verticals with increasing demand"
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "growth_drivers_generic" in e.check]
        # "Revenue growth" at start should trigger generic pattern
        assert len(errors) >= 1

    def test_35_fewer_than_three_drivers_blocked(self):
        co = _make_minimal_co(growth_drivers=[
            "AI infrastructure demand driven by hyperscaler capex expansion over the next 3-5 years"
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        warnings = [w for w in result.warnings if "growth_drivers_insufficient" in w.check]
        assert len(warnings) >= 1

    def test_35_substantive_drivers_pass(self):
        co = _make_minimal_co(growth_drivers=[
            "AI infrastructure demand driven by hyperscaler capex expansion over the next 3-5 years with projected 25% CAGR",
            "Cloud migration acceleration as enterprises shift workloads from on-premise to cloud-native architectures",
            "International expansion into emerging markets with growing digital adoption and mobile-first populations",
            "Product cycle innovation with next-gen platform launches driving customer upgrade cycles",
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "growth_drivers" in e.check]
        assert len(errors) == 0, f"Substantive drivers should pass: {errors}"


# ═══════════════════════════════════════════════════════════════════════
# RULE 36: Moat Quality
# ═══════════════════════════════════════════════════════════════════════

class TestRule36MoatQuality:
    """RULE 36: Moats must be specific and evidenced."""

    def test_36_short_moat_blocked(self):
        co = _make_minimal_co(moats=["Brand recognition"])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "moats" in e.check]
        assert len(errors) >= 1, "Short moat should be blocked"

    def test_36_generic_single_word_moat_blocked(self):
        co = _make_minimal_co(moats=["Switching costs"])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "moats_generic" in e.check]
        assert len(errors) >= 1, "Generic moat without explanation should be flagged"

    def test_36_fewer_than_two_moats_blocked(self):
        co = _make_minimal_co(moats=[
            "Full-stack ecosystem integrating hardware and software creating high switching costs for enterprise customers"
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.warnings if "moats_insufficient" in e.check]
        assert len(errors) >= 1

    def test_36_substantive_moats_pass(self):
        co = _make_minimal_co(moats=[
            "Full-stack ecosystem integrating hardware, software, and developer tools creating high switching costs and deep customer lock-in",
            "Massive R&D investment ($8B+/year) maintaining 2-3 year technology lead with 10,000+ patent portfolio",
            "Proprietary data and training pipeline built over 15 years providing unmatched model accuracy",
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "moats" in e.check]
        assert len(errors) == 0, f"Substantive moats should pass: {errors}"


# ═══════════════════════════════════════════════════════════════════════
# RULE 37: Business Risks Quality
# ═══════════════════════════════════════════════════════════════════════

class TestRule37BusinessRisksQuality:
    """RULE 37: Risks must be substantive, not just market/price risks."""

    def test_37_short_risk_warns(self):
        co = _make_minimal_co(business_risks=["Market volatility"])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        wrns = [w for w in result.warnings if "risks" in w.check]
        assert len(wrns) >= 1

    def test_37_generic_market_risk_warns(self):
        co = _make_minimal_co(business_risks=[
            "Market volatility could impact the stock price significantly in the near term based on macroeconomic conditions and interest rate changes"
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        wrns = [w for w in result.warnings if "risks_generic" in w.check]
        assert len(wrns) >= 1

    def test_37_fewer_than_three_risks_warns(self):
        co = _make_minimal_co(business_risks=[
            "Customer concentration with top 3 clients representing 40% of revenue creating dependency risk"
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        wrns = [w for w in result.warnings if "risks_insufficient" in w.check]
        assert len(wrns) >= 1

    def test_37_substantive_risks_pass(self):
        co = _make_minimal_co(business_risks=[
            "Customer concentration risk: top 3 customers represent 40%+ of revenue, creating significant exposure to any single client reducing orders or switching suppliers",
            "Export control regulations restricting sales to key markets, potentially impacting revenue by $5-10B annually if fully enforced",
            "Supply chain dependency on single-source foundry with limited alternatives, creating production risk from geopolitical tension or natural disaster",
        ])
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "risks" in e.check]
        assert len(errors) == 0, f"Substantive risks should pass: {errors}"


# ═══════════════════════════════════════════════════════════════════════
# RULE 38: CEO Leadership & Vision
# ═══════════════════════════════════════════════════════════════════════

class TestRule38CEOVision:
    """RULE 38: CEO section must be substantive, not boilerplate."""

    def test_38_generic_ceo_blocked(self):
        co = _make_minimal_co(
            ceo_leadership_style="Experienced leader with demonstrated track record of strong execution",
            long_term_vision="Long-term vision focuses on growth and innovation across key markets and technology segments with sustainable value creation",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "ceo_too_generic" in e.check]
        assert len(errors) >= 1, "Generic CEO boilerplate should be blocked"

    def test_38_missing_vision_blocked(self):
        co = _make_minimal_co(
            ceo_leadership_style="CEO Jensen Huang leads with a focus on accelerated computing and platform strategy",
            long_term_vision="",  # Empty
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "vision_missing" in e.check]
        assert len(errors) >= 1, "Empty vision should be blocked"

    def test_38_short_vision_blocked(self):
        co = _make_minimal_co(
            ceo_leadership_style="CEO Jane Smith combines technical depth with aggressive execution",
            long_term_vision="Grow the company.",  # < 30 chars
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "vision_missing" in e.check]
        assert len(errors) >= 1

    def test_38_substantive_ceo_passes(self):
        co = _make_minimal_co(
            ceo_leadership_style="CEO Jane Smith combines technical depth with aggressive execution, prioritizing platform strategy over short-term revenue — evidenced by multi-year R&D commitments announced at the last investor day.",
            long_term_vision="Long-term vision focuses on becoming the computing platform for the AI era, expanding from training to inference to edge deployment across every major industry vertical by 2030.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "ceo_too_generic" in e.check or "vision_missing" in e.check]
        assert len(errors) == 0, f"Substantive CEO should pass: {errors}"


# ═══════════════════════════════════════════════════════════════════════
# RULE 39: Numerical Consistency
# ═══════════════════════════════════════════════════════════════════════

class TestRule39NumericalConsistency:
    """RULE 39: Market cap, P/E, and NaN must not leak or contradict."""

    def test_39_inconsistent_market_cap_blocked(self):
        co = _make_minimal_co(
            business_description="The company has a market cap of $3.2 trillion, making it one of the largest in the world.",
            competitive_position="With a market cap of $2.8 trillion, the company maintains significant scale advantages.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "market_cap_inconsistent" in e.check]
        assert len(errors) >= 1, f"$3.2T vs $2.8T should be flagged: {errors}"

    def test_39_consistent_market_cap_passes(self):
        co = _make_minimal_co(
            business_description="Market cap of $3.2 trillion as of latest close.",
            competitive_position="With a market cap of $3.2 trillion, the company is well-positioned.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "market_cap_inconsistent" in e.check]
        assert len(errors) == 0, f"Consistent values should pass: {errors}"

    def test_39_inconsistent_pe_blocked(self):
        co = _make_minimal_co(
            business_description="Trading at a P/E ratio of 25x, the stock appears reasonably valued.",
            competitive_position="The P/E of 45x reflects growth premium in the AI sector.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "pe_inconsistent" in e.check]
        assert len(errors) >= 1, f"25x vs 45x PE should be flagged: {errors}"

    def test_39_nan_leak_blocked(self):
        co = _make_minimal_co(
            business_description="Revenue was NaN for the quarter due to data issues.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "nan_leak" in e.check]
        assert len(errors) >= 1, "NaN leak should be blocked"

    def test_39_null_leak_blocked(self):
        co = _make_minimal_co(
            business_description="The EPS value is null for this period.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        errors = [e for e in result.errors if "nan_leak" in e.check]
        assert len(errors) >= 1, "null leak should be blocked"


# ═══════════════════════════════════════════════════════════════════════
# RULE 40: Source Quality
# ═══════════════════════════════════════════════════════════════════════

class TestRule40SourceQuality:
    """RULE 40: Sources must be truthful, no fake claims, no raw provider keys."""

    def test_40_fake_coverage_claim_blocked(self):
        co = _make_minimal_co(
            business_description="With 100% source coverage, this analysis is comprehensive.",
        )
        # Empty source_registry (list)
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
            source_registry=[],
        )
        errors = [e for e in result.errors if "fake_source_claim" in e.check]
        assert len(errors) >= 1, "Fake 100% coverage claim should be blocked"

    def test_40_full_coverage_claim_blocked(self):
        co = _make_minimal_co(
            competitive_position="Based on complete source coverage, we have high confidence.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
            source_registry={},
        )
        errors = [e for e in result.errors if "fake_source_claim" in e.check]
        assert len(errors) >= 1

    def test_40_truthful_coverage_passes(self):
        co = _make_minimal_co(
            business_description="Source coverage is adequate.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
            source_registry={"S1": "10-K", "S2": "IR", "S3": "Earnings Call", "S4": "Industry Report", "S5": "Data Provider"},
        )
        errors = [e for e in result.errors if "fake_source_claim" in e.check]
        assert len(errors) == 0

    def test_40_raw_provider_key_warns(self):
        co = _make_minimal_co(
            business_description="The trailingPE of 35x suggests premium valuation based on earningsGrowth trends.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
            source_registry=[],
        )
        wrns = [w for w in result.warnings if "raw_provider_key" in w.check]
        assert len(wrns) >= 1, "Raw provider key 'trailingPE' should be warned"


# ═══════════════════════════════════════════════════════════════════════
# RULE 41: No Markdown Syntax
# ═══════════════════════════════════════════════════════════════════════

class TestRule41NoMarkdown:
    """RULE 41: Raw Markdown syntax must never appear in PDF text fields."""

    def test_41_markdown_heading_warns(self):
        co = _make_minimal_co(
            business_description="### How we make money\n\nThe company generates revenue.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        marks = [w for w in result.warnings if "raw_markdown" in w.check]
        assert len(marks) >= 1, "Markdown heading (###) should be warned"

    def test_41_markdown_bold_warns(self):
        co = _make_minimal_co(
            revenue_model="**Subscription revenue** is the primary source of income.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        marks = [w for w in result.warnings if "raw_markdown" in w.check]
        assert len(marks) >= 1

    def test_41_markdown_table_warns(self):
        co = _make_minimal_co(
            business_description="| Segment | Revenue |\n|---|---|\n| Cloud | $10B |",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        marks = [w for w in result.warnings if "raw_markdown" in w.check]
        assert len(marks) >= 1

    def test_41_markdown_code_warns(self):
        co = _make_minimal_co(
            revenue_model="```Revenue model details```",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        marks = [w for w in result.warnings if "raw_markdown" in w.check]
        assert len(marks) >= 1

    def test_41_markdown_link_warns(self):
        co = _make_minimal_co(
            business_description="See [the annual report](https://example.com/10k) for details.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        marks = [w for w in result.warnings if "raw_markdown" in w.check]
        assert len(marks) >= 1

    def test_41_clean_text_passes(self):
        co = _make_minimal_co(
            business_description="The company generates revenue from cloud services and enterprise software.",
            revenue_model="Primary revenue comes from subscription fees and professional services.",
            competitive_position="Market leader in AI computing with significant scale advantages.",
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
        )
        marks = [w for w in result.warnings if "raw_markdown" in w.check]
        assert len(marks) == 0, f"Clean text should pass: {marks}"


# ═══════════════════════════════════════════════════════════════════════
# Integration: All rules fire together without interference
# ═══════════════════════════════════════════════════════════════════════

class TestCompanyOverviewFullValidation:
    """End-to-end: multiple rules firing on the same CompanyOverview."""

    def test_multiple_violations_all_reported(self):
        """A broken CO should trigger multiple rules simultaneously."""
        co = _make_minimal_co(
            business_description="### Overview\n\nThe company operates in two segments with trailingPE of 25x.",
            revenue_model="",
            growth_drivers=["Revenue growth"],
            moats=["Brand"],
            business_risks=["Market volatility"],
            ceo_leadership_style="Experienced leader with strong leadership qualities.",
            long_term_vision="",
            competitors=[],
            business_segments=[],
            strengths_vs_competitors="",
            weaker_areas_vs_competitors="",
            key_kpis=[],
        )
        result = validate_pre_render(
            ticker="TEST", quarter="Q1 2026", metrics=None,
            section_analysis={}, company_overview=co,
            source_registry=[],
        )
        error_checks = {e.check for e in result.errors}
        all_checks = error_checks | {w.check for w in result.warnings}
        # Should have at least 8 distinct checks firing (errors + warnings)
        assert len(all_checks) >= 8, (
            f"Expected 8+ distinct rules to fire on broken CO, got {len(all_checks)}: {all_checks}"
        )
        # Verify blocking error gates fire
        assert "company_overview_no_competitors" in error_checks  # RULE 31a
        assert "company_overview_no_segments" in error_checks      # RULE 31b
        assert "company_overview_no_strengths_weaknesses" in error_checks  # RULE 31c
        assert "company_overview_missing_section" in all_checks  # RULE 34
        assert "company_overview_growth_drivers_generic" in all_checks  # RULE 35
        assert "company_overview_ceo_too_generic" in all_checks  # RULE 38
        assert "company_overview_vision_missing" in all_checks   # RULE 38
        assert "company_overview_raw_markdown" in all_checks     # RULE 41 (now warning)
