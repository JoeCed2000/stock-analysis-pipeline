"""Context builder for the chat AI.

Assembles session info, ticker context, PDF chunks, history,
and UI state into a structured context object for the AI prompt.
"""

from __future__ import annotations

from typing import Optional

import logging

logger = logging.getLogger(__name__)


def localized_visitor_label(language: str | None = "ja") -> str:
    """Return the neutral visitor label in the active chat language."""
    lang = (language or "ja").strip().lower()
    if lang.startswith("en"):
        return "visitor"
    return "訪問者"


def resolve_visitor_display_name(metadata: dict | None, language: str | None = "ja") -> str:
    """Resolve the chat display label from trusted server-side metadata.

    The frontend still cannot choose a name through the legacy visitor_name
    payload. The backend may, however, personalize known operational devices
    from the server-observed fingerprint so the assistant can greet Nami as
    Nami-san and Ced as Ced while keeping unknown visitors neutral.
    """
    meta = metadata or {}
    display_name = (meta.get("display_name") or "").strip()
    if display_name:
        return display_name

    device = (meta.get("device") or "").strip().lower()
    user_agent = (meta.get("user_agent") or "").strip().lower()
    # Nami uses Mac (Safari or Chrome). Match on UA first, fall back to fingerprint.
    is_nami_device = (
        "macintosh" in user_agent
        or device in {"apple-mac-safari", "apple-iphone-safari", "apple-ipad-safari", "apple-mac-chrome"}
    )
    if is_nami_device:
        return "Nami-san"
    if device in {"linux-chrome", "windows-chrome", "linux-edge", "windows-edge"}:
        return "Ced"

    return localized_visitor_label(language)


def _detect_visitor_name(session_id: str) -> str:
    """Return the server-resolved display label for a chat session."""
    from . import chat_store
    import json

    try:
        session = chat_store.get_session(session_id)
        if not session:
            return localized_visitor_label("en")

        language = getattr(session, "language", "ja") or "ja"
        if not session.metadata_json:
            return localized_visitor_label(language)

        try:
            meta = json.loads(session.metadata_json)
        except json.JSONDecodeError:
            return localized_visitor_label(language)

        return resolve_visitor_display_name(meta, language)
    except Exception:
        return localized_visitor_label("en")


def _is_nami_session(session_id: str) -> bool:
    """Return true only for server-recognized Nami sessions.

    Feedback-page data is Nami-only by product convention, but it must not leak
    into Ced/unknown chat contexts. The gate is therefore the same trusted
    server-side fingerprint resolution used for the display name.
    """
    return _detect_visitor_name(session_id) == "Nami-san"


def _get_form_feedback_context(limit: int = 8) -> list[dict]:
    """Return Nami-only feedback-page entries for chat context."""
    try:
        from . import feedback_store

        items = []
        for entry in feedback_store.list_all_feedback()[:limit]:
            text = (entry.get("text") or entry.get("message") or entry.get("content") or "").strip()
            files = entry.get("files") or []
            items.append({
                "source": "feedback_page",
                "type": entry.get("category") or "feedback",
                "content": text[:200],
                "status": entry.get("status") or ("taken_into_account" if entry.get("processed") else "pending"),
                "date": (entry.get("submitted_at") or entry.get("date") or "")[:10],
                "ticker": entry.get("ticker") or entry.get("_ticker"),
                "files": files[:4] if isinstance(files, list) else [],
            })
        return items
    except Exception:
        return []


async def build_chat_context(
    session_id: str,
    user_message: str,
    *,
    ticker: Optional[str] = None,
    pdf_id: Optional[str] = None,
    pdf_title: Optional[str] = None,
    pdf_page: Optional[int] = None,
    selected_section: Optional[str] = None,
    current_url: Optional[str] = None,
    route: Optional[str] = None,
    language: Optional[str] = None,
) -> dict:
    """Build the full context dict for an AI response.

    Returns a dict with all keys needed by chat_ai.stream_ai_response().
    """
    from . import chat_store, chat_retrieval

    # Get session info
    session = chat_store.get_session(session_id)
    effective_language = language or (session.language if session else None) or "ja"
    if session:
        # Update session with latest context without overwriting the stored
        # language when debug/context callers do not provide one explicitly.
        chat_store.update_session(
            session_id,
            current_ticker=ticker or session.current_ticker,
            current_pdf_id=pdf_id or session.current_pdf_id,
            language=effective_language,
        )

    # Get recent history
    history_msgs = chat_store.get_recent_messages(session_id, limit=20)
    history_dicts = [m.to_dict() for m in history_msgs]

    # Get PDF context
    pdf_chunks = None
    pdf_summary = None
    if pdf_id:
        pdf_summary = chat_store.get_pdf_summary(pdf_id)
        # Search for relevant chunks
        try:
            pdf_chunks = chat_retrieval.retrieve_pdf_context(
                user_message, ticker=ticker, pdf_id=pdf_id, limit=5
            )
        except Exception as e:
            logger.warning(f"PDF retrieval error: {e}")

    # If no pdf_id but ticker is available, try to find PDF
    if not pdf_id and ticker:
        # Try to find any PDF for this ticker
        try:
            pdf_chunks = chat_retrieval.retrieve_pdf_context(
                user_message, ticker=ticker, limit=5
            )
        except Exception:
            pass

    return {
        "language": effective_language,
        "ticker": ticker,
        "pdf_title": pdf_title,
        "pdf_page": pdf_page,
        "selected_section": selected_section,
        "pdf_chunks": pdf_chunks,
        "pdf_summary": pdf_summary,
        "history": history_dicts,
        "current_url": current_url,
        "route": route,
        "visitor_display_name": _detect_visitor_name(session_id),
        "recent_tickers": _get_recent_tickers(session_id=session_id, limit=5, exclude_ticker=ticker),
        "feedback_context": _get_feedback_context(session_id=session_id),
        "previous_chats": _get_previous_chat_summaries(session_id=session_id),
    }


