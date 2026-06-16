"""§13b Source Display Policy — EDP-010/012 — PDF renderer tests.

Tests _table() in pdf_renderer.py for source display policy handling:
- Hides visible Source column when source_display_policy == "table_note"
- Appends table-level source note paragraph below the table
- Keeps Source column when source_display_policy == "row" (default)
- JP source column labels are detected correctly
"""

import pytest

from backend.earnings_deep_dive.report_model import (
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    SourceDisplayPolicy,
)
from backend.earnings_deep_dive.pdf_renderer import (
    _table,
    _styles,
    resolve_pdf_fonts,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def fonts():
    return resolve_pdf_fonts("en")


@pytest.fixture(scope="module")
def styles(fonts):
    return _styles(fonts)


def _section(
    columns: list[str],
    rows: list[tuple[str, ...]],
    *,
    source_display_policy: str = "row",
    table_source_note: str | None = None,
) -> RenderedSection:
    """Build a minimal RenderedSection with a RenderedTable."""
    return RenderedSection(
        key="Operating Metrics",
        title="Operating Metrics",
        question="How did the company perform operationally?",
        table=RenderedTable(
            columns=columns,
            rows=[
                RenderedTableRow(label=str(row[0]), cells=list(row[1:]))
                for row in rows
            ],
            source_display_policy=source_display_policy,
            table_source_note=table_source_note,
        ),
        summary_label="Operating Metrics",
        summary="Test summary",
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestSourceDisplayRenderer:
    """Renderer-level tests for source display policy in _table()."""

    def _count_source_in_table(
        self, section, styles, fonts
    ) -> int:
        """Count how many times 'Source' or any normalized variant appears
        as column header text in the rendered table."""
        result = _table(section, styles, fonts)
        # result[0] is the ReportLab Table — we extract header by inspecting
        # the table's data attribute via the ReportLab internal _cellvalues
        table = result[0]
        if not hasattr(table, "_cellvalues") or not table._cellvalues:
            return 0
        header = table._cellvalues[0]
        count = 0
        for cell in header:
            text = str(cell).lower()
            if "source" in text or "情報源" in text or "出典" in text:
                count += 1
        return count

    def test_table_note_hides_source_column(self, styles, fonts):
        """table_note policy should hide the visible Source column in the rendered table."""
        section = _section(
            columns=["Metric", "Current", "Prior", "YoY", "Trend", "Source"],
            rows=[
                ("ROE", "15.3%", "12.1%", "+3.2pp", "Improved", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("ROA", "8.2%", "7.5%", "+0.7pp", "Flat", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="table_note",
            table_source_note="SEC Filing (10-Q/10-K) via EDGAR",
        )
        result = _table(section, styles, fonts)
        # Result should have the source note paragraph appended
        assert len(result) >= 2, (
            f"Expected at least [table, source_note], got {len(result)} items"
        )
        # Source column should NOT appear in the rendered table header
        source_count = self._count_source_in_table(section, styles, fonts)
        assert source_count == 0, (
            f"Source column should be hidden with table_note policy, "
            f"but found {source_count} Source header(s)"
        )
        # Last flowable should be a Paragraph containing "Source:"
        last_item = result[-1]
        assert hasattr(last_item, "text"), (
            f"Expected a Paragraph (with .text) as last item, got {type(last_item)}"
        )
        assert "Source:" in str(last_item.text), (
            f"Expected source note to contain 'Source:', got '{last_item.text}'"
        )

    def test_row_policy_keeps_source_column(self, styles, fonts):
        """Default 'row' policy keeps the visible Source column."""
        section = _section(
            columns=["Metric", "Current", "Prior", "YoY", "Trend", "Source"],
            rows=[
                ("ROE", "15.3%", "12.1%", "+3.2pp", "Improved", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("ROA", "8.2%", "7.5%", "+0.7pp", "Flat", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="row",
        )
        result = _table(section, styles, fonts)
        # With row policy, Source column remains visible
        # result should be [table + prose_rows] (no source note appended)
        source_count = self._count_source_in_table(section, styles, fonts)
        assert source_count >= 1, (
            f"Source column should be visible with row policy, "
            f"but found {source_count} Source header(s)"
        )
        # No source note paragraph should be appended
        assert not any(
            hasattr(item, "text") and "Source:" in str(item.text)
            for item in result
        ), "No source note should be appended with row policy"

    def test_jp_source_label_detected(self, styles, fonts):
        """JP column header '情報源' should be detected for table_note collapse."""
        section = _section(
            columns=["指標", "当期", "前期", "前年比", "情報源"],
            rows=[
                ("ROE", "15.3%", "12.1%", "+3.2pp", "会社開示 / 計算ベース"),
                ("ROA", "8.2%", "7.5%", "+0.7pp", "会社開示 / 計算ベース"),
            ],
            source_display_policy="table_note",
            table_source_note="会社開示 / 計算ベース",
        )
        result = _table(section, styles, fonts)
        # Source column should be hidden in rendered table
        source_count = self._count_source_in_table(section, styles, fonts)
        assert source_count == 0, (
            f"JP source column should be hidden with table_note, "
            f"found {source_count} header(s)"
        )
        # Should have a source note with Japanese text
        assert any(
            hasattr(item, "text") and "Source:" in str(item.text)
            for item in result
        ), "JP source note should contain 'Source:'"

    def test_none_policy_stays_row(self, styles, fonts):
        """'none' policy behaves like 'row' for backward compatibility."""
        section = _section(
            columns=["Metric", "Value", "Source"],
            rows=[
                ("Revenue", "$10.0B", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="none",
        )
        result = _table(section, styles, fonts)
        source_count = self._count_source_in_table(section, styles, fonts)
        assert source_count >= 1, (
            f"none policy should keep Source column visible, "
            f"found {source_count} Source header(s)"
        )

    def test_table_note_not_appended_when_no_note_text(self, styles, fonts):
        """table_note without table_source_note should not crash or append note."""
        section = _section(
            columns=["Metric", "Current", "Source"],
            rows=[
                ("ROE", "15.3%", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="table_note",
            table_source_note=None,
        )
        result = _table(section, styles, fonts)
        # Should still have Source column (no note to show)
        source_count = self._count_source_in_table(section, styles, fonts)
        assert source_count >= 1, (
            "Without table_source_note, Source column should remain visible, "
            f"found {source_count}"
        )

    def test_prose_rows_preserved_with_table_note(self, styles, fonts):
        """Prose rows extracted from the table should still be rendered
        alongside the source note when source_display_policy is table_note."""
        section = _section(
            columns=["Metric", "Current", "Source"],
            rows=[
                ("Revenue", "$10.0B", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("Explanation and analysis Revenue grew 11% YoY driven by Services",
                 "$10.0B", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="table_note",
            table_source_note="SEC Filing (10-Q/10-K) via EDGAR",
        )
        result = _table(section, styles, fonts)
        # Should have table + source_note (the prose row should be extracted)
        # Prose row becomes a Paragraph before the source note
        assert len(result) >= 2, (
            f"Expected at least [table, flowable(s)], got {len(result)}"
        )
        # Source column should be hidden
        source_count = self._count_source_in_table(section, styles, fonts)
        assert source_count == 0, (
            f"Source column should be hidden with table_note, "
            f"found {source_count}"
        )

    def test_table_note_removes_row_source_cells(self, styles, fonts):
        """table_note policy should remove Source cell values from each
        rendered data row — not just the header. Regression guard for
        the src_idx off-by-one bug that left per-row source cells visible."""
        section = _section(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=[
                ("ROE", "15.3%", "12.1%", "+3.2pp", "SEC Filing (10-Q/10-K) via EDGAR"),
                ("ROA", "8.2%", "7.5%", "+0.7pp", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="table_note",
            table_source_note="SEC Filing (10-Q/10-K) via EDGAR",
        )
        result = _table(section, styles, fonts)
        table = result[0]
        assert hasattr(table, "_cellvalues"), "Expected ReportLab Table with _cellvalues"
        # Check each data row (skip header at index 0)
        for row_idx, row in enumerate(table._cellvalues[1:], start=1):
            for cell in row:
                cell_text = str(cell).lower()
                # No cell should contain source provenance text
                assert "sec filing" not in cell_text, (
                    f"Row {row_idx} should not have source cell data, "
                    f"found '{cell_text}'"
                )
                assert "edgar" not in cell_text, (
                    f"Row {row_idx} should not have source cell data, "
                    f"found '{cell_text}'"
                )
        # Verify Cash Flow (row policy) still HAS source cells
        cf_section = _section(
            columns=["Metric", "Current", "Source"],
            rows=[
                ("OCF", "$50.3B", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="row",
        )
        cf_result = _table(cf_section, styles, fonts)
        cf_table = cf_result[0]
        cf_row_texts = " ".join(str(c).lower() for c in cf_table._cellvalues[1])
        assert "10-q/k" in cf_row_texts, (
            "Row policy must keep source cells visible (shortened)"
        )

    def test_table_source_note_no_duplicate_label(self, styles, fonts):
        """When table_source_note already starts with 'Source:', the rendered
        note must NOT become 'Source: Source:' — the label prefix is
        stripped before rendering."""
        section = _section(
            columns=["Metric", "Current", "Source"],
            rows=[
                ("ROE", "15.3%", "SEC Filing (10-Q/10-K) via EDGAR"),
            ],
            source_display_policy="table_note",
            table_source_note="Source: SEC Filings (10-Q/10-K) via EDGAR",
        )
        result = _table(section, styles, fonts)
        # Find the source note paragraph
        note_paras = [
            item for item in result
            if hasattr(item, "text") and "Source:" in str(item.text)
        ]
        assert len(note_paras) >= 1, "Expected at least one source note paragraph"
        note_text = str(note_paras[-1].text)
        assert "Source: Source:" not in note_text, (
            f"Source label must not be duplicated: '{note_text}'"
        )
        assert note_text.count("Source:") == 1, (
            f"Expected exactly one 'Source:' prefix, got '{note_text}'"
        )
        # The body text should still be present
        assert "SEC Filings" in note_text, (
            f"Note body should contain 'SEC Filings', got '{note_text}'"
        )
