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

# Long-lived session cookies (expiry ≥ 7 days, often 30+).
# These survive short-lived PerimeterX/analytics rotations and are the
# ones that keep the SA auth working week-over-week. We preserve them
# across HAR imports so a fresh HAR never wipes out a still-valid
# ``slireg`` / ``sa-user-id-v3`` / ``user_remember_token``.
LONG_LIVED_AUTH_COOKIES = frozenset({
    "slireg",                   # SA main auth session (~30d)
    "sa-user-id",               # SA user id v1
    "sa-user-id-v2",            # SA user id v2
    "sa-user-id-v3",            # SA user id v3 (current)
    "user_remember_token",      # SA remember-me (~365d)
    "remember_user_token",      # legacy alias
    "gk_user_access",           # SA gatekeeper role (premium flag)
    "gk_user_access_sign",      # SA gatekeeper signature
    "user_id",                  # legacy user id
    "user_nick",                # SA username
    "user_cookie_key",          # SA cookie key (analytics, but stable)
    "user_locale",              # UI preference
    "user_devices",             # device fingerprint (medium-lived)
    "sapu",                     # SA per-user id
    "sailthru_hid",             # Sailthru visitor id (months)
})

# Medium-lived (1-7 days) cookies — refreshed by re-login but useful.
MEDIUM_LIVED_COOKIES = frozenset({
    "session_id",               # SA session (rotates)
    "pxcts",                    # PerimeterX session token
    "_px3",                     # PerimeterX payload
    "_pxvid",                   # PerimeterX visitor id (longer than pxcts)
    "machine_cookie",           # SA machine fingerprint
    "has_paid_subscription",    # Pro flag (subset of gk_user_access)
    "ever_pro",                 # Pro flag
})

# Short-lived / pure-session. Re-generated every browser launch.
# OK to overwrite on every HAR.
SHORT_LIVED_COOKIES = frozenset({
    "_ga", "_ga_*", "_fbp", "_fbc", "_gcl_au", "_hj*", "_ig",
    "_twpid", "_uet", "_ttp", "_rdt", "_clck", "_clsk",
    "amplitude_id*", "mp_*_mixpanel", "OptanonConsent",
    "LAST_VISITED_PAGE", "__hssrc", "__hstc", "hubspotutk",
    "__stripe_mid", "__stripe_sid",
    "g_state",  # Google session state, ephemeral
    "__Secure-3PSIDTS", "__Secure-3PSIDCC", "NID",  # Google auth, long but SA-incompatible
})

# Default expected lifetime in seconds when the HAR doesn't carry
# the cookie's own ``expires`` field. PerimeterX session tokens
# without ``expires`` are session cookies; SA remember tokens are
# ~1 year. Conservative defaults favor the longer estimate.
_DEFAULT_TTL_SECONDS = {
    "LONG": 30 * 24 * 3600,
    "MEDIUM": 7 * 24 * 3600,
    "SHORT": 24 * 3600,
    "UNKNOWN": 24 * 3600,
}


def _categorize_cookie_longevity(name: str) -> str:
    """Return ``LONG`` / ``MEDIUM`` / ``SHORT`` for a cookie name.

    Used by the smart HAR merge to avoid wiping still-valid auth cookies
    when a fresh HAR is missing them. ``SHORT`` cookies (analytics, ad
    pixels) refresh on every browser launch and are safe to overwrite.
    """
    if not name:
        return "UNKNOWN"
    if name in LONG_LIVED_AUTH_COOKIES:
        return "LONG"
    if name in MEDIUM_LIVED_COOKIES:
        return "MEDIUM"
    # Exact-match SHORT first (avoids the more expensive prefix loop)
    if name in SHORT_LIVED_COOKIES:
        return "SHORT"
    # Wildcard patterns in SHORT_LIVED_COOKIES. Supported forms:
    #   ``_ga_*``  → rstrip('*') == '_ga_', match by startswith
    #   ``mp_*_mixpanel``  → keep the literal ``*_mixpanel`` suffix
    #                         so ``mp_abc_mixpanel`` matches but
    #                         ``mp_abc_other`` does not.
    for pat in SHORT_LIVED_COOKIES:
        if "*" not in pat:
            continue
        if pat.endswith("*"):
            prefix = pat[:-1]
            if name.startswith(prefix):
                return "SHORT"
            continue
        if "*" in pat:
            # Treat the literal portion after ``*`` as a suffix
            head, _, tail = pat.partition("*")
            if name.startswith(head) and name.endswith(tail):
                return "SHORT"
    return "UNKNOWN"


