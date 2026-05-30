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
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

KANBAN_BOARD = "sa-pipeline"
MAX_MONITOR_SECONDS = 1800  # 30 min max before giving up
MONITOR_INTERVAL_SECONDS = 30  # Check every 30s

# ─── Pre-flight Gate ─────────────────────────────────────────────────────────

def run_preflight_gate() -> tuple[bool, str]:
    """Run kanban pre-flight. Returns (ok, detail_message)."""
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
            # Parse failures from JSON
            import json
            try:
                data = json.loads(result.stdout)
                failures = data.get("failures", [])
                return False, "; ".join(failures[:3]) if failures else "NO-GO (unknown)"
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
    """Autonomous feedback → Kanban → fix pipeline.

    Returns the Kanban task_id if successfully created, None otherwise.
    This is called as a fire-and-forget task after the AI response is delivered.
    """
    logger.info(f"Processing {feedback_type} feedback from session {session_id}")

    # Gate 0: Pre-flight check
    preflight_ok, preflight_msg = run_preflight_gate()
    if not preflight_ok:
        logger.error(f"Pre-flight FAILED for feedback pipeline: {preflight_msg}")
        # Still acknowledge but warn
        from backend import chat_store
        from backend.chat import _ws_connections, _uid, _utcnow_iso
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
    asyncio.create_task(_monitor_and_respond(task_id, session_id, language))

    return task_id


# ─── Background Monitor ──────────────────────────────────────────────────────

async def _monitor_and_respond(task_id: str, session_id: str, language: str):
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
            await _send_completion_response(session_id, task_id, result_text, language)
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


async def _send_completion_response(session_id: str, task_id: str, result: str, language: str):
    """Notify chat that the fix is deployed."""
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
