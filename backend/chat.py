"""FastAPI router for the live chat widget.

Endpoints:
- POST /api/chat/session     — create or get session
- GET  /api/chat/history     — message history
- POST /api/chat/message     — send message, triggers AI response
- WS   /api/chat/ws          — WebSocket for live streaming events
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse

from .chat_models import (
    ChatContextPayload,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSendResponse,
    ChatSessionRequest,
    ChatSessionResponse,
    ChatFeedbackRequest,
    ChatFeedbackResponse,
)
from .chat_models import ChatMessage as ChatMsg
from . import chat_store, chat_context, chat_ai

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── Security constants ─────────────────────────────────────────────────────
_MAX_MESSAGE_LENGTH = 4000  # characters
_VISITOR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_DEFAULT_VISITOR_NAME = "Visitor"

# Trusted proxy IPs for X-Forwarded-For header validation
_TRUSTED_PROXY_IPS = {
    "127.0.0.1",
    "::1",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",     # Cloudflare WARP / carrier-grade NAT
    # Add any known reverse proxy IPs here (e.g. Cloudflare, Nginx on known infra)
}


def _is_trusted_proxy(ip: str) -> bool:
    """Check if an IP address belongs to a trusted proxy.

    Validates against _TRUSTED_PROXY_IPS using direct match and CIDR.
    """
    if not ip:
        return False
    if ip in _TRUSTED_PROXY_IPS:
        return True
    # CIDR check (simplified — just check IP starts with known prefixes)
    for trusted in _TRUSTED_PROXY_IPS:
        if "/" in trusted:
            prefix = trusted.split("/")[0]
            if ip.startswith(prefix.rstrip(".")):
                return True
    return False


def _get_real_client_ip(request: Request) -> str:
    """Extract the real client IP, validating the X-Forwarded-For chain.

    Only trusts X-Forwarded-For if the immediate connection is from a known proxy.
    Otherwise uses the direct TCP connection IP.
    """
    direct_ip = request.client.host if request.client else "unknown"

    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded and _is_trusted_proxy(direct_ip):
        # X-Forwarded-For is a comma-separated list: client, proxy1, proxy2
        # Take the first (original client) IP
        return forwarded.split(",")[0].strip()

    return direct_ip


def _fingerprint_device(user_agent: str) -> str:
    """Extract device fingerprint from User-Agent for session grouping.

    Returns a short string like 'apple-mac-safari-us' or 'android-samsung-unknown'.
    """
    ua = user_agent.lower()
    parts = []

    # OS
    if "mac os" in ua or "macintosh" in ua:
        parts.append("apple-mac")
    elif "iphone" in ua:
        parts.append("apple-iphone")
    elif "ipad" in ua:
        parts.append("apple-ipad")
    elif "android" in ua:
        parts.append("android")
    elif "windows" in ua:
        parts.append("windows")
    elif "linux" in ua:
        parts.append("linux")
    else:
        parts.append("unknown-os")

    # Browser
    if "safari" in ua and "chrome" not in ua:
        parts.append("safari")
    elif "chrome" in ua:
        parts.append("chrome")
    elif "firefox" in ua:
        parts.append("firefox")
    elif "edg" in ua:
        parts.append("edge")
    else:
        parts.append("unknown-browser")

    return "-".join(parts)


def _normalize_visitor_id(raw_visitor_id: Optional[str]) -> str:
    """Return a cryptographic visitor_id, never an IP/device-derived identity.

    The frontend normally sends crypto.randomUUID() from localStorage. If the
    value is missing, blank, or malformed, generate a fresh UUID4 server-side
    instead of falling back to visitor_name, IP, or device fingerprinting.
    """
    candidate = (raw_visitor_id or "").strip()
    if _VISITOR_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _check_origin(request: Request) -> None:
    """Validate request origin for chat endpoints.
    
    Allows: any cedlabusa.net subdomain, localhost dev ports, 127.0.0.1.
    Blocks: unknown external origins.
    """
    origin = request.headers.get("origin", "")
    if not origin:
        return  # No origin header → allow (server-to-server, curl, etc.)
    
    # Allow any cedlabusa.net origin (sa., www., or bare)
    if "cedlabusa.net" in origin:
        return
    # Allow local development
    if origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
        return
    
    raise HTTPException(status_code=403, detail=f"Origin not allowed: {origin}")

# Active WebSocket connections: session_id -> WebSocket
_ws_connections: dict[str, WebSocket] = {}


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── REST Endpoints ───────────────────────────────────────────────────────────

@router.post("/session", response_model=ChatSessionResponse)
async def create_session(req: ChatSessionRequest, request: Request):
    """Create a chat session keyed by cryptographic visitor_id.

    Identity isolation is based only on visitor_id. Server-observed device
    fingerprints may personalize display/context routing for known users, but
    they never merge sessions or override visitor_id.
    """
    client_ip = _get_real_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    device_info = _fingerprint_device(user_agent)
    visitor_id = _normalize_visitor_id(req.visitor_id)

    meta = dict(req.metadata or {})
    meta.update({
        "client_ip": client_ip,
        "user_agent": user_agent[:200],
        "device": device_info,
        "visitor_id": visitor_id,
    })

    session = chat_store.create_session(
        visitor_id=visitor_id,
        visitor_name=chat_context.resolve_visitor_display_name(meta, req.language),
        language=req.language,
        metadata=meta,
    )
    chat_store.log_event(session.id, "session_created", {
        "language": req.language,
        "visitor_id": visitor_id,
        "ip": client_ip,
        "device": device_info,
    })
    return ChatSessionResponse(
        session_id=session.id,
        visitor_id=visitor_id,
        language=session.language,
    )


@router.get("/history")
async def get_history(session_id: str = Query(...)):
    """Get message history for a session."""
    msgs = chat_store.get_history(session_id, limit=100)
    return {
        "messages": [
            ChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                language=m.language,
                ticker=m.ticker,
                pdf_id=m.pdf_id,
                status=m.status,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in msgs
        ]
    }


@router.post("/message", response_model=ChatSendResponse)
async def send_message(req: ChatMessageRequest, request: Request):
    """Send a user message and trigger AI response.

    The AI response is streamed via WebSocket. This endpoint returns immediately
    with the message IDs; the actual AI response is delivered asynchronously
    via the WebSocket at /api/chat/ws.
    """
    now = _utcnow_iso()

    # Security: origin check
    _check_origin(request)

    # Security: max message size
    if len(req.message) > _MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Message too long ({len(req.message)} chars, max {_MAX_MESSAGE_LENGTH})",
        )

    # Validate session
    session = chat_store.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Idempotency check
    if req.idempotency_key:
        existing = chat_store.find_by_idempotency_key(req.idempotency_key)
        if existing:
            return JSONResponse(
                status_code=200,
                content={
                    "user_message_id": existing.id,
                    "assistant_message_id": existing.parent_message_id or "",
                    "status": existing.status,
                    "duplicate": True,
                },
            )

    # Update session context
    ctx = req.context
    chat_store.update_session(
        req.session_id,
        language=ctx.client_language,
        current_ticker=ctx.ticker,
        current_pdf_id=ctx.pdf_id,
        last_seen_at=now,
    )

    # Track ticker for this session (RAG context)
    if ctx.ticker:
        chat_store.track_session_ticker(req.session_id, ctx.ticker.upper())

    # Save user message
    user_msg = ChatMsg(
        id=_uid("msg"),
        session_id=req.session_id,
        role="user",
        content=req.message,
        language=ctx.client_language,
        ticker=ctx.ticker,
        pdf_id=ctx.pdf_id,
        status="completed",
        idempotency_key=req.idempotency_key,
        created_at=now,
        updated_at=now,
    )
    chat_store.save_message(user_msg)

    # Create assistant placeholder
    assistant_msg_id = _uid("msg")
    assistant_msg = ChatMsg(
        id=assistant_msg_id,
        session_id=req.session_id,
        role="assistant",
        content="",
        language=ctx.client_language,
        ticker=ctx.ticker,
        pdf_id=ctx.pdf_id,
        status="processing",
        parent_message_id=user_msg.id,
        created_at=now,
        updated_at=now,
    )
    chat_store.save_message(assistant_msg)

    chat_store.log_event(req.session_id, "message_created", {
        "user_message_id": user_msg.id,
        "assistant_message_id": assistant_msg_id,
    })

    # Fire-and-forget: generate AI response in background
    asyncio.create_task(_generate_and_stream(
        session_id=req.session_id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg_id,
        user_message=req.message,
        language=ctx.client_language,
        ticker=ctx.ticker,
        pdf_id=ctx.pdf_id,
        pdf_title=ctx.pdf_title,
        pdf_page=ctx.pdf_page,
        selected_section=ctx.selected_section,
        current_url=ctx.current_url,
        route=ctx.route,
    ))

    return ChatSendResponse(
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg_id,
        status="processing",
    )


# ── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_chat(ws: WebSocket, session_id: str = Query(...)):
    """WebSocket for receiving live chat events.

    Client connects here to receive assistant_started, assistant_delta,
    assistant_completed, and assistant_error events.
    """
    session = chat_store.get_session(session_id)
    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    await ws.accept()
    _ws_connections[session_id] = ws

    try:
        # Keep connection alive, listen for ping/pong
        while True:
            data = await ws.receive_text()
            # Client can send ping or context updates
            if data == "ping":
                await ws.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error for session {session_id}: {e}")
    finally:
        _ws_connections.pop(session_id, None)


# ── Background AI Generation ─────────────────────────────────────────────────

async def _generate_and_stream(
    *,
    session_id: str,
    user_message_id: str,
    assistant_message_id: str,
    user_message: str,
    language: str = "ja",
    ticker: Optional[str] = None,
    pdf_id: Optional[str] = None,
    pdf_title: Optional[str] = None,
    pdf_page: Optional[int] = None,
    selected_section: Optional[str] = None,
    current_url: Optional[str] = None,
    route: Optional[str] = None,
) -> None:
    """Generate AI response and stream to WebSocket. Runs as background task."""
    ws = _ws_connections.get(session_id)

    # Build context
    ctx = await chat_context.build_chat_context(
        session_id=session_id,
        user_message=user_message,
        ticker=ticker,
        pdf_id=pdf_id,
        pdf_title=pdf_title,
        pdf_page=pdf_page,
        selected_section=selected_section,
        current_url=current_url,
        route=route,
        language=language,
    )

    # Notify: assistant started
    chat_store.update_message_status(assistant_message_id, "processing")
    if ws:
        try:
            await ws.send_json({
                "event": "assistant_started",
                "message_id": assistant_message_id,
            })
        except Exception:
            pass

    # Stream AI response
    full_response = ""
    try:
        async for token in chat_ai.stream_ai_response(
            user_message,
            language=ctx["language"],
            ticker=ctx["ticker"],
            pdf_title=ctx["pdf_title"],
            pdf_chunks=ctx["pdf_chunks"],
            pdf_summary=ctx["pdf_summary"],
            pdf_page=ctx.get("pdf_page"),
            selected_section=ctx.get("selected_section"),
            history=ctx["history"],
            current_url=ctx["current_url"],
            route=ctx["route"],
            recent_tickers=ctx.get("recent_tickers"),
            feedback_context=ctx.get("feedback_context"),
            previous_chats=ctx.get("previous_chats"),
            visitor_name=ctx.get("visitor_display_name", "Visitor"),
        ):
            full_response += token
            if ws:
                try:
                    await ws.send_json({
                        "event": "assistant_delta",
                        "message_id": assistant_message_id,
                        "delta": token,
                    })
                except Exception:
                    pass

        # Save final response
        now = _utcnow_iso()
        status = "completed"
        # Detect truncation: response ending mid-word/mid-sentence
        stripped = full_response.rstrip()
        if stripped and not stripped[-1] in ".!?。！？)\"」\n":
            logger.warning(
                "Chat response may be truncated (ends with %r, length=%d chars). "
                "Consider increasing SA_CHAT_MAX_OUTPUT_TOKENS.",
                stripped[-10:], len(full_response),
            )
            status = "truncated"
        chat_store.update_message(
            assistant_message_id,
            content=full_response,
            status=status,
            updated_at=now,
        )

        if ws:
            try:
                await ws.send_json({
                    "event": "assistant_completed",
                    "message_id": assistant_message_id,
                })
            except Exception:
                pass

        chat_store.log_event(session_id, "assistant_completed", {
            "message_id": assistant_message_id,
            "response_length": len(full_response),
        })

        # 🔴 Stage 1: Detect if user message contains a potential correction
        fb_type = _detect_feedback(user_message)
        if fb_type:
            try:
                chat_store.save_chat_feedback(
                    session_id, fb_type, user_message,
                    message_id=user_message_id,
                )
                chat_store.log_event(session_id, "feedback_auto_detected", {
                    "feedback_type": fb_type,
                    "user_message_id": user_message_id,
                })
                logger.info(f"Auto-detected {fb_type} feedback in message {user_message_id}")
            except Exception as e:
                logger.warning(f"Failed to save auto-detected feedback: {e}")

            # 🔴 Stage 2: Check if user explicitly asked for a fix (skip confirmation)
            if _is_direct_fix_request(user_message):
                logger.info(f"Direct fix request — launching pipeline immediately")
                try:
                    from backend.feedback_pipeline import process_feedback
                    asyncio.create_task(process_feedback(
                        session_id=session_id,
                        user_message=user_message,
                        feedback_type=fb_type,
                        language=language,
                        ticker=ticker,
                    ))
                    logger.info(f"Launched feedback pipeline for direct fix: {fb_type}")
                except Exception as e:
                    logger.error(f"Failed to launch feedback pipeline: {e}")
            else:
                # Store pending fix — wait for explicit confirmation from AI conversation
                _pending_fixes[session_id] = {
                    "feedback_type": fb_type,
                    "user_message": user_message,
                    "ticker": ticker,
                    "language": language,
                    "timestamp": time.time(),
                }
                logger.info(f"Stored pending fix for session {session_id} ({fb_type}) — awaiting confirmation")
        else:
            # 🔴 Stage 3: Check if this message is a confirmation to a pending fix
            pending = _pending_fixes.pop(session_id, None)
            if pending and _is_fix_confirmation(user_message):
                logger.info(f"User confirmed fix for session {session_id}")
                try:
                    from backend.feedback_pipeline import process_feedback
                    asyncio.create_task(process_feedback(
                        session_id=session_id,
                        user_message=pending["user_message"],  # original bug report
                        feedback_type=pending["feedback_type"],
                        language=pending["language"],
                        ticker=pending.get("ticker"),
                    ))
                    logger.info(f"Launched feedback pipeline for confirmed fix: {pending['feedback_type']}")
                except Exception as e:
                    logger.error(f"Failed to launch feedback pipeline: {e}")
            elif pending:
                logger.info(f"User declined fix for session {session_id} — pending fix discarded")

    except Exception as e:
        logger.error(f"AI generation failed for {assistant_message_id}: {e}")
        now = _utcnow_iso()
        chat_store.update_message(
            assistant_message_id,
            content=f"[エラーが発生しました。もう一度お試しください。]",
            status="failed",
            updated_at=now,
        )
        if ws:
            try:
                await ws.send_json({
                    "event": "assistant_error",
                    "message_id": assistant_message_id,
                    "error": str(e),
                })
            except Exception:
                pass


# ── Utility endpoint: context debug ──────────────────────────────────────────

@router.get("/context")
async def debug_context(session_id: str = Query(...)):
    """Debug endpoint: show what context the AI would receive."""
    ctx = await chat_context.build_chat_context(
        session_id=session_id,
        user_message="[debug]",
    )
    # Truncate long fields for readability
    if ctx.get("pdf_chunks"):
        ctx["pdf_chunks"] = [{**c, "content": c["content"][:200] + "…"} for c in ctx["pdf_chunks"]]
    return ctx


# ── Feedback ─────────────────────────────────────────────────────────────────

# Simple keyword-based feedback detection (no extra LLM call)
_FEEDBACK_PATTERNS = {
    "bug": [
        "bug", "broken", "not working", "doesn't work", "error", "crash",
        "バグ", "動かない", "エラー", "壊れて", "故障", "不具合",
    ],
    "ux": [
        "confus", "hard to", "difficult to", "unclear", "should be easier",
        "わかりにくい", "使いにくい", "見にくい", "改善",
    ],
    "feature_request": [
        "can you add", "please add", "it would be nice", "could you add",
        "追加して", "あればいい", "ほしい", "できるように",
    ],
    "correction": [
        "wrong", "incorrect", "mistake", "typo", "not correct",
        "間違っている", "誤り", "違う", "正しくない",
    ],
}


def _detect_feedback(text: str) -> Optional[str]:
    """Check if a message contains feedback signals. Returns feedback_type or None."""
    text_lower = text.lower()
    for fb_type, patterns in _FEEDBACK_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                return fb_type
    return None


# ─── Pending Fix Confirmation ────────────────────────────────────────────────

# In-memory store: session_id → pending fix metadata
# Cleared on confirmation, denial, or session expiry (TTL: 30 min)
_pending_fixes: dict[str, dict] = {}

# Patterns that indicate user confirms they want a fix
_CONFIRMATION_PATTERNS = [
    # Explicit yes
    "yes", "yeah", "yep", "sure", "okay", "ok", "please do", "go ahead",
    "do it", "please fix", "create the ticket", "create a ticket",
    # French
    "oui", "ouais", "vas-y", "allez-y", "corrige", "corrigez",
    "crée le ticket", "créer le ticket", "fais-le",
    # Japanese
    "はい", "お願い", "おねがい", "よろしく", "やって", "修正して",
    "チケット作成", "お願いします", "いいです", "いいよ",
    "作成して", "対応して",
]

# Patterns that indicate user declines
_DECLINE_PATTERNS = [
    "no", "nope", "not now", "never mind", "don't", "skip",
    "non", "pas maintenant", "laisse tomber",
    "いいえ", "結構", "けっこう", "大丈夫", "だいじょうぶ",
    "今はいい", "やめとく",
]

# Patterns that indicate the user explicitly wants a fix NOW (skip confirmation)
_DIRECT_FIX_PATTERNS = [
    "please fix", "fix this", "fix it", "correct this", "correct it",
    "corrige ça", "corrige le", "corrige la", "corrigez",
    "修正して", "直して", "すぐに修正", "修正お願い",
    "create a ticket", "crée un ticket",
]


def _is_fix_confirmation(text: str) -> bool:
    """Check if a message is a confirmation to create a fix ticket.
    
    Uses word-boundary-aware matching to avoid false positives:
    - "ok" matches "ok" but NOT "broken"
    - "yes" matches "yes please" but NOT "yes but also add..."
    - Multi-word patterns use substring matching (e.g., "please fix" matches anywhere)
    """
    import re
    
    text_lower = text.lower().strip()
    
    # Must be a short confirmation message (not a new bug report)
    if len(text_lower) > 60:
        return False
    
    # Reject if the message also looks like a new bug report
    if _detect_feedback(text_lower):
        return False
    
    # Short patterns that need word boundaries (to avoid substring false matches)
    _short_patterns = {"yes", "yeah", "yep", "sure", "ok", "okay",
                       "oui", "ouais", "non",
                       "はい", "いいよ", "いいです"}
    
    for pattern in _CONFIRMATION_PATTERNS:
        if pattern in _short_patterns:
            # Word-boundary match: start/space before, end/space/punctuation after
            if re.search(rf'(?<!\w){re.escape(pattern)}(?!\w)', text_lower):
                # Make sure it's not a negation mixed in
                for decline in _DECLINE_PATTERNS:
                    if decline in _short_patterns:
                        if re.search(rf'(?<!\w){re.escape(decline)}(?!\w)', text_lower):
                            return False
                    elif decline in text_lower:
                        return False
                return True
        else:
            # Multi-word patterns: substring match is fine
            if pattern in text_lower:
                for decline in _DECLINE_PATTERNS:
                    if decline in text_lower:
                        return False
                return True
    
    return False


def _is_direct_fix_request(text: str) -> bool:
    """Check if the user explicitly demands a fix NOW (skip confirmation step)."""
    text_lower = text.lower()
    for pattern in _DIRECT_FIX_PATTERNS:
        if pattern in text_lower:
            return True
    return False


@router.post("/feedback", response_model=ChatFeedbackResponse)
async def submit_feedback(req: ChatFeedbackRequest, request: Request):
    """Submit explicit chat feedback (bug, UX, feature request, etc.)."""
    _check_origin(request)

    session = chat_store.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    fid = chat_store.save_chat_feedback(
        req.session_id,
        req.feedback_type,
        req.content,
        message_id=req.message_id,
    )
    chat_store.log_event(req.session_id, "feedback_submitted", {
        "feedback_type": req.feedback_type,
        "feedback_id": fid,
    })

    return ChatFeedbackResponse(
        id=fid,
        session_id=req.session_id,
        message_id=req.message_id,
        feedback_type=req.feedback_type,
        content=req.content,
        status="open",
        created_at=chat_store._utcnow_iso(),
    )


@router.get("/feedback")
async def list_feedback(session_id: str = Query(...)):
    """List all feedback for a session."""
    conn = chat_store.get_conn()
    rows = conn.execute(
        "SELECT id, session_id, message_id, feedback_type, content, status, created_at "
        "FROM chat_feedback WHERE session_id = ? ORDER BY created_at DESC",
        (session_id,),
    ).fetchall()
    return {
        "feedback": [
            ChatFeedbackResponse(
                id=r[0], session_id=r[1], message_id=r[2],
                feedback_type=r[3], content=r[4], status=r[5], created_at=r[6],
            )
            for r in rows
        ]
    }


# ── Session Close / Export ───────────────────────────────────────────────────

import os
from pathlib import Path as _Path

_CHAT_EXPORT_DIR = _Path(__file__).resolve().parent.parent / "chat_exports"


@router.post("/session/{session_id}/close")
async def close_chat_session(session_id: str, request: Request):
    """Close a chat session and export the transcript."""
    _check_origin(request)

    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Export the conversation
    text = chat_store.export_session(session_id)
    if not text:
        raise HTTPException(status_code=500, detail="Export failed")

    # Save to file. Use visitor_id, never visitor_name/device-derived identity.
    _CHAT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = chat_store._utcnow_iso().replace(":", "-")[:19]
    safe_visitor = re.sub(r"[^A-Za-z0-9_-]+", "", session.visitor_id or "")[:16] or "visitor"
    filename = f"chat_{safe_visitor}_{safe_ts}_{session_id[:8]}.txt"
    filepath = _CHAT_EXPORT_DIR / filename
    filepath.write_text(text, encoding="utf-8")

    # Mark closed
    chat_store.close_session(session_id)
    chat_store.log_event(session_id, "session_closed", {
        "export_file": str(filepath),
        "message_count": text.count("🧑 Visitor") + text.count("🤖 Assistant"),
    })

    # Write a pending-delivery marker for Hermes to pick up
    _delivery_dir = _Path(__file__).resolve().parent.parent / "chat_exports" / ".pending_delivery"
    _delivery_dir.mkdir(parents=True, exist_ok=True)
    (_delivery_dir / filename).write_text(str(filepath))

    return {
        "status": "closed",
        "session_id": session_id,
        "export_file": str(filepath),
        "export_size": len(text),
    }


@router.get("/session/{session_id}/export")
async def export_chat_session(session_id: str):
    """Export a chat session as plain text (without closing it)."""
    text = chat_store.export_session(session_id)
    if not text:
        raise HTTPException(status_code=404, detail="Session not found or empty")

    return {
        "session_id": session_id,
        "text": text,
        "size": len(text),
    }
