from types import SimpleNamespace
import asyncio
from pathlib import Path

import fastapi.dependencies.utils

fastapi.dependencies.utils.ensure_multipart_is_installed = lambda: None

from backend import main


def test_pipeline_adds_earnings_deep_dive_when_transcript_text_exists(tmp_path, monkeypatch, caplog):
    from backend import pipeline
    from backend.earnings_deep_dive.schemas import DeepDiveResponse

    transcript = "Revenue improved. EPS beat expectations. Guidance was constructive."
    generated_requests = []
    render_calls = []

    def fake_find_transcripts(ticker, output_dir=""):
        return {
            "found": True,
            "sources": [{"source": "Alpha Vantage API", "text": transcript}],
        }

    def fake_generate_deep_dive(request):
        generated_requests.append(request)
        report_dir = tmp_path / "07_final_report"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "earnings_deep_dive.md"
        meta_path = report_dir / "earnings_deep_dive_meta.json"
        md_path.write_text("# Earnings Deep-Dive\n", encoding="utf-8")
        meta_path.write_text("{}", encoding="utf-8")
        return DeepDiveResponse(
            ticker=request.ticker,
            company=request.company,
            quarter=request.quarter,
            language=request.language,
            markdown_path=str(md_path),
            meta_path=str(meta_path),
            report_markdown="# Earnings Deep-Dive\n",
            sections={},
            statuses=[],
            warnings=[],
        )

    def fake_render(report, pdf_path):
        render_calls.append((report.language, report.ticker, pdf_path))
        Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
        Path(pdf_path).write_bytes(b"pdf")
        return str(pdf_path)

    monkeypatch.setattr(pipeline, "find_transcripts", fake_find_transcripts)
    monkeypatch.setattr(pipeline, "generate_deep_dive", fake_generate_deep_dive)
    monkeypatch.setattr(pipeline, "render_earnings_deep_dive_pdf", fake_render)

    result = SimpleNamespace(
        financials=SimpleNamespace(
            revenue_quarterly=26_000_000_000,
            revenue_yoy_growth=0.18,
            gross_margin=0.73,
            operating_margin=0.45,
            net_income=10_000_000_000,
            free_cash_flow=8_000_000_000,
            net_debt=1_000_000_000,
            guidance_official="Revenue growth expected",
        ),
        valuation=SimpleNamespace(pe_forward=24.0),
    )

    added = pipeline._add_earnings_deep_dive_if_transcript(
        ticker="NVDA",
        company_name="NVIDIA",
        output_dir=str(tmp_path),
        result=result,
        yf_data={"financials": {"eps_actual": 1.25}},
        language="jp",
    )

    assert added is True
    assert generated_requests[0].transcript_text == transcript
    assert generated_requests[0].metrics.revenue_actual == 26_000_000_000
    assert generated_requests[0].metrics.eps_actual == 1.25
    assert [request.language for request in generated_requests] == ["jp"]
    assert render_calls == [("jp", "NVDA", str(tmp_path / "07_final_report" / "earnings_deep_dive.pdf"))]
    assert (tmp_path / "07_final_report" / "earnings_deep_dive.md").exists()
    assert (tmp_path / "07_final_report" / "earnings_deep_dive.pdf").exists()
    assert "Earnings deep-dive added to dossier" in caplog.text


