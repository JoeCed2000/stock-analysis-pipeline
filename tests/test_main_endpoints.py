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

    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.dossier_download("MISSING"))

    assert exc.value.status_code == 404
    assert called is False


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
