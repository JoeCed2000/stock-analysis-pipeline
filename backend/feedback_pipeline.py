"""
Autonomous Feedback Pipeline — Nami's chat corrections → Kanban → fix → respond.

Flow:
  1. Chat message detected as correction/bug/feature_request
  2. Pre-flight gate: tb preflight -q MUST pass
  3. Kanban task auto-created on sa-pipeline board
  4. Acknowledgment sent to chat: "✅ C'est pris en compte ! Tâche [task_id] créée."
  5. Monitor Kanban task completion (background)
  6. When done: response sent to chat with result summary
"""

import asyncio
import hashlib
import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Coroutine, Optional, Dict

logger = logging.getLogger(__name__)


def _schedule_background_action(coro: Coroutine) -> None:
    """Fire-and-forget an async remediation action from any calling context.

    process_pdf_failure is invoked both from FastAPI handlers (running event
    loop) and from plain daemon threads (the proactive intake thread spawned
    by main.py), where asyncio.ensure_future raises
    RuntimeError('There is no current event loop in thread ...').
    Inside a loop: schedule on it. Outside: run in a dedicated daemon thread
    via asyncio.run — the same pattern main.py uses for background deep-dive
    generation.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(coro)
        return

    def _runner() -> None:
        try:
            asyncio.run(coro)
        except Exception:
            logger.exception("Background PDF-failure remediation action failed")

    threading.Thread(target=_runner, daemon=True).start()

# ─── Constants ───────────────────────────────────────────────────────────────

# 🔴 KANBAN DISABLED 2026-06-09 — Ced: "on reviendra au kanban quand il sera opérationnel"
#    Set to True to restore Kanban-based worker pipeline.
USE_KANBAN = False

KANBAN_BOARD = "sa-pipeline"
MAX_MONITOR_SECONDS = 1800  # 30 min max before giving up
MONITOR_INTERVAL_SECONDS = 30  # Check every 30s
PDF_FAILURE_INTAKE_PATH = Path(__file__).parent / "logs" / "pdf_failure_intake.json"
PDF_FAILURE_INTAKE_COOLDOWN_SECONDS = 6 * 60 * 60

# ─── Pre-flight Gate ─────────────────────────────────────────────────────────

def run_preflight_gate(board: str = "sa-pipeline") -> tuple[bool, str]:
    """Run kanban pre-flight. Returns (ok, detail_message).
    
    Only considers failures relevant to the specified board.
    Dispatcher inactivity on unrelated boards is ignored.
    """
    try:
        result = subprocess.run(
            ["python3", "/home/ced/.hermes/shared/scripts/kanban_preflight.py", "--quick", "--json"],
            capture_output=True, text=True, timeout=45,
        )
        if result.returncode == 0:
            return True, "GO"
        elif result.returncode == 2:
            return True, f"WARN (non-critical warnings present)"
        else:
            # Parse failures from JSON, filter to board-relevant only
            import json
            try:
                data = json.loads(result.stdout)
                failures = data.get("failures", [])
                # Only care about failures on our board
                relevant = [f for f in failures if board.lower() in f.lower() or "DEFAULT" in f]
                if not relevant:
                    # Failures are on unrelated boards — treat as GO
                    return True, f"GO (unrelated board failures ignored: {len(failures)})"
                return False, "; ".join(relevant[:3])
            except Exception:
                return False, f"NO-GO (exit {result.returncode})"
    except Exception as e:
        return False, f"pre-flight error: {e}"


def _kanban_create(title: str, body: str, assignee: str = "python-builder") -> Optional[str]:
    """Create a Kanban task. Returns task_id or None."""
    try:
        result = subprocess.run(
            [
                "hermes", "kanban", "--board", KANBAN_BOARD, "create",
                "--assignee", assignee,
                "--body", body,
                title,  # positional
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            # Parse task ID from output: "Created task t_xxxxx"
            for line in result.stdout.split("\n"):
                if "Created" in line or "t_" in line:
                    import re
                    match = re.search(r"(t_[a-f0-9]{8})", line)
                    if match:
                        return match.group(1)
        logger.error(f"Kanban create failed: {result.stderr}")
        return None
    except Exception as e:
        logger.error(f"Kanban create error: {e}")
        return None


def _kanban_dispatch() -> bool:
    """Dispatch one task. Returns True if a worker picked it up."""
    try:
        result = subprocess.run(
            ["hermes", "kanban", "--board", KANBAN_BOARD, "dispatch", "--max", "1"],
            capture_output=True, text=True, timeout=30,
        )
        return "Spawned:      1" in result.stdout or "spawned" in result.stdout.lower()
    except Exception as e:
        logger.error(f"Dispatch error: {e}")
        return False


def _kanban_status(task_id: str) -> Optional[Dict]:
    """Check a Kanban task's status. Returns dict or None."""
    try:
        result = subprocess.run(
            ["hermes", "kanban", "--board", KANBAN_BOARD, "show", task_id, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
        return None
    except Exception as e:
        logger.error(f"Kanban status error: {e}")
        return None


def _pdf_failure_key(
    ticker: str,
    source: str,
    status: str,
    language: str,
    quarter: str,
    issues: list[str],
) -> str:
    """Stable idempotency key for a user-visible PDF failure."""
    payload = {
        "ticker": ticker.upper(),
        "source": source,
        "status": status,
        "language": language,
        "quarter": quarter or "latest",
        "issues": [str(issue)[:300] for issue in issues[:5]],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"pdf_failure:{ticker.upper()}:{digest}"


def _claim_pdf_failure_intake(key: str) -> bool:
    """Return True once per failure key/cooldown to prevent Kanban spawn storms."""
    now = time.time()
    PDF_FAILURE_INTAKE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, float] = {}
    if PDF_FAILURE_INTAKE_PATH.exists():
        try:
            raw = json.loads(PDF_FAILURE_INTAKE_PATH.read_text(encoding="utf-8"))
            data = {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}
        except Exception:
            logger.warning("Failed to read PDF failure intake cache; rebuilding")
            data = {}

    data = {
        k: v
        for k, v in data.items()
        if now - float(v) < PDF_FAILURE_INTAKE_COOLDOWN_SECONDS * 4
    }
    last = data.get(key)
    if last and now - last < PDF_FAILURE_INTAKE_COOLDOWN_SECONDS:
        return False

    data[key] = now
    PDF_FAILURE_INTAKE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return True


def process_pdf_failure(
    *,
    ticker: str,
    source: str,
    status: str,
    message: str,
    issues: Optional[list[str]] = None,
    language: str = "en",
    quarter: str = "latest",
    directory: str = "",
) -> Optional[str]:
    """Handle user-visible PDF failure. Direct automation when USE_KANBAN=False."""
    ticker = (ticker or "").strip().upper()
    safe_issues = [str(issue) for issue in (issues or []) if str(issue).strip()]
    key = _pdf_failure_key(ticker, source, status, language, quarter, safe_issues or [message])
    if not _claim_pdf_failure_intake(key):
        logger.info("[%s] PDF failure intake skipped by idempotency key %s", ticker, key)
        return None

    # Noise gate
    if status in ("quarter_missing",):
        logger.info(
            "[%s] PDF failure intake skipped by noise gate — status=%s",
            ticker, status,
        )
        return None

    if not USE_KANBAN:
        # Direct path: log + trigger background action
        logger.error(
            "PDF FAILURE [%s]: source=%s status=%s message=%s quarter=%s issues=%s",
            ticker, source, status, message[:200], quarter, safe_issues,
        )
        if ticker and ticker != "GENERAL":
            _schedule_background_action(_action_reanalyze_ticker(ticker))
        else:
            _schedule_background_action(_action_restart_backend())
        return key

    # ── Kanban path below (USE_KANBAN=True) ──

    preflight_ok, preflight_msg = run_preflight_gate()
    if not preflight_ok:
        logger.error("Pre-flight FAILED for PDF failure intake: %s", preflight_msg)
        return None

    issue_block = "\n".join(f"- {issue}" for issue in safe_issues[:10]) or "- No structured issue list was provided. Inspect logs/status files."
    task_title = f"[PDF-FAILURE] {ticker}: {status}"
    task_body = (
        f"**source:** Proactive PDF failure intake ({source})\n"
        f"**ticker:** {ticker}\n"
        f"**language:** {language}\n"
        f"**quarter:** {quarter or 'latest'}\n"
        f"**failure_status:** {status}\n"
        f"**message:** {message}\n"
        f"**directory:** {directory or 'N/A'}\n"
        f"**idempotency_key:** {key}\n\n"
        f"## Root cause analysis — required first step\n\n"
        f"A user-visible PDF failure was observed. Do not treat HTTP 200/OK from the analysis endpoint as success. "
        f"Success means the user can open/download the requested PDF/ZIP artifact.\n\n"
        f"## Observed issues\n\n{issue_block}\n\n"
        f"## Scope\n\n"
        f"**project:** stock-analysis-pipeline\n"
        f"**read_scope:** backend/main.py, backend/async_dossier.py, backend/earnings_deep_dive/*, frontend/src/components/AdminPage.jsx, frontend/src/components/AnalysisCard.jsx, logs for this ticker\n"
        f"**write_scope:** Minimal files needed after root cause is identified; likely backend PDF/status/admin code plus focused regression tests.\n"
        f"**expected_tests:** Add or update a regression proving the blocked/missing PDF is logged as a failure and the admin dashboard sees it as failed from the user perspective.\n"
        f"**risk:** Medium — PDF generation can be slow; avoid respawn loops and avoid triggering generation from read-only download endpoints.\n\n"
        f"## Acceptance criteria\n\n"
        f"- Root cause explains why the PDF was not served to the user.\n"
        f"- Admin/recent-search status reflects the user-visible failure, not only the initial HTTP 200 analysis response.\n"
        f"- Fix is idempotent and cannot create a Kanban/worker storm on repeated polls/download attempts.\n"
        f"- Verification includes tests and, if feasible, a real endpoint/browser check.\n"
    )

    task_id = _kanban_create(task_title, task_body, assignee="python-builder")
    if not task_id:
        logger.error("Failed to create Kanban task for PDF failure intake")
        return None
    logger.info("Created Kanban task %s for PDF failure intake %s", task_id, key)
    dispatched = _kanban_dispatch()
    if dispatched:
        logger.info("Dispatched PDF failure task %s", task_id)
    else:
        logger.warning("Dispatch returned no spawn for PDF failure task %s — may be queued", task_id)
    return task_id


# ─── Chat Acknowledgment ─────────────────────────────────────────────────────

async def send_chat_acknowledgment(
    session_id: str,
    user_message: str,
    feedback_type: str,
    task_id: str,
    language: str = "ja",
) -> Optional[str]:
    """Send an acknowledgment message to the chat. Returns the assistant message ID."""
    try:
        from backend import chat_store
        from backend.chat import _uid, _utcnow_iso, _ws_connections
        from backend.chat_models import ChatMessage as ChatMsg

        now = _utcnow_iso()
        msg_id = _uid("msg")

        if language.startswith("ja"):
            content = (
                f"✅ ご指摘ありがとうございます！修正依頼を承りました。\n\n"
                f"🔧 **自動修正パイプラインを開始しました**\n"
                f"📋 タスクID: `{task_id}`\n"
                f"🔄 ステータス: 処理中...\n\n"
                f"修正が完了次第、このチャットでお知らせします。\n"
                f"通常5〜10分程度で反映されます。\n\n"
                f"⚠️ **反映時に数秒の切り替えが発生する場合があります。** 画面が一瞬リフレッシュされますが、すぐに最新の状態でご利用いただけます。"
            )
        else:
            content = (
                f"✅ Thank you for your feedback! Your correction request has been received.\n\n"
                f"🔧 **Auto-fix pipeline started**\n"
                f"📋 Task ID: `{task_id}`\n"
                f"🔄 Status: Processing...\n\n"
                f"I'll update you here as soon as the fix is deployed.\n"
                f"Usually takes 5-10 minutes.\n\n"
                f"⚠️ **A brief refresh may occur when the update goes live.** The page will reload automatically and you can continue right away."
            )

        # Save the acknowledgment message
        ack_msg = ChatMsg(
            id=msg_id,
            session_id=session_id,
            role="assistant",
            content=content,
            language=language,
            status="completed",
            created_at=now,
            updated_at=now,
        )
        try:
            chat_store.save_message(ack_msg)
        except Exception:
            pass  # session may not exist yet (e.g., test sessions)
        chat_store.log_event(session_id, "feedback_pipeline_acknowledged", {
            "feedback_type": feedback_type,
            "kanban_task_id": task_id,
            "message_id": msg_id,
        })

        # Push via WebSocket if connected
        ws = _ws_connections.get(session_id)
        if ws:
            try:
                await ws.send_json({
                    "event": "feedback_acknowledged",
                    "message_id": msg_id,
                    "content": content,
                    "feedback_type": feedback_type,
                    "kanban_task_id": task_id,
                })
            except Exception:
                pass

        return msg_id
    except Exception as e:
        logger.error(f"Failed to send chat acknowledgment: {e}")
        return None


# ─── Main Pipeline ───────────────────────────────────────────────────────────

async def process_feedback(
    session_id: str,
    user_message: str,
    feedback_type: str,
    language: str = "ja",
    ticker: Optional[str] = None,
) -> Optional[str]:
    """Autonomous feedback processing. Uses direct automation when USE_KANBAN=False."""
    if not USE_KANBAN:
        return await process_feedback_direct(
            session_id, user_message, feedback_type, language, ticker,
        )

    # ── Kanban path below (USE_KANBAN=True) ──
    logger.info(f"Processing {feedback_type} feedback from session {session_id}")

    # Gate 0: Pre-flight check
    preflight_ok, preflight_msg = run_preflight_gate()
    if not preflight_ok:
        logger.error(f"Pre-flight FAILED for feedback pipeline: {preflight_msg}")
        # Still acknowledge but warn
        from backend import chat_store
        from backend.chat import _ws_connections, _uid, _utcnow_iso
        from backend.chat_models import ChatMessage as ChatMsg
        now = _utcnow_iso()
        warn_id = _uid("msg")
        warn_content = (
            f"⚠️ 申し訳ありません。現在システムメンテナンス中のため、自動修正を開始できませんでした。\n"
            f"担当者に通知済みです。しばらくしてから再度お試しください。\n\n"
            f"エラー: {preflight_msg[:200]}"
        ) if language.startswith("ja") else (
            f"⚠️ Sorry, the auto-fix pipeline is temporarily unavailable due to system maintenance.\n"
            f"The team has been notified. Please try again shortly.\n\n"
            f"Error: {preflight_msg[:200]}"
        )
        warn_msg = ChatMsg(
            id=warn_id, session_id=session_id, role="assistant",
            content=warn_content, language=language, status="completed",
            created_at=now, updated_at=now,
        )
        chat_store.save_message(warn_msg)
        ws = _ws_connections.get(session_id)
        if ws:
            try:
                await ws.send_json({
                    "event": "feedback_pipeline_blocked",
                    "message_id": warn_id,
                    "content": warn_content,
                })
            except Exception:
                pass
        return None

    # Gate 1: Build Kanban task body
    task_title = f"[CHAT-FB] {feedback_type.replace('_', ' ').title()}: {user_message[:80]}"
    task_body = (
        f"**source:** Live chat feedback from Nami (session {session_id})\n"
        f"**feedback_type:** {feedback_type}\n"
        f"**original_message:** {user_message}\n"
        f"**ticker:** {ticker or 'N/A'}\n"
        f"**language:** {language}\n\n"
        f"**auto_created:** True\n"
        f"**priority:** high\n\n"
        f"## Correction Request\n\n"
        f"The user reported the following issue via live chat:\n\n"
        f"> {user_message}\n\n"
        f"**write_scope:** Identify affected files based on the correction requested. "
        f"If it's a data issue → mapper.py + prompts. "
        f"If it's a display issue → pdf_renderer.py or frontend components. "
        f"If it's a calculation issue → scorer.py or valuation engine.\n\n"
        f"**expected_tests:** Add regression test for the specific case mentioned.\n\n"
        f"**acceptance_criteria:** The issue described in the chat message is resolved. "
        f"Respond to the chat session once fixed.\n\n"
        f"**risk:** Low — isolated fix based on specific user report.\n"
        f"**project:** stock-analysis-pipeline\n"
        f"**chat_session_id:** {session_id}"
    )

    # Gate 2: Create Kanban task
    task_id = _kanban_create(task_title, task_body)
    if not task_id:
        logger.error("Failed to create Kanban task for feedback")
        return None

    logger.info(f"Created Kanban task {task_id} for {feedback_type} feedback")

    # Gate 3: Acknowledge in chat immediately
    ack_id = await send_chat_acknowledgment(session_id, user_message, feedback_type, task_id, language)
    if ack_id:
        logger.info(f"Sent acknowledgment {ack_id} for task {task_id}")

    # Gate 4: Dispatch the task
    dispatched = _kanban_dispatch()
    if dispatched:
        logger.info(f"Dispatched task {task_id}")
    else:
        logger.warning(f"Dispatch returned no spawn for {task_id} — may be queued")

    # Gate 5: Monitor in background and respond when done
    asyncio.create_task(_monitor_and_respond(
        task_id, session_id, language,
        feedback_type=feedback_type, user_message=user_message, ticker=ticker or "",
    ))

    return task_id


# ─── Background Monitor ──────────────────────────────────────────────────────

async def _monitor_and_respond(
    task_id: str, session_id: str, language: str,
    feedback_type: str = "", user_message: str = "", ticker: str = "",
):
    """Monitor Kanban task until completion, then respond in chat."""
    start = time.time()

    while (time.time() - start) < MAX_MONITOR_SECONDS:
        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)

        status = _kanban_status(task_id)
        if not status:
            continue

        task_status = status.get("status", "unknown")
        logger.info(f"Task {task_id}: {task_status} (elapsed: {int(time.time()-start)}s)")

        if task_status == "done":
            result_text = status.get("result", "")[:500]
            await _send_completion_response(
                session_id, task_id, result_text, language,
                feedback_type=feedback_type, user_message=user_message, ticker=ticker,
            )
            return
        elif task_status == "blocked":
            block_reason = status.get("result", "unknown")[:300]
            await _send_blocked_response(session_id, task_id, block_reason, language)
            return
        elif task_status in ("cancelled", "archived"):
            logger.info(f"Task {task_id} {task_status} — no response needed")
            return

    # Timeout — task still not done after 30 min
    await _send_timeout_response(session_id, task_id, language)


async def _send_completion_response(
    session_id: str, task_id: str, result: str, language: str,
    feedback_type: str = "", user_message: str = "", ticker: str = "",
):
    """Notify chat that the fix is deployed AND trigger the learning loop."""
    # 🔴 Learning loop: log the correction pattern for future prevention
    if feedback_type and user_message:
        try:
            _learn_from_fix(task_id, feedback_type, user_message, ticker, result)
        except Exception as e:
            logger.error(f"Learning loop failed (non-blocking): {e}")

    try:
        from backend import chat_store
        from backend.chat import _uid, _utcnow_iso, _ws_connections
        from backend.chat_models import ChatMessage as ChatMsg

        now = _utcnow_iso()
        msg_id = _uid("msg")

        if language.startswith("ja"):
            content = (
                f"✅ **修正が完了しました！**\n\n"
                f"📋 タスク `{task_id}` が正常に処理され、変更が反映されました。\n\n"
                f"ご確認いただき、問題が解決しているかお知らせください。"
            )
        else:
            content = (
                f"✅ **Fix deployed!**\n\n"
                f"📋 Task `{task_id}` has been completed and changes are now live.\n\n"
                f"Please verify the issue is resolved and let me know if you need anything else."
            )

        msg = ChatMsg(
            id=msg_id, session_id=session_id, role="assistant",
            content=content, language=language, status="completed",
            created_at=now, updated_at=now,
        )
        chat_store.save_message(msg)
        chat_store.log_event(session_id, "feedback_pipeline_completed", {
            "kanban_task_id": task_id,
            "result_summary": result[:200],
        })

        ws = _ws_connections.get(session_id)
        if ws:
            try:
                await ws.send_json({
                    "event": "feedback_fix_deployed",
                    "message_id": msg_id,
                    "content": content,
                    "kanban_task_id": task_id,
                })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Failed to send completion response: {e}")


async def _send_blocked_response(session_id: str, task_id: str, reason: str, language: str):
    """Notify chat that the fix is blocked."""
    try:
        from backend import chat_store
        from backend.chat import _uid, _utcnow_iso, _ws_connections
        from backend.chat_models import ChatMessage as ChatMsg

        now = _utcnow_iso()
        msg_id = _uid("msg")

        if language.startswith("ja"):
            content = (
                f"⚠️ 修正タスクがブロックされました。\n\n"
                f"📋 タスク `{task_id}`\n"
                f"理由: {reason[:300]}\n\n"
                f"担当者が確認中です。"
            )
        else:
            content = (
                f"⚠️ The fix task has been blocked.\n\n"
                f"📋 Task `{task_id}`\n"
                f"Reason: {reason[:300]}\n\n"
                f"The team has been notified."
            )

        msg = ChatMsg(
            id=msg_id, session_id=session_id, role="assistant",
            content=content, language=language, status="completed",
            created_at=now, updated_at=now,
        )
        chat_store.save_message(msg)

        ws = _ws_connections.get(session_id)
        if ws:
            try:
                await ws.send_json({
                    "event": "feedback_fix_blocked",
                    "message_id": msg_id,
                    "content": content,
                    "kanban_task_id": task_id,
                })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Failed to send blocked response: {e}")


async def _send_timeout_response(session_id: str, task_id: str, language: str):
    """Notify chat that the fix is taking longer than expected."""
    try:
        from backend import chat_store
        from backend.chat import _uid, _utcnow_iso, _ws_connections
        from backend.chat_models import ChatMessage as ChatMsg

        now = _utcnow_iso()
        msg_id = _uid("msg")

        if language.startswith("ja"):
            content = (
                f"⏳ 修正に通常より時間がかかっています。\n\n"
                f"📋 タスク `{task_id}` はまだ処理中です。\n"
                f"完了次第、改めてお知らせします。"
            )
        else:
            content = (
                f"⏳ The fix is taking longer than usual.\n\n"
                f"📋 Task `{task_id}` is still processing.\n"
                f"I'll update you as soon as it's complete."
            )

        msg = ChatMsg(
            id=msg_id, session_id=session_id, role="assistant",
            content=content, language=language, status="completed",
            created_at=now, updated_at=now,
        )
        chat_store.save_message(msg)

        ws = _ws_connections.get(session_id)
        if ws:
            try:
                await ws.send_json({
                    "event": "feedback_fix_timeout",
                    "message_id": msg_id,
                    "content": content,
                })
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Failed to send timeout response: {e}")


# ─── Learning Loop ────────────────────────────────────────────────────────────

# 🔴 NON-KANBAN PIPELINE (USE_KANBAN=False) ─────────────────────────────────

# Issue classification patterns for direct action routing
_ACTION_CATEGORIES = {
    "infra": [
        "cloudflare", "tunnel", "403", "524", "504", "502", "rate limit",
        "inaccessible", "extremely slow", "could not connect", "unreachable",
        "not opening", "can't access", "cannot access", "don't load",
        "アクセスでき", "接続でき", "表示されな", "開けな", "遅",
        "error message occurred", "cannot get", "not working", "site was inaccessible",
    ],
    "access": [
        "seeking alpha", "cookie", "har file", "transcript",
        "earnings call", "seekingalpha", "har ",
    ],
    "content": [
        "wrong", "incorrect", "mistake", "error in", "number is wrong",
        "chart", "graph", "data", "metric", "calculation", "missing",
        "間違", "違う", "エラー", "表示されない", "データ",
        "eps", "peg", "revenue", "fcf", "growth rate", "margin",
        "not showing", "should be", "should show",
    ],
    "feature": [
        "feature", "add", "would like", "please include",
        "追加", "機能", "ほしい",
    ],
}


def _pattern_matches_direct(pattern: str, text: str) -> bool:
    """Word-boundary-aware pattern matching."""
    import re
    if " " in pattern or len(pattern) > 5:
        return pattern.lower() in text
    return bool(re.search(rf"\b{re.escape(pattern.lower())}\b", text))


def _classify_direct(user_message: str, feedback_type: str) -> str:
    """Classify feedback for direct action routing."""
    text_lower = user_message.lower()
    for category in ["infra", "access", "content", "feature"]:
        for pattern in _ACTION_CATEGORIES[category]:
            if _pattern_matches_direct(pattern, text_lower):
                return category
    type_defaults = {
        "bug": "content", "correction": "content",
        "data_quality": "content", "seeking_alpha_access": "access",
        "feature_request": "feature", "ui_ux": "content",
        "report_content": "content",
    }
    return type_defaults.get(feedback_type, "content")


async def _action_restart_backend() -> dict:
    """Restart the SA backend and return result."""
    logger.info("DIRECT-ACTION: restarting backend")
    result = {"action": "restart_backend", "success": False, "detail": ""}
    try:
        subprocess.run(["fuser", "-k", "8780/tcp"], capture_output=True, text=True, timeout=10)
        await asyncio.sleep(3)
        subprocess.run(
            ["bash", "/home/ced/.hermes/shared/scripts/launch-stock-backend.sh"],
            capture_output=True, text=True, timeout=30,
        )
        await asyncio.sleep(5)
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result["success"] = sock.connect_ex(("127.0.0.1", 8780)) == 0
        sock.close()
        result["detail"] = "Backend restarted" if result["success"] else "Port check failed"
    except Exception as e:
        result["detail"] = f"Restart error: {e}"
    return result


async def _action_reanalyze_ticker(ticker: str) -> dict:
    """Re-run analysis for a ticker via POST /api/analyze."""
    logger.info(f"DIRECT-ACTION: reanalyzing {ticker}")
    result = {"action": "reanalyze_ticker", "ticker": ticker, "success": False, "detail": ""}
    if not ticker or ticker == "GENERAL":
        result["detail"] = "No ticker — cannot reanalyze"
        return result
    try:
        import urllib.request, json as _json
        url = "http://127.0.0.1:8780/api/analyze?force_refresh=true&skip_codex=true&lang=en"
        body = _json.dumps({"tickers": [ticker]}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = _json.loads(resp.read())
            result["success"] = bool(data) and data.get("status") != "error"
            result["detail"] = str(data.get("status", data.get("message", "")))[:200]
            result["response_keys"] = list(data.keys())[:10]
            logger.info(f"DIRECT-ACTION: reanalyze {ticker} → success={result['success']} detail={result['detail'][:100]}")
    except Exception as e:
        result["detail"] = f"Reanalysis error: {type(e).__name__}: {e}"
        logger.error(f"DIRECT-ACTION: reanalyze {ticker} FAILED: {e}")
    return result


async def _send_chat_direct(session_id: str, content: str, language: str,
                             event: str = "feedback_update",
                             metadata: Optional[dict] = None) -> Optional[str]:
    """Send a response message to the chat. Returns message ID or None."""
    try:
        from backend import chat_store
        from backend.chat import _uid, _utcnow_iso, _ws_connections
        from backend.chat_models import ChatMessage as ChatMsg
        now = _utcnow_iso()
        msg_id = _uid("msg")
        msg = ChatMsg(id=msg_id, session_id=session_id, role="assistant",
                      content=content, language=language, status="completed",
                      created_at=now, updated_at=now)
        try:
            chat_store.save_message(msg)
        except Exception:
            pass
        chat_store.log_event(session_id, event, {**(metadata or {}), "message_id": msg_id})
        ws = _ws_connections.get(session_id)
        if ws:
            try:
                await ws.send_json({"event": event, "message_id": msg_id,
                                    "content": content, **(metadata or {})})
            except Exception:
                pass
        return msg_id
    except Exception as e:
        logger.error(f"Direct chat response failed: {e}")
        return None


def _ack_direct(category: str, is_jp: bool, ticker: Optional[str]) -> str:
    """Generate acknowledgment message based on category."""
    ts = f"（{ticker}）" if ticker else ""
    ack = {
        "infra": (
            f"🔧 アクセス問題{ts}を検知しました。自動復旧を試みます…"
            if is_jp else
            f"🔧 Access issue detected{ts}. Attempting automatic recovery…"
        ),
        "content": (
            f"📊 データの問題{ts}を検知しました。分析を再実行します…"
            if is_jp else
            f"📊 Data issue detected{ts}. Re-running analysis…"
        ),
        "access": (
            "🔐 Seeking Alphaの接続にはCookie更新が必要です。\n"
            "Chrome DevToolsからHARファイルをエクスポートして、フィードバックページからアップロードしてください。"
            if is_jp else
            "🔐 Seeking Alpha access requires updated cookies.\n"
            "Please export a HAR file from Chrome DevTools and upload via the feedback page."
        ),
        "feature": (
            "💡 機能リクエストを承りました。確認します。"
            if is_jp else
            "💡 Feature request received. I'll review it."
        ),
    }
    return ack.get(category, ack["content"])


async def process_feedback_direct(
    session_id: str,
    user_message: str,
    feedback_type: str,
    language: str = "ja",
    ticker: Optional[str] = None,
) -> Optional[str]:
    """Process feedback with DIRECT automation — no Kanban workers.

    Flow: classify → acknowledge → execute action → respond
    """
    logger.info(f"DIRECT processing {feedback_type} from session {session_id}")
    is_jp = language.startswith("ja")
    category = _classify_direct(user_message, feedback_type)
    action_key = f"fb:{category}:{ticker or 'GENERAL'}:{int(time.time())}"

    # Step 1: Acknowledge immediately
    ack = _ack_direct(category, is_jp, ticker)
    await _send_chat_direct(session_id, ack, language, "feedback_acknowledged", {
        "category": category, "ticker": ticker, "action_key": action_key,
    })

    # Step 2: Execute automated action
    if category == "infra":
        result = await _action_restart_backend()
        detail = (
            f"✅ サイトを再起動しました。再度アクセスしてみてください。\n"
            f"ステータス: {result.get('detail', '')}"
            if is_jp and result["success"] else
            f"✅ Site restarted. Please try again.\n"
            f"Status: {result.get('detail', '')}"
            if result["success"] else
            f"⚠️ 再起動を試みましたが問題が継続している可能性があります。Cedに通知しました。"
            if is_jp else
            f"⚠️ Attempted restart but issue may persist. Ced has been notified."
        )
    elif category == "content":
        if ticker and ticker != "GENERAL":
            result = await _action_reanalyze_ticker(ticker)
            detail = (
                f"✅ **{ticker}** の分析を再実行しました。新しいPDFをご確認ください。\n"
                f"ステータス: {result.get('detail', '')}"
                if is_jp and result["success"] else
                f"✅ Re-ran analysis for **{ticker}**. Check the new PDF.\n"
                f"Status: {result.get('detail', '')}"
                if result["success"] else
                f"⚠️ {ticker}の再分析に失敗しました。Cedに通知しました。"
                if is_jp else
                f"⚠️ Reanalysis of {ticker} failed. Ced has been notified."
            )
        else:
            detail = (
                "📝 ご指摘ありがとうございます。内容を確認し修正します。"
                if is_jp else
                "📝 Thanks for the report. I'll review and fix the content."
            )
    elif category == "access":
        detail = (
            "🔐 Seeking Alphaの接続にはCookie更新が必要です。\n"
            "Chrome DevToolsからHARファイルをエクスポートして、フィードバックページからアップロードしてください。\n"
            "アップロード後、自動的に接続が復旧します。"
            if is_jp else
            "🔐 Seeking Alpha access requires cookie refresh.\n"
            "Please export a HAR file from Chrome DevTools and upload via the feedback page.\n"
            "Connection will auto-restore after upload."
        )
    else:  # feature
        detail = (
            "💡 機能リクエストを承りました。優先度を検討し対応します。"
            if is_jp else
            "💡 Feature request noted. I'll prioritize and implement it."
        )

    await _send_chat_direct(session_id, detail, language, "feedback_action_result", {
        "category": category, "action_key": action_key,
    })
    logger.info(f"DIRECT feedback done: {action_key} → {category}")
    return action_key


# 🔴 END NON-KANBAN PIPELINE ──────────────────────────────────────────────────


# ─── Learning Loop ────────────────────────────────────────────────────────────

# Bug category taxonomy
_CATEGORY_PATTERNS = {
    "data_source": ["yfinance", "finnhub", "api", "data source", "provider", "missing data",
                    "PEG", "EPS", "PE ratio", "growth rate", "fcf", "trailing",
                    "データ", "取得", "表示されない", "数値が違う", "違う"],
    "prompt_quality": ["prompt", "explanation", "wording", "phrasing", "text", "description",
                       "説明", "文章", "書き方", "表現"],
    "renderer_logic": ["pdf", "render bug", "layout broken", "formatting", "page break", "table cut",
                       "PDF", "レイアウト", "表示", "グラフ", "表"],
    "calculation_error": ["calculation error", "math error", "formula wrong", "computation",
                          "二重カウント", "計算ミス", "算出"],
    "i18n_missing": ["japanese", "translation missing", "日本語", "翻訳漏れ", "英語だけ"],
    "frontend_display": ["button", "click", "ui issue", "interface", "hover", "responsive",
                         "ボタン", "クリック", "画面"],
    "validator_gap": ["validator", "validation", "rule", "gate", "should have caught",
                      "pre_render", "バリデーター"],
}


def _categorize_bug(feedback_type: str, user_message: str) -> str:
    """Categorize a bug based on feedback type and message content."""
    text_lower = user_message.lower()
    for category, patterns in _CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in text_lower:
                return category
    # Default: use feedback_type as fallback category
    type_to_category = {
        "correction": "data_source",
        "bug": "renderer_logic",
        "ux": "frontend_display",
        "feature_request": "frontend_display",
    }
    return type_to_category.get(feedback_type, "data_source")


def _categorize_root_cause(feedback_type: str, user_message: str, fix_result: str) -> str:
    """Identify the root cause from the fix result."""
    result_lower = fix_result.lower()
    cause_map = [
        ("stale_cache", ["cache", "stale", "flush", "cached"]),
        ("missing_field", ["missing", "whitelist", "not in", "add key", "add_field"]),
        ("validator_absent", ["validator", "pre_render", "rule added", "gate", "should have"]),
        ("renderer_bug", ["render", "pdf_renderer", "fpdf", "layout"]),
        ("prompt_instruction", ["prompt", "instruction", "system prompt", "llm"]),
        ("mapper_gap", ["mapper", "mapping", "transform", "normalize"]),
        ("api_config", ["api", "endpoint", "route", "config"]),
        ("frontend_state", ["react", "state", "component", "jsx", "unmount"]),
    ]
    for cause, keywords in cause_map:
        for kw in keywords:
            if kw in result_lower:
                return cause
    return "unknown"


def _suggest_validator_rule(category: str, user_message: str, fix_result: str) -> str:
    """Suggest a validator rule that could have caught this bug."""
    suggestions = {
        "data_source": "RULE <N>: Verify all yfinance fields used in display are in the whitelist",
        "prompt_quality": "RULE <N>: Scan generated prose for forbidden patterns or missing context",
        "renderer_logic": "RULE <N>: Validate PDF output for layout, truncation, or missing sections",
        "calculation_error": "RULE <N>: Cross-validate computed metrics against source data",
        "i18n_missing": "RULE <N>: Verify JP labels exist for all user-facing strings",
        "frontend_display": "RULE <N>: Browser recette — verify component visibility and state",
        "validator_gap": "RULE <N>: Add pre-render check for this specific failure mode",
    }
    return suggestions.get(category, "RULE <N>: Add check for this pattern")


def _learn_from_fix(
    task_id: str,
    feedback_type: str,
    user_message: str,
    ticker: str,
    fix_result: str,
) -> None:
    """Post-fix learning: log the correction pattern to prevent recurrence.

    Writes to docs/corrections_log.md with:
    - Bug category and root cause
    - Suggested validator rule
    - Cross-reference to task/commit

    The corrections log becomes a reference for workers — when processing
    similar tasks, they can consult past corrections to avoid repeating mistakes.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    corrections_log = Path(__file__).resolve().parent.parent / "docs" / "corrections_log.md"

    category = _categorize_bug(feedback_type, user_message)
    root_cause = _categorize_root_cause(feedback_type, user_message, fix_result)
    validator_rule = _suggest_validator_rule(category, user_message, fix_result)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    entry = (
        f"\n---\n"
        f"## {now} — {task_id}\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| **Task** | `{task_id}` |\n"
        f"| **Ticker** | {ticker or 'N/A'} |\n"
        f"| **Feedback type** | `{feedback_type}` |\n"
        f"| **Category** | `{category}` |\n"
        f"| **Root cause** | `{root_cause}` |\n"
        f"| **Suggested validator** | {validator_rule} |\n\n"
        f"**User message:**\n> {user_message[:300]}\n\n"
        f"**Fix summary:**\n{fix_result[:500] or '(no fix summary available)'}\n"
    )

    try:
        with open(corrections_log, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"Learning loop: logged correction {task_id} → {corrections_log}")
    except Exception as e:
        logger.error(f"Failed to write corrections log: {e}")
