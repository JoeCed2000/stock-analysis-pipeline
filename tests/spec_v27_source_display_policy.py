"""§13 Source Display Policy — EDP-010/012 — spec tests.

Tests the mapper's _apply_source_display_policy that sets RenderedTable
source_display_policy and table_source_note metadata.

Call path:
  build_earnings_deep_dive_report() → _apply_source_display_policy()
  → sets source_display_policy on RenderedTable after sanitize.
"""

import pytest
from backend.earnings_deep_dive.report_model import (
    RenderedTable,
    RenderedTableRow,
)
from backend.earnings_deep_dive.mapper import _apply_source_display_policy


# ── Fixtures ────────────────────────────────────────────────────────────────


def _table(
    columns: list[str],
    rows: list[tuple[str, ...]],
    *,
    source_display_policy: str = "row",
    table_source_note: str | None = None,
) -> RenderedTable:
    """Build a RenderedTable from column names and row tuples.
    The last cell in each row tuple is the Source cell value.
    """
    return RenderedTable(
        columns=columns,
        rows=[
            RenderedTableRow(label=str(row[0]), cells=list(row[1:]))
            for row in rows
        ],
        source_display_policy=source_display_policy,
        table_source_note=table_source_note,
    )


def _pct_val(i: int) -> str:
    vals = ["15.3%", "12.1%", "8.2%", "22.5%", "$1.2B", "$0.8B"]
    return vals[i % len(vals)]


