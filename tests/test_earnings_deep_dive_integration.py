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
        report_dir = Path(request.output_dir) / "07_final_report"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "earnings_deep_dive.md"
        meta_path = report_dir / "earnings_deep_dive_meta.json"
        sections_md = "\n\n".join(
            f"## {name}\n\n| Col A | Col B |\n|---|---|\n| Data | Data |\n\n> One-line summary: ok"
            for name in ["EPS & Revenue", "Highlights & Lowlights", "Operating Metrics",
                         "Cash Flow", "Capital Efficiency", "Segments",
                         "Forward P/E", "Backlog Quality", "Guidance", "Verdict"]
        )
        full_md = f"# Earnings Deep-Dive\n\n{sections_md}\n"
        md_path.write_text(full_md, encoding="utf-8")
        meta_path.write_text("{}", encoding="utf-8")
        return DeepDiveResponse(
            ticker=request.ticker,
            company=request.company,
            quarter=request.quarter,
            language=request.language,
            markdown_path=str(md_path),
            meta_path=str(meta_path),
            report_markdown=full_md,
            sections={name: f"## {name}\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> One-line summary: ok"
                     for name in ["EPS & Revenue", "Highlights & Lowlights", "Operating Metrics",
                                  "Cash Flow", "Capital Efficiency", "Segments",
                                  "Forward P/E", "Backlog Quality", "Guidance", "Verdict"]},
            statuses=[],
            warnings=[],
        )

    def fake_render(report, pdf_path):
        render_calls.append((report.language, report.ticker, pdf_path))
        Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
        Path(pdf_path).write_bytes(b"pdf")
        return str(pdf_path)

    from backend.earnings_deep_dive import generator as gen_mod
    from backend.earnings_deep_dive import pdf_renderer as pdf_mod
    monkeypatch.setattr(pipeline, "find_transcripts", fake_find_transcripts)
    monkeypatch.setattr(gen_mod, "generate_deep_dive", fake_generate_deep_dive)
    monkeypatch.setattr(pdf_mod, "render_earnings_deep_dive_pdf", fake_render)

    import tempfile as _tempfile
    _analyses = Path(__file__).parent.parent / "analyses"
    out_dir = _tempfile.mkdtemp(dir=_analyses)

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
        output_dir=out_dir,
        result=result,
        yf_data={"financials": {"eps_actual": 1.25}},
        language="jp",
    )

    assert added is True
    assert generated_requests[0].transcript_text == transcript
    assert generated_requests[0].metrics.revenue_actual == 26_000_000_000
    assert generated_requests[0].metrics.eps_actual == 1.25
    # Pipeline now always generates bilingual (EN + JP)
    assert [request.language for request in generated_requests] == ["en", "jp"]
    assert generated_requests[1].transcript_text == transcript
    # EN path: output_dir/07_final_report/..., JP path: output_dir/jp/07_final_report/...
    en_pdf_path = str(Path(out_dir) / "07_final_report" / "earnings_deep_dive.pdf")
    jp_pdf_path = str(Path(out_dir) / "jp" / "07_final_report" / "earnings_deep_dive.pdf")
    assert render_calls == [("en", "NVDA", en_pdf_path), ("jp", "NVDA", jp_pdf_path)]
    assert (Path(out_dir) / "07_final_report" / "earnings_deep_dive.md").exists()
    assert (Path(out_dir) / "07_final_report" / "earnings_deep_dive.pdf").exists()
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

    from backend.earnings_deep_dive import generator as gen_mod2
    from backend.earnings_deep_dive import pdf_renderer as pdf_mod2
    monkeypatch.setattr(
        pipeline,
        "find_transcripts",
        lambda ticker, output_dir="": {"found": True, "sources": [{"url": "https://example.com"}]},
    )
    monkeypatch.setattr(gen_mod2, "generate_deep_dive", fake_generate_deep_dive)
    monkeypatch.setattr(pdf_mod2, "render_earnings_deep_dive_pdf", fake_render)

    added = pipeline._add_earnings_deep_dive_if_transcript(
        ticker="MSFT",
        company_name="Microsoft",
        output_dir=str(tmp_path),
        result=SimpleNamespace(financials=SimpleNamespace(), valuation=SimpleNamespace()),
        yf_data={},
    )

    # Pipeline now correctly skips when no usable transcript text
    assert added is False


def test_deep_dive_metrics_coerces_numeric_guidance_to_string():
    from backend import pipeline

    metrics = pipeline._deep_dive_metrics(
        SimpleNamespace(financials=SimpleNamespace(), valuation=SimpleNamespace()),
        {"financials": {"guidance": 0.1787}},
    )

    # Guidance from yfinance was EPS growth, not revenue guidance — deliberately None
    # Press release fills real guidance text separately
    assert metrics.guidance is None


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
            markdown_path=str(request.output_dir) + "/07_final_report/earnings_deep_dive.md",
            meta_path=str(request.output_dir) + "/07_final_report/earnings_deep_dive_meta.json",
            report_markdown="# Earnings Deep-Dive\n",
            sections={},
            statuses=[],
            warnings=[],
        )

    from backend.earnings_deep_dive import generator as gen_mod3
    monkeypatch.setattr(gen_mod3, "generate_deep_dive", fake_generate_deep_dive)
    # Prevent real yfinance data fetch from overriding test metrics
    monkeypatch.setattr(main, "get_yahoo_data", lambda ticker: None)

    import tempfile as _tempfile4
    _analyses4 = Path(__file__).parent.parent / "analyses"
    out_dir4 = _tempfile4.mkdtemp(dir=_analyses4)
    request = main.DeepDiveRequest(
        ticker="nvda",
        company="NVIDIA",
        quarter="latest quarter",
        language="en",
        output_dir=out_dir4,
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
