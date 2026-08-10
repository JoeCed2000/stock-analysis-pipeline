"""Regression tests for API compatibility and in-process TestClient behavior."""

from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from backend.models import TickerRequest
import backend.main as main


def test_ticker_request_accepts_legacy_single_ticker_payload():
    """Legacy clients may still send {"ticker": "NVDA"}."""
    request = TickerRequest.model_validate({"ticker": "NVDA", "language": "en"})

    assert request.tickers == ["NVDA"]
    assert request.deep_dive is False


def test_ticker_request_rejects_missing_tickers():
    """The compatibility shim must not allow an empty analysis request."""
    with pytest.raises(ValueError, match="At least one ticker is required"):
        TickerRequest.model_validate({})


def test_testclient_without_api_key_is_rejected_when_api_key_is_configured(monkeypatch, tmp_path):
    """Protected endpoints fail closed: no X-API-Key header means 403, regardless of host.

    FastAPI TestClient uses synthetic host 'testclient', not localhost, but _require_auth
    intentionally performs no host/loopback/Origin bypass — every caller must present the key.
    """
    monkeypatch.setattr(main, "_API_KEY", "test-key")
    analyses_dir = tmp_path / "analyses"
    analyses_dir.mkdir()
    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)

    response = TestClient(main.app).get("/api/analyses")

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid API key"}


def test_page_loads_do_not_rate_limit_ticker_parser(monkeypatch):
    """Static/page requests from one IP must not make ticker typing look broken."""
    monkeypatch.setattr(main, "_API_KEY", "test-key")
    monkeypatch.setattr(main, "_rate_limits", {})
    client = TestClient(main.app, client=("203.0.113.10", 50000))

    for _ in range(main._RATE_LIMIT_MODERATE + 5):
        assert client.get("/").status_code == 200

    response = client.post(
        "/api/batch/upload",
        headers={"X-API-Key": "test-key"},
        files={"file": ("input.txt", b"NVDA", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["normalized"] == "NVDA"


def test_async_analyze_endpoint_accepts_legacy_single_ticker(monkeypatch):
    """HTTP smoke payload {"ticker": "NVDA"} must not 422 before queuing."""
    started = []

    class DummyThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append(self.daemon)

    monkeypatch.setattr(main, "_API_KEY", "test-key")
    monkeypatch.setattr("backend.job_store.create_job", lambda tickers, lang: "job-test")
    monkeypatch.setattr("backend.job_store.update_job", lambda *args, **kwargs: None)
    monkeypatch.setattr("threading.Thread", DummyThread)

    response = TestClient(main.app).post(
        "/api/analyze/async",
        json={"ticker": "NVDA", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-test", "status": "pending"}
    assert started == [True]


def test_async_analyze_worker_forwards_live_progress_updates(monkeypatch, tmp_path):
    """Background jobs must expose live progress, not stay frozen at Starting analysis."""
    updates = []

    class InlineThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    class DummyResult:
        scoring = SimpleNamespace(total=33)

        def model_dump(self):
            return {
                "ticker": "NVDA",
                "company_name": "NVIDIA Corp",
                "financials": {},
                "valuation": {},
                "scoring": {},
            }

    def fake_run_analysis_parallel(*args, progress_callback=None, **kwargs):
        assert callable(progress_callback)
        progress_callback("Analyzing NVDA: financial data, SEC filings, scoring…")
        return {"results": {"NVDA": DummyResult()}, "errors": {}}

    def fake_update_job(job_id, **kwargs):
        updates.append(kwargs)

    monkeypatch.setattr(main, "_API_KEY", "test-key")
    monkeypatch.setattr(main, "ANALYSES_DIR", tmp_path / "analyses")
    monkeypatch.setattr("backend.job_store.create_job", lambda tickers, lang: "job-progress")
    monkeypatch.setattr("backend.job_store.update_job", fake_update_job)
    monkeypatch.setattr("threading.Thread", InlineThread)
    monkeypatch.setattr(main, "run_analysis_parallel", fake_run_analysis_parallel)
    monkeypatch.setattr(main, "log_search", lambda *args, **kwargs: None)

    response = TestClient(main.app).post(
        "/api/analyze/async?lang=jp",
        json={"tickers": ["NVDA"], "deep_dive": False},
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-progress", "status": "pending"}
    assert any(
        update.get("status") == "processing"
        and update.get("progress") == "Analyzing NVDA: financial data, SEC filings, scoring…"
        for update in updates
    )
