"""Quick-analysis latency contract: score first, build the PDF in background."""

from pathlib import Path
from types import SimpleNamespace

from backend import orchestrator, pipeline


def test_background_deep_dive_worker_is_daemon_and_runs_generation(monkeypatch):
    calls = []
    thread_config = {}

    def fake_add(**kwargs):
        calls.append(kwargs)

    class ImmediateThread:
        def __init__(self, *, target, kwargs, name, daemon):
            thread_config.update(
                target=target,
                kwargs=kwargs,
                name=name,
                daemon=daemon,
            )

        def start(self):
            thread_config["target"](**thread_config["kwargs"])

    monkeypatch.setattr(pipeline, "_add_earnings_deep_dive_if_transcript", fake_add)
    monkeypatch.setattr(pipeline.threading, "Thread", ImmediateThread)

    pipeline._start_earnings_deep_dive_background(
        ticker="AAPL",
        company_name="Apple Inc.",
        output_dir="/tmp/aapl",
        result=SimpleNamespace(),
        yf_data={},
        language="en",
        company_website="https://www.apple.com",
    )

    assert thread_config["daemon"] is True
    assert thread_config["name"] == "deep-dive-AAPL"
    assert calls[0]["ticker"] == "AAPL"


def test_orchestrator_forwards_background_mode_to_each_ticker(monkeypatch):
    seen = []
    scoring = SimpleNamespace(
        financial_health=8,
        growth=8,
        valuation=5,
        management=3,
        moat=3,
        sentiment=1,
        total=28,
    )

    def fake_analyze(ticker, output_base, language, force_refresh, *, background_deep_dive):
        seen.append((ticker, background_deep_dive))
        return SimpleNamespace(decision="BUY", scoring=scoring)

    monkeypatch.setattr(orchestrator, "analyze_ticker_fast", fake_analyze)

    batch = orchestrator.run_analysis_parallel(
        ["AAPL"],
        max_workers=1,
        background_deep_dive=True,
    )

    assert not batch["errors"]
    assert seen == [("AAPL", True)]


def test_async_api_uses_background_pdf_when_deep_dive_not_requested():
    source = Path("backend/main.py").read_text(encoding="utf-8")

    assert "background_deep_dive=not do_deep_dive" in source
