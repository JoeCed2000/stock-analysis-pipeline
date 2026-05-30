"""Context builder for the chat AI.

Assembles session info, ticker context, PDF chunks, history,
and UI state into a structured context object for the AI prompt.
"""

from __future__ import annotations

from typing import Optional

import logging

logger = logging.getLogger(__name__)


def _detect_visitor_name(session_id: str) -> str:
    """Detect visitor display name for personalized AI greeting.

    Priority:
    1. visitor_id (once CHAT-HARDEN t_8e1f1cdd ships) → resolved via metadata
    2. Device fingerprint (current heuristic, pre-visitor_id)
    3. Default: "Nami"
    """
    from . import chat_store
    import json

    try:
        session = chat_store.get_session(session_id)
        if not session:
            return "Nami"

        meta = {}
        if session.metadata_json:
            try:
                meta = json.loads(session.metadata_json)
            except json.JSONDecodeError:
                pass

        # Phase 2 (CHAT-HARDEN): visitor_id-based identity
        visitor_id = None
        try:
            visitor_id = getattr(session, "visitor_id", None)
        except Exception:
            pass
        if not visitor_id:
            visitor_id = meta.get("visitor_id")

        if visitor_id:
            # Check metadata for stored display_name
            name = meta.get("display_name")
            if name:
                return name
            # Fallback: visitor_id → name mapping (expand as needed)
            return "Nami"

        # Phase 1 (current): device fingerprint heuristic
        device = meta.get("device", "")
        if device == "linux-chrome":
            return "Cédric"
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
    """Get recent feedback for the chat AI context, scoped by visitor."""
    from . import chat_store
    try:
        session = chat_store.get_session(session_id)
        if not session or not session.visitor_id:
            return []
        return chat_store.get_recent_feedback_for_context(
            visitor_id=session.visitor_id, limit=8,
        )
    except Exception:
        return []


def _get_recent_tickers(
    session_id: Optional[str] = None,
    limit: int = 5,
    exclude_ticker: Optional[str] = None,
) -> list[dict]:
    """Get tickers this visitor has viewed, with their available PDFs.

    Uses the visitor's ticker history (NOT the global analyses/ directory).
    """
    from pathlib import Path

    # Get tickers from visitor history
    tickers: list[str] = []
    if session_id:
        from . import chat_store
        session = chat_store.get_session(session_id)
        if session and session.visitor_id:
            tickers = chat_store.get_session_tickers(session.visitor_id, max_age_hours=2)

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

    # Get tickers for this visitor
    tickers = set()
    if session_id:
        from . import chat_store
        session = chat_store.get_session(session_id)
        if session and session.visitor_id:
            tickers = set(chat_store.get_session_tickers(session.visitor_id, max_age_hours=24))

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
