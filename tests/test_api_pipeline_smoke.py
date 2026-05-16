"""
API pipeline smoke test — HTTP-level flow (requires running backend).
Tests the orchestration/cache/root_path/browser-flow bugs that SA historically suffered.
Marked 'integration' — not mandatory on every commit.
"""
import pytest
import time
import requests

BASE = "http://127.0.0.1:8780/stock-analysis"
pytestmark = pytest.mark.integration


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

    def test_async_analyze_and_poll(self):
        """POST /api/analyze/async for NVDA → poll until complete."""
        r = requests.post(f"{BASE}/api/analyze/async", json={
            "ticker": "NVDA",
            "language": "en",
        })
        assert r.status_code in (200, 202), f"Async analyze failed: {r.status_code} {r.text[:200]}"
        data = r.json()
        job_id = data.get("job_id")
        assert job_id, f"No job_id in response: {data}"

        result = _wait_for_job(job_id, timeout=180)
        assert result.get("status") == "completed", \
            f"Job failed: {result.get('error', 'unknown')}"

    def test_pdf_endpoint_returns_pdf(self):
        """GET /api/report/NVDA/pdf returns valid PDF."""
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
        """GET /api/health returns commit info."""
        r = requests.get(f"{BASE}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "commit" in data, f"No commit in health: {data}"

    def test_no_root_path_double_prefix(self):
        """Regression: /stock-analysis/stock-analysis/ should not exist."""
        r = requests.get(f"{BASE}/stock-analysis/api/health")
        assert r.status_code == 404, \
            f"Double prefix should 404, got {r.status_code} — root_path double-prefix bug present"


class TestAPIAnalyzeSync:
    """Sync analyze endpoint (may be slow — use with long timeout)."""

    @pytest.mark.slow
    def test_sync_analyze_returns_result(self):
        """POST /api/analyze returns full analysis result."""
        r = requests.post(f"{BASE}/api/analyze", json={
            "ticker": "AAPL",
            "language": "en",
        }, timeout=300)
        assert r.status_code in (200, 422), \
            f"Sync analyze failed: {r.status_code} {r.text[:200]}"
        if r.status_code == 200:
            data = r.json()
            assert data.get("ticker") == "AAPL"
            assert "score" in data, f"No score in response: {list(data.keys())[:10]}"
            assert "decision" in data
