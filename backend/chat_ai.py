"""AI service for the live chat widget.

Builds the system prompt, calls DeepSeek with streaming,
and saves the final response.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncGenerator, Optional

import logging

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = r"""You are Nami's AI assistant inside Ced's Stock Analysis platform.

## Your Role
Your job is to help Nami understand stock analysis reports, ticker pages, PDFs, risks,
assumptions, financial metrics, product UX, bugs, and confusing parts of the platform.

## Default Language
- Always answer in Japanese by default.
- Switch to English ONLY if Nami explicitly asks for English
  (e.g. "Please answer in English").
- If Nami writes a short English sentence but does NOT request English, continue in Japanese.
- If Nami asks to switch back to Japanese (e.g. "日本語に戻して"), switch back immediately.
- Never answer in French to the client.

## Tone
- Patient and warm.
- Friendly but polite (ていねい).
- Professional and clear.
- Helpful and calm.
- Never passive, never dismissive, never cold, never arrogant.

## Conversation Behavior
- Do NOT merely say "OK", "thanks", or "noted" — always add value.
- If the request is CLEAR → answer directly, then offer a useful next step.
- If the request is AMBIGUOUS → briefly reformulate what you understood,
  then ask ONE or TWO targeted clarification questions.
- Do NOT ask questions just to ask questions.
- Ask at most 3 clarification questions at once. Prefer one precise useful question.

## Bug Reports
If Nami reports something not working:
- Apologize briefly for the inconvenience (in Japanese: 不便をかけてしまってすみません).
- Ask for: URL, browser, steps to reproduce, expected behavior, actual behavior.
- Ask for a screenshot if possible.
- Say that you'll flag this for Ced to review.

## UX Feedback
If Nami gives UX feedback:
- Thank her for the feedback.
- Ask what she expected to see.
- Ask which part was confusing.
- Ask for a concrete example if vague.

## Stock / PDF Questions
- If Nami asks about a stock but no ticker is available → ask which ticker.
- If Nami asks about a PDF and PDF context is provided → use it.
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

## Important
- Keep answers structured and readable.
- For complex analysis, use short sections.
- Avoid overly long paragraphs.
- Be supportive and clear.
- End with a useful next step or one targeted clarification question when appropriate.
- The CURRENT CONTEXT section below provides real-time info about the page Nami is viewing.
"""


def build_prompt(
    user_message: str,
    *,
    language: str = "ja",
    ticker: Optional[str] = None,
    pdf_title: Optional[str] = None,
    pdf_chunks: Optional[list[dict]] = None,
    pdf_summary: Optional[str] = None,
    history: Optional[list[dict]] = None,
    current_url: Optional[str] = None,
    route: Optional[str] = None,
) -> str:
    """Build the full prompt sent to the AI, including context."""

    parts = []

    # Language instruction
    if language == "ja":
        parts.append("## 指示\n日本語で回答してください。")
    elif language == "en":
        parts.append("## Instruction\nPlease answer in English.")
    else:
        parts.append("## 指示\n日本語で回答してください。")

    # Current context
    ctx_lines = ["## Current Context"]
    if ticker:
        ctx_lines.append(f"- Ticker: {ticker}")
    if current_url:
        ctx_lines.append(f"- Page URL: {current_url}")
    if route:
        ctx_lines.append(f"- Route: {route}")
    if pdf_title:
        ctx_lines.append(f"- Open PDF: {pdf_title}")
    if not ticker and not pdf_title:
        ctx_lines.append("- No specific ticker or PDF is currently open.")
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
            role_label = "Nami" if msg["role"] == "user" else "Assistant"
            hist_lines.append(f"{role_label}: {msg['content']}")
        parts.append("\n".join(hist_lines))

    # User message
    parts.append(f"## Nami's Message\n{user_message}")

    return "\n\n".join(parts)


# ── Streaming DeepSeek Call ──────────────────────────────────────────────────

async def stream_deepseek(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> AsyncGenerator[str, None]:
    """Stream tokens from DeepSeek API. Yields content deltas."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        yield "[ERROR: DeepSeek API key not configured]"
        return

    import httpx

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream(
                "POST",
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error(f"DeepSeek HTTP {response.status_code}: {body[:500]}")
                    yield f"[ERROR: DeepSeek returned {response.status_code}]"
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.ReadTimeout:
        logger.warning("DeepSeek stream timeout")
        yield "\n\n[応答がタイムアウトしました。もう一度お試しください。]"
    except Exception as e:
        logger.error(f"DeepSeek stream error: {e}")
        yield f"\n\n[エラーが発生しました: {type(e).__name__}]"


async def stream_ai_response(
    user_message: str,
    *,
    language: str = "ja",
    ticker: Optional[str] = None,
    pdf_title: Optional[str] = None,
    pdf_chunks: Optional[list[dict]] = None,
    pdf_summary: Optional[str] = None,
    history: Optional[list[dict]] = None,
    current_url: Optional[str] = None,
    route: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Build prompt, stream AI response. Main entry point."""
    prompt = build_prompt(
        user_message,
        language=language,
        ticker=ticker,
        pdf_title=pdf_title,
        pdf_chunks=pdf_chunks,
        pdf_summary=pdf_summary,
        history=history,
        current_url=current_url,
        route=route,
    )
    async for token in stream_deepseek(SYSTEM_PROMPT, prompt):
        yield token
