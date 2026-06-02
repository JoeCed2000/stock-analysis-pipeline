"""Tests for /api/report/{ticker}/pdf idempotency guard.

TDD scope: prevent the 202-infinite-poll bug where every client poll
of the JP deep-dive PDF endpoint spawned a new background generator
thread. Fix references t_fda2f272 (sa-pipeline board 2026-06-01).

Expected behavior (after fix):
  - phase=PDF_GENERATING or PDF_VALIDATING  → 202 (no new thread)
  - phase=PDF_BLOCKED or FAILED             → 422 (terminal, no retry)
  - phase=None or other                     → normal flow (tested by
    existing curl/manual recipe, not in unit test)

Strategy: mock _find_analysis_dirs to return a synthetic dir with no
JP PDF, mock get_dossier_status to control the phase, hit the endpoint
via FastAPI TestClient, verify the HTTP status code.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture
def fake_analysis_dir(tmp_path: Path) -> Path:
    """Return a tmp dir with NO JP PDF — endpoint should consider it
    missing and decide whether to spawn a generator."""
    d = tmp_path / "NVDA_2026Q1_fake"
    d.mkdir()
    return d


@pytest.fixture
def client():
    """FastAPI TestClient for the real app. Heavy deps are mocked per-test."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


def test_jp_pdf_in_flight_returns_202_no_respawn(client, fake_analysis_dir):
    """When dossier phase is PDF_GENERATING, polling JP PDF must return
    202 (acknowledge "still generating") WITHOUT spawning a new thread."""
    with patch("backend.main._find_analysis_dirs", return_value=[fake_analysis_dir]), \
         patch("backend.async_dossier.get_dossier_status",
               return_value={"phase": "pdf_generating", "ready": False}), \
         patch("threading.Thread") as mock_thread:
        resp = client.get("/api/report/NVDA/pdf?lang=jp")
    assert resp.status_code == 202, (
        f"Expected 202 for in-flight generation, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["status"] == "generating"
    assert body["ticker"] == "NVDA"
    assert "retry_after_seconds" in body
    # CRITICAL: no new thread should have been spawned
    assert mock_thread.call_count == 0, (
        f"Expected 0 new threads, got {mock_thread.call_count}. "
        "This is the original bug — every poll was spawning a thread."
    )


def test_jp_pdf_validating_returns_202_no_respawn(client, fake_analysis_dir):
    """Same as above but during PDF_VALIDATING phase."""
    with patch("backend.main._find_analysis_dirs", return_value=[fake_analysis_dir]), \
         patch("backend.async_dossier.get_dossier_status",
               return_value={"phase": "pdf_validating", "ready": False}), \
         patch("threading.Thread") as mock_thread:
        resp = client.get("/api/report/NVDA/pdf?lang=jp")
    assert resp.status_code == 202
    assert mock_thread.call_count == 0


def test_jp_pdf_blocked_returns_422_terminal(client, fake_analysis_dir):
    """When dossier phase is PDF_BLOCKED, polling must return 422
    (terminal failure) — no retry, no new thread."""
    with patch("backend.main._find_analysis_dirs", return_value=[fake_analysis_dir]), \
         patch("backend.async_dossier.get_dossier_status",
               return_value={"phase": "pdf_blocked", "ready": False,
                             "error": "validator failed"}), \
         patch("threading.Thread") as mock_thread:
        resp = client.get("/api/report/NVDA/pdf?lang=jp")
    assert resp.status_code == 422, (
        f"Expected 422 for terminal failure, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("retryable") is False
    assert detail.get("phase") == "pdf_blocked"
    assert mock_thread.call_count == 0


def test_jp_pdf_failed_returns_422_terminal(client, fake_analysis_dir):
    """When dossier phase is FAILED, polling must return 422 — no retry."""
    with patch("backend.main._find_analysis_dirs", return_value=[fake_analysis_dir]), \
         patch("backend.async_dossier.get_dossier_status",
               return_value={"phase": "failed", "ready": False,
                             "error": "deep-dive generation crashed"}), \
         patch("threading.Thread") as mock_thread:
        resp = client.get("/api/report/NVDA/pdf?lang=jp")
    assert resp.status_code == 422
    detail = resp.json().get("detail", {})
    assert detail.get("phase") == "failed"
    assert mock_thread.call_count == 0


def test_jp_pdf_no_phase_proceeds_to_spawn(client, fake_analysis_dir):
    """When dossier has no phase (cold start, or after a stale thread
    died without updating phase), endpoint MUST still be able to spawn
    a new generator. This is the recovery path."""
    with patch("backend.main._find_analysis_dirs", return_value=[fake_analysis_dir]), \
         patch("backend.async_dossier.get_dossier_status",
               return_value={"phase": None, "ready": False}), \
         patch("threading.Thread") as mock_thread:
        # The spawn target itself will fail in test env (no real yfinance
        # data, no real generator), but we only assert that the spawn
        # was ATTEMPTED — i.e., a thread was created.
        try:
            resp = client.get("/api/report/NVDA/pdf?lang=jp")
        except Exception:
            # Spawning may raise (no real yfinance data in test env).
            # We only care that the spawn was attempted.
            pass
    # A new thread was scheduled (the bug-fix's "allowed" path)
    assert mock_thread.call_count == 1, (
        f"Expected 1 new thread on cold-start, got {mock_thread.call_count}. "
        "Recovery from stale phase state must still work."
    )
