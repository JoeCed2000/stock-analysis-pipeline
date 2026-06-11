"""SQLite-backed search log for queryable traceability.

Writes to SQLite in parallel with JSONL (search_logger.py).
The admin dashboard reads from SQLite for stats and filtering.
"""
import sqlite3
import os
import json
import re
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone


DB_PATH = Path(__file__).parent / "logs" / "searches.db"


def _ensure_db():
    """Create the searches table if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('started','completed','failed')),
            duration_ms INTEGER DEFAULT 0,
            cache_hit INTEGER DEFAULT 0,
            user_agent TEXT DEFAULT '',
            client_ip TEXT DEFAULT '',
            error TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_timestamp ON searches(timestamp DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_ticker ON searches(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_status ON searches(status)")
    conn.commit()
    conn.close()


def _is_ticker_like(value: str) -> bool:
    """Return True for compact ticker labels, False for exception text pollution."""
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", str(value or "").upper()))


def log_search_sqlite(
    ticker: str,
    status: str,
    duration_ms: float = 0.0,
    cache_hit: bool = False,
    user_agent: str = "",
    client_ip: str = "",
    error: str = "",
):
    """Insert a search event into SQLite."""
    _ensure_db()
    # Add client_ip column if missing (migration from older schema)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("ALTER TABLE searches ADD COLUMN client_ip TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute(
        "INSERT INTO searches (timestamp, ticker, status, duration_ms, cache_hit, user_agent, client_ip, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            ticker.upper(),
            status,
            round(duration_ms),
            1 if cache_hit else 0,
            user_agent[:200] if user_agent else "",
            client_ip[:45] if client_ip else "",
            error[:500] if error else "",
        ),
    )
    conn.commit()
    conn.close()


def _text_filter_matches(value: str, needle: str) -> bool:
    """Case-insensitive substring match for admin text filters."""
    if not needle:
        return True
    return needle.casefold() in str(value or "").casefold()


def _read_recent_jsonl(
    limit: int = 50,
    offset: int = 0,
    status_filter: str = "all",
    user_agent_filter: str = "",
    error_filter: str = "",
) -> list:
    """Fallback reader for the durable JSONL log.

    SQLite is queryable, but JSONL is the append-only source that already has
    production history. If the SQLite file is missing, empty, or temporarily
    corrupt, the admin dashboard must not look empty.
    """
    log_path = DB_PATH.parent / "searches.jsonl"
    if not log_path.exists():
        return []

    rows = []
    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if status_filter != "all" and entry.get("status") != status_filter:
                continue
            if not _text_filter_matches(entry.get("user_agent", ""), user_agent_filter):
                continue
            if not _text_filter_matches(entry.get("error", ""), error_filter):
                continue
            rows.append(entry)

    newest = rows[::-1]
    return newest[offset:offset + limit]


def _stats_from_jsonl() -> dict:
    """Compute admin stats from JSONL when SQLite has no rows."""
    rows = _read_recent_jsonl(limit=100000, offset=0, status_filter="all")
    if not rows:
        return {
            "total": 0, "success_rate": 0, "avg_duration_ms": 0,
            "top_tickers": [], "recent_errors": [], "last_24h": 0,
        }

    total = len(rows)
    completed = [r for r in rows if r.get("status") == "completed"]
    durations = [int(r.get("duration_ms") or 0) for r in completed if int(r.get("duration_ms") or 0) > 0]
    top = Counter(str(r.get("ticker", "")).upper() for r in rows if _is_ticker_like(str(r.get("ticker", ""))))
    recent_errors = [
        {"timestamp": r.get("timestamp", ""), "ticker": r.get("ticker", ""), "error": r.get("error", "")}
        for r in rows
        if r.get("status") == "failed"
    ][:5]

    cutoff = datetime.now(timezone.utc).timestamp() - 24 * 60 * 60
    last_24h = 0
    for row in rows:
        try:
            ts = datetime.fromisoformat(str(row.get("timestamp", "")).replace("Z", "+00:00"))
            if ts.timestamp() > cutoff:
                last_24h += 1
        except ValueError:
            continue

    return {
        "total": total,
        "success_rate": round(len(completed) / total * 100, 1) if total else 0,
        "avg_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
        "top_tickers": [{"ticker": ticker, "count": count} for ticker, count in top.most_common(10)],
        "recent_errors": recent_errors,
        "last_24h": last_24h,
    }


def read_recent_sqlite(
    limit: int = 50,
    offset: int = 0,
    status_filter: str = "all",
    user_agent_filter: str = "",
    error_filter: str = "",
) -> list:
    """Read recent searches from SQLite, newest first.

    Falls back to the append-only JSONL log when SQLite has no rows. This keeps
    the admin dashboard populated even after SQLite reset/recreation while
    preserving SQLite as the primary query store.
    """
    _ensure_db()
    bounded_limit = max(1, min(limit, 200))
    bounded_offset = max(0, offset)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    filters = []
    params = []
    if status_filter != "all":
        filters.append("status = ?")
        params.append(status_filter)
    if user_agent_filter:
        filters.append("LOWER(user_agent) LIKE ?")
        params.append(f"%{user_agent_filter.lower()}%")
    if error_filter:
        filters.append("LOWER(error) LIKE ?")
        params.append(f"%{error_filter.lower()}%")
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    rows = conn.execute(
        f"SELECT timestamp, ticker, status, duration_ms, cache_hit, user_agent, client_ip, error FROM searches {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, bounded_limit, bounded_offset),
    ).fetchall()
    sqlite_total_rows = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]

    conn.close()
    results = [dict(r) for r in rows]
    if results or sqlite_total_rows > 0:
        return results
    return _read_recent_jsonl(
        limit=bounded_limit,
        offset=bounded_offset,
        status_filter=status_filter,
        user_agent_filter=user_agent_filter,
        error_filter=error_filter,
    )


def count_recent_sqlite(status_filter: str = "all", user_agent_filter: str = "", error_filter: str = "") -> int:
    """Count recent searches with the same filters used by read_recent_sqlite."""
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))

    filters = []
    params = []
    if status_filter != "all":
        filters.append("status = ?")
        params.append(status_filter)
    if user_agent_filter:
        filters.append("LOWER(user_agent) LIKE ?")
        params.append(f"%{user_agent_filter.lower()}%")
    if error_filter:
        filters.append("LOWER(error) LIKE ?")
        params.append(f"%{error_filter.lower()}%")
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    count = conn.execute(f"SELECT COUNT(*) FROM searches {where_clause}", tuple(params)).fetchone()[0]
    sqlite_total_rows = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    conn.close()
    if count > 0 or sqlite_total_rows > 0:
        return count
    return len(_read_recent_jsonl(
        limit=100000,
        offset=0,
        status_filter=status_filter,
        user_agent_filter=user_agent_filter,
        error_filter=error_filter,
    ))


def get_stats() -> dict:
    """Return aggregate stats for the admin dashboard.

    SQLite remains the primary query store. If it has no rows, rebuild the
    dashboard stats from the durable JSONL log instead of showing an empty admin
    base.
    """
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    total = conn.execute("SELECT COUNT(*) as n FROM searches").fetchone()["n"]
    
    if total == 0:
        conn.close()
        return _stats_from_jsonl()
    
    completed = conn.execute("SELECT COUNT(*) as n FROM searches WHERE status='completed'").fetchone()["n"]
    avg_dur = conn.execute("SELECT AVG(duration_ms) as n FROM searches WHERE status='completed' AND duration_ms > 0").fetchone()["n"] or 0
    
    top_tickers = conn.execute(
        "SELECT ticker, COUNT(*) as cnt FROM searches WHERE ticker GLOB '[A-Z]*' AND LENGTH(ticker) <= 10 GROUP BY ticker ORDER BY cnt DESC LIMIT 20"
    ).fetchall()
    
    recent_errors = conn.execute(
        "SELECT timestamp, ticker, error FROM searches WHERE status='failed' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    
    last_24h = conn.execute(
        "SELECT COUNT(*) as n FROM searches WHERE timestamp > datetime('now', '-1 day')"
    ).fetchone()["n"]
    
    conn.close()
    
    return {
        "total": total,
        "success_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "avg_duration_ms": round(avg_dur),
        "top_tickers": [
            {"ticker": r["ticker"], "count": r["cnt"]}
            for r in top_tickers
            if _is_ticker_like(r["ticker"])
        ][:10],
        "recent_errors": [dict(r) for r in recent_errors],
        "last_24h": last_24h,
    }
