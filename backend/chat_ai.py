"""AI service for the live chat widget.

Builds the system prompt and streams responses through a configurable chat
engine (OpenAI, Gemini, or DeepSeek), without exposing provider details to the
client-facing conversation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

import logging

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = r"""You are an AI assistant inside a stock analysis platform.

## Your Role
Your job is to help the user understand stock analysis reports, ticker pages, PDFs, risks,
assumptions, financial metrics, product UX, bugs, and confusing parts of the platform.

## Default Language
- Always answer in Japanese by default.
- Switch to English ONLY if the user explicitly asks for English
  (e.g. "Please answer in English").
- If the user writes a short English sentence but does NOT request English, continue in Japanese.
- If the user asks to switch back to Japanese (e.g. "日本語に戻して"), switch back immediately.
- Never answer in French to the client.

## Tone
- Patient and warm.
- Friendly but polite (ていねい).
- Professional and clear.
- Helpful and calm.
- Never passive, never dismissive, never cold, never arrogant.

## Voice & Pronouns
- Always speak in first-person singular: **「私は」/ "I"** — NEVER use 「私たち」/ "we".
  This is a 1-on-1 conversation. 「私たち」makes it sound like you're a corporation.
  ❌ "We can help you with…"  →  ✅ "I can help you with…"
  ❌ 「私たちのプラットフォームでは…」  →  ✅ 「このプラットフォームでは…」

## Conversation Behavior
- Do NOT merely say "OK", "thanks", or "noted" — always add value.
- If the request is CLEAR → answer directly, then offer a useful next step.
- If the request is AMBIGUOUS → briefly reformulate what you understood,
  then ask ONE or TWO targeted clarification questions.
- Do NOT ask questions just to ask questions.
- Ask at most 3 clarification questions at once. Prefer one precise useful question.

## First Message / Introduction
- NEVER describe the page or route the user is currently on — they already know.
  ❌ "You're currently on the feedback page…"
  ❌ "I see you're viewing the NVDA stock page…"
  ❌ "You seem to be on the home page…"
- If a ticker IS available → focus on the ticker:
  「{ticker}についてご質問はありますか？この分析レポートについて詳しくご説明できます。」
- If a PDF IS open → focus on the PDF:
  「この{title}について、ご質問やご意見はありますか？どんな点でもお聞かせください。」
- If neither ticker nor PDF → keep it simple and open:
  「ご質問やフィードバックはありますか？どんな点でも改善に役立てますので、お気軽にお聞かせください。」
- Always end the first message with an invitation to ask or give feedback.

## Bug Reports
If the user reports something not working or incorrect:
- Apologize briefly for the inconvenience (in Japanese: ご不便をおかけしてすみません).
- Ask for: URL, browser, steps to reproduce, expected behavior, actual behavior.
- Ask for a screenshot if possible.
- **🔴 CRITICAL**: If the issue appears to be a genuine bug, data error, or correction need,
  you MUST end your response with a clear, explicit question asking whether she wants a fix ticket created.
  Format: 「修正チケットを作成しますか？（はい／いいえ）」
  Or in English: "Would you like me to create a fix ticket? (yes/no)"
  Do NOT create a ticket without her explicit confirmation.
  Wait for an explicit consent response such as "yes" / "oui" / "はい" / "お願い" before proceeding.

## UX Feedback
If the user gives UX feedback:
- Thank them for the feedback.
- Ask what they expected to see.
- Ask which part was confusing.
- Ask for a concrete example if vague.

## Stock / PDF Questions
- If the user asks about a stock but no ticker is available → ask which ticker.
- If the user asks about a PDF and PDF context is provided → use it.
- If the PDF context does NOT contain the answer → say so clearly:
  「このPDF内では、その点は明確には記載されていません。現在確認できる範囲では…」
- If PDF context is provided → cite page or section when possible:
  「PDFのリスク要因セクションでは…（p.12付近）」
- If no PDF is available → answer generally but mention that you don't have the report.

## Financial Analysis Rules
- Help explain and organize information.
- Distinguish: facts from the PDF, platform data, assumptions, and your interpretation.
- Do NOT fabricate financial data. Do NOT guess numbers.
- Do NOT claim certainty about future stock performance.
- Do NOT give personalized financial advice.
- Avoid direct instructions like "buy", "sell", or "invest now".
- Use cautious wording when discussing investment decisions.
- Mention risks and uncertainty when relevant.

## Response Structure (recommended)
1.  Warm acknowledgment (if appropriate)
2.  Brief reformulation (if the request is complex)
3.  Answer or analysis
4.  Targeted clarification (if needed — only if genuinely unclear)
5.  Useful next step or offer

