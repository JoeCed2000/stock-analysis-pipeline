"""Regression tests for public client workflows on the static production UI.

The React app served from sa.cedlabusa.net cannot embed CED_CONTROL_KEY.
Client-facing analysis endpoints must therefore be public but rate-limited,
while privileged admin/debug/internal endpoints remain protected.
"""

import threading

import pytest
from fastapi.testclient import TestClient

import backend.main as _bm

TEST_KEY = "test-public-client-key"


@pytest.fixture(autouse=True)
def isolate_auth_and_rate_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setattr(_bm, "_API_KEY", TEST_KEY)
    monkeypatch.setattr(_bm, "_rate_limits", {})
    monkeypatch.setattr(_bm, "_RATE_LIMIT_HEAVY", 9999)
    monkeypatch.setattr(_bm, "_RATE_LIMIT_MODERATE", 9999)
    monkeypatch.setattr(_bm, "_RATE_LIMIT_DEFAULT", 9999)

    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    monkeypatch.setattr(_bm, "BATCH_DIR", batch_dir)
    monkeypatch.setattr(_bm, "_batch_jobs", {})


@pytest.fixture
def remote_client():
    """Simulate a production browser so loopback/testclient auth bypass does not apply."""
    return TestClient(_bm.app, client=("203.0.113.10", 50000))


def test_remote_quick_parser_upload_is_public(remote_client):
    resp = remote_client.post(
        "/api/batch/upload",
        files={"file": ("tickers.txt", b"NVDA\nAAPL", "text/plain")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_found"] == 2
    assert [item["normalized"] for item in payload["items"]] == ["NVDA", "AAPL"]


def test_remote_batch_submit_is_public_but_limited_by_schema(remote_client):
    resp = remote_client.post("/api/batch/analyze", json={"tickers": ["NVDA"]})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "pending"
    assert payload["tickers"] == ["NVDA"]
    assert payload["job_id"]


def test_remote_async_analysis_submit_is_public_without_starting_worker(remote_client, monkeypatch):
    created = {}

    def fake_create_job(tickers, lang):
        created["tickers"] = tickers
        created["lang"] = lang
        return "job-public-123"

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            # Do not execute the expensive background analysis in this auth regression test.
            created["thread_started"] = True

    monkeypatch.setattr("backend.job_store.create_job", fake_create_job)
    monkeypatch.setattr(threading, "Thread", FakeThread)

    resp = remote_client.post(
        "/api/analyze/async?lang=jp",
        json={"tickers": ["NVDA"], "deep_dive": False},
    )

    assert resp.status_code == 200
    assert resp.json() == {"job_id": "job-public-123", "status": "pending"}
    assert created == {"tickers": ["NVDA"], "lang": "jp", "thread_started": True}


def test_remote_admin_endpoint_stays_protected_without_api_key(remote_client):
    resp = remote_client.get("/api/admin/recent-searches")

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid API key"