def _estimate_expires_at(name: str, har_expires: float | int | None) -> float | None:
    """Return the expiry epoch (seconds) for a cookie, or None if unknown.

    ``har_expires`` is the value from the HAR (usually -1 for session
    cookies, otherwise a unix timestamp). We map it to a usable epoch;
    session cookies (-1) get a 24h default so the next probe still works.
    """
    import time as _time
    longevity = _categorize_cookie_longevity(name)
    if har_expires is None or har_expires == -1 or har_expires == 0:
        # Session cookie or unknown — use longevity default
        ttl = _DEFAULT_TTL_SECONDS[longevity]
        return _time.time() + ttl
    if har_expires < _time.time():
        # Already expired (HAR was taken more than 1d ago) — treat as session
        return _time.time() + _DEFAULT_TTL_SECONDS[longevity]
    return float(har_expires)


def _cookies_by_name(cookies_parsed: list[dict[str, str]] | None) -> dict[str, dict[str, str]]:
    """Index ``cookies_parsed`` by name for O(1) merge lookups."""
    out: dict[str, dict[str, str]] = {}
    for c in cookies_parsed or []:
        name = (c.get("name") or "").strip()
        if name:
            out[name] = c
    return out


def _is_earnings_call_transcript_link(label: str, href: str) -> bool:
    """Return True for any transcript article; reject explicit non-transcripts.

    SA's `/earnings/transcripts` listing mixes earnings-call transcripts,
    conference transcripts (e.g. "Presents at Bank of America 2026 ... Conference
    Transcript"), and obvious non-transcripts (slideshows, slides, news,
    commentary, comment anchors). Earnings content and conference presentations
    with Q&A are both useful — the title word "transcript" is the reliable signal.

    Previously this filter rejected anything containing "conference" or
    "presentation" — that wrongly excluded legitimate conference transcripts
    like "Nvidia Corporation presents at Bank of America 2026 Global Technology
    Conference Transcript" which Ced flagged on 2026-06-09 as valid earnings
    content. The fix keeps "transcript" as the primary accept signal and only
    rejects clearly non-transcript content (slideshows, slides, news,
    commentary, comment anchors, and the slides-only "Earnings Call Presentation"
    variant).
    """
    return _rank_transcript_link(label, href) > 0


# Ranking tiers — higher is better. Used to pick the best transcript article
# when several are available, so that the quarterly earnings call is preferred
# over a more recent conference presentation of the same company.
_RANK_EARNINGS_CALL = 100          # "Q1 2027 Earnings Call Transcript"
_RANK_EARNINGS_CALL_LEGACY = 50     # "Earnings Call Transcript" (no quarter tag)
_RANK_SHAREHOLDER_CALL = 40         # "Shareholder/Analyst Call Transcript"
_RANK_OPERATOR_QA = 30              # any transcript whose body has "operator:" (Q&A)
_RANK_CONFERENCE_TRANSCRIPT = 20    # "Presents at X Conference Transcript"
_RANK_PREPARED_REMARKS = 10         # "Prepared Remarks Transcript" (no Q&A)
_RANK_OTHER_TRANSCRIPT = 5          # other transcripts we can't classify


def _rank_transcript_link(label: str, href: str) -> int:
    """Score a candidate article link; 0 means reject.

    Higher score = better. Used to pick the best transcript when several
    candidates are available. The filter itself is the boolean return from
    ``_is_earnings_call_transcript_link`` (any non-zero score passes).
    """
    text = f"{label or ''} {href or ''}".lower()
    if "/article/" not in text:
        return 0
    # Comment anchor (e.g. "8 Comments" linked to #scroll_comments)
    if "#scroll_comments" in text:
        return 0
    # Slideshows / pure slides / news / commentary are not transcripts
    if any(kw in text for kw in ("slideshow", "-slides", "slides", "news", "commentary")):
        return 0
    # "Earnings Call Presentation" is the slides-only variant of the call —
    # not the spoken transcript. Real transcripts end in "Transcript".
    if "earnings call presentation" in text:
        return 0
    # Must have a transcript signal (or legacy fallback)
    if "transcript" not in text:
        if "earnings call transcript" not in text and re.search(
            r"\bq[1-4]\b.*earnings.*call", text
        ) is None:
            return 0
    # Score the transcript type
    if re.search(r"\bq[1-4]\b.*earnings.*call.*transcript", text):
        return _RANK_EARNINGS_CALL
    if "earnings call transcript" in text:
        return _RANK_EARNINGS_CALL_LEGACY
    if "shareholder/analyst call transcript" in text:
        return _RANK_SHAREHOLDER_CALL
    # "Conference Call Transcript" / "Q1 Conference Call" — these are real
    # Q&A calls (analyst + operator), not pure presentations. Score above a
    # plain "Conference Transcript" because they have operator-driven Q&A.
    if re.search(r"conference\s+call", text) and "transcript" in text:
        return _RANK_SHAREHOLDER_CALL
    # "Presents at X Conference Transcript" — prepared + Q&A at an event
    if "conference transcript" in text or (
        "presents at" in text and "transcript" in text
    ):
        return _RANK_CONFERENCE_TRANSCRIPT
    if "prepared remarks" in text and "transcript" in text:
        return _RANK_PREPARED_REMARKS
    # Any other transcript with "call" in the title is a Q&A call
    if "call" in text and "transcript" in text:
        return _RANK_SHAREHOLDER_CALL
    if "transcript" in text:
        return _RANK_OTHER_TRANSCRIPT
    return 0


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
    freshness = _compute_cookie_freshness(payload)
    return {
        "configured": configured,
        "cookie_count": _cookie_count(cookie_header) if configured else 0,
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "user_agent_configured": bool(payload.get("user_agent")),
        "cookie_diagnostics": _cookie_diagnostics(cookie_header),
        "server_side_only": True,
        "test_ticker_default": DEFAULT_TEST_TICKER,
        "freshness": freshness,
        "merge_metadata": payload.get("_har_merged", {}),
    }


