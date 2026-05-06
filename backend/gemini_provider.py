"""Gemini API provider — free tier via Google AI Studio (1M tokens/day, no credit card)."""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"  # Fast, free tier
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_chat(
    prompt: str,
    system: str = "",
    max_tokens: int = 800,
    temperature: float = 0.3,
) -> Optional[str]:
    """Send a prompt to Gemini and return the response text. Free tier."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.debug("GEMINI_API_KEY not set")
        return None

    from backend.http_client import http
    try:
        url = GEMINI_URL.format(model=GEMINI_MODEL)
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        resp = http.post(
            f"{url}?key={api_key}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        else:
            logger.warning(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Gemini error: {e}")
    return None
