"""process_pdf_failure must schedule its async remediation action from any
calling context.

Regression: main.py spawns the proactive PDF-failure intake in a plain daemon
thread (no event loop). asyncio.ensure_future at feedback_pipeline.py:209 then
raised RuntimeError('There is no current event loop in thread ...') and the
remediation coroutine was never awaited.
"""
import asyncio
import threading

import backend.feedback_pipeline as fp


def _stub_pdf_failure_env(monkeypatch, record):
    """Direct path, idempotency claimed, remediation actions stubbed."""
    monkeypatch.setattr(fp, "USE_KANBAN", False)
    monkeypatch.setattr(fp, "_claim_pdf_failure_intake", lambda key: True)

    async def _stub_reanalyze(ticker):
        record["ran"] = ticker
        record["event"].set()
        return {"ok": True}

    async def _stub_restart():
        record["ran"] = "RESTART"
        record["event"].set()
        return {"ok": True}

    monkeypatch.setattr(fp, "_action_reanalyze_ticker", _stub_reanalyze)
    monkeypatch.setattr(fp, "_action_restart_backend", _stub_restart)


def test_process_pdf_failure_outside_event_loop_schedules_action(monkeypatch):
    """Called from a plain thread (the proactive intake path in main.py):
    must not raise, and the remediation action must actually run."""
    record = {"event": threading.Event()}
    _stub_pdf_failure_env(monkeypatch, record)

    result = {}

    def _run_intake():
        try:
            result["key"] = fp.process_pdf_failure(
                ticker="ACME",
                source="report_pdf",
                status="pdf_blocked",
                message="PDF build blocked",
            )
        except Exception as exc:  # the original bug: RuntimeError escapes here
            result["exc"] = exc

    thread = threading.Thread(target=_run_intake, daemon=True)
    thread.start()
    thread.join(10)

    assert "exc" not in result, f"process_pdf_failure raised: {result.get('exc')!r}"
    assert result.get("key"), "intake key must be returned after scheduling"
    assert record["event"].wait(5), "remediation coroutine never ran"
    assert record["ran"] == "ACME"


def test_process_pdf_failure_inside_event_loop_unchanged(monkeypatch):
    """Normal async-context behavior: the action is scheduled on the already
    running loop and completes there."""
    record = {"event": threading.Event()}
    _stub_pdf_failure_env(monkeypatch, record)

    async def _main():
        key = fp.process_pdf_failure(
            ticker="ACME",
            source="report_pdf",
            status="pdf_blocked",
            message="PDF build blocked",
        )
        assert key
        # The stub task must complete on THIS loop without thread handoff.
        for _ in range(50):
            if record["event"].is_set():
                break
            await asyncio.sleep(0.05)
        assert record["event"].is_set(), "action did not run on the running loop"

    asyncio.run(_main())
    assert record["ran"] == "ACME"


def test_process_pdf_failure_general_ticker_restart_path(monkeypatch):
    """GENERAL ticker takes the restart action — same scheduling contract."""
    record = {"event": threading.Event()}
    _stub_pdf_failure_env(monkeypatch, record)

    result = {}

    def _run_intake():
        try:
            result["key"] = fp.process_pdf_failure(
                ticker="GENERAL",
                source="report_pdf",
                status="pdf_blocked",
                message="PDF build blocked",
            )
        except Exception as exc:
            result["exc"] = exc

    thread = threading.Thread(target=_run_intake, daemon=True)
    thread.start()
    thread.join(10)

    assert "exc" not in result, f"process_pdf_failure raised: {result.get('exc')!r}"
    assert record["event"].wait(5), "restart coroutine never ran"
    assert record["ran"] == "RESTART"
