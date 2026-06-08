"""IN-006: Tests for batch analysis endpoints.

Endpoints tested:
- POST /api/batch/upload — upload CSV/text with tickers
- POST /api/batch/analyze — submit tickers, get job_id
- GET /api/batch/{job_id}/status — poll for status
- GET /api/batch/{job_id}/download — download ZIP of results
"""
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Do NOT import `app` from backend.main at module level —
# we need to control auth/env state per test.
import backend.main as _bm

TEST_KEY = "test-batch-key"


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch, tmp_path):
    """Isolate all backend state for batch testing."""
    # Auth
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setattr(_bm, "_API_KEY", TEST_KEY)
    # Batch storage
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    monkeypatch.setattr(_bm, "BATCH_DIR", batch_dir)
    # In-memory jobs — point to a fresh dict
    fresh_jobs = {}
    monkeypatch.setattr(_bm, "_batch_jobs", fresh_jobs)
    # Disable rate limiting for tests
    monkeypatch.setattr(_bm, "_rate_limits", {})
    monkeypatch.setattr(_bm, "_RATE_LIMIT_HEAVY", 9999)
    monkeypatch.setattr(_bm, "_RATE_LIMIT_MODERATE", 9999)
    monkeypatch.setattr(_bm, "_RATE_LIMIT_DEFAULT", 9999)


@pytest.fixture
def client():
    return TestClient(_bm.app)


def _headers():
    return {"X-API-Key": TEST_KEY}


def _make_fake_result(ticker="TEST"):
    """Create a mock analysis result."""
    from backend.models import AnalysisResult, Scoring
    return AnalysisResult(
        ticker=ticker,
        company_name=f"Test {ticker} Inc.",
        decision="BUY",
        scoring=Scoring(
            financial_health=7, growth=8, valuation=7, management=4,
            moat=3, sentiment=2,
        ),
        price_native=150.0,
        currency="USD",
        market_cap=2.5e12,
        sector="Technology",
        retrieved_at="2026-05-26T12:00:00",
    )


# ── POST /api/batch/upload ────────────────────────────────────────────────


