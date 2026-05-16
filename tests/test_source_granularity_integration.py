"""Integration tests for claim→source traceability.

Tests that:
- major claims have source mappings
- missing URLs/fields degrade gracefully
- no source mapping breaks PDF generation
- existing overrides remain intact
"""

import pytest
from datetime import datetime, timezone

from backend.earnings_deep_dive.report_model import (
    ClaimSource,
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    SourceRef,
)
from backend.earnings_deep_dive.mapper import _build_claim_sources


def _make_section(key: str, rows: list[list[str]]) -> RenderedSection:
    """Helper to build a RenderedSection with table rows."""
    table_rows = []
    for cells in rows:
        label = cells[0] if cells else ""
        table_rows.append(RenderedTableRow(label=label, cells=cells))
    return RenderedSection(
        key=key,
        title=key,
        question="",
        table=RenderedTable(columns=[], rows=table_rows),
        analysis=[],
        summary_label="",
        summary="",
    )


def _make_sources() -> list[SourceRef]:
    return [
        SourceRef(source_id="S1", source_type="yfinance", label="Financial Data",
                  url="https://finance.yahoo.com/quote/TSLA"),
        SourceRef(source_id="S2", source_type="sec_edgar", label="SEC EDGAR Filings",
                  url="https://www.sec.gov/cgi-bin/browse-edgar?CIK=TSLA"),
        SourceRef(source_id="S3", source_type="seeking_alpha", label="Seeking Alpha Transcripts"),
    ]


class TestClaimSourceMapping:
    """Major claims must have source mappings."""

    def test_sections_produce_claims(self):
        sources = _make_sources()
        sections = [
            _make_section("EPS & Revenue", [
                ["Revenue", "$22.4B", "$20.8B", "+7.7%"],
                ["EPS", "$2.94", "$2.48", "+18.5%"],
            ]),
            _make_section("Cash Flow", [
                ["Operating Cash Flow", "$14.2B", "$11.1B", "+27.9%"],
            ]),
        ]
        claims = _build_claim_sources(sections, sources, None, "TSLA")
        assert len(claims) == 3  # one per non-placeholder row
        # Check claim fields
        assert claims[0].claim_id == "EPS-001"
        assert claims[0].section == "EPS & Revenue"
        assert claims[0].source_type == "yfinance"
        assert claims[0].source_name == "Financial Data"
        assert claims[0].source_url == "https://finance.yahoo.com/quote/TSLA"
        assert claims[0].grounding == "direct_metric"
        assert claims[0].confidence == "high"

    def test_placeholder_rows_skipped(self):
        sources = _make_sources()
        sections = [
            _make_section("Margins", [
                ["Gross Margin", "Not disclosed"],
                ["Revenue", "$22.4B"],
            ]),
        ]
        claims = _build_claim_sources(sections, sources, None, "TSLA")
        # Only "Revenue" row should produce a claim; "Not disclosed" row skipped
        assert len(claims) == 1
        assert claims[0].claim_text and "Revenue" in claims[0].claim_text

    def test_guidance_section_has_inference_grounding(self):
        sources = _make_sources()
        sections = [
            _make_section("Guidance", [
                ["Revenue", "Guided $24B-$26B"],
            ]),
        ]
        claims = _build_claim_sources(sections, sources, None, "NVDA")
        assert len(claims) == 1
        assert claims[0].grounding == "inference"
        assert claims[0].confidence == "medium"

    def test_verdict_has_inference_low_confidence(self):
        sources = _make_sources()
        sections = [
            _make_section("Verdict", [
                ["Score", "8/10"],
            ]),
        ]
        claims = _build_claim_sources(sections, sources, None, "TSLA")
        assert len(claims) == 1
        assert claims[0].grounding == "inference"
        assert claims[0].confidence == "low"


class TestGracefulDegradation:
    """Missing URLs or missing fields degrade gracefully."""

    def test_missing_source_url_produces_none(self):
        sources = [
            SourceRef(source_id="S1", source_type="yfinance", label="Financial Data"),
            # No URL
        ]
        sections = [_make_section("EPS & Revenue", [["Revenue", "$22.4B"]])]
        claims = _build_claim_sources(sections, sources, None, "TSLA")
        assert claims[0].source_url is None

    def test_missing_source_id_uses_placeholder(self):
        sources = []  # No sources at all
        sections = [_make_section("EPS & Revenue", [["Revenue", "$22.4B"]])]
        claims = _build_claim_sources(sections, sources, None, "TSLA")
        assert len(claims) == 1
        assert claims[0].source_id == "S?"
        # When no source ref exists, source_name falls back to source_type
        assert claims[0].source_name == "yfinance"  # fallback to source_type

    def test_empty_sections_produce_no_claims(self):
        sources = _make_sources()
        claims = _build_claim_sources([], sources, None, "TSLA")
        assert claims == []

    def test_empty_report_does_not_break_pdf_model(self):
        """Verifies that a report with no claim_sources still builds."""
        report = EarningsDeepDiveReport(
            ticker="TEST", company="Test Inc", quarter="Q1",
            language="en", generated_at="2026-05-16", title="Test",
            sections=[], sources=_make_sources(), claim_sources=[],
        )
        assert report.claim_sources == []
        assert len(report.sources) == 3


class TestExistingOverridesIntact:
    """CRITICAL OVERRIDE preservation — source mapping must not break them."""

    def test_source_ids_preserved_across_sections(self):
        """Each section gets appropriate source_id based on source type."""
        sources = _make_sources()
        sections = [
            _make_section("EPS & Revenue", [["Revenue", "$10B"]]),
            _make_section("Cash Flow", [["OCF", "$3B"]]),
            _make_section("Forward P/E", [["P/E", "25.3"]]),
        ]
        claims = _build_claim_sources(sections, sources, None, "TEST")
        # EPS & Revenue → yfinance → S1
        assert claims[0].source_id == "S1"
        assert claims[0].source_type == "yfinance"
        # Cash Flow → sec_edgar → S2 
        assert claims[1].source_id == "S2"
        assert claims[1].source_type == "sec_edgar"
        # Forward P/E → yfinance → S1
        assert claims[2].source_id == "S1"
        assert claims[2].source_type == "yfinance"

    def test_capital_efficiency_uses_sec_edgar(self):
        sources = _make_sources()
        sections = [_make_section("Capital Efficiency", [["ROIC", "23.4%"]])]
        claims = _build_claim_sources(sections, sources, None, "TEST")
        assert claims[0].source_type == "sec_edgar"
        assert claims[0].source_id == "S2"
