#!/usr/bin/env python3
"""Persistent proof for t_bd23aab4 metric-based rounding architecture split."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/feedback-audits/metric-renderer-rounding-architecture.md"
WIKI = ROOT / "WIKI.md"
MAPPER = ROOT / "backend/earnings_deep_dive/mapper.py"
PDF_RENDERER = ROOT / "backend/earnings_deep_dive/pdf_renderer.py"
CLASSIFICATION = ROOT / "docs/feedback-audits/jp-en-parity-classification.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.exists(), f"missing path: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    doc = read(DOC)
    wiki = read(WIKI)
    mapper = read(MAPPER)
    pdf = read(PDF_RENDERER)
    classification = read(CLASSIFICATION)

    required_doc_markers = [
        "Task:** `t_bd23aab4`",
        "keep `pdf_renderer.py` presentation-only",
        "mapper/table-construction seam",
        "banker's rounding",
        "t_c02f3308",
        "t_3eb11127",
        "_rows_for_section",
        "_extract_segment_rows",
        "GRAPH_EVIDENCE",
        "SYMBOL_PLAN",
    ]
    for marker in required_doc_markers:
        require(marker in doc, f"doc missing marker: {marker}")

    require("Metric-based rounding architecture split (t_bd23aab4)" in wiki, "WIKI missing t_bd23aab4 entry")
    require("t_c02f3308" in wiki and "t_3eb11127" in wiki, "WIKI missing child IDs")

    require('"Operating Metrics", "Cash Flow", "Capital Efficiency"' in mapper, "mapper data-driven set missing Operating Metrics context")
    require('"Segments", "Geographic Segments"' in mapper, "mapper data-driven set missing Segments context")
    require('def _rows_for_section(' in mapper, "mapper missing _rows_for_section")
    require('def _extract_segment_rows(' in mapper, "mapper missing _extract_segment_rows")
    require('def _table(' in pdf, "pdf_renderer missing presentation table function")
    require('story.extend(_table(section, styles, fonts))' in pdf, "pdf_renderer does not render section.table through _table")

    require("Real gap 6" in classification, "classification missing Real gap 6")
    require("Gross Profit" in classification and "Segments prior-year" in classification, "classification missing target rounding examples")

    print("VERIFY_T_BD23AAB4_READY")


if __name__ == "__main__":
    main()