class TestSourceDisplayPolicy:
    """Unit tests for _apply_source_display_policy."""

    def test_homogeneous_capital_efficiency_collapses(self):
        """Homogeneous Capital Efficiency with identical source should collapse."""
        src = "SEC Filing (10-Q/10-K) via EDGAR"
        table = _table(
            columns=["Metric", "Current", "Prior", "YoY", "Trend", "Source"],
            rows=[
                ("ROE", "15.3%", "12.1%", "+3.2pp", "Improved", src),
                ("ROTCE", "12.1%", "11.5%", "+0.6pp", "Improved", src),
                ("ROA", "8.2%", "7.5%", "+0.7pp", "Flat", src),
                ("ROIC", "22.5%", "20.0%", "+2.5pp", "Improved", src),
                ("Capital Allocation — Buybacks", "$1.2B", "$1.0B", "+20%", "N/A", src),
                ("Capital Allocation — Dividends", "$0.8B", "$0.7B", "+14.3%", "N/A", src),
            ],
        )
        result = _apply_source_display_policy("Capital Efficiency", table)
        assert result.source_display_policy == "table_note", (
            f"Expected table_note, got {result.source_display_policy}"
        )
        assert result.table_source_note is not None
        assert "SEC" in result.table_source_note

    def test_mixed_cash_flow_keeps_row_source(self):
        """Cash Flow with mixed direct + calculated source keeps row-level."""
        table = _table(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=[
                ("Operating Cash Flow", "$2.5B", "$2.3B", "+8.7%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("CapEx", "($0.5B)", "($0.4B)", "-25%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Free Cash Flow", "$2.0B", "$1.9B", "+5.3%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("FCF Margin", "18.5%", "17.2%", "+1.3pp", "Calculated (FCF ÷ Revenue)"),
                ("Cash & Marketable Securities", "$10.0B", "$9.5B", "+5.3%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Net Cash / (Net Debt)", "$5.0B", "$4.5B", "+11.1%", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
        )
        result = _apply_source_display_policy("Cash Flow", table)
        assert result.source_display_policy == "row", (
            f"Expected row, got {result.source_display_policy}: "
            f"mixed calculated + direct source should not collapse"
        )

    def test_unavailable_source_does_not_collapse(self):
        """Unavailable source labels prevent collapse."""
        table = _table(
            columns=["Metric", "Current", "Source"],
            rows=[
                ("ROE", "15.3%", "Not disclosed"),
                ("ROA", "8.2%", "Unavailable from reviewed sources"),
            ],
        )
        result = _apply_source_display_policy("Capital Efficiency", table)
        assert result.source_display_policy == "row", (
            f"Expected row (unavailable source), got {result.source_display_policy}"
        )

    def test_non_allowlisted_section_keeps_row(self):
        """EPS & Revenue (not allow-listed) keeps row-level source."""
        table = _table(
            columns=["Metric", "Actual", "Estimate", "Source"],
            rows=[
                ("EPS", "$1.23", "$1.15", "Yahoo Finance (consensus)"),
            ],
        )
        result = _apply_source_display_policy("EPS & Revenue", table)
        assert result.source_display_policy == "row", (
            f"Expected row for non-allowlisted section, got {result.source_display_policy}"
        )

    def test_no_source_column_keeps_default(self):
        """Table without 'Source' column header stays at default row."""
        table = _table(
            columns=["Metric", "Value"],
            rows=[("Revenue", "$10.0B")],
        )
        result = _apply_source_display_policy("Capital Efficiency", table)
        assert result.source_display_policy == "row"

    def test_calculated_label_blocks_collapse(self):
        """At least one calculated row should block collapse even if all others share source."""
        table = _table(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=[
                ("Operating Cash Flow", "$2.5B", "$2.3B", "+8.7%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Free Cash Flow", "$2.0B", "$1.9B", "+5.3%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("FCF Margin", "18.5%", "17.2%", "+1.3pp", "Calculated (FCF ÷ Revenue)"),
            ],
        )
        result = _apply_source_display_policy("Cash Flow", table)
        assert result.source_display_policy == "row", (
            f"Expected row (calculated label blocks collapse), got {result.source_display_policy}"
        )

    def test_no_mutation_of_rows_or_cells(self):
        """source_display_policy must NOT mutate row labels or cell values."""
        original_rows = [
            ("ROE", "15.3%", "12.1%", "+3.2pp", "SEC Filing (10-Q/10-K) via EDGAR"),
            ("ROA", "8.2%", "7.5%", "+0.7pp", "SEC Filing (10-Q/10-K) via EDGAR"),
        ]
        table = _table(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=original_rows,
        )
        result = _apply_source_display_policy("Capital Efficiency", table)
        # Verify row labels and cells unchanged
        for orig_row, result_row in zip(original_rows, result.rows):
            assert result_row.label == orig_row[0], (
                f"Label mutated: {result_row.label} != {orig_row[0]}"
            )
            assert list(result_row.cells) == list(orig_row[1:]), (
                f"Cells mutated for {orig_row[0]}: {result_row.cells} != {list(orig_row[1:])}"
            )

    def test_operating_metrics_collapses_when_complete_and_identical(self):
        """Operating Metrics collapses only when all rows have identical source."""
        src = "SEC Filing (10-Q/10-K) via EDGAR"
        table = _table(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=[
                ("Revenue", "$10.0B", "$9.0B", "+11.1%", src),
                ("Gross Profit", "$6.5B", "$5.8B", "+12.1%", src),
                ("Gross Margin", "65.0%", "64.4%", "+0.6pp", src),
                ("OpEx", "$3.0B", "$2.8B", "+7.1%", src),
                ("Operating Income", "$3.5B", "$3.0B", "+16.7%", src),
                ("Operating Margin", "35.0%", "33.3%", "+1.7pp", src),
                ("Net Income", "$2.8B", "$2.4B", "+16.7%", src),
            ],
        )
        result = _apply_source_display_policy("Operating Metrics", table)
        assert result.source_display_policy == "table_note", (
            f"Expected table_note for homogeneous Operating Metrics, "
            f"got {result.source_display_policy}"
        )

    def test_operating_metrics_mixed_source_keeps_row(self):
        """Operating Metrics with mixed source keeps row-level."""
        table = _table(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=[
                ("Revenue", "$10.0B", "$9.0B", "+11.1%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Gross Profit", "$6.5B", "$5.8B", "+12.1%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Gross Margin", "65.0%", "64.4%", "+0.6pp", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("OpEx", "$3.0B", "$2.8B", "+7.1%", "yfinance (Yahoo Finance)"),
                ("Operating Income", "$3.5B", "$3.0B", "+16.7%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Operating Margin", "35.0%", "33.3%", "+1.7pp", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Net Income", "$2.8B", "$2.4B", "+16.7%", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
        )
        result = _apply_source_display_policy("Operating Metrics", table)
        assert result.source_display_policy == "row", (
            f"Expected row for mixed-source Operating Metrics, "
            f"got {result.source_display_policy}"
        )

    def test_homogeneous_japanese_labels_collapse(self):
        """Japanese source labels collapse when identical and allow-listed."""
        src = "会社開示 / 計算ベース"
        table = _table(
            columns=["指標", "当期", "前期", "前年比", "情報源"],
            rows=[
                ("ROE", "15.3%", "12.1%", "+3.2pp", src),
                ("ROTCE", "12.1%", "11.5%", "+0.6pp", src),
                ("ROA", "8.2%", "7.5%", "+0.7pp", src),
            ],
        )
        result = _apply_source_display_policy("Capital Efficiency", table)
        assert result.source_display_policy == "table_note", (
            f"Expected table_note for homogeneous JP labels, "
            f"got {result.source_display_policy}"
        )

    def test_missing_source_cell_does_not_collapse(self):
        """A row with missing source (dash/empty) prevents collapse."""
        table = _table(
            columns=["Metric", "Current", "Source"],
            rows=[
                ("ROE", "15.3%", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("ROA", "8.2%", "—"),
            ],
        )
        result = _apply_source_display_policy("Capital Efficiency", table)
        assert result.source_display_policy == "row", (
            f"Expected row (missing source), got {result.source_display_policy}"
        )


class TestMetadataPreservation:
    """Verify table-copying helpers preserve source_display_policy."""

    def test_sanitize_preserves_metadata(self):
        """_sanitize_table must preserve source_display_policy."""
        from backend.earnings_deep_dive.mapper import _sanitize_table
        table = _table(
            columns=["Metric", "Value", "Source"],
            rows=[("ROE", "15.3%", "SEC Filing (10-Q/10-K) via EDGAR")],
            source_display_policy="table_note",
            table_source_note="Source: SEC Filing",
        )
        result = _sanitize_table(table)
        assert result.source_display_policy == "table_note"
        assert result.table_source_note == "Source: SEC Filing"

    def test_number_highlights_preserves_metadata(self):
        """_number_highlights_rows must preserve source_display_policy."""
        from backend.earnings_deep_dive.mapper import _number_highlights_rows
        table = _table(
            columns=["Number", "Metric", "Source"],
            rows=[("?", "Revenue", "SEC Filing (10-Q/10-K) via EDGAR")],
            source_display_policy="table_note",
            table_source_note="Source: SEC Filing",
        )
        result = _number_highlights_rows(table)
        assert result.source_display_policy == "table_note"
        assert result.table_source_note == "Source: SEC Filing"
