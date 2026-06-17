#!/usr/bin/env python3
"""Persistent proof for t_54e5bf38 source-label dynamic period repair."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MAPPER = ROOT / "backend/earnings_deep_dive/mapper.py"
TEST = ROOT / "tests/spec_v27_source_display_policy.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    mapper = MAPPER.read_text(encoding="utf-8", errors="replace")
    test = TEST.read_text(encoding="utf-8", errors="replace")

    require('"sec-filing": "SEC 10-Q (Q1 FY2027)"' not in mapper, "hardcoded Q1 FY2027 sec-filing display remains")
    require("def _format_filing_period(" in mapper, "period extraction helper missing")
    require("raw_labels" in mapper and "source_raw_values" in mapper, "display restore lacks raw source context")
    require("Company filings / earnings release metrics" in mapper, "mixed filing/release neutral display missing")
    require("test_sec_10q_table_note_derives_non_q1_period_from_source_label" in test, "non-Q1 regression missing")
    require("test_jp_en_cashflow_10q_earnings_release_collapse" in test, "mixed 10-Q/release regression missing")
    wiki = (ROOT / "WIKI.md").read_text(encoding="utf-8", errors="replace")
    require("Source label dynamic period repair (t_54e5bf38)" in wiki, "WIKI evidence missing")

    sys.path.insert(0, str(ROOT))
    from backend.earnings_deep_dive.mapper import _apply_source_display_policy
    from backend.earnings_deep_dive.report_model import RenderedTable, RenderedTableRow

    def table(source_labels: list[str]) -> RenderedTable:
        return RenderedTable(
            columns=["Metric", "Current", "Prior", "YoY", "Source"],
            rows=[
                RenderedTableRow(label="Operating Cash Flow", cells=["$2.5B", "$2.3B", "+8.7%", source_labels[0]]),
                RenderedTableRow(label="CapEx", cells=["($0.5B)", "($0.4B)", "-25%", source_labels[1]]),
                RenderedTableRow(label="Free Cash Flow", cells=["$2.0B", "$1.9B", "+5.3%", source_labels[2]]),
            ],
        )

    pure_10q = _apply_source_display_policy(
        "Cash Flow",
        table(["ACME FY2026 Q4 10-Q (supplied metrics)"] * 3),
    )
    require(pure_10q.source_display_policy == "table_note", "pure 10-Q rows should collapse")
    require(pure_10q.table_source_note == "Source: SEC 10-Q (Q4 FY2026)", f"period not derived: {pure_10q.table_source_note}")
    require("Q1 FY2027" not in (pure_10q.table_source_note or ""), "hardcoded Q1 FY2027 leaked")

    mixed = _apply_source_display_policy(
        "Cash Flow",
        table([
            "NVIDIA FY2027 Q1 10-Q (supplied metrics)",
            "Q1 FY2027 earnings release (supplied metrics)",
            "NVIDIA FY2027 Q1 10-Q (supplied metrics)",
        ]),
    )
    require(mixed.source_display_policy == "table_note", "comparison-key parity should still collapse mixed 10-Q/release")
    require(mixed.table_source_note == "Source: Company filings / earnings release metrics", f"false SEC provenance remains: {mixed.table_source_note}")

    print("VERIFY_SOURCE_LABEL_DYNAMIC_PERIOD_READY")


if __name__ == "__main__":
    main()
