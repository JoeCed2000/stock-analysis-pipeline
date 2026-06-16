#!/usr/bin/env python3
"""Deterministic proof for GOOG annotated-PDF manual review closeout."""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "analyses" / "feedback_GOOG"
ENTRY_ID = "2026-05-28_043100"
FORBIDDEN = ["Auto-intake", "Kanban", "task_id", "processing_task", "processing_profile", "cron", "triage", "client"]


def load_entry() -> dict:
    data = json.loads((BASE / "index.json").read_text())
    for entry in data:
        if entry.get("id") == ENTRY_ID:
            return entry
    raise AssertionError(f"missing feedback entry {ENTRY_ID}")


def check_api_file(ticker: str, filename: str) -> None:
    url = f"http://127.0.0.1:8780/api/feedback-file/{ticker}/{urllib.request.pathname2url(filename)}"
    with urllib.request.urlopen(url, timeout=15) as response:
        assert response.status == 200, (filename, response.status)
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith(("application/pdf", "image/")), (filename, content_type)
        assert int(response.headers.get("content-length") or "0") > 1000, filename
        response.read(64)


def main() -> None:
    entry = load_entry()
    note = entry.get("notes") or ""
    assert entry.get("processed") is True
    assert "manual review completed" in note.lower(), note
    bad = [term for term in FORBIDDEN if re.search(re.escape(term), note, re.I)]
    assert not bad, bad
    summary_name = entry.get("manual_review_summary")
    assert summary_name == "2026-05-28_043100_manual_review_summary.json", summary_name
    summary_path = BASE / summary_name
    summary = json.loads(summary_path.read_text())
    assert summary.get("decision") == "MANUAL_REVIEW_COMPLETED_NEEDS_PRODUCT_DECISION"
    assert summary.get("annotation_count", 0) >= 20
    statuses = {theme["theme"]: theme["status"] for theme in summary.get("themes", [])}
    assert statuses.get("Japanese translation / language toggle") == "MISSING"
    assert statuses.get("Quarter label on title/tables") == "AMBIGUOUS_NEEDS_DECISION"
    assert any(v == "REFLECTED" for v in statuses.values())
    files = entry.get("files") or []
    assert len(files) == 5, files
    for filename in files:
        local_path = BASE / filename
        assert local_path.exists() and local_path.stat().st_size > 1000, filename
        check_api_file("GOOG", filename)
    # Public combined endpoint should expose the updated entry and clean note.
    with urllib.request.urlopen("http://127.0.0.1:8780/api/feedback", timeout=15) as response:
        data = json.load(response)
    entries = data if isinstance(data, list) else data.get("items") or data.get("feedback") or data.get("entries") or []
    public = next((item for item in entries if item.get("id") == ENTRY_ID), None)
    assert public is not None
    public_note = public.get("notes") or ""
    assert "manual review completed" in public_note.lower(), public_note
    assert not [term for term in FORBIDDEN if re.search(re.escape(term), public_note, re.I)]
    print("GOOG_MANUAL_REVIEW_READY")


if __name__ == "__main__":
    main()
