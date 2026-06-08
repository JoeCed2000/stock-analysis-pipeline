"""Tests for FastAPI endpoint edge cases."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fastapi.dependencies.utils
import pytest
from fastapi import HTTPException, Request

fastapi.dependencies.utils.ensure_multipart_is_installed = lambda: None

from backend import main


def test_list_analyses_parses_hyphenated_date_and_snapshot_ticker(tmp_path, monkeypatch):
    analyses_dir = tmp_path / "analyses"
    analysis = analyses_dir / "2026-05-04_MC_PA_LVMH_Moet_Hennessy"
    (analysis / "03_financial_data_sources").mkdir(parents=True)
    (analysis / "07_final_report").mkdir(parents=True)
    (analysis / "03_financial_data_sources" / "yahoo_snapshot_MC.PA.json").write_text("{}")
    (analysis / "07_final_report" / "report.md").write_text("# Report")

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)

    response = asyncio.run(main.list_analyses())

    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload["analyses"][0]["ticker"] == "MC.PA"
    assert payload["analyses"][0]["date"] == "2026-05-04"
    assert payload["analyses"][0]["has_report"] is True


def test_dossier_download_finds_existing_uppercase_directory_for_lowercase_request(
    tmp_path, monkeypatch
):
    analyses_dir = tmp_path / "analyses"
    analysis = analyses_dir / "2026-05-04_AAPL_Apple_Inc"
    (analysis / "03_financial_data_sources").mkdir(parents=True)
    (analysis / "07_final_report").mkdir(parents=True)
    (analysis / "03_financial_data_sources" / "financials_AAPL.xlsx").write_bytes(b"xlsx")
    (analysis / "07_final_report" / "report.pdf").write_bytes(b"pdf")

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr(
        "backend.async_dossier.get_dossier_status",
        lambda ticker: {"ready": True, "files": [], "stage": "complete", "download_enabled": True},
    )

    response = asyncio.run(main.dossier_download("aapl"))

    assert response.status_code == 200
    assert response.media_type == "application/zip"


def test_require_auth_rejects_forged_allowed_origin_without_api_key(monkeypatch):
    monkeypatch.setattr(main, "_API_KEY", "secret-test-key")
    request = SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.10"),
        headers={"origin": "https://sa.cedlabusa.net", "referer": "https://sa.cedlabusa.net/admin"},
        query_params={},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main._require_auth(cast(Request, request)))

    assert exc.value.status_code == 403


def test_cache_overview_flush_route_requires_auth_dependency():
    route = cast(Any, next(
        route
        for route in main.app.routes
        if getattr(route, "path", "") == "/api/cache/overview/{ticker}/flush"
    ))

    assert any(
        dependency.call is main._require_auth
        for dependency in route.dependant.dependencies
    )


def test_dossier_download_missing_dossier_is_read_only(tmp_path, monkeypatch):
    analyses_dir = tmp_path / "analyses"
    analyses_dir.mkdir()
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("GET /api/dossier/{ticker}/download must not trigger analysis")

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr(
        "backend.async_dossier.get_dossier_status",
        lambda ticker: {"ready": False, "files": [], "stage": "missing", "download_enabled": False},
    )
    monkeypatch.setattr("backend.pipeline.analyze_ticker", fail_if_called)
    # Mock _ticker_exists to simulate a non-existent ticker so the noise gate fires
    monkeypatch.setattr("backend.main._ticker_exists", lambda ticker: False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.dossier_download("MISSING"))

    assert exc.value.status_code == 404
    assert called is False


def test_dossier_download_noise_gate_prevents_intake_on_fake_ticker(tmp_path, monkeypatch):
    """When a non-existent ticker has no local analysis, the noise gate
    returns 404 without calling _record_pdf_client_failure (no Kanban intake).
    """
    analyses_dir = tmp_path / "analyses"
    analyses_dir.mkdir()
    intake_calls = []

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr("backend.main._ticker_exists", lambda ticker: False)
    monkeypatch.setattr(
        "backend.main._record_pdf_client_failure",
        lambda *args, **kwargs: intake_calls.append(True),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.dossier_download("FAKETKR"))

    assert exc.value.status_code == 404
    assert len(intake_calls) == 0, "Noise gate must NOT call _record_pdf_client_failure for fake tickers"


def test_dossier_download_noise_gate_skips_intake_on_invalid_ticker(tmp_path, monkeypatch):
    """Invalid ticker (shorter than 2 chars) should still 404 silently."""
    analyses_dir = tmp_path / "analyses"
    analyses_dir.mkdir()
    intake_calls = []

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr("backend.main._ticker_exists", lambda ticker: False)
    monkeypatch.setattr(
        "backend.main._record_pdf_client_failure",
        lambda *args, **kwargs: intake_calls.append(True),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.dossier_download("X"))

    assert exc.value.status_code == 404
    assert len(intake_calls) == 0


def test_dossier_download_still_records_failure_for_real_ticker_without_analysis(tmp_path, monkeypatch):
    """Real tickers (AAPL) with no analysis must still record the failure
    and create a Kanban intake — the noise gate only blocks fake tickers.
    """
    analyses_dir = tmp_path / "analyses"
    analyses_dir.mkdir()
    intake_calls = []

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr("backend.main._ticker_exists", lambda ticker: True)
    monkeypatch.setattr(
        "backend.async_dossier.get_dossier_status",
        lambda ticker: {"ready": False, "files": [], "stage": "not_started", "download_enabled": False},
    )
    monkeypatch.setattr(
        "backend.main._record_pdf_client_failure",
        lambda *args, **kwargs: intake_calls.append(True),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.dossier_download("AAPL"))

    assert exc.value.status_code == 404
    assert len(intake_calls) == 1, "Real tickers must still trigger failure intake"


def test_dossier_download_quarter_param_is_read_only(tmp_path, monkeypatch):
    analyses_dir = tmp_path / "analyses"
    analysis = analyses_dir / "2026-05-04_AAPL_Apple_Inc"
    (analysis / "07_final_report").mkdir(parents=True)
    (analysis / "07_final_report" / "report.pdf").write_bytes(b"pdf")

    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr(
        "backend.async_dossier.get_dossier_status",
        lambda ticker: {"ready": True, "files": [], "stage": "complete", "download_enabled": True},
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.dossier_download("AAPL", quarter="2025Q4"))

    assert exc.value.status_code == 404


def test_report_pdf_does_not_retry_when_validator_blocked(tmp_path, monkeypatch):
    analyses_dir = tmp_path / "analyses"
    analysis = analyses_dir / "2026-05-04_AAPL_Apple_Inc"
    final_report_dir = analysis / "07_final_report"
    data_dir = analysis / "03_financial_data_sources"
    final_report_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    (final_report_dir / "report.md").write_text("# Report")
    (data_dir / "financials_AAPL.xlsx").write_bytes(b"xlsx")
    (final_report_dir / "deep_dive_validation.json").write_text(
        json.dumps({"passed": False, "issues": ["Forbidden marker found"]}),
        encoding="utf-8",
    )

    def fail_if_thread_started(*args, **kwargs):
        raise AssertionError("Validator-blocked PDFs must not be regenerated indefinitely")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr("threading.Thread", fail_if_thread_started)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.get_report_pdf("AAPL"))

    assert exc.value.status_code == 422
    detail = cast(dict[str, Any], exc.value.detail)
    assert detail["status"] == "pdf_blocked"
    assert detail["retryable"] is False
    assert "Forbidden marker found" in detail["issues"]


def test_root_requirements_include_backend_requirements():
    def package_names(path):
        names = set()
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line.split("==")[0].split(">=")[0].split("[")[0].lower())
        return names

    project_root = Path(__file__).resolve().parents[1]
    root = package_names(project_root / "requirements.txt")
    backend = package_names(project_root / "backend" / "requirements.txt")

    assert backend <= root


def test_record_pdf_client_failure_logs_failed_and_launches_intake(monkeypatch):
    events = []
    intake_calls = []

    monkeypatch.setattr(main, "log_search", lambda *args, **kwargs: events.append((args, kwargs)))

    class ImmediateThread:
        def __init__(self, target, daemon=True):
            self.target = target
            self.daemon = daemon
        def start(self):
            self.target()

    monkeypatch.setattr("threading.Thread", ImmediateThread)

    import backend.feedback_pipeline as feedback_pipeline
    monkeypatch.setattr(
        feedback_pipeline,
        "process_pdf_failure",
        lambda **kwargs: intake_calls.append(kwargs) or "t_pdf1234",
    )

    main._record_pdf_client_failure(
        "avgo",
        source="report_pdf",
        status="pdf_blocked",
        message="PDF blocked for client",
        issues=["validator failed"],
        language="jp",
        quarter="latest",
        directory="/tmp/analysis",
    )

    assert events[0][0][:3] == ("avgo", "failed", 0)
    assert events[0][1]["user_agent"] == "pdf-client-failure"
    assert "report_pdf:pdf_blocked" in events[0][1]["error"]
    assert intake_calls == [{
        "ticker": "avgo",
        "source": "report_pdf",
        "status": "pdf_blocked",
        "message": "PDF blocked for client",
        "issues": ["validator failed"],
        "language": "jp",
        "quarter": "latest",
        "directory": "/tmp/analysis",
    }]


def test_process_pdf_failure_is_idempotent_and_creates_single_task(tmp_path, monkeypatch):
    from backend import feedback_pipeline

    monkeypatch.setattr(feedback_pipeline, "PDF_FAILURE_INTAKE_PATH", tmp_path / "intake.json")
    monkeypatch.setattr(feedback_pipeline, "run_preflight_gate", lambda: (True, "GO"))
    created = []
    dispatched = []
    monkeypatch.setattr(
        feedback_pipeline,
        "_kanban_create",
        lambda title, body, assignee="python-builder": created.append((title, body, assignee)) or "t_deadbeef",
    )
    monkeypatch.setattr(feedback_pipeline, "_kanban_dispatch", lambda: dispatched.append(True) or True)

    assert feedback_pipeline.process_pdf_failure(
        ticker="AVGO",
        source="report_pdf",
        status="pdf_blocked",
        message="PDF failed from the client perspective",
        issues=["pre-render error"],
        language="jp",
        quarter="latest",
        directory="/tmp/analysis",
    ) == "t_deadbeef"
    assert feedback_pipeline.process_pdf_failure(
        ticker="AVGO",
        source="report_pdf",
        status="pdf_blocked",
        message="PDF failed from the client perspective",
        issues=["pre-render error"],
        language="jp",
        quarter="latest",
        directory="/tmp/analysis",
    ) is None
    assert len(created) == 1
    assert created[0][2] == "python-builder"
    assert "Root cause analysis" in created[0][1]
    assert "client-visible PDF failure" in created[0][1]
    assert dispatched == [True]
