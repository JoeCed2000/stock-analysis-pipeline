#!/usr/bin/env python3
"""Kernel proof for NVDA transcript URL fiscal-quarter resolution.

Verifies the 2026-06-16 feedback closeout:
- StockAnalysis transcript URL `/q1-2027/` resolves to FY2027 Q1 before filing/yfinance fallbacks.
- Focused regression suites pass.
- NVDA feedback notes are public-safe and attachments are reachable.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV_PY = ROOT / "backend" / ".venv" / "bin" / "python"
TARGET_ID = "2026-06-11_061719"
FORBIDDEN_PUBLIC_TERMS = ("Auto-intake", "Kanban", "cron", "worker", "task_id", "dispatcher")
ATTACHMENTS = [
    "2026-06-11_061719_deep_dive_NVDA.pdf",
    "2026-06-11_061719_NVDA_company_earnings_results_2026-06-09_comment_by_nt.pdf",
    "2026-06-11_061719_Screenshot_2026-06-10_at_10.48.22_PM.png",
]


def run(cmd: list[str], *, timeout: int = 120) -> str:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed {cmd!r}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout + proc.stderr


def check_resolver() -> None:
    code = """
import backend.pipeline as pl
pl._latest_filing_period = lambda ticker: '2026Q1'
print(pl._resolve_deep_dive_quarter(
    ticker='NVDA',
    transcript_source={'url':'https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/'},
    yf_data={'quarter':'2026Q1','financials':{}},
))
"""
    out = run([str(VENV_PY), "-c", code])
    assert out.strip().endswith("FY2027 Q1"), out


def check_tests() -> None:
    out = run([
        str(VENV_PY),
        "-m",
        "pytest",
        "tests/test_deep_dive_quarter_resolution.py",
        "tests/test_client_pdf_revision.py",
        "tests/test_pipeline_transcript_url.py",
        "tests/test_earnings_pdf_template.py",
        "tests/test_earnings_pdf_renderer.py",
        "-q",
    ], timeout=240)
    assert "65 passed" in out, out


def check_feedback_json() -> None:
    path = ROOT / "analyses" / "feedback_NVDA" / "index.json"
    data = json.loads(path.read_text())
    entry = next((x for x in data if x.get("id") == TARGET_ID), None)
    assert entry, f"missing feedback {TARGET_ID}"
    assert entry.get("processed") is True
    assert entry.get("status") == "taken_into_account"
    notes = entry.get("notes") or ""
    assert "FY2027 Q1" in notes
    assert "q1-2027" in notes
    for term in FORBIDDEN_PUBLIC_TERMS:
        assert term.lower() not in notes.lower(), f"forbidden term in public note: {term}"

    access_entry = next((x for x in data if x.get("id") == "2026-06-11_061802"), None)
    assert access_entry and access_entry.get("status") == "taken_into_account"
    access_notes = access_entry.get("notes") or ""
    for term in FORBIDDEN_PUBLIC_TERMS:
        assert term.lower() not in access_notes.lower(), f"forbidden term in access note: {term}"


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        assert resp.status == 200, resp.status
        return json.load(resp)


def check_api_and_attachments() -> None:
    payload = fetch_json("http://127.0.0.1:8780/api/feedback/NVDA")
    entries = payload.get("entries") or []
    entry = next((x for x in entries if x.get("id") == TARGET_ID), None)
    assert entry, f"feedback {TARGET_ID} missing from API"
    assert entry.get("status") == "taken_into_account"
    assert "FY2027 Q1" in (entry.get("notes") or "")

    for filename in ATTACHMENTS:
        url = f"http://127.0.0.1:8780/api/feedback-file/NVDA/{filename}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read(16)
            assert resp.status == 200
            assert body, filename


def check_fresh_pdf_endpoint() -> None:
    url = "http://127.0.0.1:8780/api/report/NVDA/pdf?lang=en&audience_mode=nami_personal"
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = resp.read()
        assert resp.status == 200
        assert resp.headers.get("content-type", "").startswith("application/pdf")
        assert len(body) > 300_000, len(body)
    import tempfile
    import fitz
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(body)
        tmp.flush()
        doc = fitz.open(tmp.name)
        text = "\n".join(str(page.get_text("text")) for page in doc)
        assert doc.page_count >= 15, doc.page_count
        assert "FY2027 Q1" in text
        assert "FY2026 Q4" not in text
        assert "Recommendation: BUY" in text
        assert "FCF Margin" in text
        assert "Net Cash" in text


def main() -> int:
    check_resolver()
    check_tests()
    check_feedback_json()
    check_api_and_attachments()
    check_fresh_pdf_endpoint()
    print("ALL CHECKS PASSED: NVDA_TRANSCRIPT_URL_QUARTER_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
