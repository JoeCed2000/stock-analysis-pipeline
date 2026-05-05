"""Document translation via NVIDIA NIM free tier (Kimi K2.6)."""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
KIMI_MODEL = "moonshotai/kimi-k2.6"


def _get_client():
    """Get OpenAI-compatible client for NVIDIA NIM."""
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    except ImportError:
        return None


def translate_text(text: str, target_lang: str = "ja") -> str:
    """Translate text to target language using Kimi K2.6 via NVIDIA NIM.
    Falls back to original text if translation fails."""
    if not text or not text.strip():
        return text

    if target_lang == "en":
        return text

    lang_names = {"ja": "Japanese", "fr": "French", "zh": "Chinese", "ko": "Korean", "de": "German"}
    lang_name = lang_names.get(target_lang, target_lang)

    # For long texts, chunk into paragraphs and translate each
    if len(text) > 2000:
        paragraphs = text.split("\n\n")
        translated = []
        for para in paragraphs:
            if para.strip():
                translated.append(translate_text(para.strip(), target_lang))
            else:
                translated.append("")
        return "\n\n".join(translated)

    system = f"You are a professional financial translator. Translate the following text to {lang_name}. Preserve all numbers, tickers, percentages, and formatting exactly. Return ONLY the translation, no explanations."

    client = _get_client()
    if client:
        try:
            resp = client.chat.completions.create(
                model=KIMI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Translate to {lang_name}:\n\n{text}"},
                ],
                max_tokens=min(len(text) * 2, 2000),
                temperature=0.1,
            )
            translated = resp.choices[0].message.content.strip()
            # Remove quotes if model wraps in them
            if translated.startswith('"') and translated.endswith('"'):
                translated = translated[1:-1]
            return translated
        except Exception as e:
            logger.warning(f"NVIDIA translation error: {e}")

    # HTTP fallback
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        logger.warning("NVIDIA_API_KEY not set — translation unavailable")
        return text

    import requests
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
                "max_tokens": min(len(text) * 2, 2000),
                "temperature": 0.1,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            translated = data["choices"][0]["message"]["content"].strip()
            if translated.startswith('"') and translated.endswith('"'):
                translated = translated[1:-1]
            return translated
        else:
            logger.warning(f"NVIDIA HTTP {resp.status_code}: {resp.text[:200]}")
            return text
    except Exception as e:
        logger.warning(f"NVIDIA HTTP error: {e}")
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
        return True
    except Exception as e:
        logger.warning(f"Translation failed for {filepath}: {e}")
        return False
