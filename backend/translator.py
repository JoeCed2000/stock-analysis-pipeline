"""Document translation via NVIDIA NIM free tier (Kimi K2.6).

Quality > Speed configuration:
- 180s timeout (Kimi free tier can be slow)
- 3 retries with exponential backoff (3s → 6s → 12s)
- Temperature 0.0 for deterministic financial translation
- Proper token budgeting for CJK languages
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
KIMI_MODEL = "moonshotai/kimi-k2.6"

# Quality > Speed tunables
API_TIMEOUT = 180  # generous — Kimi free tier can spike
MAX_RETRIES = 3
RETRY_DELAY_BASE = 3  # exponential: 3s → 6s → 12s


def _get_client(timeout: int = API_TIMEOUT):
    """Get OpenAI-compatible client for NVIDIA NIM with explicit timeout."""
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key, timeout=timeout, max_retries=0)
    except ImportError:
        return None


def _estimate_max_tokens(text: str, target_lang: str) -> int:
    """Estimate output tokens. CJK languages need more headroom (~1.5x char count)."""
    cjk_langs = {"ja", "zh", "ko"}
    if target_lang in cjk_langs:
        return min(int(len(text) * 1.5) + 50, 4000)
    return min(len(text) * 2, 2000)


def translate_text(text: str, target_lang: str = "ja") -> str:
    """Translate text with retry + exponential backoff. Falls back to original only after all retries exhausted."""
    if not text or not text.strip():
        return text

    if target_lang == "en":
        return text

    lang_names = {"ja": "Japanese", "fr": "French", "zh": "Chinese", "ko": "Korean", "de": "German"}
    lang_name = lang_names.get(target_lang, target_lang)

    # Chunk long texts by paragraph for reliability
    if len(text) > 2000:
        paragraphs = text.split("\n\n")
        translated = []
        for para in paragraphs:
            if para.strip():
                translated.append(translate_text(para.strip(), target_lang))
            else:
                translated.append("")
        return "\n\n".join(translated)

    system = (
        f"You are a professional financial translator. "
        f"Translate the following text to {lang_name}. "
        f"Preserve ALL numbers, tickers (AAPL, ^GSPC), ISINs, percentages (15.3%), "
        f"dates, and markdown/JSON/XML formatting exactly. "
        f"Return ONLY the translation — no explanations, no notes, no prefixes."
    )

    max_tokens = _estimate_max_tokens(text, target_lang)

    # --- Attempt 1: OpenAI SDK ---
    client = _get_client()
    if client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = client.chat.completions.create(
                    model=KIMI_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Translate to {lang_name}:\n\n{text}"},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
                translated = resp.choices[0].message.content.strip()
                if translated.startswith('"') and translated.endswith('"'):
                    translated = translated[1:-1]
                return translated
            except Exception as e:
                logger.warning(f"NVIDIA SDK attempt {attempt}/{MAX_RETRIES}: {e}")
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                    time.sleep(delay)
                else:
                    logger.error(f"NVIDIA SDK exhausted all {MAX_RETRIES} retries")
                    # Fall through to HTTP fallback

    # --- Attempt 2: HTTP fallback ---
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        logger.warning("NVIDIA_API_KEY not set — translation unavailable")
        return text

    import requests
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": KIMI_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Translate to {lang_name}:\n\n{text}"},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.0,
                },
                timeout=API_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                translated = data["choices"][0]["message"]["content"].strip()
                if translated.startswith('"') and translated.endswith('"'):
                    translated = translated[1:-1]
                return translated
            elif resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", RETRY_DELAY_BASE * (2 ** (attempt - 1))))
                logger.warning(f"NVIDIA HTTP 429 (rate limit) — retry {attempt}/{MAX_RETRIES} after {retry_after}s")
                if attempt < MAX_RETRIES:
                    time.sleep(retry_after)
                continue
            else:
                logger.warning(f"NVIDIA HTTP {resp.status_code} (attempt {attempt}/{MAX_RETRIES}): {resp.text[:200]}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_BASE * (2 ** (attempt - 1)))
        except requests.Timeout:
            logger.warning(f"NVIDIA HTTP timeout {API_TIMEOUT}s (attempt {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_BASE * (2 ** (attempt - 1)))
        except Exception as e:
            logger.warning(f"NVIDIA HTTP error (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_BASE * (2 ** (attempt - 1)))

    logger.error(f"NVIDIA translation FAILED after {MAX_RETRIES} SDK + {MAX_RETRIES} HTTP retries")
    return text


def translate_file(filepath: str, target_lang: str = "ja") -> bool:
    """Translate a text file in-place. Returns True on success."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        translated = translate_text(content, target_lang)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(translated)

        logger.info(f"Translated {filepath} → {target_lang} ({len(content)} → {len(translated)} chars)")
        return translated != content  # True only if actually changed
    except Exception as e:
        logger.warning(f"Translation failed for {filepath}: {e}")
        return False
