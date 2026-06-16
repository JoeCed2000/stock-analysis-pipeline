#!/usr/bin/env python3
"""Deterministic verification for Kanban task t_c6ffc957.

Verifies that the EDP-010/012 source policy architecture spec exists,
is substantive, contains all required architecture sections, and that no
application/API files were modified by this documentation-only card.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/feedback-audits/edp010_012_source_policy_architecture_2026-06-16.md"
REQUIRED_MARKERS = [
    "Executive decision",
    "WIKI_EVIDENCE",
    "GAP_MAP_EVIDENCE",
    "GRAPH_EVIDENCE",
    "SYMBOL_PLAN_EVIDENCE",
    "Options compared",
    "Recommended policy rules",
    "Acceptance criteria",
    "False-positive / false-collapse risks",
    "Validation command plan",
    "Rollback plan",
    "Claude critique placeholder",
]
REQUIRED_FILES = [
    "backend/earnings_deep_dive/prompts.py",
    "backend/earnings_deep_dive/report_model.py",
    "backend/earnings_deep_dive/pdf_renderer.py",
    "backend/earnings_deep_dive/mapper.py",
]


def fail(message: str) -> None:
    raise SystemExit(f"VERIFY_T_C6FFC957_FAIL: {message}")


def main() -> None:
    if not DOC.exists():
        fail(f"missing document: {DOC}")
    text = DOC.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count < 250:
        fail(f"document too short: {line_count} lines")
    for marker in REQUIRED_MARKERS:
        if marker not in text:
            fail(f"missing required marker: {marker}")
    for rel in REQUIRED_FILES:
        if rel not in text:
            fail(f"missing future implementation file reference: {rel}")
    if "No `/api/` endpoint changes" not in text and "No `/api/`" not in text:
        fail("missing explicit /api/ no-touch statement")

    tracked_changed = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    changed = tracked_changed + untracked
    forbidden = [p for p in tracked_changed if p.startswith("backend/") or p.startswith("frontend/")]
    if forbidden:
        fail(f"documentation-only task changed application files: {forbidden}")
    if "docs/feedback-audits/edp010_012_source_policy_architecture_2026-06-16.md" not in changed:
        # If already committed, this is still acceptable as long as the file exists.
        committed = subprocess.check_output(
            ["git", "log", "--oneline", "-5", "--", str(DOC.relative_to(ROOT))],
            cwd=ROOT,
            text=True,
        )
        committed_l = committed.lower()
        if not any(token in committed_l for token in ("edp010", "edp-010", "source policy", "source display policy")):
            fail("document is neither in current diff nor recent git history")

    print(f"VERIFY_T_C6FFC957_READY: doc_lines={line_count}; app_files_unchanged=True; required_sections={len(REQUIRED_MARKERS)}")


if __name__ == "__main__":
    main()