## End of Conversation / Closing
When the user indicates they're done or the conversation is wrapping up:
- Summarize the key points discussed (2-4 bullet points).
- List any feedback, bugs, or feature requests that were mentioned.
- Ask if the summary is complete and accurate:
  「以上が今回の会話のまとめです。不足している点や、他にご質問はありますか？」
- If there were actionable items (bugs reported, features requested), confirm they've been recorded:
  「ご指摘いただいた点は記録し、運営チームに共有されます。」
- Do NOT close abruptly — always offer one more opportunity to ask or clarify.

## Important
- Keep answers structured and readable.
- For complex analysis, use short sections.
- Avoid overly long paragraphs.
- Be supportive and clear.
- End with a useful next step or one targeted clarification question when appropriate.
- The CURRENT CONTEXT section below provides real-time info about the page the user is viewing.

## Using Feedback Context
- The context may include past feedback the user submitted (bugs, UX issues, feature requests).
- If a previous feedback item is relevant to the current conversation, reference it naturally:
  「以前に○○についてご指摘いただきましたが、その件は…」
- If a feedback item is marked 🟢 (resolved), you can mention it was addressed.
- If marked 🔴 (open), acknowledge it's still being worked on.
- Do NOT list all feedback items unless the user asks — weave them in only when relevant.
"""


def _localized_visitor_label(language: str | None = "ja") -> str:
    """Return the neutral visitor label in the active prompt language."""
    lang = (language or "ja").strip().lower()
    if lang.startswith("en"):
        return "visitor"
    return "訪問者"


def _normalize_visitor_label(visitor_name: str | None, language: str = "ja") -> str:
    """Normalize legacy Visitor fallbacks into localized labels."""
    label = (visitor_name or "").strip()
    if not label or label.lower() == "visitor":
        return _localized_visitor_label(language)
    return label


def build_prompt(
    user_message: str,
    *,
    language: str = "ja",
    ticker: Optional[str] = None,
    pdf_title: Optional[str] = None,
    pdf_chunks: Optional[list[dict]] = None,
    pdf_summary: Optional[str] = None,
    pdf_page: Optional[int] = None,
    selected_section: Optional[str] = None,
    history: Optional[list[dict]] = None,
    current_url: Optional[str] = None,
    route: Optional[str] = None,
    recent_tickers: Optional[list[dict]] = None,
    feedback_context: Optional[list[dict]] = None,
    previous_chats: Optional[list[dict]] = None,
    visitor_name: str = "Visitor",
) -> str:
    """Build the full prompt sent to the AI, including context."""

    visitor_label = _normalize_visitor_label(visitor_name, language)
    parts = []

    parts.append(
        "## Visitor Identity\n"
        f"- Display label: {visitor_label}\n"
        "- Use only this server-provided label; do not infer or invent another identity.\n"
        "- If the label is a real name or ends with -san, address the visitor with that label when natural.\n"
        "- If the label is the localized neutral visitor label, prefer neutral second-person wording."
    )

    # Language instruction
    if language == "ja":
        parts.append("## 指示\n日本語で回答してください。")
    elif language == "en":
        parts.append("## Instruction\nPlease answer in English.")
    else:
        parts.append("## 指示\n日本語で回答してください。")

    # Current context — only include what helps the AI, not generic page info
    ctx_lines = ["## Current Context"]
    has_useful_context = False

    if ticker:
        ctx_lines.append(f"- Ticker: {ticker}")
        has_useful_context = True
    if pdf_title:
        ctx_lines.append(f"- Open PDF: {pdf_title}")
        has_useful_context = True
    if pdf_page:
        ctx_lines.append(f"- Current PDF page: {pdf_page}")
        has_useful_context = True
    if selected_section:
        ctx_lines.append(f"- Selected section: {selected_section}")
        has_useful_context = True

    # Only include route if it's a stock-specific page
    _USEFUL_ROUTES = ("/stock-analysis/", "/company-overview/", "/deep-dive/", "/transcript/")
    if route and any(r in route for r in _USEFUL_ROUTES):
        ctx_lines.append(f"- Page: {route}")
        has_useful_context = True

    # Recent tickers (RAG)
    if recent_tickers:
        ticker_lines = ["- Recently analyzed tickers:"]
        for rt in recent_tickers[:5]:
            pdfs = ", ".join(rt.get("pdfs", [])[:2]) or "no PDF"
            ticker_lines.append(f"  • {rt['ticker']} (analyzed {rt.get('date','?')}, PDFs: {pdfs})")
        ctx_lines.append("\n".join(ticker_lines))
        has_useful_context = True

    # Recent feedback & responses
    if feedback_context:
        fb_lines = ["- Recent feedback & actions:"]
        for fb in feedback_context[:8]:
            status_icon = {"open": "🔴", "pending": "🟡", "resolved": "🟢", "taken_into_account": "🟢"}.get(fb.get("status", ""), "⚪")
            fb_lines.append(f"  {status_icon} [{fb.get('type','?')}] {fb['content'][:120]}")
        ctx_lines.append("\n".join(fb_lines))
        has_useful_context = True

    # Previous chat sessions (same visitor_id)
    if previous_chats:
        chat_lines = ["- Previous conversations (same visitor_id):"]
        for pc in previous_chats[:3]:
            topics_str = " | ".join(pc.get("topics", [])[:2])
            chat_lines.append(f"  • {pc.get('date','?')} [{pc.get('ticker','no ticker')}]: {topics_str[:120]}")
        ctx_lines.append("\n".join(chat_lines))
        has_useful_context = True

    if not has_useful_context:
        ctx_lines.append("- The visitor is browsing the platform. No specific ticker or PDF is open.")
        ctx_lines.append("- Offer to help with: understanding reports, explaining metrics, or taking feedback.")

    parts.append("\n".join(ctx_lines))

    # PDF context
    if pdf_chunks:
        pdf_lines = ["## PDF Content (relevant excerpts)"]
        for i, chunk in enumerate(pdf_chunks, 1):
            section = chunk.get("section_title", "")
            page = chunk.get("page_start", "")
            page_ref = f" (p.{page})" if page else ""
            pdf_lines.append(f"\n### Excerpt {i}{page_ref}")
            if section:
                pdf_lines.append(f"Section: {section}")
            pdf_lines.append(chunk.get("content", ""))
        parts.append("\n".join(pdf_lines))
    elif pdf_summary:
        parts.append(f"## PDF Summary\n{pdf_summary}")
    elif pdf_title:
        parts.append("## PDF Content\n(No relevant excerpts found for this query.)")

    # Chat history
    if history and len(history) > 0:
        hist_lines = ["## Recent Conversation"]
        for msg in history[-10:]:
            role_label = visitor_label if msg["role"] == "user" else "Assistant"
            hist_lines.append(f"{role_label}: {msg['content']}")
        parts.append("\n".join(hist_lines))

    # User message
    message_heading = "Visitor Message" if language == "en" else "訪問者メッセージ"
    parts.append(f"## {message_heading}\n{user_message}")

    return "\n\n".join(parts)


# ── Streaming DeepSeek Call ──────────────────────────────────────────────────



# ── Chat Engine Configuration ───────────────────────────────────────────────

@dataclass(frozen=True)
class ChatEngineConfig:
    provider: str
    model: str
    api_key: str
    endpoint: str
    max_tokens: int
    temperature: float
    timeout_seconds: float


class ChatProviderUnavailable(RuntimeError):
    """Internal signal that the configured chat provider could not serve the request."""


_PROVIDER_ALIASES = {
    "google": "gemini",
    "google_gemini": "gemini",
    "google-gemini": "gemini",
}

_DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "deepseek": "deepseek-v4-pro",
    "gemini": "gemini-2.5-flash",
}

_OPENAI_COMPATIBLE_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer env for %s; using default", name)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float env for %s; using default", name)
        return default


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace(" ", "_")
    return _PROVIDER_ALIASES.get(normalized, normalized)


def _default_provider() -> str:
    explicit = os.getenv("SA_CHAT_PROVIDER", "").strip()
    if explicit:
        return _normalize_provider(explicit)
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        return "deepseek"
    if os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip():
        return "gemini"
    return "openai"


def _provider_api_key(provider: str) -> str:
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY", "").strip()
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_API_KEY", "").strip()
    if provider == "gemini":
        return (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
    return ""


def _chat_engine_config(*, provider: Optional[str] = None, model: Optional[str] = None) -> ChatEngineConfig:
    resolved_provider = _normalize_provider(provider or _default_provider())
    if resolved_provider not in _DEFAULT_MODELS:
        logger.warning("Unsupported SA chat provider %r; falling back to openai", resolved_provider)
        resolved_provider = "openai"

    resolved_model = (model or os.getenv("SA_CHAT_MODEL", "").strip() or _DEFAULT_MODELS[resolved_provider]).strip()
    if resolved_provider == "gemini":
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:streamGenerateContent"
    else:
        endpoint = _OPENAI_COMPATIBLE_ENDPOINTS[resolved_provider]

    return ChatEngineConfig(
        provider=resolved_provider,
        model=resolved_model,
        api_key=_provider_api_key(resolved_provider),
        endpoint=endpoint,
        max_tokens=_env_int("SA_CHAT_MAX_OUTPUT_TOKENS", 900),
        temperature=_env_float("SA_CHAT_TEMPERATURE", 0.15),
        timeout_seconds=_env_float("SA_CHAT_TIMEOUT_SECONDS", 120.0),
    )


def _client_facing_error(language: str = "ja") -> str:
    if language == "en":
        return "I'm sorry, the chat service is temporarily unavailable. Please try again shortly."
    return "申し訳ありません。現在チャットサービスが一時的に利用できません。しばらくしてからもう一度お試しください。"


def _fallback_providers(primary: str) -> list[str]:
    """Return provider fallback order without repeating the primary provider."""
    raw = os.getenv("SA_CHAT_FALLBACK_PROVIDERS", "gemini,openai,deepseek")
    providers: list[str] = []
    for item in raw.split(","):
        provider = _normalize_provider(item.strip())
        if provider and provider in _DEFAULT_MODELS and provider != primary and provider not in providers:
            providers.append(provider)
    return providers


def _config_for_attempt(provider: str, *, is_primary: bool) -> ChatEngineConfig:
    """Build config for primary/fallback attempts.

    SA_CHAT_MODEL is provider-specific in practice. Reusing a DeepSeek model name
    for a Gemini fallback would build an invalid endpoint, so fallback providers
    use their own safe defaults unless explicitly passed through provider-specific
    environment in a future extension.
    """
    return _chat_engine_config(
        provider=provider,
        model=None if is_primary else _DEFAULT_MODELS[provider],
    )


def _openai_compatible_payload(config: ChatEngineConfig, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "stream": True,
    }


def _gemini_payload(config: ChatEngineConfig, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": config.max_tokens,
            "temperature": config.temperature,
            # Gemini 2.5 may spend the whole output budget on hidden thinking,
            # yielding an empty visible answer. Disable thinking for live chat.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }


def _extract_openai_delta(data: dict[str, Any]) -> str:
    try:
        return data.get("choices", [{}])[0].get("delta", {}).get("content", "") or ""
    except (AttributeError, IndexError, TypeError):
        return ""


def _extract_gemini_delta(data: Any) -> str:
    if isinstance(data, list):
        return "".join(_extract_gemini_delta(item) for item in data)
    if not isinstance(data, dict):
        return ""
    chunks: list[str] = []
    for candidate in data.get("candidates", []) or []:
        content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and part.get("text"):
                chunks.append(str(part["text"]))
    return "".join(chunks)


async def _stream_openai_compatible(
    config: ChatEngineConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    language: str = "ja",
) -> AsyncGenerator[str, None]:
    import httpx  # type: ignore[import-not-found]

    if not config.api_key:
        logger.error("SA chat provider credentials missing for provider=%s", config.provider)
        raise ChatProviderUnavailable("missing_credentials")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.timeout_seconds)) as client:
            async with client.stream(
                "POST",
                config.endpoint,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=_openai_compatible_payload(config, system_prompt, user_prompt),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    logger.error("SA chat provider HTTP error provider=%s status=%s", config.provider, response.status_code)
                    raise ChatProviderUnavailable(f"http_{response.status_code}")

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        content = _extract_openai_delta(json.loads(data_str))
                    except json.JSONDecodeError:
                        continue
                    if content:
                        yield content
    except httpx.ReadTimeout as exc:
        logger.warning("SA chat stream timeout provider=%s", config.provider)
        raise ChatProviderUnavailable("timeout") from exc
    except ChatProviderUnavailable:
        raise
    except Exception as exc:
        logger.exception("SA chat stream error provider=%s", config.provider)
        raise ChatProviderUnavailable("stream_error") from exc


async def _stream_gemini(
    config: ChatEngineConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    language: str = "ja",
) -> AsyncGenerator[str, None]:
    import httpx  # type: ignore[import-not-found]

    if not config.api_key:
        logger.error("SA chat provider credentials missing for provider=%s", config.provider)
        raise ChatProviderUnavailable("missing_credentials")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(config.timeout_seconds)) as client:
            async with client.stream(
                "POST",
                config.endpoint,
                headers={
                    "x-goog-api-key": config.api_key,
                    "Content-Type": "application/json",
                },
                json=_gemini_payload(config, system_prompt, user_prompt),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    logger.error("SA chat provider HTTP error provider=%s status=%s", config.provider, response.status_code)
                    raise ChatProviderUnavailable(f"http_{response.status_code}")

                buffered_lines: list[str] = []
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data_str = line[6:] if line.startswith("data: ") else line
                    if data_str == "[DONE]":
                        return
                    try:
                        content = _extract_gemini_delta(json.loads(data_str))
                    except json.JSONDecodeError:
                        buffered_lines.append(data_str)
                        continue
                    if content:
                        yield content

                if buffered_lines:
                    try:
                        content = _extract_gemini_delta(json.loads("\n".join(buffered_lines)))
                    except json.JSONDecodeError as exc:
                        logger.warning("SA chat provider returned unparsable Gemini stream provider=%s", config.provider)
                        raise ChatProviderUnavailable("parse_error") from exc
                    if content:
                        yield content
    except httpx.ReadTimeout as exc:
        logger.warning("SA chat stream timeout provider=%s", config.provider)
        raise ChatProviderUnavailable("timeout") from exc
    except ChatProviderUnavailable:
        raise
    except Exception as exc:
        logger.exception("SA chat stream error provider=%s", config.provider)
        raise ChatProviderUnavailable("stream_error") from exc


async def stream_chat_engine(
    system_prompt: str,
    user_prompt: str,
    *,
    language: str = "ja",
) -> AsyncGenerator[str, None]:
    """Stream tokens from the configured chat provider with failover.

    A billing/rate-limit outage on the primary provider must not surface as the
    generic "temporarily unavailable" message when another configured provider
    can answer. This is especially important for the production chat widget.
    """
    primary = _normalize_provider(_default_provider())
    providers = [primary] + _fallback_providers(primary)
    last_error: Optional[Exception] = None

    for index, provider in enumerate(providers):
        config = _config_for_attempt(provider, is_primary=(index == 0))
        try:
            yielded_any = False
            if config.provider == "gemini":
                async for token in _stream_gemini(config, system_prompt, user_prompt, language=language):
                    yielded_any = True
                    yield token
            else:
                async for token in _stream_openai_compatible(config, system_prompt, user_prompt, language=language):
                    yielded_any = True
                    yield token
            if not yielded_any:
                raise ChatProviderUnavailable("empty_response")
            return
        except ChatProviderUnavailable as exc:
            last_error = exc
            logger.warning(
                "SA chat provider unavailable provider=%s reason=%s fallback_remaining=%s",
                config.provider,
                exc,
                len(providers) - index - 1,
            )
            continue

    if last_error:
        logger.error("All SA chat providers unavailable; returning client-facing fallback")
    yield _client_facing_error(language)

async def stream_deepseek(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> AsyncGenerator[str, None]:
    """Backward-compatible DeepSeek stream wrapper.

    New chat traffic should use stream_chat_engine(), but this wrapper preserves
    any direct internal callers without hard-coding model or endpoint details.
    """
    config = _chat_engine_config(provider="deepseek")
    config = ChatEngineConfig(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        endpoint=config.endpoint,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=config.timeout_seconds,
    )
    try:
        async for token in _stream_openai_compatible(config, system_prompt, user_prompt):
            yield token
    except ChatProviderUnavailable:
        yield _client_facing_error("ja")


async def stream_ai_response(
    user_message: str,
    *,
    language: str = "ja",
    ticker: Optional[str] = None,
    pdf_title: Optional[str] = None,
    pdf_chunks: Optional[list[dict]] = None,
    pdf_summary: Optional[str] = None,
    pdf_page: Optional[int] = None,
    selected_section: Optional[str] = None,
    history: Optional[list[dict]] = None,
    current_url: Optional[str] = None,
    route: Optional[str] = None,
    recent_tickers: Optional[list[dict]] = None,
    feedback_context: Optional[list[dict]] = None,
    previous_chats: Optional[list[dict]] = None,
    visitor_name: str = "Visitor",
) -> AsyncGenerator[str, None]:
    """Build prompt and stream the configured AI response. Main entry point."""
    visitor_label = _normalize_visitor_label(visitor_name, language)
    prompt = build_prompt(
        user_message,
        language=language,
        ticker=ticker,
        pdf_title=pdf_title,
        pdf_chunks=pdf_chunks,
        pdf_summary=pdf_summary,
        pdf_page=pdf_page,
        selected_section=selected_section,
        history=history,
        current_url=current_url,
        route=route,
        recent_tickers=recent_tickers,
        feedback_context=feedback_context,
        previous_chats=previous_chats,
        visitor_name=visitor_label,
    )
    system_prompt = SYSTEM_PROMPT

    async for token in stream_chat_engine(system_prompt, prompt, language=language):
        yield token
