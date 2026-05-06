"""Gemini API provider — free tier via Google AI Studio (1M tokens/day, no credit card).

Free tier limits:
  - gemini-2.5-flash: 5 RPM (bursty), 1M TPD
  - gemini-2.5-flash-lite: 30 RPM, 1M TPD

Strategy: use gemini-2.5-flash by default with retry+backoff on 429.
The pipeline may fire multiple LLM calls per ticker → stay under 5 RPM.
"""
import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-lite"  # Fast, free tier (30 RPM)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Global rate-limit tracking: free tier 5 RPM → 12s minimum between calls
_last_call_ts = 0.0
_MIN_INTERVAL = 2.5  # seconds between calls (30 RPM = 2s, add 0.5s buffer)


def gemini_chat(
    prompt: str,
    system: str = "",
    max_tokens: int = 800,
    temperature: float = 0.3,
) -> Optional[str]:
    """Send a prompt to Gemini and return the response text. Free tier.

    Respects 5 RPM rate limit with automatic throttling + retry on 429.
    Returns None if all retries exhausted or API key missing.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.debug("GEMINI_API_KEY not set — skipping Gemini")
        return None

    from backend.http_client import http

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    headers = {"Content-Type": "application/json"}
    url = GEMINI_URL.format(model=GEMINI_MODEL)

    for attempt in range(3):
        # ── Rate-limit throttle ──
        global _last_call_ts
        elapsed = time.monotonic() - _last_call_ts
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
            logger.debug(f"Gemini throttle: waiting {wait:.1f}s (free tier 5 RPM)")
            time.sleep(wait)

        _last_call_ts = time.monotonic()

        try:
            resp = http.post(
                f"{url}?key={api_key}",
                json=payload,
                headers=headers,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        logger.info(f"Gemini ✓ ({len(text)} chars, attempt {attempt+1})")
                        return text

            elif resp.status_code == 429:
                # Extract retry delay from response
                retry_s = 15  # default
                try:
                    body = resp.json()
                    msg = body.get("error", {}).get("message", "")
                    m = re.search(r"retry in (\d+\.?\d*)s", msg)
                    if m:
                        retry_s = float(m.group(1)) + 1
                except Exception:
                    pass
                logger.warning(f"Gemini 429 (attempt {attempt+1}/3) — waiting {retry_s:.1f}s")
                time.sleep(retry_s)
                continue  # retry

            else:
                logger.warning(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
                return None  # Non-retryable error

        except Exception as e:
            logger.warning(f"Gemini error (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)  # exponential backoff
            continue

    return None