def _get_previous_chat_summaries(session_id: str) -> list[dict]:
    """Get summaries of previous chat sessions from the same visitor."""
    from . import chat_store
    from . import chat_store as _cs
    try:
        session = _cs.get_session(session_id)
        if not session or not session.visitor_id:
            return []
        return chat_store.get_recent_chat_summaries(
            session.visitor_id, max_sessions=3, max_age_hours=24,
            exclude_session_id=session_id,
        )
    except Exception:
        return []


def _get_feedback_context(session_id: str) -> list[dict]:
    """Get recent feedback for the chat AI context.

    Chat-origin feedback remains strictly scoped by visitor_id. The separate
    feedback page store has no visitor_id field; by product convention that
    area belongs to Nami only, so it is included only for sessions that the
    server-side fingerprint resolves to Nami-san.
    """
    from . import chat_store
    try:
        session = chat_store.get_session(session_id)
        if not session or not session.visitor_id:
            return []

        items = chat_store.get_recent_feedback_for_context(
            visitor_id=session.visitor_id, limit=8,
        )
        if _is_nami_session(session_id):
            remaining = max(0, 8 - len(items))
            if remaining:
                items.extend(_get_form_feedback_context(limit=remaining))
        return items[:8]
    except Exception:
        return []


def _get_recent_tickers(
    session_id: Optional[str] = None,
    limit: int = 5,
    exclude_ticker: Optional[str] = None,
) -> list[dict]:
    """Get tickers this visitor has viewed, with their available PDFs.

    Uses visitor history by default. Feedback-page uploads are Nami-only by
    product convention and are therefore included only for sessions that the
    server recognizes as Nami-san.
    """
    from pathlib import Path

    is_nami = _is_nami_session(session_id) if session_id else False

    # Get tickers from visitor history
    tickers: list[str] = []
    if session_id:
        from . import chat_store
        session = chat_store.get_session(session_id)
        if session and session.visitor_id:
            tickers = chat_store.get_session_tickers(session.visitor_id, max_age_hours=2)

    if not tickers:
        return _get_uploaded_feedback_pdfs(session_id, limit=limit) if is_nami else []

    # Reverse to get most recent first, filter, deduplicate
    seen = set()
    result = []
    for t in reversed(tickers):
        t = t.upper()
        if t == (exclude_ticker or "").upper():
            continue
        if t in seen or t in _TICKER_BLACKLIST:
            continue
        seen.add(t)

        # Find PDFs for this ticker in analyses/
        analyses_dir = Path(__file__).resolve().parent.parent / "analyses"
        pdfs = []
        if analyses_dir.exists():
            for entry in sorted(analyses_dir.iterdir(), key=lambda e: e.stat().st_mtime, reverse=True):
                if not entry.is_dir():
                    continue
                # Check if this directory is for the ticker
                dir_ticker = None
                for token in entry.name.split("_"):
                    token = token.strip()
                    if token.upper() == t:
                        dir_ticker = token.upper()
                        break
                if dir_ticker != t:
                    continue
                # Found matching directory — list its PDFs
                from datetime import datetime
                mtime = entry.stat().st_mtime
                for pdf_file in sorted(entry.rglob("*.pdf")):
                    pdfs.append(pdf_file.name)
                result.append({
                    "ticker": t,
                    "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                    "pdfs": pdfs[:4],
                })
                break  # found the most recent dir for this ticker

        # If no directory found, still include the ticker
        if not result or result[-1]["ticker"] != t:
            result.append({
                "ticker": t,
                "date": "?",
                "pdfs": [],
            })

        if len(result) >= limit:
            break

    # Also include uploaded PDFs from feedback directories, but only for Nami.
    if is_nami:
        feedback_uploads = _get_uploaded_feedback_pdfs(session_id, limit=3)
        for fu in feedback_uploads:
            if fu["ticker"] not in seen:
                result.append(fu)

    return result[:limit]


def _get_uploaded_feedback_pdfs(session_id: Optional[str], limit: int = 3) -> list[dict]:
    """Find PDFs uploaded via the Nami-only feedback area.

    These uploads are intentionally exposed only to server-recognized Nami
    sessions. Other visitors only see PDFs tied to their explicit ticker
    history through _get_recent_tickers().
    """
    if not session_id or not _is_nami_session(session_id):
        return []

    from pathlib import Path
    analyses_dir = Path(__file__).resolve().parent.parent / "analyses"
    if not analyses_dir.exists():
        return []

    results = []
    for fb_dir in sorted(analyses_dir.glob("feedback_*"), key=lambda d: d.stat().st_mtime, reverse=True):
        ticker = fb_dir.name.replace("feedback_", "").upper()
        pdfs = list(fb_dir.glob("*.pdf"))
        if pdfs:
            from datetime import datetime
            mtime = fb_dir.stat().st_mtime
            results.append({
                "ticker": ticker,
                "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                "pdfs": [p.name for p in sorted(pdfs, key=lambda p: p.stat().st_mtime, reverse=True)[:4]],
                "_source": "uploaded",
            })
        if len(results) >= limit:
            break
    return results


_TICKER_BLACKLIST = {"ZZZZ", "FAIL", "TEST", "NVDQ", "NBUS", "NBIS", "EEM", "MC", "SNDK"}