def _compute_cookie_freshness(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a freshness summary for the current cookie store.

    The frontend uses this to decide whether to nag the user about a
    re-upload or whether the long-lived auth cookies are about to expire.
    """
    import time as _time
    now = _time.time()
    cookies_parsed = payload.get("cookies_parsed") or []
    cookie_expires = payload.get("cookie_expires") or {}
    long_lived_present: list[str] = []
    long_lived_missing: list[str] = []
    earliest_expiry: float | None = None
    for name in LONG_LIVED_AUTH_COOKIES:
        if any(c.get("name") == name for c in cookies_parsed):
            exp = cookie_expires.get(name)
            if exp is None and cookies_parsed:
                # Backfill estimate from cookie name
                exp = _estimate_expires_at(name, None)
            if exp is not None:
                if earliest_expiry is None or exp < earliest_expiry:
                    earliest_expiry = exp
            long_lived_present.append(name)
        else:
            long_lived_missing.append(name)
    updated_at = payload.get("updated_at")
    age_hours: float | None = None
    if updated_at:
        try:
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(updated_at.replace("Z", "+00:00"))
            age_hours = max(0.0, (now - ts.timestamp()) / 3600.0)
        except (ValueError, AttributeError):
            pass
    if not cookies_parsed:
        status = "not_configured"
    elif long_lived_missing and len(long_lived_missing) >= 3:
        status = "missing_long_lived_auth"  # user should re-login
    elif earliest_expiry is not None and earliest_expiry < now + 24 * 3600:
        status = "expiring_soon"  # next 24h
    elif age_hours is not None and age_hours > 72:
        status = "stale_over_72h"  # should refresh
    else:
        status = "fresh"
    return {
        "status": status,
        "long_lived_present": long_lived_present,
        "long_lived_missing": long_lived_missing,
        "earliest_long_lived_expiry": earliest_expiry,
        "earliest_long_lived_expiry_iso": (
            _dt.fromtimestamp(earliest_expiry, tz=timezone.utc).isoformat()
            if earliest_expiry else None
        ),
        "store_age_hours": age_hours,
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


def import_har_cookies(file_path: str | Path) -> dict[str, Any]:
    """Import Seeking Alpha cookies from a browser HAR export file.

    Parses a Chrome/Edge/Firefox HAR (HTTP Archive) JSON file, finds all
    requests to ``*.seekingalpha.com``, extracts cookies from both the
    ``request.cookies`` array and the ``Cookie`` request header, deduplicates
    by cookie name, and persists them to the server-side SA access store in
    Netscape-compatible format so Playwright can use them with per-cookie
    domain/path for PerimeterX bypass.

    Returns the access status dict on success.
    Raises ValueError if the file is not valid JSON, not a HAR, or contains
    no Seeking Alpha cookies.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"HAR file not found: {file_path}")

    # Strict read: refuse files over 100 MB
    try:
        fstat = path.stat()
        if fstat.st_size > 100 * 1024 * 1024:
            raise ValueError(
                f"HAR file too large ({fstat.st_size} bytes, max 100 MB). "
                "Export a shorter session or filter to seekingalpha.com only."
            )
    except OSError:
        pass

    raw = path.read_text(encoding="utf-8")
    try:
        har = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid HAR JSON: {e}") from e

    entries = har.get("log", {}).get("entries")
    if entries is None:
        raise ValueError("Not a valid HAR file: missing log.entries")

    # Collect cookies from seekingalpha.com entries.
    # ``sa_cookies`` keeps the LAST value seen (Chrome/FF usually send
    # the same value across requests, so last-write-wins is fine).
    # ``sa_expires`` carries the explicit expires timestamp from the
    # HAR's structured cookie record, when present (Chrome only — FF
    # HAR omits this; we then fall back to category-based default).
    sa_cookies: dict[str, str] = {}
    sa_expires: dict[str, float | int] = {}
    sa_user_agent: str | None = None

    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")

        # Only Seeking Alpha domains
        if "seekingalpha.com" not in url:
            continue

        # 1) request.cookies array (structured, may carry expires)
        for c in req.get("cookies", []):
            name = (c.get("name") or "").strip()
            value = (c.get("value") or "").strip()
            if name and value:
                sa_cookies[name] = value
                # expires is sometimes -1 (session), sometimes a unix ts
                exp = c.get("expires")
                if exp is not None and exp != "":
                    try:
                        sa_expires[name] = float(exp)
                    except (TypeError, ValueError):
                        pass

        # 2) Cookie header (raw, may contain cookies not in the array)
        for h in req.get("headers", []):
            if (h.get("name") or "").lower() == "cookie":
                for part in h["value"].split(";"):
                    if "=" not in part:
                        continue
                    name, val = part.strip().split("=", 1)
                    name, val = name.strip(), val.strip()
                    if name and val:
                        sa_cookies[name] = val

        # 3) User-Agent (first one wins)
        if sa_user_agent is None:
            for h in req.get("headers", []):
                if (h.get("name") or "").lower() == "user-agent":
                    ua = h.get("value", "").strip()
                    if ua:
                        sa_user_agent = ua
                    break

    if not sa_cookies:
        raise ValueError(
            "No Seeking Alpha cookies found in HAR file. "
            "Make sure the browser session included requests to seekingalpha.com "
            "while logged in."
        )

    # ── Smart merge: preserve long-lived auth cookies from the existing
    # store when the HAR doesn't carry them. This stops a fresh HAR from
    # wiping out ``slireg`` / ``sa-user-id-v3`` when the user only
    # re-exported after navigating a single page.
    existing = _read_store()
    existing_by_name = _cookies_by_name(existing.get("cookies_parsed"))
    preserved_long_lived: list[str] = []
    merged_short_lived: list[str] = []
    cookie_expires: dict[str, float] = {}
    cookies_parsed: list[dict[str, Any]] = []
    cookie_parts: list[str] = []

    # First pass: walk HAR cookies, but for LONG-lived ones that the HAR
    # is missing, copy from the existing store. We do NOT silently keep
    # the existing value if the HAR has a fresher copy of the same name.
    har_names = set(sa_cookies.keys())
    for name in existing_by_name:
        if name in har_names:
            continue  # HAR is the source of truth
        longevity = _categorize_cookie_longevity(name)
        if longevity == "LONG":
            cookies_parsed.append(dict(existing_by_name[name]))
            preserved_long_lived.append(name)

    # Second pass: write HAR cookies, computing per-cookie expiry.
    for name, value in sa_cookies.items():
        expires_at = _estimate_expires_at(name, sa_expires.get(name))
        # Domain — Chrome HAR often doesn't carry it; default to
        # .seekingalpha.com (covers both apex and subdomains).
        domain = ".seekingalpha.com"
        cookies_parsed.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": "/",
            "expires_at": expires_at,
            "longevity": _categorize_cookie_longevity(name),
        })
        cookie_parts.append(f"{name}={value}")
        cookie_expires[name] = expires_at
        merged_short_lived.append(name)

    # Sort cookies_parsed for deterministic output: LONG first, then by name
    _longevity_rank = {"LONG": 0, "MEDIUM": 1, "SHORT": 2, "UNKNOWN": 3}
    cookies_parsed.sort(key=lambda c: (_longevity_rank.get(c.get("longevity", "UNKNOWN"), 3), c.get("name", "")))

    cookie_header = "; ".join(cookie_parts)
    payload = {
        "cookie_header": cookie_header,
        "cookies_parsed": cookies_parsed,
        "cookie_expires": cookie_expires,
        "user_agent": (sa_user_agent or existing.get("user_agent") or DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
        "created_at": existing.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "_import_source": f"har:{path.name}",
        "_har_merged": {
            "har_cookie_count": len(merged_short_lived),
            "preserved_long_lived": preserved_long_lived,
            "preserved_count": len(preserved_long_lived),
            "merge_strategy": "har_overwrites_short_medium_preserves_long",
        },
    }
    _write_store(payload)
    logger.info(
        "Imported %d SA cookies from HAR %s (preserved %d long-lived: %s)",
        len(merged_short_lived), path.name,
        len(preserved_long_lived),
        ", ".join(preserved_long_lived) or "(none)",
    )
    if preserved_long_lived:
        logger.info(
            "Smart HAR merge kept long-lived auth cookies that were absent "
            "from the upload: %s",
            preserved_long_lived,
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


def refresh_cookies_from_firefox(preserve_existing: bool = True) -> dict[str, Any]:
    """Launch Firefox with persistent profile, extract fresh SA cookies.

    Uses a persistent Firefox profile so cookies survive across restarts.
    The first run may need manual login; subsequent runs reuse the session.
    Stores extracted cookies in the backend's cookie store.

    When ``preserve_existing=True`` (default), long-lived auth cookies
    that the live session doesn't carry (e.g. ``slireg`` was rotated)
    are *kept* from the previous store rather than wiped out. This
    means a Firefox refresh never downgrades the auth coverage.
    """
    profile_dir = Path(_storage_path()).parent / "firefox_sa_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "reason": "patchright_not_installed", "cookie_count": 0}

    try:
        with sync_playwright() as p:
            # Persistent Firefox context — cookies survive across runs.
            # We use the same profile that refresh_cookies_from_firefox
            # has been writing to so existing slireg/user_remember_token
            # cookies are reused when the browser relaunches.
            browser = p.firefox.launch_persistent_context(
                str(profile_dir),
                headless=True,
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = browser.new_page()

            # Navigate to SA — if logged in, cookies from profile will authenticate
            page.goto("https://seekingalpha.com/symbol/NVDA/earnings/transcripts",
                     timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            body = page.inner_text("body")[:1000].lower()

            # Check if we're authenticated
            if any(m in body for m in ["press & hold", "verify", "access denied"]):
                browser.close()
                return {
                    "ok": False,
                    "reason": "perimeterx_blocked_persistent",
                    "cookie_count": 0,
                    "hint": "Launch Firefox manually once to log in: playwright.firefox.launch_persistent_context(headless=False)"
                }

            # Extract all cookies from the browser context
            all_cookies = browser.cookies()
            sa_cookies = [c for c in all_cookies if "seekingalpha" in c.get("domain", "")]

            # Convert to parsed format with per-cookie expiry + longevity
            parsed_cookies: list[dict[str, Any]] = []
            cookie_expires: dict[str, float] = {}
            import time as _time
            for c in sa_cookies:
                exp = c.get("expires", -1)
                expires_at: float | None
                if exp and exp > 0:
                    expires_at = float(exp)
                else:
                    expires_at = _estimate_expires_at(c["name"], None)
                parsed_cookies.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".seekingalpha.com"),
                    "path": c.get("path", "/"),
                    "expires_at": expires_at,
                    "longevity": _categorize_cookie_longevity(c["name"]),
                })
                if expires_at is not None:
                    cookie_expires[c["name"]] = expires_at

            cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in sa_cookies)

            browser.close()

            if not sa_cookies:
                return {"ok": False, "reason": "no_sa_cookies_found", "cookie_count": 0}

            has_pro = any(
                str(c.get("value", "")).lower() in ("1", "true")
                for c in parsed_cookies
                if c["name"] in ("ever_pro", "has_paid_subscription")
            )

            # Smart merge: keep long-lived cookies from the existing
            # store that aren't in the fresh Firefox session. This
            # protects against slireg/sa-user-id-v3 silently dropping
            # out of the live browser cookie jar.
            existing = _read_store()
            preserved: list[str] = []
            if preserve_existing:
                existing_by_name = _cookies_by_name(existing.get("cookies_parsed"))
                live_names = {c["name"] for c in parsed_cookies}
                for name, c in existing_by_name.items():
                    if name in live_names:
                        continue
                    if _categorize_cookie_longevity(name) == "LONG":
                        # Re-add to parsed_cookies (LONGEVITY first)
                        parsed_cookies.append(dict(c))
                        if not str(cookie_header).endswith(";"):
                            cookie_header = cookie_header + "; " if cookie_header else ""
                            # Re-join: we need a single header string
                        cookie_header = "; ".join(
                            f"{x['name']}={x['value']}" for x in parsed_cookies
                        )
                        preserved.append(name)
                # Sort LONG first for deterministic output
                _longevity_rank = {"LONG": 0, "MEDIUM": 1, "SHORT": 2, "UNKNOWN": 3}
                parsed_cookies.sort(key=lambda c: (
                    _longevity_rank.get(c.get("longevity", "UNKNOWN"), 3),
                    c.get("name", ""),
                ))

            store_data = {
                "cookie_header": cookie_header,
                "cookies_parsed": parsed_cookies,
                "cookie_expires": cookie_expires,
                "user_agent": existing.get("user_agent") or DEFAULT_USER_AGENT,
                "created_at": existing.get("created_at") or _now_iso(),
                "updated_at": _now_iso(),
                "source": "firefox_persistent_profile",
                "refreshed_at": _now_iso(),
                "pro_level": has_pro,
                "_har_merged": {
                    "har_cookie_count": len(sa_cookies),
                    "preserved_long_lived": preserved,
                    "preserved_count": len(preserved),
                    "merge_strategy": "firefox_refresh_preserves_long_lived",
                },
            }
            _write_store(store_data)

            return {
                "ok": True,
                "reason": "cookies_refreshed_from_firefox",
                "cookie_count": len(sa_cookies),
                "preserved_long_lived": preserved,
                "pro_level": has_pro,
                "profile_dir": str(profile_dir),
            }

    except Exception as e:
        logger.warning(f"Firefox cookie refresh failed: {e}")
        return {"ok": False, "reason": f"error_{type(e).__name__}", "cookie_count": 0, "error": str(e)}


