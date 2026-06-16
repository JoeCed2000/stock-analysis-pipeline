#!/usr/bin/env python3
"""Deterministic verification for t_e7846d85 EDP-010/012 Claude spec repair."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs/feedback-audits/edp010_012_source_policy_architecture_2026-06-16.md"
REVIEW = ROOT / "docs/feedback-audits/edp010_012_source_policy_claude_review_2026-06-16.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    require(SPEC.exists(), f"missing spec: {SPEC}")
    require(REVIEW.exists(), f"missing review artifact: {REVIEW}")

    wiki_path = ROOT / "WIKI.md"
    require(wiki_path.exists(), f"missing WIKI: {wiki_path}")

    spec = SPEC.read_text(encoding="utf-8")
    review = REVIEW.read_text(encoding="utf-8")
    wiki = wiki_path.read_text(encoding="utf-8")

    required_spec_markers = [
        "repair task: t_e7846d85",
        "Claude CHANGES_REQUIRED corrections integrated",
        "`_table(section, styles, fonts)`",
        "do not reference `_section_table_flowables(...)`; it is not present in the active renderer",
        "Phase 1 must detect calculated rows from conservative source-cell labels",
        "after deterministic enrichment, row numbering, and table sanitization",
        "source column is located by normalized header label",
        "must not mutate row labels or cell values",
        "all expected Operating Metrics rows are present",
        "Auditability fixture: model-level row cells still contain source values",
    ]
    for marker in required_spec_markers:
        require(marker in spec, f"spec missing marker: {marker}")

    forbidden_spec_markers = [
        "Status: PENDING EXTERNAL CRITIQUE",
        "Claude critique placeholder",
        "Current renderer has no table-level source-note path inside `_section_table_flowables(...)`.",
        "Update `_section_table_flowables(...)` to hide the visible Source column",
    ]
    for marker in forbidden_spec_markers:
        require(marker not in spec, f"spec still contains stale marker: {marker}")

    required_review_markers = [
        "Verdict: CHANGES_REQUIRED",
        "Option D, the hybrid model-level source display policy, is the right target",
        "Renderer symbol correction",
        "Grounding field reality check",
        "Policy application order",
        "No hardcoded Source column index",
        "No row/cell mutation by policy",
        "Operating Metrics default tightened",
        "Auditability regression criterion",
    ]
    for marker in required_review_markers:
        require(marker in review, f"review missing marker: {marker}")

    required_wiki_markers = [
        "EDP-010/012 source display spec repaired after Claude review",
        "Spec-only repair completed (t_e7846d85)",
        "VERIFY_T_E7846D85_READY",
        "edp010-012-claude-repair.json",
    ]
    for marker in required_wiki_markers:
        require(marker in wiki, f"WIKI missing marker: {marker}")

    print("VERIFY_T_E7846D85_READY")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"VERIFY_T_E7846D85_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
