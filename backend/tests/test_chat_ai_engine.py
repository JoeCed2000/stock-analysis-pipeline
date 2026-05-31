"""Chat AI engine configuration and prompt isolation tests.

TDD scope: configurable OpenAI/Gemini/DeepSeek chat provider routing,
provider-error redaction, and removal of client-facing hard-coded identity names.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest  # type: ignore[import-not-found]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend import chat_ai


def _collect(async_iterable) -> list[str]:
    async def _run() -> list[str]:
        return [token async for token in async_iterable]

    return asyncio.run(_run())


class _OpenAIStyleResponse:
    status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aread(self) -> bytes:
        return b""

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
        yield "data: [DONE]"


class _GeminiStyleResponse:
    status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aread(self) -> bytes:
        return b""

    async def aiter_lines(self):
        yield json.dumps({"candidates": [{"content": {"parts": [{"text": "konnichiwa"}]}}]})


class _CapturingClient:
    def __init__(self, capture: dict[str, Any], response):
        self.capture = capture
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, *, headers=None, json=None):
        self.capture.update({"method": method, "url": url, "headers": headers or {}, "json": json or {}})
        return self.response


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, capture: dict[str, Any], response) -> None:
    import httpx  # type: ignore[import-not-found]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            capture["client_kwargs"] = kwargs

        async def __aenter__(self):
            return _CapturingClient(capture, response)

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


def test_openai_provider_uses_configured_model_and_endpoint(monkeypatch: pytest.MonkeyPatch):
    """RED: SA_CHAT_PROVIDER=openai must route to OpenAI, not hard-coded DeepSeek."""
    capture: dict[str, Any] = {}
    _patch_httpx(monkeypatch, capture, _OpenAIStyleResponse())
    monkeypatch.setenv("SA_CHAT_PROVIDER", "openai")
    monkeypatch.setenv("SA_CHAT_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    tokens = _collect(chat_ai.stream_ai_response("hello", language="en"))

    assert tokens == ["hello"]
    assert capture["url"] == "https://api.openai.com/v1/chat/completions"
    assert capture["json"]["model"] == "gpt-4.1-mini"
    assert "test-openai-key" in capture["headers"]["Authorization"]


def test_deepseek_provider_uses_configured_model(monkeypatch: pytest.MonkeyPatch):
    """RED: DeepSeek model must come from SA_CHAT_MODEL, not a hard-coded value."""
    capture: dict[str, Any] = {}
    _patch_httpx(monkeypatch, capture, _OpenAIStyleResponse())
    monkeypatch.setenv("SA_CHAT_PROVIDER", "deepseek")
    monkeypatch.setenv("SA_CHAT_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    tokens = _collect(chat_ai.stream_ai_response("hello", language="en"))

    assert tokens == ["hello"]
    assert capture["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert capture["json"]["model"] == "deepseek-v4-flash"


def test_gemini_provider_uses_configured_model_and_endpoint(monkeypatch: pytest.MonkeyPatch):
    """RED: Gemini must be a first-class configurable chat provider."""
    capture: dict[str, Any] = {}
    _patch_httpx(monkeypatch, capture, _GeminiStyleResponse())
    monkeypatch.setenv("SA_CHAT_PROVIDER", "gemini")
    monkeypatch.setenv("SA_CHAT_MODEL", "gemini-1.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    tokens = _collect(chat_ai.stream_ai_response("hello", language="en"))

    assert tokens == ["konnichiwa"]
    assert "generativelanguage.googleapis.com" in capture["url"]
    assert "gemini-1.5-flash" in capture["url"]
    assert "test-gemini-key" not in json.dumps(capture["json"])


def test_missing_provider_credentials_do_not_leak_provider_details(monkeypatch: pytest.MonkeyPatch):
    """RED: client-facing chat must not expose provider names, keys, or raw [ERROR] markers."""
    monkeypatch.setenv("SA_CHAT_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    text = "".join(_collect(chat_ai.stream_ai_response("hello", language="ja")))

    assert "[ERROR" not in text
    assert "DeepSeek" not in text
    assert "API key" not in text
    assert "もう一度" in text or "しばらく" in text


def test_system_prompt_has_no_hardcoded_people_names():
    """RED: prompt/context isolation must not hard-code Ced/Nami/Cédric into client chat."""
    forbidden = ("Ced", "Cédric", "Nami")
    assert not any(name in chat_ai.SYSTEM_PROMPT for name in forbidden)
