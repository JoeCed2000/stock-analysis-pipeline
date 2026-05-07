"""Search traceability — JSONL append logger.

Near-real-time: appends one JSON line per search event.
Frontend polls the /api/admin/recent-searches endpoint every 5s.
"""
from pathlib import Path
import json
import time
from datetime import datetime, timezone


def log_search(
    ticker: str,
    status: str,  # "started" | "completed" | "failed"
    duration_ms: float = 0.0,
    cache_hit: bool = False,
    user_agent: str = "",
    client_ip: str = "",
    error: str = "",
):
    """Append a search event to the JSONL log file AND SQLite (dual write)."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "searches.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker.upper(),
        "status": status,
        "duration_ms": round(duration_ms),
        "cache_hit": cache_hit,
        "user_agent": user_agent[:200] if user_agent else "",
        "client_ip": client_ip[:45] if client_ip else "",
        "error": error[:500] if error else "",
    }

    # JSONL (durable, append-only)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # SQLite (queryable, for stats & admin dashboard)
    try:
        from backend.search_db import log_search_sqlite
        log_search_sqlite(ticker, status, duration_ms, cache_hit, user_agent, client_ip, error)
    except Exception:
        pass  # SQLite failure must never block JSONL write


def read_recent(limit: int = 50, status_filter: str = "all") -> list:
    """Read the last N search events from the JSONL file."""
    log_path = Path(__file__).parent / "logs" / "searches.jsonl"
    if not log_path.exists():
        return []

    lines = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if status_filter != "all" and entry.get("status") != status_filter:
                    continue
                lines.append(entry)
            except json.JSONDecodeError:
                continue  # skip corrupted lines

    # Return last N, newest first
    return lines[-limit:][::-1]
