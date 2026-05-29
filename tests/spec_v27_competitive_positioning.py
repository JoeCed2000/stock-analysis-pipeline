"""§17 Competitive Positioning — spec tests."""

import pytest
from backend.earnings_deep_dive.report_model import (
    CompetitivePositioning,
    CompetitivePositioningEntry,
    EarningsDeepDiveReport,
)
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


class TestCompetitivePositioningModel:
    def test_creates_entry(self):
        e = CompetitivePositioningEntry(
            competitor="AMD",
            type="direct",
            area_of_competition="Data Center GPUs",
            competitor_strength="Strong CDNA architecture",
            target_company_advantage="CUDA ecosystem lock-in",
            target_company_weakness="Lower market share in inference",
            risk_to_target_company="AMD gaining cloud provider adoption",
            source_id="S1",
            investor_implication="Monitor AMD Instinct MI400 launch",
        )
        assert e.competitor == "AMD"
        assert e.type == "direct"
        assert e.source_id == "S1"

    def test_creates_empty_positioning(self):
        cp = CompetitivePositioning()
        assert cp.entries == []
        assert cp.direct_competitors == []
        assert cp.valuation_peers == []
        assert cp.has_separated_types is True

    def test_direct_and_valuation_peers_separated(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(competitor="AMD", type="direct"),
            CompetitivePositioningEntry(competitor="INTC", type="direct"),
            CompetitivePositioningEntry(competitor="AVGO", type="valuation_peer"),
        ])
        assert len(cp.direct_competitors) == 2
        assert len(cp.valuation_peers) == 1
        assert cp.has_separated_types is True

    def test_single_type_not_mixed(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(competitor="AMD", type="direct"),
        ])
        assert cp.has_separated_types is True

    def test_integration_in_report(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(competitor="AMD", type="direct", source_id="S1"),
        ])
        report = EarningsDeepDiveReport(
            ticker="NVDA", company="NVIDIA", quarter="Q1 FY2026",
            language="en", generated_at="2026-05-29T00:00:00Z",
            title="Test", sections=[],
            competitive_positioning=cp,
        )
        assert report.competitive_positioning is not None
        assert len(report.competitive_positioning.entries) == 1


class TestRule29CompetitivePositioningGate:
    def test_29a_mixed_types_without_separator_blocked(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(competitor="AMD", type="direct", source_id="S1"),
            CompetitivePositioningEntry(competitor="AVGO", type="valuation_peer", source_id="S2"),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Competitors": "AMD competes in GPUs. AVGO is a peer for valuation.",
            },
            competitive_positioning=cp,
        )
        assert result.passed is False
        assert any("mixed_types_no_separator" in e.check for e in result.errors)

    def test_29a_with_separator_no_warning(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(competitor="AMD", type="direct", source_id="S1"),
            CompetitivePositioningEntry(competitor="AVGO", type="valuation_peer", source_id="S2"),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Competitors": (
                    "Direct competitors: AMD (GPUs). "
                    "Valuation peers (separately from operating competitors): AVGO."
                ),
            },
            competitive_positioning=cp,
        )
        assert not any("mixed_types_no_separator" in e.check for e in result.errors)

    def test_29b_incomplete_entry_blocked(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(competitor="AMD"),  # No type, no source
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            competitive_positioning=cp,
        )
        assert result.passed is False
        assert any("incomplete_entries" in e.check for e in result.errors)

    def test_29b_complete_entry_no_warning(self):
        cp = CompetitivePositioning(entries=[
            CompetitivePositioningEntry(
                competitor="AMD", type="direct", source_id="S1",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            competitive_positioning=cp,
        )
        assert not any("incomplete_entries" in e.check for e in result.errors)

    def test_29c_generic_comparison_without_data_blocked(self):
        cp = CompetitivePositioning(entries=[])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Competitors": "NVIDIA is similar to other semiconductor companies. Comparable to industry standard.",
            },
            competitive_positioning=cp,
        )
        assert result.passed is False
        assert any("generic_no_data" in e.check for e in result.errors)

    def test_null_competitive_positioning_noop(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Competitors": "Generic comparison with industry standard.",
            },
            competitive_positioning=None,
        )
        assert not any("competitive_positioning" in e.check for e in result.errors)
