"""Tests for dossier readiness lookup."""

from backend import async_dossier


def test_get_dossier_status_checks_project_analyses_when_cwd_is_backend(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend"
    dossier_dir = tmp_path / "analyses" / "2026-05-04_AAPL_Apple_Inc"
    (dossier_dir / "03_financial_data_sources").mkdir(parents=True)
    (dossier_dir / "07_final_report").mkdir(parents=True)
    (dossier_dir / "03_financial_data_sources" / "financials_AAPL.xlsx").write_bytes(b"xlsx")
    (dossier_dir / "07_final_report" / "report.md").write_text("# Report")
    backend_dir.mkdir()

    monkeypatch.chdir(backend_dir)
    async_dossier._dossier_registry.clear()

    status = async_dossier.get_dossier_status("AAPL")

    assert status["ready"] is True
    assert status["stage"] == "complete"
