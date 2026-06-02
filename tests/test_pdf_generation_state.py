from datetime import datetime, timedelta

from backend.async_dossier import (
    DossierPhase,
    _dossier_registry,
    _registry_lock,
    get_dossier_status,
    PARIS,
)


def _minimal_analysis_dir(root, ticker="NVDA"):
    analysis_dir = root / f"2026-06-02_120000_{ticker}_Test"
    final = analysis_dir / "07_final_report"
    data = analysis_dir / "03_financial_data_sources"
    final.mkdir(parents=True)
    data.mkdir(parents=True)
    (final / "report.md").write_text("report", encoding="utf-8")
    (data / f"financials_{ticker}.xlsx").write_bytes(b"xlsx")
    return analysis_dir


def test_stale_pdf_generating_phase_becomes_terminal_failure(tmp_path, monkeypatch):
    analyses = tmp_path / "analyses"
    _minimal_analysis_dir(analyses, "NVDA")
    monkeypatch.setattr("backend.async_dossier._analyses_dir", lambda: analyses)

    stale = (datetime.now(PARIS) - timedelta(minutes=25)).isoformat()
    with _registry_lock:
        _dossier_registry.clear()
        _dossier_registry["NVDA"] = {
            "phase": DossierPhase.PDF_GENERATING,
            "phase_set_at": stale,
        }

    status = get_dossier_status("NVDA")

    assert status["phase"] == DossierPhase.FAILED
    assert status["stage"] == "failed"
    assert "stale" in status["error"]


def test_fresh_pdf_generating_phase_remains_pollable(tmp_path, monkeypatch):
    analyses = tmp_path / "analyses"
    _minimal_analysis_dir(analyses, "NVDA")
    monkeypatch.setattr("backend.async_dossier._analyses_dir", lambda: analyses)

    fresh = datetime.now(PARIS).isoformat()
    with _registry_lock:
        _dossier_registry.clear()
        _dossier_registry["NVDA"] = {
            "phase": DossierPhase.PDF_GENERATING,
            "phase_set_at": fresh,
        }

    status = get_dossier_status("NVDA")

    assert status["phase"] == DossierPhase.PDF_GENERATING
    assert status["stage"] == "complete"