class TestBatchUpload:
    def test_upload_csv(self, client):
        csv_content = b"AAPL\nMSFT\nNVDA"
        resp = client.post(
            "/api/batch/upload",
            files={"file": ("tickers.csv", csv_content, "text/csv")},
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_found"] == 3
        assert len(data["items"]) == 3

    def test_upload_text_file(self, client):
        text = b"AAPL MSFT\nGOOGL, AMZN"
        resp = client.post(
            "/api/batch/upload",
            files={"file": ("tickers.txt", text, "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["total_found"] == 4

    def test_upload_empty_file(self, client):
        resp = client.post(
            "/api/batch/upload",
            files={"file": ("empty.txt", b"", "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["total_found"] == 0

    def test_upload_with_commas_newlines(self, client):
        text = b"AAPL,MSFT,GOOGL,NVDA\nAMZN,TSLA,META"
        resp = client.post(
            "/api/batch/upload",
            files={"file": ("many.csv", text, "text/csv")},
            headers=_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["total_found"] == 7

    def test_upload_no_file_rejected(self, client):
        resp = client.post("/api/batch/upload", headers=_headers())
        assert resp.status_code == 400


# ── POST /api/batch/analyze ───────────────────────────────────────────────


class TestBatchAnalyze:
    def test_submit_tickers(self, client):
        resp = client.post(
            "/api/batch/analyze",
            json={"tickers": ["AAPL", "MSFT"]},
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "job_id" in data
        assert len(data["tickers"]) == 2

    def test_empty_tickers_rejected(self, client):
        resp = client.post(
            "/api/batch/analyze",
            json={"tickers": []},
            headers=_headers(),
        )
        assert resp.status_code == 422

    def test_too_many_tickers_rejected(self, client):
        resp = client.post(
            "/api/batch/analyze",
            json={"tickers": [f"TICK{i}" for i in range(26)]},
            headers=_headers(),
        )
        assert resp.status_code == 422

    def test_missing_tickers_rejected(self, client):
        resp = client.post(
            "/api/batch/analyze",
            json={},
            headers=_headers(),
        )
        assert resp.status_code == 422


# ── GET /api/batch/{job_id}/status ────────────────────────────────────────


class TestBatchStatus:
    def test_job_not_found(self, client):
        resp = client.get("/api/batch/nonexistent-job/status", headers=_headers())
        assert resp.status_code == 404

    @patch("backend.main.run_analysis_parallel")
    def test_status_returns_job_data(self, mock_run, client):
        fake = _make_fake_result("AAPL")
        mock_run.return_value = {"results": {"AAPL": fake}, "errors": {}}

        submit = client.post(
            "/api/batch/analyze",
            json={"tickers": ["AAPL"]},
            headers=_headers(),
        )
        assert submit.status_code == 200, f"Submit failed: {submit.text}"
        job_id = submit.json()["job_id"]

        resp = client.get(f"/api/batch/{job_id}/status", headers=_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
        assert "results" in data

    @patch("backend.main.run_analysis_parallel")
    def test_job_persisted_to_disk(self, mock_run, client, tmp_path):
        fake = _make_fake_result("AAPL")
        mock_run.return_value = {"results": {"AAPL": fake}, "errors": {}}

        submit = client.post(
            "/api/batch/analyze",
            json={"tickers": ["AAPL"]},
            headers=_headers(),
        )
        assert submit.status_code == 200, f"Submit failed: {submit.text}"
        job_id = submit.json()["job_id"]

        client.get(f"/api/batch/{job_id}/status", headers=_headers())

        job_file = tmp_path / "batches" / f"{job_id}.json"
        assert job_file.exists(), f"Expected {job_file}"


# ── GET /api/batch/{job_id}/download ──────────────────────────────────────


class TestBatchDownload:
    def test_download_job_not_found(self, client):
        resp = client.get("/api/batch/nonexistent/download", headers=_headers())
        assert resp.status_code == 404

    def test_download_pending_job_blocked(self, client):
        submit = client.post(
            "/api/batch/analyze",
            json={"tickers": ["AAPL"]},
            headers=_headers(),
        )
        assert submit.status_code == 200, f"Submit failed: {submit.text}"
        job_id = submit.json()["job_id"]

        resp = client.get(f"/api/batch/{job_id}/download", headers=_headers())
        assert resp.status_code == 400

    @patch("backend.main.run_analysis_parallel")
    def test_download_after_completion(self, mock_run, client):
        fake = _make_fake_result("AAPL")
        mock_run.return_value = {"results": {"AAPL": fake}, "errors": {}}

        submit = client.post(
            "/api/batch/analyze",
            json={"tickers": ["AAPL"]},
            headers=_headers(),
        )
        assert submit.status_code == 200, f"Submit failed: {submit.text}"
        job_id = submit.json()["job_id"]

        client.get(f"/api/batch/{job_id}/status", headers=_headers())

        resp = client.get(f"/api/batch/{job_id}/download", headers=_headers())
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/zip")


# ── _parse_tickers_from_text (unit test) ───────────────────────────────────


class TestParseTickersFromText:
    def test_single_ticker(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("AAPL")
        assert len(items) == 1
        assert items[0]["normalized"] == "AAPL"

    def test_comma_separated(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("AAPL, MSFT, NVDA")
        assert len(items) == 3

    def test_newline_separated(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("AAPL\nMSFT\nNVDA")
        assert len(items) == 3

    def test_mixed_separators(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("AAPL MSFT, NVDA\nGOOGL  AMZN")
        assert len(items) == 5

    def test_isin_mapped_to_ticker(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("US0378331005")
        assert len(items) == 1
        assert items[0]["type"] == "ISIN"

    def test_lowercase_uppercased(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("aapl msft")
        assert items[0]["normalized"] == "AAPL"

    def test_empty_returns_empty(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("")
        assert len(items) == 0

    def test_whitespace_only(self):
        from backend.main import _parse_tickers_from_text
        items = _parse_tickers_from_text("   \n  \t  ")
        assert len(items) == 0

    def test_ticker_shaped_unknown_symbol_marked_invalid(self, monkeypatch):
        import backend.main as main

        monkeypatch.setattr(main, "_ticker_exists", lambda ticker: ticker == "AAPL")
        items = main._parse_tickers_from_text("AAPL APPL")

        assert items[0]["normalized"] == "AAPL"
        assert items[0]["status"] == "valid"
        assert items[1]["normalized"] == "APPL"
        assert items[1]["status"] == "invalid"
        assert "Ticker not found" in items[1]["error"]

    def test_analyze_async_rejects_ticker_shaped_unknown_symbol(self, monkeypatch):
        import backend.main as main
        from fastapi import HTTPException
        from backend.models import TickerRequest

        monkeypatch.setattr(main, "_ticker_exists", lambda ticker: ticker == "AAPL")

        try:
            import asyncio
            asyncio.run(main.analyze_async(TickerRequest(tickers=["APPL"])))
        except HTTPException as exc:
            assert exc.status_code == 422
            assert isinstance(exc.detail, dict)
            assert exc.detail["error"] == "Ticker not found"
            assert exc.detail["invalid"] == ["APPL"]
        else:
            raise AssertionError("Expected APPL to be rejected before job creation")
