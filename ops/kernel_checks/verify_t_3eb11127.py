#!/usr/bin/env python3
"""Persistent proof for t_3eb11127 Segments metric-based rounding."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPPER = ROOT / "backend/earnings_deep_dive/mapper.py"
TEST = ROOT / "tests/spec_v27_pdf_renderer.py"
WIKI = ROOT / "WIKI.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.exists(), f"missing path: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def run(command: list[str], timeout: int = 120) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise AssertionError(f"command failed ({result.returncode}): {' '.join(command)}\n{output}")
    return output


def main() -> None:
    mapper = read(MAPPER)
    test = read(TEST)
    wiki = read(WIKI)

    mapper_markers = [
        'def _extract_segment_rows(',
        'segments.get("product_segments")',
        'segment["revenue"] = segment.get("revenue_quarterly")',
        'has_usable_segments = any(',
        'def _total_row(label: str = "Total")',
        'rows.append(_total_row("Total"))',
    ]
    for marker in mapper_markers:
        require(marker in mapper, f"mapper missing marker: {marker}")

    test_markers = [
        'def test_segments_rows_ignore_llm_rounded_values_for_en_jp_parity',
        '"Data Center"',
        '+92.0%',
        '$44.06B',
        'assert jp_rows["Data Center"][2] == en_rows["Data Center"][2]',
        'assert jp_rows["Total"][1] == en_rows["Total"][1]',
    ]
    for marker in test_markers:
        require(marker in test, f"test missing marker: {marker}")

    require("Segments canonical table rounding (t_3eb11127)" in wiki, "WIKI missing t_3eb11127 entry")
    require("pdf_renderer.py` presentation-only" in wiki, "WIKI missing presentation-only invariant")

    focused = run([
        sys.executable,
        "-m",
        "pytest",
        "tests/spec_v27_pdf_renderer.py::test_segments_rows_ignore_llm_rounded_values_for_en_jp_parity",
        "-q",
    ])
    require("1 passed" in focused, "focused Segments regression did not pass")

    print("VERIFY_T_3EB11127_READY")


if __name__ == "__main__":
    main()
