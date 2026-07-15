"""Security contract tests for public/private artifact access.

These tests encode docs/security/public-artifact-access-contract.md:
public curated artifacts stay usable without a frontend secret; private/raw
artifacts require the master key; batch status/download use a scoped signed
capability instead of enumerable internal job ids.
"""

import io
import json
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.main as _bm

TEST_KEY = "artifact-access-test-key"
CAPABILITY_SECRET = "batch-capability-test-secret-with-enough-entropy"


@pytest.fixture(autouse=True)
def isolate_artifact_state(monkeypatch, tmp_path):
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setenv("BATCH_CAPABILITY_SECRET", CAPABILITY_SECRET)
    monkeypatch.setenv("BATCH_CAPABILITY_TTL_SECONDS", "86400")
    monkeypatch.setattr(_bm, "_API_KEY", TEST_KEY)
    monkeypatch.setattr(_bm, "_rate_limits", {})
    monkeypatch.setattr(_bm, "_RATE_LIMIT_HEAVY", 9999)
    monkeypatch.setattr(_bm, "_RATE_LIMIT_MODERATE", 9999)
    monkeypatch.setattr(_bm, "_RATE_LIMIT_DEFAULT", 9999)
    monkeypatch.setattr(_bm, "_batch_jobs", {})
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    monkeypatch.setattr(_bm, "BATCH_DIR", batch_dir)
    analyses_dir = tmp_path / "analyses"
    analysis = analyses_dir / "2026-07-11_AAPL_Apple_Inc"
    (analysis / "03_financial_data_sources").mkdir(parents=True)
    (analysis / "04_transcripts_and_management").mkdir(parents=True)
    (analysis / "06_extracted_data").mkdir(parents=True)
    (analysis / "07_final_report").mkdir(parents=True)

    (analysis / "03_financial_data_sources" / "financials_AAPL.xlsx").write_bytes(b"xlsx")
    (analysis / "04_transcripts_and_management" / "transcript_AAPL_Q1.txt").write_text(
        "verbatim transcript", encoding="utf-8"
    )
    (analysis / "04_transcripts_and_management" / "notes_secret.txt").write_text(
        "API_KEY=secret-like-value", encoding="utf-8"
    )
    (analysis / "06_extracted_data" / "sources_manifest.json").write_text(
        json.dumps([{"url": "https://example.test/source"}]), encoding="utf-8"
    )
    (analysis / "06_extracted_data" / "claim_traceability_matrix.csv").write_text(
        "claim,source\n1,source", encoding="utf-8"
    )
    (analysis / "06_extracted_data" / "raw_table.csv").write_text("raw,internal", encoding="utf-8")
    (analysis / "07_final_report" / "report.md").write_text("# AAPL Report", encoding="utf-8")
    (analysis / "07_final_report" / "earnings_deep_dive.pdf").write_bytes(b"%PDF-1.4\n")
    (analysis / "07_final_report" / "README.txt").write_text("final report readme", encoding="utf-8")
    hidden_secret = analysis / ".env"
    hidden_secret.write_text("TOKEN=hidden", encoding="utf-8")

    monkeypatch.setattr(_bm, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr(_bm, "_ticker_exists", lambda ticker: True)

    def fake_status(ticker):
        return {
            "ready": True,
            "download_enabled": True,
            "phase": "complete",
            "stage": "complete",
            "directory": str(analysis),
            "files": [str(analysis / "07_final_report" / "earnings_deep_dive.pdf")],
            "verification_issues": [],
        }

    monkeypatch.setattr("backend.async_dossier.get_dossier_status", fake_status)


@pytest.fixture
def remote_client():
    return TestClient(_bm.app, client=("203.0.113.42", 51000))


@pytest.fixture
def loopback_client():
    return TestClient(_bm.app, client=("127.0.0.1", 51000))


def _auth_headers():
    return {"X-API-Key": TEST_KEY}


# Public curated routes stay usable without a frontend master key.


def test_public_report_markdown_and_head_remain_unauthenticated(remote_client):
    get_resp = remote_client.get("/api/report/AAPL")
    head_resp = remote_client.head("/api/report/AAPL")

    assert get_resp.status_code == 200
    assert get_resp.text == "# AAPL Report"
    assert head_resp.status_code == 200


def test_public_dossier_download_filters_raw_and_secret_like_files(remote_client):
    resp = remote_client.get("/api/dossier/AAPL/download?lang=en")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = set(zf.namelist())

    assert "03_financial_data_sources/financials_AAPL.xlsx" in names
    assert "04_transcripts_and_management/transcript_AAPL_Q1.txt" in names
    assert "07_final_report/README.txt" in names
    assert all(not name.endswith((".json", ".csv", ".md")) for name in names)
    assert "04_transcripts_and_management/notes_secret.txt" not in names
    assert ".env" not in names


def test_public_dossier_status_hides_absolute_filesystem_paths(remote_client):
    resp = remote_client.get("/api/dossier/AAPL/status")

    assert resp.status_code == 200
    payload = resp.json()
    serialized = json.dumps(payload)
    assert "directory" not in payload
    assert "/" not in serialized
    assert "\\\\" not in serialized


# Private/raw artifact routes deny unauthenticated enumeration equally.


@pytest.mark.parametrize(
    "path",
    [
        "/api/analyze/AAPL/download",
        "/api/sources/AAPL",
        "/api/traceability/AAPL",
    ],
)
def test_private_artifact_routes_reject_remote_without_key_before_lookup(remote_client, path):
    resp = remote_client.get(path)

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid API key"


@pytest.mark.parametrize(
    "path",
    [
        "/api/analyze/AAPL/download",
        "/api/sources/AAPL",
        "/api/traceability/AAPL",
    ],
)
def test_private_artifact_routes_reject_loopback_and_spoofed_browser_headers(loopback_client, path):
    resp = loopback_client.get(
        path,
        headers={
            "Origin": "https://sa.cedlabusa.net",
            "Referer": "https://sa.cedlabusa.net/",
            "Host": "sa.cedlabusa.net",
            "ngrok-skip-browser-warning": "true",
        },
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid API key"


@pytest.mark.parametrize(
    "path,content_type",
    [
        ("/api/analyze/AAPL/download", "application/zip"),
        ("/api/sources/AAPL", "application/json"),
        ("/api/traceability/AAPL", "text/csv"),
    ],
)
def test_private_artifact_routes_accept_correct_master_key(remote_client, path, content_type):
    resp = remote_client.get(path, headers=_auth_headers())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(content_type)


# Batch access is capability-scoped, signed, time-bounded, and non-enumerable.


def _make_fake_result(ticker="AAPL"):
    from backend.models import AnalysisResult, Scoring

    return AnalysisResult(
        ticker=ticker,
        company_name=f"Test {ticker} Inc.",
        decision="BUY",
        scoring=Scoring(
            financial_health=7,
            growth=8,
            valuation=7,
            management=4,
            moat=3,
            sentiment=2,
        ),
        price_native=150.0,
        currency="USD",
        market_cap=2.5e12,
        sector="Technology",
        retrieved_at="2026-07-11T12:00:00",
    )


def test_batch_submit_returns_signed_capability_not_internal_id(remote_client):
    resp = remote_client.post("/api/batch/analyze", json={"tickers": ["AAPL"]})

    assert resp.status_code == 200
    capability = resp.json()["job_id"]
    assert "." in capability
    assert len(capability) > 80
    assert capability not in _bm._batch_jobs
    assert len(_bm._batch_jobs) == 1


@patch("backend.main.run_analysis_parallel")
def test_valid_batch_capability_status_download_and_mutation_rejection(mock_run, remote_client):
    mock_run.return_value = {"results": {"AAPL": _make_fake_result("AAPL")}, "errors": {}}
    submit = remote_client.post("/api/batch/analyze", json={"tickers": ["AAPL"]})
    capability = submit.json()["job_id"]
    internal_job_id = next(iter(_bm._batch_jobs))

    status = remote_client.get(f"/api/batch/{capability}/status")
    assert status.status_code == 200
    assert status.json()["job_id"] == capability
    assert status.json()["status"] == "completed"

    download = remote_client.get(f"/api/batch/{capability}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")

    mutated = capability[:-1] + ("A" if capability[-1] != "A" else "B")
    assert remote_client.get(f"/api/batch/{mutated}/status").status_code == 404
    assert remote_client.get(f"/api/batch/{internal_job_id}/status").status_code == 404
    assert remote_client.get(
        f"/api/batch/{internal_job_id}/status", headers=_auth_headers()
    ).status_code == 200


def test_expired_batch_capability_returns_generic_not_found(remote_client):
    internal_job_id = "internal-expired-job"
    _bm._batch_jobs[internal_job_id] = {
        "job_id": internal_job_id,
        "tickers": ["AAPL"],
        "status": "completed",
        "created_at": "2026-07-11T12:00:00",
        "results": {"AAPL": _make_fake_result("AAPL")},
        "errors": {},
        "completed": 1,
        "total": 1,
    }
    expired = _bm._sign_batch_capability(
        internal_job_id,
        issued_at=int(time.time()) - 3600,
        ttl_seconds=1,
    )

    resp = remote_client.get(f"/api/batch/{expired}/status")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Job not found"}
