"""SQLite storage for chat sessions, messages, PDF documents, and events.

Auto-creates tables on first use. Uses WAL mode for concurrent reads.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .chat_models import ChatMessage, ChatSession

DB_PATH = Path(__file__).resolve().parent.parent / "chat.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── Connection Management ────────────────────────────────────────────────────

_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _init_tables(_conn)
    return _conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id              TEXT PRIMARY KEY,
            visitor_name    TEXT NOT NULL DEFAULT 'Nami',
            language        TEXT NOT NULL DEFAULT 'ja',
            status          TEXT NOT NULL DEFAULT 'active',
            current_ticker  TEXT,
            current_pdf_id  TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            last_seen_at    TEXT,
            metadata_json   TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            role              TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
            content           TEXT NOT NULL DEFAULT '',
            language          TEXT NOT NULL DEFAULT 'ja',
            ticker            TEXT,
            pdf_id            TEXT,
            status            TEXT NOT NULL DEFAULT 'pending'
                              CHECK(status IN ('pending','processing','completed','failed')),
            parent_message_id TEXT,
            idempotency_key   TEXT,
            metadata_json     TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS pdf_documents (
            id            TEXT PRIMARY KEY,
            ticker        TEXT NOT NULL,
            title         TEXT NOT NULL,
            report_date   TEXT,
            source_path   TEXT,
            sha256        TEXT,
            summary       TEXT,
            metadata_json TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pdf_chunks (
            id             TEXT PRIMARY KEY,
            pdf_id         TEXT NOT NULL,
            ticker         TEXT NOT NULL,
            chunk_index    INTEGER NOT NULL,
            page_start     INTEGER,
            page_end       INTEGER,
            section_title  TEXT,
            content        TEXT NOT NULL,
            embedding_json TEXT,
            metadata_json  TEXT,
            created_at     TEXT NOT NULL,
            FOREIGN KEY (pdf_id) REFERENCES pdf_documents(id)
        );

        CREATE TABLE IF NOT EXISTS chat_events (
            id           TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            event_type   TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS chat_feedback (
            id            TEXT PRIMARY KEY,
            session_id    TEXT NOT NULL,
            message_id    TEXT,
            feedback_type TEXT NOT NULL
                          CHECK(feedback_type IN ('bug','ux','correction','misunderstanding','feature_request','other')),
            content       TEXT NOT NULL DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'open',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON chat_messages(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_messages_status
            ON chat_messages(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_updated
            ON chat_sessions(updated_at);
        CREATE INDEX IF NOT EXISTS idx_pdf_ticker
            ON pdf_documents(ticker);
        CREATE INDEX IF NOT EXISTS idx_chunks_pdf
            ON pdf_chunks(pdf_id, chunk_index);
        CREATE INDEX IF NOT EXISTS idx_chunks_ticker
            ON pdf_chunks(ticker);
        CREATE INDEX IF NOT EXISTS idx_feedback_status
            ON chat_feedback(status, created_at);

        -- FTS5 for PDF chunk search
        CREATE VIRTUAL TABLE IF NOT EXISTS pdf_chunks_fts USING fts5(
            content,
            section_title,
            content=pdf_chunks,
            content_rowid=rowid
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS pdf_chunks_ai AFTER INSERT ON pdf_chunks BEGIN
            INSERT INTO pdf_chunks_fts(rowid, content, section_title)
            VALUES (new.rowid, new.content, new.section_title);
        END;

        CREATE TRIGGER IF NOT EXISTS pdf_chunks_ad AFTER DELETE ON pdf_chunks BEGIN
            INSERT INTO pdf_chunks_fts(pdf_chunks_fts, rowid, content, section_title)
            VALUES ('delete', old.rowid, old.content, old.section_title);
        END;

        CREATE TRIGGER IF NOT EXISTS pdf_chunks_au AFTER UPDATE ON pdf_chunks BEGIN
            INSERT INTO pdf_chunks_fts(pdf_chunks_fts, rowid, content, section_title)
            VALUES ('delete', old.rowid, old.content, old.section_title);
            INSERT INTO pdf_chunks_fts(rowid, content, section_title)
            VALUES (new.rowid, new.content, new.section_title);
        END;
    """)
    conn.commit()


# ── Session Operations ───────────────────────────────────────────────────────

