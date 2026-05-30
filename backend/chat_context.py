"""Context builder for the chat AI.

Assembles session info, ticker context, PDF chunks, history,
and UI state into a structured context object for the AI prompt.
"""

from __future__ import annotations

from typing import Optional

import logging

logger = logging.getLogger(__name__)


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
        "recent_tickers": _get_recent_tickers(session_id=session_id, limit=5, exclude_ticker=ticker),
    }


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
        tickers = chat_store.get_session_tickers(session_id)

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

    return result[:limit]


_TICKER_BLACKLIST = {"ZZZZ", "FAIL", "TEST", "NVDQ", "NBUS", "NBIS", "EEM", "MC", "SNDK"}
