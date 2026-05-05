"""Tests for FastAPI endpoint edge cases."""
import asyncio
import json
from pathlib import Path

import fastapi.dependencies.utils

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
        lambda ticker: {"ready": True, "files": [], "stage": "complete"},
    )

    response = asyncio.run(main.dossier_download("aapl"))

    assert response.status_code == 200
    assert response.media_type == "application/zip"


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
