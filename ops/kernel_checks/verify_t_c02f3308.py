#!/usr/bin/env python3
"""Persistent proof for t_c02f3308 Operating Metrics metric-based rounding."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPPER = ROOT / "backend/earnings_deep_dive/mapper.py"
TEST = ROOT / "tests/spec_v27_pdf_renderer.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    mapper = MAPPER.read_text(encoding="utf-8", errors="replace")
    test = TEST.read_text(encoding="utf-8", errors="replace")

    for marker in (
        "def _canonical_gross_profit(",
        "def _canonical_opex(",
        'gross_profit = _canonical_gross_profit(metrics)',
        'opex = _canonical_opex(metrics)',
    ):
        require(marker in mapper, f"mapper missing marker: {marker}")

    require("revenue_actual" in mapper and "gross_margin" in mapper, "gross profit derivation inputs missing")
    require("operating_income" in mapper, "OpEx derivation input missing")
    require("def test_operating_metrics_derives_gross_profit_and_opex_from_canonical_metrics" in test, "focused regression missing")

    # Execute the same data path used by EN and JP reports.
    import sys
    sys.path.insert(0, str(ROOT))
    from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
    from backend.earnings_deep_dive.schemas import FinancialMetrics

    metrics = FinancialMetrics(
        revenue_actual=81_610_000_000,
        revenue_yoy=0.78,
        gross_margin=0.7493,
        gross_profit=10_000_000_000,
        opex=2_000_000_000,
        operating_income=53_540_000_000,
        operating_margin=0.656,
        net_income=18_000_000_000,
    )

    rows_by_lang = {}
    for language in ("en", "jp"):
        report = build_earnings_deep_dive_report(
            ticker="NVDA",
            company="NVIDIA Corporation",
            quarter="FY2027 Q1",
            language=language,
            metrics=metrics,
        )
        section = next(item for item in report.sections if item.key == "Operating Metrics")
        rows_by_lang[language] = section.table.rows

    en_rows = rows_by_lang["en"]
    jp_rows = rows_by_lang["jp"]
    require(en_rows[1].cells[0] == "$61.2B", f"EN Gross Profit not canonical: {en_rows[1].cells[0]}")
    require(jp_rows[1].cells[0] == en_rows[1].cells[0], "JP Gross Profit differs from EN")
    require(en_rows[3].cells[0] == "$7.6B", f"EN OpEx not canonical: {en_rows[3].cells[0]}")
    require(jp_rows[3].cells[0] == en_rows[3].cells[0], "JP OpEx differs from EN")
    require(en_rows[1].cells[0] != "$10.0B", "Gross Profit still uses stale gross_profit field")
    require(en_rows[3].cells[0] != "$2.0B", "OpEx still uses stale opex field")

    print("VERIFY_T_C02F3308_READY")


if __name__ == "__main__":
    main()
