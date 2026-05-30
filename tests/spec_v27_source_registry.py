"""§5 Source Registry — spec tests.

Tests for SourceRegistry/SourceRegistryEntry models and RULE 26 validator gate.
"""

import pytest
from backend.earnings_deep_dive.report_model import (
    SourceRegistry,
    SourceRegistryEntry,
    EarningsDeepDiveReport,
)
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


# ── Model tests ────────────────────────────────────────────────────────


class TestSourceRegistryModel:
    """SourceRegistry and SourceRegistryEntry model tests."""

    def test_creates_entry(self):
        e = SourceRegistryEntry(
            source_id="S1",
            human_label="SEC 10-Q Filing",
            provider="sec_edgar",
            source_type="SEC_filing",
            status="used",
            public_display_label="SEC EDGAR Filing (10-Q)",
        )
        assert e.source_id == "S1"
        assert e.human_label == "SEC 10-Q Filing"
        assert e.status == "used"
        assert e.public_display_label == "SEC EDGAR Filing (10-Q)"

    def test_entry_defaults(self):
        e = SourceRegistryEntry(source_id="S2", human_label="Test Source")
        assert e.status == "candidate"
        assert e.period_matched is False
        assert e.fields_used == []
        assert e.public_display_label is None

    def test_creates_empty_registry(self):
        r = SourceRegistry()
        assert r.entries == []
        assert r.used_sources == []
        assert r.used_count == 0
        assert r.has_transcript is False
        assert r.has_sec_filing is False
        assert r.has_consensus is False

    def test_used_sources_filtered(self):
        r = SourceRegistry(entries=[
            SourceRegistryEntry(source_id="S1", human_label="SEC", status="used"),
            SourceRegistryEntry(source_id="S2", human_label="Transcript", status="used"),
            SourceRegistryEntry(source_id="S3", human_label="Candidate", status="candidate"),
        ])
        assert r.used_count == 2
        assert len(r.used_sources) == 2
        assert r.used_sources[0].source_id == "S1"

    def test_has_transcript(self):
        r = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="Trans",
                source_type="transcript", status="used",
            ),
        ])
        assert r.has_transcript is True
        assert r.has_sec_filing is False

    def test_has_sec_filing(self):
        r = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S2", human_label="SEC",
                source_type="SEC_filing", status="used",
            ),
        ])
        assert r.has_sec_filing is True

    def test_has_consensus(self):
        r = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S3", human_label="Yahoo",
                source_type="consensus", status="used",
            ),
        ])
        assert r.has_consensus is True

    def test_get_label_returns_public_display_label(self):
        r = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="Raw",
                public_display_label="SEC Filing Q1 2026",
                status="used",
            ),
        ])
        assert r.get_label("S1") == "SEC Filing Q1 2026"

    def test_get_label_fallback_to_human_label(self):
        r = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="Yahoo Finance",
                public_display_label=None,
                status="used",
            ),
        ])
        assert r.get_label("S1") == "Yahoo Finance"

    def test_get_label_unknown_returns_none(self):
        r = SourceRegistry()
        assert r.get_label("S99") is None

    def test_integration_in_report(self):
        reg = SourceRegistry(entries=[
            SourceRegistryEntry(source_id="S1", human_label="SEC", status="used"),
        ])
        report = EarningsDeepDiveReport(
            ticker="NVDA", company="NVIDIA", quarter="Q1 FY2026",
            language="en", generated_at="2026-05-29T00:00:00Z",
            title="Test", sections=[],
            source_registry=reg,
        )
        assert report.source_registry is not None
        assert report.source_registry.used_count == 1


# ── RULE 26 validator gate tests ───────────────────────────────────────


class TestRule26SourceRegistryGate:
    """RULE 26: No raw provider keys, no unmapped source refs, used-only citations."""

    def test_26a_raw_provider_key_leak_warns(self):
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="Yahoo",
                status="used", public_display_label="Yahoo Finance",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "EPS & Revenue": "EPS data from yfinance key: eps_actual.",
            },
            source_registry=sr,
        )
        assert result.passed is True
        assert any("raw_provider_key" in w.check for w in result.warnings)

    def test_26a_clean_text_no_warning(self):
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="Yahoo",
                status="used", public_display_label="Yahoo Finance",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "EPS & Revenue": "EPS data sourced from Yahoo Finance.",
            },
            source_registry=sr,
        )
        assert not any("raw_provider_key" in e.check for e in result.errors)

    def test_26b_unmapped_source_refs_blocked(self):
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S2", human_label="SEC",
                status="used", public_display_label="SEC EDGAR",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "As shown in S1 and S2, revenue grew. S3 confirms margins.",
            },
            source_registry=sr,
        )
        assert result.passed is False
        assert any("unmapped_source_refs" in e.check for e in result.errors)

    def test_26b_all_refs_mapped_no_warning(self):
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="SEC",
                status="used", public_display_label="SEC Filing",
            ),
            SourceRegistryEntry(
                source_id="S2", human_label="Yahoo",
                status="used", public_display_label="Yahoo Finance",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "As shown in S1 and S2, revenue grew.",
            },
            source_registry=sr,
        )
        assert not any("unmapped_source_refs" in e.check for e in result.errors)

    def test_26c_candidate_cited_as_evidence_blocked(self):
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="Candidate Source",
                status="candidate", public_display_label="Candidate",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "According to S1, revenue was $22.4B.",
            },
            source_registry=sr,
        )
        assert result.passed is False
        assert any("candidate_cited" in e.check for e in result.errors)

    def test_26c_used_source_cited_no_warning(self):
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1", human_label="SEC",
                status="used", public_display_label="SEC Filing",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "According to S1, revenue was $22.4B.",
            },
            source_registry=sr,
        )
        assert not any("candidate_cited" in e.check for e in result.errors)

    def test_null_source_registry_noop(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "yfinance key: test. S1 shows data.",
            },
            source_registry=None,
        )
        assert not any("source_registry" in e.check for e in result.errors)
