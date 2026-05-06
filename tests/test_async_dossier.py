"""Tests for dossier readiness lookup."""

import json

from backend import async_dossier


def _write_ready_dossier(base, ticker="AAPL", validation=None):
    dossier_dir = base / "analyses" / f"2026-05-04_{ticker}_Apple_Inc"
    (dossier_dir / "03_financial_data_sources").mkdir(parents=True)
    (dossier_dir / "07_final_report").mkdir(parents=True)
    (dossier_dir / "03_financial_data_sources" / f"financials_{ticker}.xlsx").write_bytes(b"xlsx")
    (dossier_dir / "07_final_report" / "report.md").write_text("# Report")
    if validation is not None:
        (dossier_dir / "07_final_report" / "deep_dive_validation.json").write_text(
            json.dumps(validation),
            encoding="utf-8",
        )
    return dossier_dir


def test_get_dossier_status_checks_project_analyses_when_cwd_is_backend(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    _write_ready_dossier(tmp_path)
    backend_dir.mkdir()

    monkeypatch.chdir(backend_dir)
    async_dossier._dossier_registry.clear()

    status = async_dossier.get_dossier_status("AAPL")

    assert status["ready"] is True
    assert status["stage"] == "complete"


def test_get_dossier_status_enables_download_only_after_passed_validation(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write_ready_dossier(tmp_path, validation={"passed": True, "issues": []})

    monkeypatch.chdir(backend_dir)
    async_dossier._dossier_registry.clear()

    status = async_dossier.get_dossier_status("AAPL")

    assert status["ready"] is True
    assert status["deep_dive_validated"] is True
    assert status["verified"] is True
    assert status["download_enabled"] is True
    assert status["verification_issues"] == []


def test_get_dossier_status_blocks_download_when_validation_fails(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write_ready_dossier(
        tmp_path,
        validation={"passed": False, "issues": ["Forbidden marker found"]},
    )

    monkeypatch.chdir(backend_dir)
    async_dossier._dossier_registry.clear()

    status = async_dossier.get_dossier_status("AAPL")

    assert status["ready"] is True
    assert status["deep_dive_validated"] is False
    assert status["verified"] is False
    assert status["download_enabled"] is False
    assert "Forbidden marker found" in status["verification_issues"]


def test_get_dossier_status_blocks_download_when_validation_is_missing(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write_ready_dossier(tmp_path)

    monkeypatch.chdir(backend_dir)
    async_dossier._dossier_registry.clear()

    status = async_dossier.get_dossier_status("AAPL")

    assert status["ready"] is True
    assert status["deep_dive_validated"] is None
    assert status["verified"] is False
    assert status["download_enabled"] is False
    assert status["verification_issues"] == ["Deep-dive validation has not run yet."]


def test_get_dossier_status_does_not_trust_stale_complete_cache(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    _write_ready_dossier(
        tmp_path,
        validation={"passed": False, "issues": ["Validation failed on disk"]},
    )

    monkeypatch.chdir(backend_dir)
    async_dossier._dossier_registry.clear()
    async_dossier._dossier_registry["AAPL"] = {
        "ready": True,
        "verified": True,
        "download_enabled": True,
        "files": [],
        "stage": "complete",
    }

    status = async_dossier.get_dossier_status("AAPL")

    assert status["verified"] is False
    assert status["download_enabled"] is False
    assert "Validation failed on disk" in status["verification_issues"]
