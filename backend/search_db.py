"""SQLite-backed search log for queryable traceability.

Writes to SQLite in parallel with JSONL (search_logger.py).
The admin dashboard reads from SQLite for stats and filtering.
"""
import sqlite3
import os
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
            error TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_timestamp ON searches(timestamp DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_ticker ON searches(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_searches_status ON searches(status)")
    conn.commit()
    conn.close()


def log_search_sqlite(
    ticker: str,
    status: str,
    duration_ms: float = 0.0,
    cache_hit: bool = False,
    user_agent: str = "",
    error: str = "",
):
    """Insert a search event into SQLite."""
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO searches (timestamp, ticker, status, duration_ms, cache_hit, user_agent, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            ticker.upper(),
            status,
            round(duration_ms),
            1 if cache_hit else 0,
            user_agent[:200] if user_agent else "",
            error[:500] if error else "",
        ),
    )
    conn.commit()
    conn.close()


def read_recent_sqlite(limit: int = 50, status_filter: str = "all") -> list:
    """Read recent searches from SQLite, newest first."""
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    if status_filter == "all":
        rows = conn.execute(
            "SELECT timestamp, ticker, status, duration_ms, cache_hit, user_agent, error FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT timestamp, ticker, status, duration_ms, cache_hit, user_agent, error FROM searches WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status_filter, limit),
        ).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Return aggregate stats for the admin dashboard."""
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    total = conn.execute("SELECT COUNT(*) as n FROM searches").fetchone()["n"]
    
    if total == 0:
        conn.close()
        return {
            "total": 0, "success_rate": 0, "avg_duration_ms": 0,
            "top_tickers": [], "recent_errors": [], "last_24h": 0,
        }
    
    completed = conn.execute("SELECT COUNT(*) as n FROM searches WHERE status='completed'").fetchone()["n"]
    avg_dur = conn.execute("SELECT AVG(duration_ms) as n FROM searches WHERE status='completed' AND duration_ms > 0").fetchone()["n"] or 0
    
    top_tickers = conn.execute(
        "SELECT ticker, COUNT(*) as cnt FROM searches GROUP BY ticker ORDER BY cnt DESC LIMIT 10"
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
        "top_tickers": [{"ticker": r["ticker"], "count": r["cnt"]} for r in top_tickers],
        "recent_errors": [dict(r) for r in recent_errors],
        "last_24h": last_24h,
    }