async def auto_refresh_cookies_if_needed() -> dict[str, Any]:
    """Conditionally refresh SA cookies via Firefox when the store looks stale.

    Called by the cron watchdog (3am daily) and by the feedback pipeline
    when an "access" complaint comes in. Returns the refresh outcome so
    callers can decide whether to notify Ced.

    Triggers a Firefox refresh when:
      * freshness.status in {expiring_soon, missing_long_lived_auth, stale_over_72h}
      * AND the Firefox profile dir already exists (user logged in once)

    If the profile dir is missing, we return a "manual_login_required"
    hint so the user is told what to do instead of silently failing.
    """
    payload = _read_store()
    freshness = _compute_cookie_freshness(payload)
    profile_dir = _storage_path().parent / "firefox_sa_profile"
    profile_exists = profile_dir.exists() and any(profile_dir.iterdir())

    if freshness["status"] in ("fresh", "not_configured"):
        return {
            "skipped": True,
            "reason": f"freshness_{freshness['status']}",
            "freshness": freshness,
        }

    if not profile_exists:
        return {
            "skipped": True,
            "reason": "no_firefox_profile",
            "hint": (
                "Run `hermes-admin seeking-alpha login-firefox` once manually "
                "to create the persistent Firefox profile at "
                f"{profile_dir}, then re-run."
            ),
            "freshness": freshness,
        }

    # Run the sync refresh in a thread (it blocks on browser lifecycle)
    import asyncio
    result = await asyncio.to_thread(refresh_cookies_from_firefox)
    result["freshness"] = _compute_cookie_freshness(_read_store())
    return result


