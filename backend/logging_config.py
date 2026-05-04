"""
Production logging config — structured, rotated, SECRET-FREE.

Usage:
    from backend.logging_config import setup_logging, log_context
    setup_logging()
    logger = logging.getLogger(__name__)

    with log_context(job_id="abc123"):
        logger.info("Starting analysis", extra={"ticker": "AAPL"})

Output format:
    2026-05-03 22:15:30.123 | INFO     | pipeline.analyze | JOB:abc123 | AAPL: Starting analysis
"""

import os
import re
import logging
import logging.handlers
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

# Context variables for structured logging
_job_id: ContextVar[Optional[str]] = ContextVar("job_id", default=None)
_ticker: ContextVar[Optional[str]] = ContextVar("ticker", default=None)

# ── Secret redaction ──────────────────────────────────────────────────────

class SecretRedactingFormatter(logging.Formatter):
    """Formatter that redacts API keys and secrets before they hit disk/stderr."""

    _SECRET_KEYS = [
        "NVIDIA_API_KEY", "FINNHUB_API_KEY", "TWELVEDATA_API_KEY",
        "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
    ]

    # Patterns that look like secrets
    _PATTERNS = [
        (re.compile(r'(?:api_key|apikey|token|secret|password|key)=["\']?([^\s&\'"]{12,})["\']?', re.I), r'\1=***REDACTED***'),
        (re.compile(r'(?:Bearer|Basic)\s+([A-Za-z0-9_\-\.]{20,})'), r'***REDACTED***'),
        (re.compile(r'(sk-[A-Za-z0-9_\-]{20,})'), 'sk-***REDACTED***'),
        (re.compile(r'(nvapi-[A-Za-z0-9_\-]{20,})'), 'nvapi-***REDACTED***'),
        (re.compile(r'(sess-[A-Za-z0-9_\-]{20,})'), 'sess-***REDACTED***'),
        (re.compile(r'([A-Za-z0-9_\-]{32,})'), r'***REDACTED***'),  # catch-all: long tokens
    ]

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        # Pre-fetch actual key values from env to redact them
        self._env_secrets = []
        for key in self._SECRET_KEYS:
            val = os.getenv(key, "")
            if val and len(val) > 4:
                # Add both the full value and a masked version
                self._env_secrets.append(val)
                # Also add first/last 4 chars to catch partial leaks
                if len(val) > 12:
                    self._env_secrets.append(val[:6])
                    self._env_secrets.append(val[-6:])

    def format(self, record):
        msg = super().format(record)
        # Redact known env secret values
        for secret in self._env_secrets:
            msg = msg.replace(secret, "***REDACTED***")
        # Redact patterns
        for pattern, replacement in self._PATTERNS:
            msg = pattern.sub(replacement, msg)
        return msg


class ContextInjectingFormatter(SecretRedactingFormatter):
    """Adds job_id and ticker context from contextvars."""

    def format(self, record):
        job = _job_id.get()
        ticker = _ticker.get()
        parts = []
        if job:
            parts.append(f"JOB:{job}")
        if ticker:
            parts.append(ticker)
        record.context = " | ".join(parts) if parts else "-"
        return super().format(record)


# ── Public API ────────────────────────────────────────────────────────────

def setup_logging(
    level: int = logging.INFO,
    log_dir: str = "logs",
    log_name: str = "pipeline",
) -> None:
    """
    Configure structured logging for the pipeline.

    - INFO+ to rotating file (5 MB × 5 backups)
    - WARNING+ to stderr
    - All secrets redacted

    Args:
        level: Minimum log level for file handler.
        log_dir: Directory for log files (created if missing).
        log_name: Base name for log files (→ {log_dir}/{log_name}.log).
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Format with context injection + secret redaction
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(context)s | %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers (idempotent)
    root.handlers.clear()

    # ── File handler: INFO+, rotated ──
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / f"{log_name}.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(ContextInjectingFormatter(fmt, datefmt))
    root.addHandler(file_handler)

    # ── Stderr handler: WARNING+ ──
    console_handler = logging.StreamHandler()  # stderr by default
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(ContextInjectingFormatter(fmt, datefmt))
    root.addHandler(console_handler)

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


class LogContext:
    """
    Context manager to inject job_id / ticker into all log records.

    Usage:
        with LogContext(job_id="abc123"):
            logger.info("Processing")  # → JOB:abc123 | Processing

    Can also be used with extra kwarg for per-message ticker:
        logger.info("Done", extra={"ticker": "AAPL"})
    """

    def __init__(self, job_id: Optional[str] = None, ticker: Optional[str] = None):
        self._token_job = None
        self._token_ticker = None
        self._job_id = job_id
        self._ticker = ticker

    def __enter__(self):
        if self._job_id:
            self._token_job = _job_id.set(self._job_id)
        if self._ticker:
            self._token_ticker = _ticker.set(self._ticker)
        return self

    def __exit__(self, *args):
        if self._token_job is not None:
            _job_id.reset(self._token_job)
        if self._token_ticker is not None:
            _ticker.reset(self._token_ticker)


log_context = LogContext  # alias for convenience


# ── Per-message context via extra ─────────────────────────────────────────

class ContextAdapter(logging.LoggerAdapter):
    """
    LoggerAdapter that injects job_id and ticker from contextvars,
    and allows per-message overrides via extra={"ticker": "AAPL"}.
    """

    def process(self, msg, kwargs):
        ctx = {}
        job = _job_id.get()
        ticker = _ticker.get()
        if job:
            ctx["job_id"] = job
        if ticker:
            ctx["ticker"] = ticker
        # Extra from the caller overrides context
        extra = kwargs.pop("extra", {})
        if isinstance(extra, dict):
            ctx.update(extra)
        kwargs["extra"] = ctx
        return msg, kwargs


def get_logger(name: str) -> ContextAdapter:
    """Get a logger that auto-injects context from contextvars."""
    return ContextAdapter(logging.getLogger(name), {})
