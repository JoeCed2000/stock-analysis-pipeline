import logging
import time

from backend import orchestrator


def test_run_analysis_parallel_runs_multiple_tickers_concurrently(monkeypatch, tmp_path):
    starts = []

    class DummyScore:
        financial_health = 8
        growth = 7
        valuation = 6
        management = 4
        moat = 3
        sentiment = 2
        total = 30

    class DummyResult:
        decision = "BUY"
        scoring = DummyScore()

    def fake_analyze_ticker_fast(ticker, output_base, language="en", force_refresh=False):
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


def test_run_analysis_parallel_waits_for_slow_running_worker_instead_of_false_timeout(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="backend.orchestrator")

    class DummyScore:
        financial_health = 8
        growth = 7
        valuation = 6
        management = 4
        moat = 3
        sentiment = 2
        total = 30

    class DummyResult:
        decision = "BUY"
        scoring = DummyScore()

    def fake_analyze_ticker_fast(ticker, output_base, language="en", force_refresh=False):
        time.sleep(0.12)
        return DummyResult()

    monkeypatch.setattr(orchestrator, "PER_TICKER_TIMEOUT", 0.03)
    monkeypatch.setattr(orchestrator, "analyze_ticker_fast", fake_analyze_ticker_fast)

    result = orchestrator.run_analysis_parallel(["NVDA"], output_base=str(tmp_path), max_workers=1)

    assert set(result["results"]) == {"NVDA"}
    assert result["errors"] == {}
    assert "still running after 0.03s" in caplog.text


def test_run_analysis_sequential_waits_for_slow_running_worker_instead_of_false_timeout(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="backend.orchestrator")

    class DummyScore:
        financial_health = 8
        growth = 7
        valuation = 6
        management = 4
        moat = 3
        sentiment = 2
        total = 30

    class DummyResult:
        decision = "BUY"
        scoring = DummyScore()

    def fake_analyze_ticker_fast(ticker, output_base):
        time.sleep(0.12)
        return DummyResult()

    monkeypatch.setattr(orchestrator, "PER_TICKER_TIMEOUT", 0.03)
    monkeypatch.setattr(orchestrator, "analyze_ticker_fast", fake_analyze_ticker_fast)

    result = orchestrator.run_analysis_sequential(["AAPL"], output_base=str(tmp_path))

    assert set(result["results"]) == {"AAPL"}
    assert result["errors"] == {}
    assert "still running after 0.03s" in caplog.text


def test_orchestrator_logs_new_scoring_fields(caplog, monkeypatch):
    """Verify orchestrator logs all 6 canonical scoring categories with their weights."""
    caplog.set_level(logging.INFO, logger="backend.orchestrator")

    class DummyScore:
        financial_health = 8
        growth = 7
        valuation = 6
        management = 4
        moat = 3
        sentiment = 2

        @property
        def total(self):
            return self.financial_health + self.growth + self.valuation \
                + self.management + self.moat + self.sentiment  # = 30

    class DummyResult:
        decision = "HOLD"
        scoring = DummyScore()

    def fake_analyze_ticker_fast(ticker, output_base):
        return DummyResult()

    monkeypatch.setattr(orchestrator, "analyze_ticker_fast", fake_analyze_ticker_fast)

    orchestrator.run_analysis_sequential(["MSFT"], output_base="/tmp")

    log_output = caplog.text

    # Verify the 6 categories are logged with their weights
    assert "FH=8/10" in log_output
    assert "G=7/10" in log_output
    assert "V=6/8" in log_output
    assert "M=4/5" in log_output
    assert "Mo=3/4" in log_output
    assert "S=2/3" in log_output
    assert "= 30/40" in log_output
    assert "HOLD" in log_output