def _probe_with_playwright(listing_url: str, cookie_store: dict) -> dict[str, Any]:
    """Retry transcript probe using Playwright for PRO accounts (JS-enabled).
    
    SA serves full transcript content to PRO subscribers via JavaScript.
    The HTTP-only probe sees isMpwLocked:true in raw HTML, but the browser
    JS unlocks it for PRO accounts. This function uses a headless browser.
    """
    import re as _re
    
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "reason": "playwright_not_installed", "phase": "playwright_fallback"}
    
    pw_cookies = []
    # SA-specific cookie prefixes. We must send ALL of these together —
    # PerimeterX scores the request fingerprint and refuses the request
    # when too many of these are missing. The list is intentionally
    # broad: it's strictly better to send a slightly-stale analytic
    # cookie than to look bot-shaped.
    sa_prefixes = (
        # SA-native
        "sa-", "user_", "sapu", "gk_", "ever_", "has_", "sailthru",
        # PerimeterX (anti-bot)
        "_px", "pxcts", "machine_", "pxvid", "_pxvid", "_px3", "_pxhd",
        # Session
        "LAST_", "session_", "u_voc", "slireg", "g_state",
        # Google analytics + ads
        "_ga", "_gcl", "_fbp", "_fbc", "_ig", "_hj", "_twpid", "_uet",
        # NEW: missing in v1 — Cloudflare/PerimeterX/OneTrust/Mixpanel
        "__cf_bm", "cf_clearance",
        "OptanonConsent", "OptanonAlertBoxClosed",
        "amplitude_id", "mp_",  # Mixpanel
        "_ttp", "_rdt",  # TikTok / Reddit
        "_clck", "_clsk",  # Microsoft Clarity
        "hubspotutk", "__hssrc", "__hstc",  # HubSpot
        "__stripe", "stripe*",
    )
    for c in cookie_store.get("cookies_parsed", []):
        name = (c.get("name") or "").strip()
        value = (c.get("value") or "")
        domain = (c.get("domain") or ".seekingalpha.com")
        path = (c.get("path") or "/")
        if not name:
            continue
        # Only include SA-native cookies, not third-party
        if not any(name.startswith(p) for p in sa_prefixes):
            continue
        if domain.startswith("."):
            domain = domain[1:]
        pw_cookies.append({
            "name": name,
            "value": str(value),
            "domain": domain,
            "path": path,
        })
    
    try:
        with sync_playwright() as p:
            # Prefer Firefox (camoufox if available) — same engine that
            # generated the cookie store, so fingerprinting stays
            # consistent and PerimeterX doesn't see a Chrome vs Firefox
            # UA mismatch.
            browser = None
            profile_dir = _storage_path().parent / "firefox_sa_profile"
            use_persistent_firefox = profile_dir.exists() and any(profile_dir.iterdir())
            if use_persistent_firefox:
                try:
                    browser = p.firefox.launch_persistent_context(
                        str(profile_dir),
                        headless=True,
                        viewport={"width": 1920, "height": 1080},
                        locale="en-US",
                    )
                    # Reuse the profile's cookies (they include slireg +
                    # all Px tokens) instead of overriding with pw_cookies
                    context = browser
                    page = browser.new_page()
                except Exception as fx_err:
                    logger.info("Persistent Firefox unavailable (%s); falling back to chromium", fx_err)
                    browser = None
            if browser is None:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                context.add_cookies(pw_cookies)
                page = context.new_page()
            
            # Step 1: listing page
            page.goto(listing_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            body = page.inner_text("body")[:500].lower()
            if any(m in body for m in ["press & hold", "verify", "access denied", "are you a robot"]):
                browser.close()
                return {"ok": False, "reason": "blocked_perimeterx", "phase": "playwright_listing"}
            
            # Step 2: find first transcript article link
            links = page.query_selector_all('a[href*="/article/"]')
            article_url = None
            for link in links:
                href = link.get_attribute("href") or ""
                label = (link.inner_text() or "").lower()
                if _is_earnings_call_transcript_link(label, href):
                    article_url = "https://seekingalpha.com" + href if href.startswith("/") else href
                    break
            
            if not article_url and links:
                href = links[0].get_attribute("href") or ""
                article_url = "https://seekingalpha.com" + href if href.startswith("/") else href
            
            if not article_url:
                browser.close()
                return {"ok": False, "reason": "no_article_link_found", "phase": "playwright_listing"}
            
            # Step 3: fetch article with JS
            page.goto(article_url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            # Get text from the transcript section specifically
            article_text = page.inner_text("body")
            article_html = page.content()
            text_len = len(article_text)
            
            # Try to get transcript content more specifically
            try:
                transcript_el = page.query_selector('[data-test-id="transcript-presentation"]')
                if transcript_el:
                    article_text = transcript_el.inner_text()
                    text_len = len(article_text)
            except Exception:
                pass
            
            browser.close()
            
            # Check for MPW in rendered page
            is_mpw_locked = 'isMpwLocked":true' in article_html
            is_mpw_unlocked = 'isMpwLocked":false' in article_html
            
            # Check for transcript content
            has_transcript = 'transcript-presentation-section' in article_html
            section_count = len(_re.findall(r'seq="(\d+)"', article_html))
            
            # Key: check if the article text is substantial (not just preview)
            if text_len > 8000 and has_transcript:
                return {
                    "ok": True,
                    "authenticated": True,
                    "reachable": True,
                    "blocked": False,
                    "url": article_url,
                    "status_code": 200,
                    "reason": "ok_full_transcript_playwright",
                    "text_length": text_len,
                    "mpw_locked": is_mpw_locked,
                    "transcript_sections": section_count,
                    "has_transcript_content": has_transcript,
                    "phase": "playwright_transcript",
                    "tested_at": _now_iso(),
                }
            elif is_mpw_locked and text_len < 5000:
                return {
                    "ok": False,
                    "reason": "mpw_locked_even_with_playwright",
                    "text_length": text_len,
                    "url": article_url,
                    "phase": "playwright_transcript",
                    "tested_at": _now_iso(),
                }
            else:
                return {
                    "ok": True,
                    "authenticated": True,
                    "reachable": True,
                    "url": article_url,
                    "status_code": 200,
                    "reason": "ok_partial_or_non_transcript",
                    "text_length": text_len,
                    "phase": "playwright_transcript",
                    "tested_at": _now_iso(),
                }
                
    except Exception as e:
        logger.warning(f"Playwright probe failed: {e}")
        return {"ok": False, "reason": f"playwright_error_{type(e).__name__}", "phase": "playwright_fallback", "tested_at": _now_iso()}


async def probe_access_async(ticker: str | None = None) -> dict[str, Any]:
    """Cookie health check — probes a REAL transcript article, not just the listing page.

    The listing page is always public. The real gate is individual transcript articles.
    This probe:
      1. Fetches the listing page, extracts the first earnings-call transcript link
      2. Fetches THAT article, checks for isMpwLocked (MPW = metered paywall)
      3. If MPW locked and account has PRO cookies, retries with Playwright (JS-enabled)
         because SA serves full content to PRO subscribers via JavaScript.
      4. Reports ok=True only if the transcript article is fully accessible.
    Uses httpx first (fast), Playwright as fallback for PRO accounts.
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
        import httpx

        def _deep_probe() -> dict[str, Any]:
            h = build_request_headers()
            h["Accept"] = "text/html"

            # Check if PRO cookies are present — if so, skip httpx and go straight to Playwright
            # because SA uses JavaScript to unlock content for PRO subscribers
            cookie_store = _read_store()
            has_pro = any(
                c.get("name") in ("ever_pro", "has_paid_subscription") 
                and str(c.get("value")).lower() in ("1", "true")
                for c in cookie_store.get("cookies_parsed", [])
            )
            
            if has_pro:
                logger.info(f"PRO cookies detected — using Playwright probe for {clean_ticker}")
                return _probe_with_playwright(listing_url, cookie_store)

            with httpx.Client(timeout=25, follow_redirects=True) as client:
                # ── Step 1: fetch listing page, extract first transcript link ──
                listing_resp = client.get(listing_url, headers=h)
                if listing_resp.status_code == 403:
                    return {
                        "authenticated": False, "reachable": False, "blocked": True,
                        "url": listing_url, "status_code": 403,
                        "reason": "blocked_403", "text_length": 0,
                        "phase": "listing_page",
                    }
                if listing_resp.status_code not in (200, 301, 302, 307, 308):
                    return {
                        "authenticated": False, "reachable": False, "blocked": False,
                        "url": listing_url, "status_code": listing_resp.status_code,
                        "reason": f"listing_http_{listing_resp.status_code}", "text_length": 0,
                        "phase": "listing_page",
                    }

                # Extract first earnings-call transcript article URL
                import re as _re
                article_matches = _re.findall(
                    r'"(/article/\d+[^"]*earnings-call-transcript[^"]*)"',
                    listing_resp.text,
                )
                if not article_matches:
                    # Broader: any earnings call link
                    article_matches = _re.findall(
                        r'"(/article/\d+[^"]*transcript[^"]*)"',
                        listing_resp.text,
                    )
                if not article_matches:
                    # Fallback: any article link
                    article_matches = _re.findall(
                        r'"(/article/\d+[^"]*)"',
                        listing_resp.text,
                    )

                if not article_matches:
                    return {
                        "authenticated": False, "reachable": True, "blocked": False,
                        "url": listing_url, "status_code": listing_resp.status_code,
                        "reason": "no_transcript_link_found", "text_length": 0,
                        "phase": "listing_page",
                    }

                transcript_url = "https://seekingalpha.com" + article_matches[0]

                # ── Step 2: fetch the actual transcript article ──
                article_resp = client.get(transcript_url, headers=h)
                article_text = article_resp.text
                text_len = len(article_text)

                if article_resp.status_code == 403:
                    return {
                        "authenticated": False, "reachable": False, "blocked": True,
                        "url": transcript_url, "status_code": 403,
                        "reason": "transcript_blocked_403", "text_length": text_len,
                        "phase": "transcript_article",
                    }

                # ── Step 3: check for paywall ──
                is_mpw_locked = 'isMpwLocked":true' in article_text
                is_mpw_unlocked = 'isMpwLocked":false' in article_text

                if is_mpw_locked:
                    # Check if account has PRO cookies — if so, retry with Playwright
                    # because SA serves full transcripts to PRO users via JavaScript
                    cookie_store = _read_store()
                    has_pro = any(
                        c.get("name") in ("ever_pro", "has_paid_subscription") 
                        and str(c.get("value")).lower() in ("1", "true")
                        for c in cookie_store.get("cookies_parsed", [])
                    )
                    
                    if has_pro:
                        logger.info(f"MPW locked but PRO cookies detected — retrying with Playwright for {clean_ticker}")
                        pw_result = _probe_with_playwright(listing_url, cookie_store)
                        if pw_result.get("ok"):
                            return pw_result
                    
                    return {
                        "authenticated": True, "reachable": True, "blocked": False,
                        "url": transcript_url, "status_code": article_resp.status_code,
                        "reason": "mpw_locked_preview_only",
                        "text_length": text_len,
                        "mpw_locked": True,
                        "phase": "transcript_article",
                    }

                # ── Check for actual transcript content ──
                has_transcript_sections = _re.search(
                    r'class="transcript-presentation-section"', article_text
                ) is not None
                section_count = len(_re.findall(r'seq="(\d+)"', article_text))

                return {
                    "authenticated": True,
                    "reachable": True,
                    "blocked": False,
                    "url": transcript_url,
                    "status_code": article_resp.status_code,
                    "reason": "ok_full_transcript" if (is_mpw_unlocked or not is_mpw_locked) else "ok",
                    "text_length": text_len,
                    "mpw_locked": is_mpw_locked,
                    "transcript_sections": section_count,
                    "has_transcript_content": has_transcript_sections,
                    "phase": "transcript_article",
                }

        probe_result = await asyncio.to_thread(_deep_probe)
        return {
            **status,
            "ok": probe_result["authenticated"] and not probe_result.get("mpw_locked", False),
            "ticker": clean_ticker,
            **probe_result,
            "probe_method": "transcript_deep_probe",
            "tested_at": _now_iso(),
        }

    except Exception as exc:
        logger.warning("Seeking Alpha deep probe failed for %s: %s", clean_ticker, exc)
        return {
            **status, "ok": False, "authenticated": False, "reachable": False,
            "ticker": clean_ticker, "url": listing_url,
            "reason": "request_error", "error": str(exc), "tested_at": _now_iso(),
        }
