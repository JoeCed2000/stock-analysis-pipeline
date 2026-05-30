"""§4 Metrics Ledger — spec tests.

Tests for MetricsLedger/MetricsLedgerEntry models and RULE 27 validator gate.
"""

import pytest
from backend.earnings_deep_dive.report_model import (
    MetricsLedger,
    MetricsLedgerEntry,
    EarningsDeepDiveReport,
)
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


# ── Model tests ────────────────────────────────────────────────────────


class TestMetricsLedgerModel:
    """MetricsLedger and MetricsLedgerEntry model tests."""

    def test_creates_entry(self):
        e = MetricsLedgerEntry(
            metric_id="EPS-001",
            canonical_metric_name="eps_actual",
            display_name="EPS (Actual)",
            value=2.94,
            unit="USD",
            period_type="quarterly",
            source_type="yfinance",
            basis="provider_supplied",
        )
        assert e.metric_id == "EPS-001"
        assert e.canonical_metric_name == "eps_actual"
        assert e.value == 2.94
        assert e.unit == "USD"

    def test_entry_with_formula(self):
        e = MetricsLedgerEntry(
            metric_id="EPS-003",
            canonical_metric_name="eps_calculated",
            display_name="EPS (Calculated)",
            value=3.50,
            unit="USD",
            period_type="calculated",
            source_type="calculated",
            basis="calculated",
            formula="net_income / shares_outstanding",
            numerator=10000000000.0,
            denominator=2850000000.0,
        )
        assert e.formula is not None
        assert e.numerator == 10e9
        assert e.denominator == 2.85e9

    def test_creates_empty_ledger(self):
        l = MetricsLedger()
        assert l.entries == []
        assert l.count == 0
        assert l.verified_count == 0
        assert l.metric_ids == set()

    def test_ledger_with_entries(self):
        l = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="EPS-001", canonical_metric_name="eps_actual",
                display_name="EPS", value=2.94, validation_status="verified",
            ),
            MetricsLedgerEntry(
                metric_id="REV-001", canonical_metric_name="revenue_actual",
                display_name="Revenue", value=22.4e9, validation_status="unverified",
            ),
        ])
        assert l.count == 2
        assert l.verified_count == 1
        assert l.metric_ids == {"EPS-001", "REV-001"}
        assert l.canonical_names == {"eps_actual", "revenue_actual"}

    def test_get_by_id(self):
        l = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="EPS-001", canonical_metric_name="eps_actual",
                display_name="EPS", value=2.94,
            ),
        ])
        found = l.get("EPS-001")
        assert found is not None
        assert found.value == 2.94
        assert l.get("NONEXISTENT") is None

    def test_get_by_name(self):
        l = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="EPS-001", canonical_metric_name="eps_actual",
                display_name="EPS", value=2.94,
            ),
        ])
        found = l.get_by_name("eps_actual")
        assert found is not None
        assert found.value == 2.94
        assert l.get_by_name("nonexistent") is None

    def test_integration_in_report(self):
        l = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="EPS-001", canonical_metric_name="eps_actual",
                display_name="EPS", value=2.94,
            ),
        ])
        report = EarningsDeepDiveReport(
            ticker="NVDA", company="NVIDIA", quarter="Q1 FY2026",
            language="en", generated_at="2026-05-29T00:00:00Z",
            title="Test", sections=[],
            metrics_ledger=l,
        )
        assert report.metrics_ledger is not None
        assert report.metrics_ledger.count == 1


# ── RULE 27 validator gate tests ───────────────────────────────────────


class TestRule27MetricsLedgerGate:
    """RULE 27: Sanity checks, not-retrieved contradiction, SEC/consensus confusion."""

    def test_27a_not_retrieved_but_metric_in_ledger_blocked(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="REV-001", canonical_metric_name="revenue_actual",
                display_name="Revenue", value=22.4e9,
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "Revenue data was not retrieved for this quarter.",
            },
            metrics_ledger=ml,
        )
        assert result.passed is False
        assert any("not_retrieved_contradiction" in e.check for e in result.errors)

    def test_27a_not_retrieved_without_ledger_entry_no_warning(self):
        ml = MetricsLedger(entries=[])  # Empty ledger
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "Revenue data was not retrieved for this quarter.",
            },
            metrics_ledger=ml,
        )
        assert not any("not_retrieved_contradiction" in e.check for e in result.errors)

    def test_27b_margin_exceeds_100_blocked(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="MAR-001", canonical_metric_name="gross_margin",
                display_name="Gross Margin", value=150.0, unit="%",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
        )
        assert result.passed is False
        assert any("sanity_margin_exceeds_100" in e.check for e in result.errors)

    def test_27b_normal_margin_no_warning(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="MAR-001", canonical_metric_name="gross_margin",
                display_name="Gross Margin", value=65.0, unit="%",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
        )
        assert not any("sanity_margin" in e.check for e in result.errors)

    def test_27b_extreme_dividend_yield_blocked(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="DIV-001", canonical_metric_name="dividend_yield",
                display_name="Dividend Yield", value=25.0, unit="%",
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
        )
        assert result.passed is False
        assert any("sanity_dividend_yield" in e.check for e in result.errors)

    def test_27c_sec_consensus_confusion_warned(self):
        ml = MetricsLedger(entries=[])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "EPS & Revenue": "EPS of $2.94 per SEC consensus estimates.",
            },
            metrics_ledger=ml,
        )
        assert result.passed is True  # Phase 1: warning, not error
        assert any("sec_consensus_confusion" in w.check for w in result.warnings)

    def test_27c_clean_text_no_warning(self):
        ml = MetricsLedger(entries=[])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "EPS & Revenue": "EPS of $2.94 as company-reported. Analyst consensus was $2.80 per Bloomberg.",
            },
            metrics_ledger=ml,
        )
        assert not any("sec_consensus_confusion" in e.check for e in result.errors)

    def test_null_metrics_ledger_noop(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "Revenue was not retrieved. Margin is 150%. SEC consensus says EPS beat.",
            },
            metrics_ledger=None,
        )
        assert not any("metrics_ledger" in e.check for e in result.errors)
