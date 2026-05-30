"""Pydantic models for the live chat widget."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


# ── Request Models ──────────────────────────────────────────────────────────

class ChatSessionRequest(BaseModel):
    visitor_name: str = "Nami"
    language: str = "ja"
    metadata: dict = Field(default_factory=dict)


class ChatContextPayload(BaseModel):
    current_url: Optional[str] = None
    route: Optional[str] = None
    ticker: Optional[str] = None
    pdf_id: Optional[str] = None
    pdf_title: Optional[str] = None
    pdf_page: Optional[int] = None
    selected_section: Optional[str] = None
    selected_text: Optional[str] = None
    client_language: str = "ja"
    viewport_width: Optional[int] = None
    viewport_height: Optional[int] = None


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    idempotency_key: Optional[str] = None
    context: ChatContextPayload = Field(default_factory=ChatContextPayload)


# ── Response Models ──────────────────────────────────────────────────────────

class ChatSessionResponse(BaseModel):
    session_id: str
    language: str
    visitor_name: str


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    language: str
    ticker: Optional[str] = None
    pdf_id: Optional[str] = None
    status: str
    created_at: str
    updated_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]


class ChatSendResponse(BaseModel):
    user_message_id: str
    assistant_message_id: str
    status: str  # "processing"


# ── DB Row Models (internal) ─────────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatSession:
    def __init__(
        self,
        id: str,
        visitor_name: str = "Nami",
        language: str = "ja",
        status: str = "active",
        current_ticker: Optional[str] = None,
        current_pdf_id: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        last_seen_at: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ):
        self.id = id
        self.visitor_name = visitor_name
        self.language = language
        self.status = status
        self.current_ticker = current_ticker
        self.current_pdf_id = current_pdf_id
        self.created_at = created_at or _utcnow_iso()
        self.updated_at = updated_at or _utcnow_iso()
        self.last_seen_at = last_seen_at
        self.metadata_json = metadata_json


class ChatMessage:
    def __init__(
        self,
        id: str,
        session_id: str,
        role: str,
        content: str = "",
        language: str = "ja",
        ticker: Optional[str] = None,
        pdf_id: Optional[str] = None,
        status: str = "pending",
        parent_message_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata_json: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.id = id
        self.session_id = session_id
        self.role = role
        self.content = content
        self.language = language
        self.ticker = ticker
        self.pdf_id = pdf_id
        self.status = status
        self.parent_message_id = parent_message_id
        self.idempotency_key = idempotency_key
        self.metadata_json = metadata_json
        self.created_at = created_at or _utcnow_iso()
        self.updated_at = updated_at or _utcnow_iso()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "language": self.language,
            "ticker": self.ticker,
            "pdf_id": self.pdf_id,
            "status": self.status,
            "parent_message_id": self.parent_message_id,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
