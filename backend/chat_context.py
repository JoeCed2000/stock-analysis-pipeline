"""Context builder for the chat AI.

Assembles session info, ticker context, PDF chunks, history,
and UI state into a structured context object for the AI prompt.
"""

from __future__ import annotations

from typing import Optional

import logging

logger = logging.getLogger(__name__)


def _detect_visitor_name(session_id: str) -> str:
    """Detect visitor display name from session fingerprint (IP + device).

    Used for personalized AI greetings during the fingerprint→visitor_id transition.
    Once CHAT-HARDEN (t_8e1f1cdd) ships, visitor_id replaces this heuristic.
    """
    from . import chat_store
    import json

    try:
        session = chat_store.get_session(session_id)
        if not session or not session.metadata_json:
            return "Nami"
        meta = json.loads(session.metadata_json)
        device = meta.get("device", "")
        client_ip = meta.get("client_ip", "")

        # Ced: France IP + Linux Chrome
        if device == "linux-chrome":
            return "Cédric"

        # Nami: US IP + Mac Safari
        if device == "apple-mac-safari":
            return "Nami"

        return "Nami"
    except Exception:
        return "Nami"


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
    language: str = "ja",
) -> dict:
    """Build the full context dict for an AI response.

    Returns a dict with all keys needed by chat_ai.stream_ai_response().
    """
    from . import chat_store, chat_retrieval

    # Get session info
    session = chat_store.get_session(session_id)
    if session:
        # Update session with latest context
        chat_store.update_session(
            session_id,
            current_ticker=ticker or session.current_ticker,
            current_pdf_id=pdf_id or session.current_pdf_id,
            language=language,
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
        "language": language,
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
        "feedback_context": _get_feedback_context(),
        "previous_chats": _get_previous_chat_summaries(session_id),
    }


def _get_previous_chat_summaries(session_id: str) -> list[dict]:
    """Get summaries of previous chat sessions from the same user (IP+device)."""
    from . import chat_store
    try:
        return chat_store.get_recent_chat_summaries(session_id, max_sessions=3, max_age_hours=24)
    except Exception:
        return []


def _get_feedback_context() -> list[dict]:
    """Get recent feedback for the chat AI context."""
    from . import chat_store
    try:
        return chat_store.get_recent_feedback_for_context(limit=8)
    except Exception:
        return []


def _get_recent_tickers(
    session_id: Optional[str] = None,
    limit: int = 5,
    exclude_ticker: Optional[str] = None,
) -> list[dict]:
    """Get tickers this session has viewed, with their available PDFs.

    Uses the session's ticker history (NOT the global analyses/ directory)
    so Nami only sees her own tickers, not Ced's.
    """
    from pathlib import Path

    # Get tickers from session history
    tickers: list[str] = []
    if session_id:
        from . import chat_store
        tickers = chat_store.get_session_tickers(session_id, max_age_hours=2)

    if not tickers:
        return []

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

    # Also include uploaded PDFs from feedback directories
    feedback_uploads = _get_uploaded_feedback_pdfs(session_id, limit=3)
    for fu in feedback_uploads:
        if fu["ticker"] not in seen:
            result.append(fu)

    return result[:limit]


def _get_uploaded_feedback_pdfs(session_id: Optional[str], limit: int = 3) -> list[dict]:
    """Find PDFs uploaded via feedback that belong to this session's tickers."""
    from pathlib import Path
    analyses_dir = Path(__file__).resolve().parent.parent / "analyses"
    if not analyses_dir.exists():
        return []

    # Get tickers for this session
    tickers = set()
    if session_id:
        from . import chat_store
        tickers = set(chat_store.get_session_tickers(session_id, max_age_hours=24))

    results = []
    for fb_dir in sorted(analyses_dir.glob("feedback_*"), key=lambda d: d.stat().st_mtime, reverse=True):
        ticker = fb_dir.name.replace("feedback_", "").upper()
        if tickers and ticker not in tickers:
            continue
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