def test_pipeline_generates_earnings_deep_dive_without_usable_transcript(tmp_path, monkeypatch):
    from backend import pipeline
    from backend.earnings_deep_dive.schemas import DeepDiveResponse

    generated_requests = []

    def fake_generate_deep_dive(request):
        generated_requests.append(request)
        report_dir = Path(request.output_dir) / "07_final_report"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "earnings_deep_dive.md"
        meta_path = report_dir / "earnings_deep_dive_meta.json"
        md_path.write_text("# Earnings Deep-Dive\n", encoding="utf-8")
        meta_path.write_text("{}", encoding="utf-8")
        return DeepDiveResponse(
            ticker=request.ticker,
            company=request.company,
            quarter=request.quarter,
            language=request.language,
            markdown_path=str(md_path),
            meta_path=str(meta_path),
            report_markdown="# Earnings Deep-Dive\n",
            sections={},
            statuses=[],
            warnings=[],
        )

    def fake_render(report, pdf_path):
        Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
        Path(pdf_path).write_bytes(b"pdf")
        return str(pdf_path)

    monkeypatch.setattr(
        pipeline,
        "find_transcripts",
        lambda ticker, output_dir="": {"found": True, "sources": [{"url": "https://example.com"}]},
    )
    monkeypatch.setattr(pipeline, "generate_deep_dive", fake_generate_deep_dive)
    monkeypatch.setattr(pipeline, "render_earnings_deep_dive_pdf", fake_render)

    added = pipeline._add_earnings_deep_dive_if_transcript(
        ticker="MSFT",
        company_name="Microsoft",
        output_dir=str(tmp_path),
        result=SimpleNamespace(financials=SimpleNamespace(), valuation=SimpleNamespace()),
        yf_data={},
    )

    assert added is True
    assert [request.language for request in generated_requests] == ["en"]
    assert all(request.transcript_text == "" for request in generated_requests)
    assert (tmp_path / "07_final_report" / "earnings_deep_dive.pdf").exists()


def test_deep_dive_metrics_coerces_numeric_guidance_to_string():
    from backend import pipeline

    metrics = pipeline._deep_dive_metrics(
        SimpleNamespace(financials=SimpleNamespace(), valuation=SimpleNamespace()),
        {"financials": {"guidance": 0.1787}},
    )

    assert metrics.guidance == "0.1787"


def test_earnings_deep_dive_endpoint_returns_generator_response(tmp_path, monkeypatch):
    from backend.earnings_deep_dive.schemas import DeepDiveResponse

    seen_requests = []

    def fake_generate_deep_dive(request):
        seen_requests.append(request)
        return DeepDiveResponse(
            ticker=request.ticker,
            company=request.company or request.ticker,
            quarter=request.quarter,
            language=request.language,
            markdown_path=str(tmp_path / "07_final_report" / "earnings_deep_dive.md"),
            meta_path=str(tmp_path / "07_final_report" / "earnings_deep_dive_meta.json"),
            report_markdown="# Earnings Deep-Dive\n",
            sections={},
            statuses=[],
            warnings=[],
        )

    monkeypatch.setattr(main, "generate_deep_dive", fake_generate_deep_dive)

    request = main.DeepDiveRequest(
        ticker="nvda",
        company="NVIDIA",
        quarter="latest quarter",
        language="en",
        output_dir=str(tmp_path),
        transcript_text="Revenue EPS guidance backlog cash flow segments.",
        metrics={"eps_actual": 1.25, "revenue_actual": 26_000_000_000},
    )
    response = asyncio.run(main.earnings_deep_dive(request))

    assert response.ticker == "NVDA"
    assert response.markdown_path.endswith("earnings_deep_dive.md")
    assert seen_requests[0].ticker == "NVDA"
    assert seen_requests[0].metrics.eps_actual == 1.25
    assert any(
        getattr(route, "path", "") == "/api/earnings/deep-dive"
        and "POST" in getattr(route, "methods", set())
        for route in main.app.routes
    )


def test_dossier_status_lists_earnings_deep_dive_as_bonus_file(tmp_path, monkeypatch):
    from backend import async_dossier

    analyses_dir = tmp_path / "analyses"
    dossier = analyses_dir / "2026-05-05_NVDA_NVIDIA"
    (dossier / "03_financial_data_sources").mkdir(parents=True)
    (dossier / "07_final_report").mkdir(parents=True)
    (dossier / "03_financial_data_sources" / "financials_NVDA.xlsx").write_bytes(b"xlsx")
    (dossier / "07_final_report" / "report.md").write_text("# Report", encoding="utf-8")
    (dossier / "07_final_report" / "earnings_deep_dive.md").write_text(
        "# Earnings Deep-Dive",
        encoding="utf-8",
    )

    monkeypatch.setattr(async_dossier, "_analyses_dir", lambda: analyses_dir)
    async_dossier._dossier_registry.clear()

    status = async_dossier.get_dossier_status("NVDA")

    assert status["ready"] is True
    assert "07_final_report/earnings_deep_dive.md" in status["files"]
    assert status["bonus_files"] == ["07_final_report/earnings_deep_dive.md"]
