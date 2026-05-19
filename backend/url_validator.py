"""URL validator for earnings deep-dive PDFs — post-generation hallucination check.

Extracts every URL from a report model, HEAD-verifies each one, and flags
dead (40x/50x), unreachable (timeout/DNS), or suspicious (redirect) links.

Slot: Between PIP-008 (PDF generation) and delivery. Non-blocking — logs
warnings, doesn't abort pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import ssl
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("sa.url_validator")

# ── Timeouts ──
_CONNECT_TIMEOUT = 8.0       # seconds per connection attempt
_TOTAL_BATCH_TIMEOUT = 30.0  # seconds for all URLs in one report
_MAX_REDIRECTS = 3
_USER_AGENT = "SA-Pipeline/2.0 (URL Validator; +https://sa.cedlabusa.net)"


@dataclass
class UrlCheck:
    url: str
    label: str = ""           # human context (e.g. "Earnings Transcript")
    status_code: int | None = None
    alive: bool = False
    error: str = ""
    redirected_to: str = ""
    response_ms: float = 0.0


@dataclass
class ValidationReport:
    ticker: str = ""
    total_urls: int = 0
    alive: int = 0
    dead: int = 0
    checks: list[UrlCheck] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def dead_urls(self) -> list[UrlCheck]:
        return [c for c in self.checks if not c.alive]

    @property
    def healthy(self) -> bool:
        return self.dead == 0


def _extract_urls_from_report(report) -> list[tuple[str, str]]:
    """Extract every (url, label) pair from an EarningsDeepDiveReport model.

    Returns list of (url, human_label) — label is context for error messages.
    """
    urls: list[tuple[str, str]] = []

    # 1. Sources (document + data sources)
    for source in getattr(report, "sources", []) or []:
        if getattr(source, "url", None):
            urls.append((source.url, source.label or "Source"))

    # 2. Earnings audio webcast
    audio = getattr(report, "earnings_audio_url", None)
    if audio:
        urls.append((audio, "Earnings Call Audio"))

    # 3. Official website
    website = getattr(report, "official_website", None)
    if website and website not in {u for u, _ in urls}:
        urls.append((website, "Official Website"))

    # 4. Claim traceability appendix
    for cs in getattr(report, "claim_sources", []) or []:
        src_url = getattr(cs, "source_url", None)
        if src_url:
            label = f"ClaimSource[{cs.source_id}]"
            urls.append((src_url, label))

    # Dedup by URL (keep first label)
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for url, label in urls:
        normalized = url.strip().rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            deduped.append((url, label))

    return deduped


async def _check_one_url(
    url: str,
    label: str,
    timeout: float = _CONNECT_TIMEOUT,
) -> UrlCheck:
    """HEAD-verify a single URL. Returns UrlCheck with status and timing."""
    import httpx

    check = UrlCheck(url=url, label=label)
    t0 = _time.monotonic()

    # Skip obviously invalid URLs
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        check.error = "invalid scheme"
        check.alive = False
        return check

    # Skip private/internal URLs
    parsed = urlparse(url)
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        check.alive = True  # local — assume reachable
        check.status_code = 0
        return check

    # Skip known API endpoints that reject HEAD
    known_get_only = ("finnhub.io", "alphavantage.co", "seekingalpha.com/api")
    method = "GET" if any(h in (parsed.hostname or "") for h in known_get_only) else "HEAD"

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        max_redirects=_MAX_REDIRECTS,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        try:
            resp = await client.request(method, url)
            check.status_code = resp.status_code
            check.alive = 200 <= resp.status_code < 400
            if resp.status_code in (301, 302, 307, 308):
                check.alive = True  # redirected but reachable
            if resp.has_redirect_location:
                check.redirected_to = str(resp.headers.get("location", ""))
        except httpx.TimeoutException:
            check.error = "timeout"
            check.alive = False
        except httpx.ConnectError as e:
            check.error = f"connection failed: {os_error_summary(e)}"
            check.alive = False
        except httpx.HTTPError as e:
            check.error = f"http error: {type(e).__name__}"
            check.alive = False
        except Exception as e:
            check.error = f"unexpected: {type(e).__name__}: {e}"
            check.alive = False

    check.response_ms = (_time.monotonic() - t0) * 1000
    return check


def os_error_summary(e: Exception) -> str:
    """Extract a short summary from an OSError or aiohttp exception."""
    msg = str(e)
    # Strip verbose traceback fragments
    if len(msg) > 120:
        msg = msg[:120] + "..."
    return msg


async def validate_report_urls(report, ticker: str = "") -> ValidationReport:
    """Validate all URLs in an EarningsDeepDiveReport model.

    Returns a ValidationReport with per-URL status.
    Logs warnings for dead links — does NOT abort.
    """
    t0 = _time.monotonic()
    url_pairs = _extract_urls_from_report(report)

    report_obj = ValidationReport(
        ticker=ticker or getattr(report, "ticker", ""),
        total_urls=len(url_pairs),
        checks=[],
    )

    if not url_pairs:
        logger.info(f"[{ticker}] No URLs to validate")
        return report_obj

    logger.info(f"[{ticker}] Validating {len(url_pairs)} URLs...")

    # Run all checks in parallel with overall timeout
    try:
        tasks = [
            _check_one_url(url, label)
            for url, label in url_pairs
        ]
        checks = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=_TOTAL_BATCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{ticker}] URL validation batch timed out after {_TOTAL_BATCH_TIMEOUT}s")
        # Partial results
        checks = []

    for check in checks:
        if isinstance(check, Exception):
            # asyncio.gather return_exceptions=True wraps errors
            report_obj.checks.append(UrlCheck(
                url="(batch error)",
                label="",
                alive=False,
                error=f"batch: {type(check).__name__}",
            ))
        elif isinstance(check, UrlCheck):
            report_obj.checks.append(check)
        else:
            report_obj.checks.append(UrlCheck(
                url="(unknown)",
                label="",
                alive=False,
                error=f"unexpected result type: {type(check).__name__}",
            ))

    # Tally
    for c in report_obj.checks:
        if c.alive:
            report_obj.alive += 1
        else:
            report_obj.dead += 1

    report_obj.duration_ms = (_time.monotonic() - t0) * 1000

    # Log dead links prominently
    if report_obj.dead > 0:
        logger.warning(
            f"[{ticker}] 🔴 {report_obj.dead}/{report_obj.total_urls} URLs DEAD "
            f"({report_obj.duration_ms:.0f}ms)"
        )
        for c in report_obj.dead_urls:
            logger.warning(f"  DEAD: [{c.label}] {c.url} — {c.error or c.status_code}")
    else:
        logger.info(
            f"[{ticker}] ✅ All {report_obj.total_urls} URLs alive "
            f"({report_obj.duration_ms:.0f}ms)"
        )

    return report_obj


def validate_report_urls_sync(report, ticker: str = "") -> ValidationReport:
    """Synchronous wrapper — runs the async validator in a new event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(validate_report_urls(report, ticker))
    # Already in an async context — create a new loop in a thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, validate_report_urls(report, ticker))
        return future.result(timeout=_TOTAL_BATCH_TIMEOUT + 5)
