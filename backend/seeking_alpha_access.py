"""Server-side Seeking Alpha cookie storage + connectivity probe.

Stores the raw Cookie header on disk so the backend can probe transcript pages
without exposing the value back to the browser/UI.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

from backend.http_client import http
from backend.storage_paths import REPO_ROOT

logger = logging.getLogger(__name__)

ACCESS_FILE_ENV = "SA_SEEKING_ALPHA_ACCESS_FILE"
DEFAULT_TEST_TICKER = "NVDA"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 "
    "StockAnalysisPipeline/1.0"
)
STATE_DIR = REPO_ROOT / ".state"
DENIED_MARKERS = (
    "access to this page has been denied",
    "please verify you are a human",
    "enable cookies",
    "captcha",
    "sign in",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _storage_path() -> Path:
    raw = os.getenv(ACCESS_FILE_ENV)
    if raw:
        candidate = Path(raw).expanduser()
        path = candidate if candidate.is_absolute() else (REPO_ROOT / candidate)
    else:
        path = STATE_DIR / "seeking_alpha_access.json"
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    return path


def _normalize_cookie_header(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Cookie header cannot be empty")
    text = re.sub(r"^cookie\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("\r", "; ").replace("\n", "; ")
    parts = []
    for chunk in text.split(";"):
        item = chunk.strip()
        if not item:
            continue
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        parts.append(f"{name}={value}")
    if not parts:
        raise ValueError("No valid cookies found in the provided header")
    return "; ".join(parts)


def _cookie_count(header: str) -> int:
    try:
        jar = SimpleCookie()
        jar.load(header)
        if jar:
            return len(jar)
    except Exception:
        pass
    return sum(1 for part in header.split(";") if "=" in part)


def _read_store() -> dict[str, Any]:
    path = _storage_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Seeking Alpha access store unreadable: %s", exc)
        return {}


def _write_store(payload: dict[str, Any]) -> None:
    path = _storage_path()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp_path, 0o600)
    except OSError:
        pass
    tmp_path.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_access_status() -> dict[str, Any]:
    payload = _read_store()
    cookie_header = payload.get("cookie_header", "")
    configured = bool(cookie_header)
    return {
        "configured": configured,
        "cookie_count": _cookie_count(cookie_header) if configured else 0,
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "user_agent_configured": bool(payload.get("user_agent")),
        "server_side_only": True,
        "test_ticker_default": DEFAULT_TEST_TICKER,
    }


def save_access(cookie_header: str, user_agent: str | None = None) -> dict[str, Any]:
    normalized = _normalize_cookie_header(cookie_header)
    existing = _read_store()
    payload = {
        "cookie_header": normalized,
        "user_agent": (user_agent or existing.get("user_agent") or DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
        "created_at": existing.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
    }
    _write_store(payload)
    logger.info("Seeking Alpha cookies saved server-side (%s cookies)", _cookie_count(normalized))
    return get_access_status()


def clear_access() -> dict[str, Any]:
    path = _storage_path()
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Seeking Alpha access clear failed: %s", exc)
    logger.info("Seeking Alpha cookies cleared")
    return get_access_status()


def build_request_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    payload = _read_store()
    headers = {
        "User-Agent": payload.get("user_agent") or DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    cookie_header = payload.get("cookie_header", "")
    if cookie_header:
        headers["Cookie"] = cookie_header
    if extra_headers:
        headers.update(extra_headers)
    return headers


def probe_access(ticker: str | None = None) -> dict[str, Any]:
    status = get_access_status()
    clean_ticker = re.sub(r"[^A-Z0-9.]", "", (ticker or DEFAULT_TEST_TICKER).upper()) or DEFAULT_TEST_TICKER
    url = f"https://seekingalpha.com/symbol/{clean_ticker}/earnings/transcripts"

    if not status["configured"]:
        return {
            **status,
            "ok": False,
            "authenticated": False,
            "reachable": False,
            "ticker": clean_ticker,
            "url": url,
            "reason": "no_cookies_configured",
            "tested_at": _now_iso(),
        }

    try:
        response = http.get(url, headers=build_request_headers(), timeout=15, follow_redirects=True)
        body = (response.text or "")[:4000].lower()
        denied = response.status_code in {401, 403} or any(marker in body for marker in DENIED_MARKERS)
        authenticated = response.status_code == 200 and not denied
        return {
            **status,
            "ok": authenticated,
            "authenticated": authenticated,
            "reachable": True,
            "ticker": clean_ticker,
            "url": url,
            "response_url": str(response.url),
            "status_code": response.status_code,
            "reason": "ok" if authenticated else "denied",
            "tested_at": _now_iso(),
        }
    except Exception as exc:
        logger.warning("Seeking Alpha connectivity probe failed for %s: %s", clean_ticker, exc)
        return {
            **status,
            "ok": False,
            "authenticated": False,
            "reachable": False,
            "ticker": clean_ticker,
            "url": url,
            "reason": "request_error",
            "error": str(exc),
            "tested_at": _now_iso(),
        }
