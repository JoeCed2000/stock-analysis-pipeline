"""
API pipeline smoke test — HTTP-level flow (requires running backend).
Tests the orchestration/cache/root_path/browser-flow bugs that SA historically suffered.
Marked 'integration' — not mandatory on every commit.

Tests auto-skip when no backend listens on 127.0.0.1:8780. The two
analyze tests trigger REAL pipeline runs (LLM cost, several minutes):
they additionally require SA_RUN_LIVE_SMOKE=1.
"""
import os
import pytest
import time
import requests

BASE = "http://127.0.0.1:8780/stock-analysis"


def _backend_up() -> bool:
    try:
        return requests.get(f"{BASE}/api/health", timeout=5).status_code == 200
    except requests.RequestException:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _backend_up(), reason="live backend not reachable on 127.0.0.1:8780"),
]

requires_live_generation = pytest.mark.skipif(
    os.getenv("SA_RUN_LIVE_SMOKE") != "1",
    reason="triggers a real analysis pipeline run (LLM cost) — set SA_RUN_LIVE_SMOKE=1 to enable",
)


def _wait_for_job(job_id: str, timeout: int = 120) -> dict:
    """Poll job status until complete or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/analyze/job/{job_id}")
        assert r.status_code == 200, f"Job status failed: {r.status_code}"
        data = r.json()
        if data.get("status") in ("completed", "failed"):
            return data
        time.sleep(2)
    pytest.fail(f"Job {job_id} timed out after {timeout}s")


class TestAPIPipelineSmoke:
    """Full HTTP flow: async analyze → poll → PDF/download."""

    @requires_live_generation
    def test_async_analyze_and_poll(self):
        """POST /api/analyze/async for NVDA → poll until complete.

        A full dossier run includes the LLM deep-dive (4-8 min in
        production) — 180s was a guaranteed timeout."""
        r = requests.post(f"{BASE}/api/analyze/async", json={
            "tickers": ["NVDA"],
            "language": "en",
        })
        assert r.status_code in (200, 202), f"Async analyze failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        job_id = data.get("job_id")
        assert job_id, f"No job_id in response: {data}"

        result = _wait_for_job(job_id, timeout=600)
        assert result.get("status") == "completed", \
            f"Job failed: {result.get('error', 'unknown')}"

    def test_pdf_endpoint_returns_pdf(self):
        """GET /api/report/NVDA/pdf returns valid PDF.

        202 means the endpoint spawned/joined a background generation —
        without the live-generation opt-in we skip instead of timing out,
        with it we poll to completion (4-8 min for a full deep-dive)."""
        r = requests.get(f"{BASE}/api/report/NVDA/pdf")
        if r.status_code in (202, 422) and os.getenv("SA_RUN_LIVE_SMOKE") != "1":
            pytest.skip(
                f"PDF not immediately servable (HTTP {r.status_code}) — requires a "
                "generation run; set SA_RUN_LIVE_SMOKE=1 to wait for it"
            )
        deadline = time.time() + 600
        while r.status_code == 202 and time.time() < deadline:
            time.sleep(10)
            r = requests.get(f"{BASE}/api/report/NVDA/pdf")
        assert r.status_code == 200, f"PDF endpoint failed: {r.status_code}"
        assert "application/pdf" in r.headers.get("content-type", ""), \
            f"Not a PDF: {r.headers.get('content-type')}"
        assert len(r.content) > 10000, f"PDF too small: {len(r.content)} bytes"
        assert r.content[:4] == b"%PDF", "Not a valid PDF header"

    def test_dossier_download_returns_zip(self):
        """GET /api/dossier/NVDA/download returns ZIP."""
        r = requests.get(f"{BASE}/api/dossier/NVDA/download")
        if r.status_code == 404:
            pytest.skip("Dossier not yet generated (may need prior deep-dive)")
        assert r.status_code == 200, f"Dossier download failed: {r.status_code}"
        assert "application/zip" in r.headers.get("content-type", ""), \
            f"Not a ZIP: {r.headers.get('content-type')}"

    def test_health_endpoint(self):
        """GET /api/health returns commit info, timestamp, and version."""
        r = requests.get(f"{BASE}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "commit" in data, f"No commit in health: {data}"
        assert "timestamp" in data, f"No timestamp in health: {data}"
        assert "version" in data, f"No version in health: {data}"

    def test_no_root_path_double_prefix(self):
        """Regression: /stock-analysis/stock-analysis/ should not exist."""
        r = requests.get(f"{BASE}/stock-analysis/api/health")
        assert r.status_code == 404, \
            f"Double prefix should 404, got {r.status_code} — root_path double-prefix bug present"


class TestAPIAnalyzeSync:
    """Sync analyze endpoint (may be slow — use with long timeout)."""

    @pytest.mark.slow
    @requires_live_generation
    def test_sync_analyze_returns_result(self):
        """POST /api/analyze returns the batch analysis shape.

        Contract: the endpoint takes {"tickers": [...]} and answers
        {"results": [...], "errors": [...]} with per-result scoring.total
        on the /40 scale (the flat top-level ticker/score shape is gone)."""
        r = requests.post(f"{BASE}/api/analyze", json={
            "tickers": ["AAPL"],
            "language": "en",
        }, timeout=600)
        assert r.status_code in (200, 422), \
            f"Sync analyze failed: {r.status_code} {r.text[:200]}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("results"), f"No results in response: {list(data.keys())[:10]}"
            result = data["results"][0]
            assert result.get("ticker") == "AAPL"
            assert "scoring" in result, f"No scoring in result: {list(result.keys())[:10]}"
            assert 0 <= result["scoring"]["total"] <= 40
            assert "decision" in result
