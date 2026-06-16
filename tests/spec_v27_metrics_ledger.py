"""§4 Metrics Ledger — spec tests.

Tests for MetricsLedger/MetricsLedgerEntry models and RULE 27 validator gate.
"""

import pytest
from backend.earnings_deep_dive.report_model import (
    MetricsLedger,
    MetricsLedgerEntry,
    EarningsDeepDiveReport,
    SourceRegistry,
    SourceRegistryEntry,
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
        assert e.period_type == "Calculated"
        assert e.basis == "calculated"
        assert e.source_status == "used"
        assert e.inputs == []

    def test_period_type_is_normalized_to_public_label(self):
        e = MetricsLedgerEntry(
            metric_id="MKT-001",
            canonical_metric_name="market_cap",
            display_name="Market Cap",
            value=5.22e12,
            unit="USD",
            period_type="market_data",
            basis="market",
            source_type="yfinance",
        )
        assert e.period_type == "Market Snapshot"

    def test_unresolved_internal_period_is_blocked(self):
        with pytest.raises(ValueError, match="annual_or_ttm"):
            MetricsLedgerEntry(
                metric_id="REV-AMBIG",
                canonical_metric_name="revenue",
                display_name="Revenue",
                value=22.4e9,
                unit="USD",
                period_type="annual_or_ttm",
                basis="provider_supplied",
                source_type="yfinance",
            )

    def test_calculated_metric_requires_formula(self):
        with pytest.raises(ValueError, match="formula"):
            MetricsLedgerEntry(
                metric_id="PEG-001",
                canonical_metric_name="peg_ratio",
                display_name="PEG Ratio",
                value=0.66,
                unit="ratio",
                period_type="calculated",
                basis="calculated",
                source_type="calculated",
                inputs=["PE-001", "GRW-001"],
            )

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
        assert result.passed is True
        assert any("not_retrieved_contradiction" in w.check for w in result.warnings)

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

    def test_27d_metric_source_capability_mismatch_blocked(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="GUID-001",
                canonical_metric_name="revenue_guidance",
                display_name="Revenue Guidance",
                value=25.0e9,
                unit="USD",
                period_type="Guidance",
                source_id="S1",
                source_type="yfinance",
                basis="guidance",
                metric_family="management_guidance",
            ),
        ])
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1",
                human_label="Yahoo Finance",
                source_type="market_data",
                status="used",
                capability_families=["market_snapshot", "consensus"],
                unsupported_metric_families=["management_guidance"],
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
            source_registry=sr,
        )
        assert result.passed is False
        assert any("metric_source_capability_mismatch" in e.check for e in result.errors)

    def test_27d_supported_metric_source_no_error(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="MKT-001",
                canonical_metric_name="market_cap",
                display_name="Market Cap",
                value=5.22e12,
                unit="USD",
                period_type="Market Snapshot",
                source_id="S1",
                source_type="yfinance",
                basis="market",
                metric_family="market_snapshot",
            ),
        ])
        sr = SourceRegistry(entries=[
            SourceRegistryEntry(
                source_id="S1",
                human_label="Yahoo Finance",
                source_type="market_data",
                status="used",
                capability_families=["market_snapshot", "consensus"],
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
            source_registry=sr,
        )
        assert not any("metric_source_capability_mismatch" in e.check for e in result.errors)

    def test_27e_calculated_metric_formula_mismatch_blocked(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="EPS-CALC-001",
                canonical_metric_name="eps_calculated",
                display_name="EPS (Calculated)",
                value=5.00,
                unit="USD",
                period_type="Calculated",
                basis="calculated",
                source_type="calculated",
                formula="net_income / diluted_shares",
                numerator=10_000_000_000.0,
                denominator=2_850_000_000.0,
                inputs=["NET-001", "SHR-001"],
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
        )
        assert result.passed is False
        assert any("calculated_formula_mismatch" in e.check for e in result.errors)

    def test_27e_calculated_metric_formula_match_no_error(self):
        ml = MetricsLedger(entries=[
            MetricsLedgerEntry(
                metric_id="EPS-CALC-001",
                canonical_metric_name="eps_calculated",
                display_name="EPS (Calculated)",
                value=3.51,
                unit="USD",
                period_type="Calculated",
                basis="calculated",
                source_type="calculated",
                formula="net_income / diluted_shares",
                numerator=10_000_000_000.0,
                denominator=2_850_000_000.0,
                inputs=["NET-001", "SHR-001"],
            ),
        ])
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={},
            metrics_ledger=ml,
        )
        assert not any("calculated_formula_mismatch" in e.check for e in result.errors)

    def test_null_metrics_ledger_noop(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "Revenue was not retrieved. Margin is 150%. SEC consensus says EPS beat.",
            },
            metrics_ledger=None,
        )
        assert not any("metrics_ledger" in e.check for e in result.errors)


class TestNetDebtCapitalEfficiencyOverride:
    """Regression: Net Cash / (Net Debt) must use net_debt directly."""

    def test_net_debt_override_in_prompt(self):
        from backend.earnings_deep_dive.prompts import capital_efficiency_prompt
        metrics = {
            "roe": 80.0, "roa": 30.0, "roic": 45.0, "rotce": 60.0,
            "net_income": 20_000_000_000,
            "net_debt": -72_102_000_000,
        }
        prompt = capital_efficiency_prompt(
            language="en", ticker="NVDA", company="NVIDIA Corp",
            quarter="FY2027 Q1", metrics=metrics,
            transcript_excerpt="No transcript available.",
        )
        assert "CRITICAL OVERRIDE: Net Cash / (Net Debt)" in prompt
        assert "72.1B" in prompt
        assert "Do NOT recalculate from" in prompt

    def test_net_cash_row_in_en_template(self):
        from backend.earnings_deep_dive.prompts import EN_SECTION_FORMATS
        assert "| Net Cash / (Net Debt) |" in EN_SECTION_FORMATS["Capital Efficiency"]

    def test_net_cash_row_in_jp_template(self):
        from backend.earnings_deep_dive.prompts import SECTION_FORMATS
        assert "| Net Cash / (Net Debt) |" in SECTION_FORMATS["Capital Efficiency"]

    def test_net_debt_override_positive(self):
        """Positive net_debt (net debt position) renders correctly."""
        from backend.earnings_deep_dive.prompts import capital_efficiency_prompt
        metrics = {
            "roe": 10.0, "roa": 5.0, "roic": 8.0, "rotce": 12.0,
            "net_income": 5_000_000_000,
            "net_debt": 15_000_000_000,
        }
        prompt = capital_efficiency_prompt(
            language="en", ticker="TEST", company="Test Corp",
            quarter="FY2027 Q1", metrics=metrics,
            transcript_excerpt="No transcript available.",
        )
        assert "CRITICAL OVERRIDE: Net Cash / (Net Debt)" in prompt
        assert "net debt position" in prompt.lower()
