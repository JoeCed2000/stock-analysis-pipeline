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
        "pdf_chunks": pdf_chunks,
        "pdf_summary": pdf_summary,
        "history": history_dicts,
        "current_url": current_url,
        "route": route,
    }
