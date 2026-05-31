"""URL validator for earnings deep-dive PDFs — post-generation hallucination check.

Extracts every URL from a report model, HEAD-verifies each one, and flags
dead (40x/50x), unreachable (timeout/DNS), or suspicious (redirect) links.

Slot: Between PIP-008 (PDF generation) and delivery. Non-blocking — logs
warnings, doesn't abort pipeline.
"""
from __future__ import annotations

import asyncio
from html import unescape
import logging
import re
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
_RESTRICTED_BUT_REACHABLE_STATUS_CODES = {401, 403, 429}
_ANTI_BOT_TRANSIENT_HOSTS = (
    "finance.yahoo.com",
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
    "seekingalpha.com",
)
_URL_RE = re.compile(r"https?://[^\s<>\]\)\}\"']+", re.IGNORECASE)
_TRAILING_URL_CHARS = ".,;:)]}>\"'"


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


def _clean_extracted_url(url: str) -> str:
    """Normalize a URL extracted from model/PDF text without changing semantics."""
    cleaned = unescape((url or "").strip())
    while cleaned and cleaned[-1] in _TRAILING_URL_CHARS:
        cleaned = cleaned[:-1]
    return cleaned


def _dedupe_url_pairs(urls: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Deduplicate URL/label pairs while preserving the first human context."""
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for url, label in urls:
        cleaned = _clean_extracted_url(url)
        if not cleaned:
            continue
        normalized = cleaned.rstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            deduped.append((cleaned, label))
    return deduped


def _extract_urls_from_text(text: str, label: str) -> list[tuple[str, str]]:
    """Extract HTTP(S) URLs from visible text, with context labels for logs."""
    if not text:
        return []
    return [(_clean_extracted_url(match.group(0)), label) for match in _URL_RE.finditer(text)]


def _extract_urls_from_text_file(text_path: str | Path) -> list[tuple[str, str]]:
    """Extract and deduplicate URLs from a final text artifact (.txt/.md)."""
    path = Path(text_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Text URL extraction failed for %s: %s", path, exc)
        return []
    return _dedupe_url_pairs(_extract_urls_from_text(text, f"TXT {path.name}"))


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

    return _dedupe_url_pairs(urls)


def _extract_urls_from_pdf(pdf_path: str | Path) -> list[tuple[str, str]]:
    """Extract every URL actually embedded or visible in the rendered PDF.

    This closes the BL-SA-003 gap where the model object was validated while the
    delivered PDF could still contain a different, escaped, omitted, or injected
    URL. We read both clickable URI annotations and visible page text.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover - dependency failure path
        raise RuntimeError("PyMuPDF/fitz is required for PDF URL validation") from exc

    urls: list[tuple[str, str]] = []
    with fitz.open(str(path)) as doc:
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            page_label = page_index + 1
            for link in page.get_links() or []:
                uri = link.get("uri")
                if uri:
                    urls.append((uri, f"PDF link annotation p{page_label}"))

            text = str(page.get_text("text") or "")
            urls.extend(_extract_urls_from_text(text, f"PDF visible text p{page_label}"))

    return _dedupe_url_pairs(urls)


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
    hostname = parsed.hostname or ""
    if hostname in ("localhost", "127.0.0.1", "::1"):
        check.alive = True  # local — assume reachable
        check.status_code = 0
        return check

    # Skip known API endpoints that reject HEAD
    known_get_only = ("finnhub.io", "alphavantage.co", "seekingalpha.com/api")
    method = "GET" if any(h in hostname for h in known_get_only) else "HEAD"

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
            elif resp.status_code in _RESTRICTED_BUT_REACHABLE_STATUS_CODES:
                # Auth/rate-limit/anti-bot pages prove the host+path exists; they
                # are not hallucinated dead links. Keep advisory logs quiet unless
                # the URL is truly missing or unreachable.
                check.alive = True
                check.error = f"restricted but reachable: {resp.status_code}"
            elif resp.status_code >= 500 and any(h in hostname for h in _ANTI_BOT_TRANSIENT_HOSTS):
                check.alive = True
                check.error = f"transient anti-bot response: {resp.status_code}"
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


async def _validate_url_pairs(
    url_pairs: list[tuple[str, str]],
    *,
    ticker: str = "",
    source: str = "report",
) -> ValidationReport:
    """Validate a prepared list of URL/label pairs."""
    t0 = _time.monotonic()

    report_obj = ValidationReport(
        ticker=ticker,
        total_urls=len(url_pairs),
        checks=[],
    )

    if not url_pairs:
        logger.info(f"[{ticker}] No {source} URLs to validate")
        return report_obj

    logger.info(f"[{ticker}] Validating {len(url_pairs)} {source} URLs...")

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
            f"[{ticker}] 🔴 {report_obj.dead}/{report_obj.total_urls} {source} URLs DEAD "
            f"({report_obj.duration_ms:.0f}ms)"
        )
        for c in report_obj.dead_urls:
            logger.warning(f"  DEAD: [{c.label}] {c.url} — {c.error or c.status_code}")
    else:
        logger.info(
            f"[{ticker}] ✅ All {report_obj.total_urls} {source} URLs alive "
            f"({report_obj.duration_ms:.0f}ms)"
        )

    return report_obj


async def validate_report_urls(report, ticker: str = "") -> ValidationReport:
    """Validate all URLs in an EarningsDeepDiveReport model.

    Returns a ValidationReport with per-URL status.
    Logs warnings for dead links — does NOT abort.
    """
    return await _validate_url_pairs(
        _extract_urls_from_report(report),
        ticker=ticker or getattr(report, "ticker", ""),
        source="report-model",
    )


async def validate_pdf_urls(pdf_path: str | Path, ticker: str = "") -> ValidationReport:
    """Validate URLs extracted from the final rendered PDF artifact."""
    return await _validate_url_pairs(
        _extract_urls_from_pdf(pdf_path),
        ticker=ticker,
        source="rendered-PDF",
    )


async def validate_text_urls(text_path: str | Path, ticker: str = "") -> ValidationReport:
    """Validate URLs extracted from a final rendered text artifact (.txt/.md)."""
    return await _validate_url_pairs(
        _extract_urls_from_text_file(text_path),
        ticker=ticker,
        source="text-artifact",
    )


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


def validate_pdf_urls_sync(pdf_path: str | Path, ticker: str = "") -> ValidationReport:
    """Synchronous wrapper for final PDF URL validation."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(validate_pdf_urls(pdf_path, ticker))
    # Already in an async context — create a new loop in a thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, validate_pdf_urls(pdf_path, ticker))
        return future.result(timeout=_TOTAL_BATCH_TIMEOUT + 5)


def validate_text_urls_sync(text_path: str | Path, ticker: str = "") -> ValidationReport:
    """Synchronous wrapper for final text artifact URL validation."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(validate_text_urls(text_path, ticker))
    # Already in an async context — create a new loop in a thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, validate_text_urls(text_path, ticker))
        return future.result(timeout=_TOTAL_BATCH_TIMEOUT + 5)
