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
    "before we continue",
    "press & hold",
    "please verify you are a human",
    "verify you are human",
    "enable cookies",
    "captcha",
    "sign in",
)
AUTH_COOKIE_NAMES = {
    "slireg",
    "user_id",
    "user_nick",
    "remember_user_token",
    "gk_user_access",
    "gk_user_access_sign",
    "session_id",
}
ANTIBOT_COOKIE_NAMES = {"pxcts", "_px3", "_pxvid", "cf_clearance"}

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


def _cookie_names(header: str) -> set[str]:
    names: set[str] = set()
    for part in (header or "").split(";"):
        if "=" not in part:
            continue
        name = part.split("=", 1)[0].strip()
        if name:
            names.add(name)
    return names


def _cookie_diagnostics(header: str) -> dict[str, Any]:
    names = _cookie_names(header)
    has_auth_cookie = bool(names & AUTH_COOKIE_NAMES)
    has_antibot_cookie = bool(names & ANTIBOT_COOKIE_NAMES)
    configured = bool(header)

    if not configured:
        quality = "not_configured"
    elif not has_auth_cookie and not has_antibot_cookie:
        quality = "analytics_only_or_incomplete"
    elif not has_auth_cookie:
        quality = "missing_auth_cookie"
    elif not has_antibot_cookie:
        quality = "missing_antibot_cookie"
    else:
        quality = "browser_session_like"

    return {
        "quality": quality,
        "has_auth_cookie": has_auth_cookie,
        "has_antibot_cookie": has_antibot_cookie,
        "required_categories": ["auth", "antibot"],
    }


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
        "cookie_diagnostics": _cookie_diagnostics(cookie_header),
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
    # Preserve cookies_parsed if already present (from Netscape import)
    if existing.get("cookies_parsed"):
        payload["cookies_parsed"] = existing["cookies_parsed"]
    _write_store(payload)
    logger.info("Seeking Alpha cookies saved server-side (%s cookies)", _cookie_count(normalized))
    return get_access_status()


def import_netscape_cookies(file_path: str | Path) -> dict[str, Any]:
    """Import cookies from a Netscape-format cookie file (browser export).
    
    Parses the tab-separated format preserving per-cookie domain/path,
    which is critical for Seeking Alpha PerimeterX bypass via Playwright.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Cookie file not found: {file_path}")
    
    lines = path.read_text().splitlines()
    cookies_parsed: list[dict[str, str]] = []
    cookie_parts: list[str] = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) >= 2:
            name = parts[0].strip()
            value = parts[1].strip()
            if name and value:
                domain = parts[2].strip() if len(parts) > 2 else "seekingalpha.com"
                path = parts[3].strip() if len(parts) > 3 else "/"
                cookies_parsed.append({
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path,
                })
                cookie_parts.append(f"{name}={value}")
    
    if not cookie_parts:
        raise ValueError("No valid cookies found in Netscape file")
    
    cookie_header = "; ".join(cookie_parts)
    existing = _read_store()
    payload = {
        "cookie_header": cookie_header,
        "cookies_parsed": cookies_parsed,
        "user_agent": existing.get("user_agent") or DEFAULT_USER_AGENT,
        "created_at": existing.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
    }
    _write_store(payload)
    logger.info(
        "Imported %d Seeking Alpha cookies from Netscape file (%d with domain info)",
        len(cookies_parsed), sum(1 for c in cookies_parsed if c.get("domain")),
    )
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


async def probe_access_async(ticker: str | None = None) -> dict[str, Any]:
    """Validate stored Seeking Alpha cookies via Playwright Firefox.

    Uses the same Firefox + per-cookie-domain approach as the transcript pipeline.
    Navigates to the transcript listing, checks for PerimeterX, and if successful
    extracts the first article link as proof of authenticated access.
    """
    import asyncio

    status = get_access_status()
    clean_ticker = re.sub(r"[^A-Z0-9.]", "", (ticker or DEFAULT_TEST_TICKER).upper()) or DEFAULT_TEST_TICKER
    listing_url = f"https://seekingalpha.com/symbol/{clean_ticker}/earnings/transcripts"

    if not status["configured"]:
        return {
            **status, "ok": False, "authenticated": False, "reachable": False,
            "ticker": clean_ticker, "url": listing_url,
            "reason": "no_cookies_configured", "tested_at": _now_iso(),
        }

    cookie_quality = status.get("cookie_diagnostics", {}).get("quality")
    if cookie_quality == "analytics_only_or_incomplete":
        return {
            **status, "ok": False, "authenticated": False, "reachable": False,
            "ticker": clean_ticker, "url": listing_url, "status_code": 403,
            "reason": "missing_auth_or_antibot_cookies", "text_length": 0, "tested_at": _now_iso(),
        }

    try:
        store = _read_store()
        pw_cookies: list[dict[str, str]] = []
        cookies_parsed = store.get("cookies_parsed")
        if cookies_parsed:
            for c in cookies_parsed:
                pw_cookies.append({
                    "name": c["name"], "value": c["value"],
                    "domain": c.get("domain", ".seekingalpha.com"),
                    "path": c.get("path", "/"),
                })
        else:
            cookie_header = store.get("cookie_header", "")
            for part in cookie_header.split(";"):
                part = part.strip()
                if "=" in part:
                    name, value = part.split("=", 1)
                    pw_cookies.append({
                        "name": name.strip(), "value": value.strip(),
                        "domain": ".seekingalpha.com", "path": "/",
                    })

        user_agent = store.get("user_agent") or DEFAULT_USER_AGENT

        from playwright.sync_api import sync_playwright

        def _run_probe() -> dict[str, Any]:
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                context = browser.new_context(
                    user_agent=user_agent,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                context.add_cookies(pw_cookies)
                page = context.new_page()

                page.goto(listing_url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)

                body_text = page.inner_text("body")[:800].lower()
                blocked = any(m in body_text for m in DENIED_MARKERS)

                if blocked:
                    browser.close()
                    return {
                        "authenticated": False, "reachable": True, "blocked": True,
                        "url": listing_url, "status_code": 403,
                        "reason": "blocked_by_perimeterx", "text_length": 0,
                    }

                # Find first article link
                links = page.query_selector_all('a[href*="/article/"]')
                article_url = ""
                text_length = 0
                if links:
                    first_href = links[0].get_attribute("href")
                    if first_href:
                        if first_href.startswith("/"):
                            article_url = "https://seekingalpha.com" + first_href
                        else:
                            article_url = first_href

                if article_url:
                    page.goto(article_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(5000)
                    article_body = page.inner_text("body")
                    text_length = len(article_body)

                browser.close()

                authenticated = bool(article_url) and "seekingalpha.com/article/" in article_url
                return {
                    "authenticated": authenticated, "reachable": True, "blocked": False,
                    "url": article_url or listing_url,
                    "status_code": 200 if authenticated else 200,
                    "reason": "ok" if authenticated else "no_article_link_found",
                    "text_length": text_length,
                }

        probe_result = await asyncio.to_thread(_run_probe)
        return {**status, "ok": probe_result["authenticated"], **probe_result, "tested_at": _now_iso()}

    except Exception as exc:
        logger.warning("Seeking Alpha probe failed for %s: %s", clean_ticker, exc)
        return {
            **status, "ok": False, "authenticated": False, "reachable": False,
            "ticker": clean_ticker, "url": listing_url,
            "reason": "request_error", "error": str(exc), "tested_at": _now_iso(),
        }
