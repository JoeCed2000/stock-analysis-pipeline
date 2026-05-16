"""Tests for source granularity — claim→source traceability."""

import pytest
from backend.earnings_deep_dive.report_model import (
    SourceRef,
    ClaimSource,
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    GroundingLevel,
)


class TestSourceRef:
    """SourceRef now has source_id + source_type + optional fields."""

    def test_source_ref_has_new_fields(self):
        sr = SourceRef(
            source_id="S1",
            source_type="yfinance",
            label="Financial Data",
            url="https://finance.yahoo.com/quote/NVDA",
            note="Price and metrics",
            publisher="Yahoo Finance",
            retrieved_at="2026-05-16T00:00:00Z",
            period="FY2026 Q1",
        )
        assert sr.source_id == "S1"
        assert sr.source_type == "yfinance"
        assert sr.label == "Financial Data"
        assert sr.publisher == "Yahoo Finance"
        assert sr.period == "FY2026 Q1"

    def test_source_ref_optional_fields_default_none(self):
        sr = SourceRef(label="Test")
        assert sr.source_id is None
        assert sr.source_type is None
        assert sr.publisher is None
        assert sr.retrieved_at is None
        assert sr.period is None


class TestClaimSource:
    """ClaimSource links a claim to its evidence."""

    def test_claim_source_required_fields(self):
        cs = ClaimSource(
            claim_id="EPS-001",
            section="EPS & Revenue",
            source_id="S1",
        )
        assert cs.claim_id == "EPS-001"
        assert cs.section == "EPS & Revenue"
        assert cs.source_id == "S1"
        assert cs.grounding == "inference"  # default

    def test_claim_source_full(self):
        cs = ClaimSource(
            claim_id="EPS-002",
            section="EPS & Revenue",
            source_id="S1",
            source_field="eps_actual",
            source_value="$2.94",
            as_of_date="2026-04-15",
            grounding="direct_metric",
        )
        assert cs.source_field == "eps_actual"
        assert cs.source_value == "$2.94"
        assert cs.grounding == "direct_metric"

    def test_grounding_level_values(self):
        """All grounding levels should be valid."""
        valid = {"direct_metric", "calculated", "direct_quote", "document_fact", "inference", "unsupported"}
        for level in valid:
            cs = ClaimSource(claim_id="T-1", section="Test", source_id="S1", grounding=level)
            assert cs.grounding == level


class TestEarningsDeepDiveReport:
    """Report now carries claim_sources."""

    def test_report_has_claim_sources(self):
        report = EarningsDeepDiveReport(
            ticker="NVDA",
            company="NVIDIA",
            quarter="FY2026 Q1",
            language="en",
            generated_at="2026-05-16",
            title="Test",
            sections=[],
            claim_sources=[
                ClaimSource(claim_id="EPS-001", section="EPS & Revenue", source_id="S1", grounding="direct_metric"),
            ],
        )
        assert len(report.claim_sources) == 1
        assert report.claim_sources[0].claim_id == "EPS-001"

    def test_report_claim_sources_default_empty(self):
        report = EarningsDeepDiveReport(
            ticker="NVDA",
            company="NVIDIA",
            quarter="FY2026 Q1",
            language="en",
            generated_at="2026-05-16",
            title="Test",
            sections=[],
        )
        assert report.claim_sources == []


class TestRenderedTableRow:
    """Table rows now carry optional source provenance."""

    def test_row_has_provenance_fields(self):
        row = RenderedTableRow(
            label="Revenue",
            cells=["$22.4B", "$20.8B", "+7.7%"],
            source_field="revenue_actual",
            source_value_raw="22400000000",
            grounding="direct_metric",
        )
        assert row.source_field == "revenue_actual"
        assert row.source_value_raw == "22400000000"
        assert row.grounding == "direct_metric"

    def test_row_provenance_optional(self):
        row = RenderedTableRow(label="Revenue", cells=["$22.4B"])
        assert row.source_field is None
        assert row.source_value_raw is None
        assert row.grounding is None


class TestSourceIdAssignment:
    """All SourceRef entries should receive unique source_ids."""

    def test_source_ids_unique(self):
        sources = [
            SourceRef(source_id="S1", source_type="yfinance", label="Financial Data"),
            SourceRef(source_id="S2", source_type="sec_edgar", label="SEC EDGAR"),
            SourceRef(source_id="S3", source_type="seeking_alpha", label="Transcript"),
        ]
        ids = [s.source_id for s in sources]
        assert len(ids) == len(set(ids))  # all unique
        assert "S1" in ids
        assert "S2" in ids
        assert "S3" in ids
