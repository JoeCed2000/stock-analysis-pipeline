"""Regression tests for API compatibility and in-process TestClient behavior."""

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


def test_testclient_bypasses_auth_when_api_key_is_configured(monkeypatch, tmp_path):
    """FastAPI TestClient uses synthetic host 'testclient', not localhost."""
    monkeypatch.setattr(main, "_API_KEY", "test-key")
    analyses_dir = tmp_path / "analyses"
    analyses_dir.mkdir()
    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)

    response = TestClient(main.app).get("/api/analyses")

    assert response.status_code == 200
    assert response.json() == {"analyses": []}


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
