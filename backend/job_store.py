"""In-memory job store for async analysis. Thread-safe, auto-cleanup after 1h."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, Optional, List


_store: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_MAX_AGE_SECONDS = 3600  # 1 hour


def _cleanup_expired() -> None:
    now = time.time()
    with _lock:
        expired = [jid for jid, job in _store.items()
                   if now - job.get("created_at", 0) > _MAX_AGE_SECONDS]
        for jid in expired:
            del _store[jid]


def create_job(tickers: List[str], language: str = "en") -> str:
    _cleanup_expired()
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _store[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "tickers": tickers,
            "language": language,
            "progress": f"Queued {len(tickers)} ticker(s)",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    _cleanup_expired()
    with _lock:
        return _store.get(job_id)


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _store:
            _store[job_id].update(kwargs)
