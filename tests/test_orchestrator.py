import time

from backend import orchestrator


def test_run_analysis_parallel_runs_multiple_tickers_concurrently(monkeypatch, tmp_path):
    starts = []

    class DummyScore:
        total = 30

    class DummyResult:
        decision = "BUY"
        scoring = DummyScore()

    def fake_analyze_ticker_fast(ticker, output_base):
        starts.append((ticker, time.perf_counter()))
        time.sleep(0.2)
        return DummyResult()

    monkeypatch.setattr(orchestrator, "analyze_ticker_fast", fake_analyze_ticker_fast)

    result = orchestrator.run_analysis_parallel(
        ["AAPL", "MSFT", "NVDA"],
        output_base=str(tmp_path),
        max_workers=3,
    )

    assert set(result["results"]) == {"AAPL", "MSFT", "NVDA"}
    assert result["errors"] == {}
    assert max(started_at for _, started_at in starts) - min(started_at for _, started_at in starts) < 0.15