def create_session(
    visitor_name: str = "Nami",
    language: str = "ja",
    metadata: Optional[dict] = None,
) -> ChatSession:
    conn = get_conn()
    sid = _uid("sess")
    now = _utcnow_iso()
    meta_json = json.dumps(metadata) if metadata else None
    conn.execute(
        """INSERT INTO chat_sessions (id, visitor_name, language, created_at, updated_at, last_seen_at, metadata_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sid, visitor_name, language, now, now, now, meta_json),
    )
    conn.commit()
    return ChatSession(
        id=sid, visitor_name=visitor_name, language=language,
        created_at=now, updated_at=now, last_seen_at=now,
        metadata_json=meta_json,
    )


def get_session(session_id: str) -> Optional[ChatSession]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    return ChatSession(**dict(row))


def update_session(
    session_id: str,
    *,
    language: Optional[str] = None,
    current_ticker: Optional[str] = None,
    current_pdf_id: Optional[str] = None,
    last_seen_at: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    conn = get_conn()
    now = _utcnow_iso()
    parts = []
    params = []
    if language is not None:
        parts.append("language = ?"); params.append(language)
    if current_ticker is not None:
        parts.append("current_ticker = ?"); params.append(current_ticker)
    if current_pdf_id is not None:
        parts.append("current_pdf_id = ?"); params.append(current_pdf_id)
    if last_seen_at is not None:
        parts.append("last_seen_at = ?"); params.append(last_seen_at)
    if status is not None:
        parts.append("status = ?"); params.append(status)
    parts.append("updated_at = ?"); params.append(now)
    params.append(session_id)
    conn.execute(f"UPDATE chat_sessions SET {', '.join(parts)} WHERE id = ?", params)
    conn.commit()


def track_session_ticker(session_id: str, ticker: str) -> None:
    """Record that this session viewed/analyzed a ticker. Stored in metadata_json."""
    conn = get_conn()
    row = conn.execute(
        "SELECT metadata_json FROM chat_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not row:
        return

    meta = json.loads(row[0]) if row[0] else {}
    viewed = meta.get("viewed_tickers", [])
    if ticker not in viewed:
        viewed.append(ticker)
        # Keep last 10
        if len(viewed) > 10:
            viewed = viewed[-10:]
        meta["viewed_tickers"] = viewed
        conn.execute(
            "UPDATE chat_sessions SET metadata_json=?, updated_at=? WHERE id=?",
            (json.dumps(meta), _utcnow_iso(), session_id),
        )
        conn.commit()


def get_session_tickers(session_id: str) -> list[str]:
    """Get tickers this session has viewed, most recent last."""
    conn = get_conn()
    row = conn.execute(
        "SELECT metadata_json FROM chat_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not row or not row[0]:
        return []
    meta = json.loads(row[0]) if row[0] else {}
    return meta.get("viewed_tickers", [])


# ── Message Operations ───────────────────────────────────────────────────────

def save_message(msg: ChatMessage) -> ChatMessage:
    conn = get_conn()
    conn.execute(
        """INSERT INTO chat_messages
           (id, session_id, role, content, language, ticker, pdf_id, status,
            parent_message_id, idempotency_key, metadata_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             content=excluded.content, status=excluded.status,
             updated_at=excluded.updated_at""",
        (
            msg.id, msg.session_id, msg.role, msg.content, msg.language,
            msg.ticker, msg.pdf_id, msg.status,
            msg.parent_message_id, msg.idempotency_key, msg.metadata_json,
            msg.created_at, msg.updated_at,
        ),
    )
    conn.commit()
    return msg


def get_message(message_id: str) -> Optional[ChatMessage]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        return None
    return ChatMessage(**dict(row))


def get_history(session_id: str, limit: int = 50) -> list[ChatMessage]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM chat_messages WHERE session_id = ?
           ORDER BY created_at ASC LIMIT ?""",
        (session_id, limit),
    ).fetchall()
    return [ChatMessage(**dict(r)) for r in rows]


def get_recent_messages(session_id: str, limit: int = 20) -> list[ChatMessage]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM chat_messages WHERE session_id = ? AND role IN ('user','assistant')
           ORDER BY created_at DESC LIMIT ?""",
        (session_id, limit),
    ).fetchall()
    rows.reverse()
    return [ChatMessage(**dict(r)) for r in rows]


def find_by_idempotency_key(key: str) -> Optional[ChatMessage]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM chat_messages WHERE idempotency_key = ?", (key,)
    ).fetchone()
    if not row:
        return None
    return ChatMessage(**dict(row))


def get_stuck_messages(minutes: int = 5) -> list[ChatMessage]:
    """Find messages stuck in 'processing' state for too long (for fallback cron)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM chat_messages
           WHERE status = 'processing'
             AND datetime(created_at) < datetime('now', ?)
           ORDER BY created_at ASC""",
        (f'-{minutes} minutes',),
    ).fetchall()
    return [ChatMessage(**dict(r)) for r in rows]


def update_message(
    message_id: str,
    *,
    content: str | None = None,
    status: str | None = None,
    updated_at: str | None = None,
) -> None:
    """Update message content and/or status."""
    conn = get_conn()
    now = updated_at or _utcnow_iso()
    parts = []
    params: list = []
    if content is not None:
        parts.append("content = ?"); params.append(content)
    if status is not None:
        parts.append("status = ?"); params.append(status)
    parts.append("updated_at = ?"); params.append(now)
    params.append(message_id)
    conn.execute(f"UPDATE chat_messages SET {', '.join(parts)} WHERE id = ?", params)
    conn.commit()


def update_message_status(message_id: str, status: str) -> None:
    """Shortcut: update only the status field."""
    update_message(message_id, status=status)


# ── PDF Operations ───────────────────────────────────────────────────────────

def upsert_pdf_document(
    pdf_id: str,
    ticker: str,
    title: str,
    *,
    report_date: Optional[str] = None,
    source_path: Optional[str] = None,
    sha256: Optional[str] = None,
    summary: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    conn = get_conn()
    now = _utcnow_iso()
    meta_json = json.dumps(metadata) if metadata else None
    conn.execute(
        """INSERT INTO pdf_documents (id, ticker, title, report_date, source_path, sha256, summary, metadata_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             title=excluded.title, summary=excluded.summary,
             updated_at=excluded.updated_at""",
        (pdf_id, ticker, title, report_date, source_path, sha256, summary, meta_json, now, now),
    )
    conn.commit()
    return pdf_id


def upsert_pdf_chunk(
    pdf_id: str,
    ticker: str,
    chunk_index: int,
    content: str,
    *,
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    section_title: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    conn = get_conn()
    now = _utcnow_iso()
    cid = _uid("chunk")
    meta_json = json.dumps(metadata) if metadata else None
    conn.execute(
        """INSERT INTO pdf_chunks (id, pdf_id, ticker, chunk_index, page_start, page_end, section_title, content, metadata_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             content=excluded.content, section_title=excluded.section_title,
             page_start=excluded.page_start, page_end=excluded.page_end""",
        (cid, pdf_id, ticker, chunk_index, page_start, page_end, section_title, content, meta_json, now),
    )
    conn.commit()
    return cid


def clear_pdf_chunks(pdf_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM pdf_chunks WHERE pdf_id = ?", (pdf_id,))
    conn.commit()


def search_pdf_chunks(query: str, ticker: Optional[str] = None, pdf_id: Optional[str] = None, limit: int = 5) -> list[dict]:
    """FTS5 search across PDF chunks. Returns relevant passages with page/section info."""
    conn = get_conn()
    conditions = ["pdf_chunks_fts MATCH ?"]
    params: list = [query]
    if ticker:
        conditions.append("pdf_chunks.ticker = ?")
        params.append(ticker)
    if pdf_id:
        conditions.append("pdf_chunks.pdf_id = ?")
        params.append(pdf_id)
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT pdf_chunks.content, pdf_chunks.section_title, pdf_chunks.page_start,
                   pdf_chunks.page_end, pdf_chunks.ticker, pdf_chunks.pdf_id,
                   snippet(pdf_chunks_fts, 1, '<b>', '</b>', '…', 64) AS snippet
            FROM pdf_chunks_fts
            JOIN pdf_chunks ON pdf_chunks_fts.rowid = pdf_chunks.rowid
            WHERE {where}
            ORDER BY rank
            LIMIT ?""",
        (*params, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pdf_summary(pdf_id: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT summary FROM pdf_documents WHERE id = ?", (pdf_id,)).fetchone()
    return row["summary"] if row else None


# ── Event Operations ─────────────────────────────────────────────────────────

def log_event(session_id: str, event_type: str, payload: dict) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO chat_events (id, session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (_uid("evt"), session_id, event_type, json.dumps(payload), _utcnow_iso()),
    )
    conn.commit()


# ── Feedback Operations ──────────────────────────────────────────────────────

def save_chat_feedback(
    session_id: str,
    feedback_type: str,
    content: str,
    message_id: Optional[str] = None,
) -> str:
    conn = get_conn()
    fid = _uid("cfb")
    now = _utcnow_iso()
    conn.execute(
        """INSERT INTO chat_feedback (id, session_id, message_id, feedback_type, content, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
        (fid, session_id, message_id, feedback_type, content, now, now),
    )
    conn.commit()
    return fid


def export_session(session_id: str) -> Optional[str]:
    """Export a chat session as formatted text. Returns the text or None."""
    conn = get_conn()
    session = conn.execute(
        "SELECT visitor_name, language, current_ticker, created_at FROM chat_sessions WHERE id=?",
        (session_id,),
    ).fetchone()
    if not session:
        return None

    messages = conn.execute(
        "SELECT role, content, language, ticker, created_at FROM chat_messages "
        "WHERE session_id=? AND status IN ('completed','processing') ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    feedbacks = conn.execute(
        "SELECT feedback_type, content, status, created_at FROM chat_feedback "
        "WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    lines = []
    lines.append("=" * 60)
    lines.append(f"CHAT SESSION: {session_id}")
    lines.append(f"Visitor: {session[0]}  |  Language: {session[1]}  |  Ticker: {session[2] or 'N/A'}")
    lines.append(f"Started: {session[3]}")
    lines.append(f"Messages: {len(messages)}  |  Feedback items: {len(feedbacks)}")
    lines.append("=" * 60)
    lines.append("")

    for msg in messages:
        role_label = "🧑 Nami" if msg[0] == "user" else "🤖 Assistant"
        ticker_tag = f" [{msg[3]}]" if msg[3] else ""
        lines.append(f"{role_label}{ticker_tag} — {msg[4][:19]}")
        lines.append("-" * 40)
        lines.append(msg[1])
        lines.append("")

    if feedbacks:
        lines.append("=" * 60)
        lines.append("DETECTED FEEDBACK")
        lines.append("=" * 60)
        for fb in feedbacks:
            lines.append(f"  [{fb[0]}] ({fb[2]}) {fb[1][:200]}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("END OF SESSION")
    lines.append("=" * 60)

    return "\n".join(lines)


def close_session(session_id: str) -> bool:
    """Mark a session as closed."""
    conn = get_conn()
    conn.execute(
        "UPDATE chat_sessions SET status='closed', updated_at=? WHERE id=?",
        (_utcnow_iso(), session_id),
    )
    conn.commit()
    return conn.total_changes > 0


def get_recent_feedback_for_context(visitor_name: str = "Nami", limit: int = 10) -> list[dict]:
    """Get recent feedback items for chat context.

    Pulls from both chat_feedback (auto-detected) and the JSON feedback_store.
    Returns a list of {type, content, status, date, ticker} for the AI prompt.
    """
    conn = get_conn()
    items = []

    # 1. Chat feedback (auto-detected)
    rows = conn.execute(
        """SELECT cf.feedback_type, cf.content, cf.status, cf.created_at,
                  cs.current_ticker
           FROM chat_feedback cf
           JOIN chat_sessions cs ON cf.session_id = cs.id
           WHERE cs.visitor_name = ?
           ORDER BY cf.created_at DESC
           LIMIT ?""",
        (visitor_name, limit),
    ).fetchall()

    for r in rows:
        items.append({
            "source": "chat",
            "type": r[0],
            "content": r[1][:200],
            "status": r[2],
            "date": (r[3] or "")[:10],
            "ticker": r[4],
        })

    # 2. Form feedback (JSON feedback_store) — try to load
    try:
        from . import feedback_store
        all_fb = feedback_store.list_all_feedback()
        for fb in all_fb[-limit:]:
            files = fb.get("files", [])
            content = (fb.get("text") or "")[:200]
            if files:
                content += f" [attached: {', '.join(f[:50] for f in files[:3])}]"
            items.append({
                "source": "form",
                "type": fb.get("category", "other"),
                "content": content,
                "status": fb.get("status", "pending"),
                "date": (fb.get("created_at") or "")[:10],
                "ticker": fb.get("ticker"),
            })
    except Exception:
        pass  # feedback_store may not be available

    # Sort by date, most recent first, deduplicate by content
    seen = set()
    unique = []
    for item in sorted(items, key=lambda x: x["date"], reverse=True):
        key = item["content"][:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:limit]


# ── Init ─────────────────────────────────────────────────────────────────────

def initialize() -> None:
    """Call at backend startup to ensure DB and tables exist."""
    get_conn()
