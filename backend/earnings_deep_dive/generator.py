"""Synchronous orchestrator for earnings call deep-dive generation."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.earnings_deep_dive.errors import KimiFailureError, TranscriptMissingError, ValidationError
from backend.earnings_deep_dive.markdown import assemble_final_report, post_process_markdown
from backend.earnings_deep_dive.prompts import (
    SECTION_KEYWORDS,
    SECTION_ORDER,
    TABLE_SECTIONS,
    build_prompt,
    system_prompt,
)
from backend.earnings_deep_dive.schemas import DeepDiveRequest, DeepDiveResponse, SectionStatus
from backend.earnings_deep_dive.validators import (
    check_table_presence,
    detect_repetition_loop,
    is_bilingual,
    validate_section_heading,
)
from backend.codex_provider import _codex_chat as codex_chat
from backend.transcript_finder import find_transcripts

logger = logging.getLogger(__name__)


MAX_CODEX_TOKENS = 16000

def _llm_chat(prompt: str, system: str = "", max_tokens: int = MAX_CODEX_TOKENS) -> str | None:
    """DeepSeek (reliable, fast) → Codex GPT-5.5 (free but Cloudflare-blocked) → Gemini Flash Lite."""
    # 1. DeepSeek — paid, reliable ($0.27/M tokens), fast
    from backend.kimi_provider import _deepseek_chat
    result = _deepseek_chat(prompt, system, max_tokens)
    if result:
        return result
    # 2. Codex (GPT-5.5 via ChatGPT Plus) — free, but Cloudflare blocks cause hangs
    result = codex_chat(prompt, system=system, max_tokens=max_tokens)
    if result:
        return result
    # 3. Gemini Flash Lite — free, fallback (may 429/503 under load)
    from backend.gemini_provider import gemini_chat as _gemini
    return _gemini(prompt, system=system, max_tokens=max_tokens)

primary_chat = _llm_chat
SECTION_MAX_CHARS = 6000

SECTION_METRIC_KEYS = {
    "EPS & Revenue": {
        "eps_estimate",
        "eps_actual",
        "eps_vs_estimate",
        "eps_yoy",
        "revenue_estimate",
        "revenue_actual",
        "revenue_yoy",
    },
    "Highlights": {
        "eps_actual",
        "eps_estimate",
        "eps_vs_estimate",
        "revenue_actual",
        "revenue_estimate",
        "revenue_vs_estimate",
        "revenue_yoy",
        "gross_margin",
        "operating_margin",
        "guidance",
    },
    "Operating Metrics": {
        "gross_margin",
        "operating_margin",
        "operating_income",
        "revenue_yoy",
        "segments",
    },
    "Cash Flow": {
        "free_cash_flow",
        "operating_cash_flow",
        "capex",
        "net_debt",
    },
    "Capital Efficiency": {
        "roic",
        "roe",
        "free_cash_flow",
        "capex",
        "net_income",
    },
    "Segments": {
        "segments",
        "revenue_actual",
        "revenue_yoy",
        "gross_margin",
    },
    "Forward P/E": {
        "pe_forward",
        "eps_actual",
        "eps_estimate",
        "revenue_yoy",
        "guidance",
    },
    "Backlog": {
        "backlog",
        "guidance",
        "revenue_actual",
    },
    "Guidance": {
        "guidance",
        "revenue_estimate",
        "eps_estimate",
        "revenue_yoy",
        "pe_forward",
    },
    "Verdict": {
        "eps_actual",
        "revenue_actual",
        "revenue_yoy",
        "free_cash_flow",
        "pe_forward",
        "backlog",
        "guidance",
    },
}


def generate_deep_dive(request: DeepDiveRequest) -> DeepDiveResponse:
    """Generate a section-by-section earnings call deep-dive and save it to the dossier."""
    if request.language == "bilingual":
        en_response = _generate_deep_dive_single(
            request.model_copy(update={"language": "en", "output_dir": os.path.join(request.output_dir, "en")})
        )
        jp_response = _generate_deep_dive_single(
            request.model_copy(update={"language": "jp", "output_dir": os.path.join(request.output_dir, "jp")})
        )
        return DeepDiveResponse(
            ticker=en_response.ticker,
            company=en_response.company,
            quarter=en_response.quarter,
            language="bilingual",
            audience_mode=request.audience_mode,
            transcript_url=request.transcript_url or en_response.transcript_url or jp_response.transcript_url,
            markdown_path=en_response.markdown_path,
            meta_path=en_response.meta_path,
            report_markdown=(
                "# Earnings Call Deep-Dive (Bilingual)\n\n"
                "## English\n\n"
                f"{en_response.report_markdown.strip()}\n\n"
                "## Japanese\n\n"
                f"{jp_response.report_markdown.strip()}\n"
            ),
            sections={"en": en_response.report_markdown, "jp": jp_response.report_markdown},
            statuses=en_response.statuses + jp_response.statuses,
            warnings=en_response.warnings + jp_response.warnings,
        )
    return _generate_deep_dive_single(request)


def _generate_deep_dive_single(request: DeepDiveRequest) -> DeepDiveResponse:
    """Generate one language variant of an earnings call deep-dive."""
    company = request.company or request.ticker
    output_dir = request.output_dir
    metrics = _normalize_metrics(request.metrics.model_dump(mode="json"))
    warnings: List[str] = []
    sections: Dict[str, str] = {}
    statuses: List[SectionStatus] = []

    try:
        transcript_text, transcript_meta = _load_transcript(request)
    except TranscriptMissingError as exc:
        transcript_text = ""
        transcript_meta = {"found": False, "error": str(exc)}
        # Extract URL from error message if present (e.g. paywalled transcript)
        import re as _re
        url_match = _re.search(r"URL: (https?://\S+)", str(exc))
        if url_match:
            transcript_meta["url"] = url_match.group(1)

    excerpts = {
        section: _extract_relevant_excerpt(transcript_text, SECTION_KEYWORDS[section])
        for section in SECTION_ORDER
    }
    
    has_tx = bool(transcript_text)
    
    def _gen_batch(
        secs: List[str],
        provider_name: str,
        chat_fn,
    ) -> Tuple[Dict[str, str], List[SectionStatus], List[str]]:
        """Generate a batch of sections in PARALLEL (max 3 concurrent) with a specific provider."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        batch_sections: Dict[str, str] = {}
        batch_statuses: List[SectionStatus] = []
        batch_warnings: List[str] = []
        
        def _process_section(section: str) -> Tuple[str, SectionStatus, Optional[str]]:
            """Process a single section with retry. Thread-safe."""
            sector = str(metrics.get("sector", "") or "")
            industry = str(metrics.get("industry", "") or "")
            sys_prompt = system_prompt(request.language, sector, industry)
            last_error = ""
            
            for attempt in (1, 2):
                prompt = build_prompt(
                    section, request.language, request.ticker, company,
                    request.quarter, _section_metrics(section, metrics),
                    excerpts[section],
                    sector=sector,
                    industry=industry,
                )
                if attempt == 2:
                    prompt += (
                        "\nRetry instruction: fix the previous malformed output. "
                        "Keep the exact required heading, avoid repeated lines, "
                        "and follow table requirements.\n"
                    )
                
                try:
                    try:
                        output = chat_fn(prompt, system=sys_prompt, max_tokens=MAX_CODEX_TOKENS, temperature=0.3)
                    except TypeError:
                        output = chat_fn(prompt, system=sys_prompt, max_tokens=MAX_CODEX_TOKENS)
                    if not output:
                        raise KimiFailureError(f"{provider_name} returned no content")
                    
                    cleaned = _clean_section_output(output, request.max_section_chars, request.audience_mode)
                    _validate_section(
                        cleaned, section, request.language,
                        request.max_section_chars, require_table=has_tx,
                    )
                    return cleaned, SectionStatus(
                        name=section,
                        status="ok" if attempt == 1 else "retry_ok",
                        attempts=attempt,
                    ), None
                except (KimiFailureError, ValidationError) as exc:
                    last_error = str(exc)
            
            # Failed after retries
            return _placeholder_section(section, last_error), SectionStatus(
                name=section, status="failed", attempts=2, error=last_error or "failed",
            ), f"{section}: {last_error or 'section unavailable'}"
        
        # ── Parallel execution (3 workers = safe for Gemini 30 RPM with 2.5s throttle) ──
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_process_section, s): s for s in secs}
            for future in as_completed(futures):
                content, status, warning = future.result()
                batch_sections[status.name] = content
                batch_statuses.append(status)
                if warning:
                    batch_warnings.append(warning)
        
        return batch_sections, batch_statuses, batch_warnings
    
    # The wrapper keeps retries and provider fallback behavior patchable in tests.
    sections_a_dict, statuses_a, warnings_a = _gen_batch(list(SECTION_ORDER), "primary", primary_chat)
    sections_b_dict, statuses_b, warnings_b = {}, [], []
    
    # Merge in original order
    for section in SECTION_ORDER:
        if section in sections_a_dict:
            sections[section] = sections_a_dict[section]
        elif section in sections_b_dict:
            sections[section] = sections_b_dict[section]
    statuses = statuses_a + statuses_b
    warnings = warnings_a + warnings_b
    # Keep existing warnings from status failures
    for status in statuses:
        if status.status in {"failed", "placeholder"} and status.name not in [w.split(":")[0] for w in warnings]:
            warnings.append(f"{status.name}: {status.error or 'section unavailable'}")

    transcript_url = request.transcript_url or transcript_meta.get("url") or transcript_meta.get("transcript_url")
    transcript_source = transcript_meta.get("primary_source") or transcript_meta.get("source") or ""
    company_website = _company_website_from_metrics(metrics)
    report_markdown = _append_sources_section(
        post_process_markdown(
            assemble_final_report(sections, warnings=warnings, company_website=company_website)
        ),
        transcript_url,
        company_website,
        transcript_source=transcript_source,
    )
    # Final pass: sanitize assembled report for audience mode
    report_markdown = _sanitize_for_audience(report_markdown, request.audience_mode)
    markdown_path, meta_path = _save_outputs(
        output_dir=output_dir,
        request=request,
        company=company,
        report_markdown=report_markdown,
        sections=sections,
        statuses=statuses,
        warnings=warnings,
        transcript_meta=transcript_meta,
        transcript_url=transcript_url,
        transcript_text=transcript_text,
    )

    return DeepDiveResponse(
        ticker=request.ticker,
        company=company,
        quarter=request.quarter,
        language=request.language,
        audience_mode=request.audience_mode,
        transcript_url=transcript_url,
        markdown_path=markdown_path,
        meta_path=meta_path,
        report_markdown=report_markdown,
        sections=sections,
        statuses=statuses,
        warnings=warnings,
    )


def _generate_section(
    *,
    section: str,
    request: DeepDiveRequest,
    company: str,
    metrics: Dict[str, Any],
    transcript_excerpt: str,
    has_transcript: bool,
) -> Tuple[str, SectionStatus]:
    last_error = ""
    # Extract sector/industry for sector-aware prompting
    sector = str(metrics.get("sector", "") or "")
    industry = str(metrics.get("industry", "") or "")
    sys_prompt = system_prompt(request.language, sector, industry)

    for attempt in (1, 2):
        prompt = build_prompt(
            section,
            request.language,
            request.ticker,
            company,
            request.quarter,
            _section_metrics(section, metrics),
            transcript_excerpt,
            sector=sector,
            industry=industry,
        )
        if attempt == 2:
            prompt += (
                "\nRetry instruction: fix the previous malformed output. "
                "Keep the exact required heading, avoid repeated lines, and follow table requirements.\n"
            )

        try:
            output = primary_chat(prompt, system=sys_prompt, max_tokens=MAX_CODEX_TOKENS)
            if not output:
                raise KimiFailureError("LLM returned no content")
            cleaned = _clean_section_output(output, request.max_section_chars, request.audience_mode)
            _validate_section(
                cleaned,
                section,
                request.language,
                request.max_section_chars,
                require_table=has_transcript,
            )
            return cleaned, SectionStatus(
                name=section,
                status="ok" if attempt == 1 else "retry_ok",
                attempts=attempt,
            )
        except (KimiFailureError, ValidationError) as exc:
            last_error = str(exc)

    return _placeholder_section(section, last_error), SectionStatus(
        name=section,
        status="failed",
        attempts=2,
        error=last_error or "Section generation failed",
    )


def _normalize_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in metrics.items():
        if value is None:
            normalized[key] = "Not disclosed"
        elif isinstance(value, dict):
            normalized[key] = value or "Not disclosed"
        else:
            normalized[key] = value
    return normalized


def _section_metrics(section: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    keys = SECTION_METRIC_KEYS[section]
    relevant = {key: metrics.get(key, "Not disclosed") for key in keys}
    disclosed = {key: value for key, value in relevant.items() if value != "Not disclosed"}
    return disclosed or relevant


def _load_transcript(request: DeepDiveRequest) -> Tuple[str, Dict[str, Any]]:
    if request.transcript_text and request.transcript_text.strip():
        # Extract source name from URL or fall back to generic label
        source_name = "Earnings Call Transcript"
        source_url = request.transcript_url or ""
        if source_url:
            from urllib.parse import urlparse
            domain = urlparse(source_url).netloc.replace("www.", "")
            domain_map = {
                "fool.com": "The Motley Fool",
                "seekingalpha.com": "Seeking Alpha",
                "stockanalysis.com": "Seeking Alpha",
                "alphavantage.co": "Alpha Vantage",
            }
            source_name = domain_map.get(domain, domain.split(".")[0].title())
        return request.transcript_text.strip(), {
            "found": True,
            "source": source_name,
            "primary_source": source_name,
            "url": source_url,
        }

    try:
        results = find_transcripts(request.ticker, output_dir=request.output_dir, company=request.company)
    except TypeError as exc:
        if "company" not in str(exc):
            raise
        results = find_transcripts(request.ticker, output_dir=request.output_dir)
    sources = results.get("sources", []) if isinstance(results, dict) else []
    transcript_text, transcript_source = _best_transcript(sources)
    
    # Extract best URL from sources (even when text is unavailable/paywalled)
    best_url = transcript_source.get("url") or transcript_source.get("link") or ""
    if not best_url:
        for src in sources:
            url = src.get("url") or src.get("link") or ""
            if url:
                best_url = url
                break
    
    if transcript_text:
        return transcript_text, {
            "found": True,
            "source_count": len(sources),
            "primary_source": _primary_source_name(sources),
            "url": best_url,
        }
    # No usable text — but if we have URLs, pass them through for source attribution
    if best_url:
        raise TranscriptMissingError(
            f"No usable transcript text found for {request.ticker} "
            f"(paywalled or inaccessible). URL: {best_url[:120]}"
        )
    raise TranscriptMissingError(f"No usable earnings call transcript found for {request.ticker}")


def _best_transcript_text(sources: Iterable[Dict[str, Any]]) -> str:
    best, _ = _best_transcript(sources)
    return best


def _best_transcript(sources: Iterable[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    best = ""
    best_source: Dict[str, Any] = {}
    for source in sources:
        text = source.get("text") or source.get("content") or source.get("transcript") or ""
        if isinstance(text, list):
            text = "\n".join(str(item) for item in text)
        if isinstance(text, str) and len(text.strip()) > len(best):
            best = text.strip()
            best_source = source
    return best, best_source


def _primary_source_name(sources: Iterable[Dict[str, Any]]) -> str:
    for source in sources:
        if source.get("text") or source.get("content") or source.get("transcript"):
            return str(source.get("source") or source.get("title") or "unknown")
    return "unknown"


def _extract_relevant_excerpt(transcript: str, keywords: List[str], max_chars: int = 1600) -> str:
    if not transcript:
        return ""

    blocks = _split_transcript_blocks(transcript)
    scored = []
    for idx, block in enumerate(blocks):
        lower = block.lower()
        score = sum(1 for keyword in keywords if keyword.lower() in lower)
        if score:
            scored.append((score, idx, block.strip()))

    if not scored:
        return _truncate_clean(" ".join(blocks[:4]), max_chars)

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: List[Tuple[int, str]] = []
    char_count = 0
    for _, idx, block in scored:
        if char_count + len(block) > max_chars and selected:
            continue
        selected.append((idx, block))
        char_count += len(block)
        if char_count >= max_chars:
            break

    selected.sort(key=lambda item: item[0])
    return _truncate_clean("\n\n".join(block for _, block in selected), max_chars)


def _split_transcript_blocks(transcript: str) -> List[str]:
    text = re.sub(r"\r\n?", "\n", transcript)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paragraphs) >= 4:
        return paragraphs

    sentences = re.split(r"(?<=[.!?])\s+", text)
    blocks: List[str] = []
    current: List[str] = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        current.append(sentence.strip())
        if len(" ".join(current)) >= 350:
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return blocks or [text.strip()]


def _validate_section(
    markdown: str,
    section: str,
    language: str,
    max_chars: int = SECTION_MAX_CHARS,
    *,
    require_table: bool = True,
) -> None:
    if not validate_section_heading(markdown, section):
        raise ValidationError(f"Missing required heading: ## {section}")
    if detect_repetition_loop(markdown):
        raise ValidationError("Repetition loop detected")
    if require_table and section in TABLE_SECTIONS and not check_table_presence(markdown):
        raise ValidationError(f"Missing required markdown table for {section}")
    if is_bilingual(markdown, language):
        raise ValidationError("Bilingual output detected")
    if len(markdown) > max_chars:
        raise ValidationError(f"Section exceeds {max_chars} characters")


def _clean_section_output(output: str, max_chars: int, audience_mode: str = "nami_personal") -> str:
    cleaned = output.strip().rstrip("!").rstrip()
    # Fix unicode linebreak in "For\nNami-san"
    cleaned = cleaned.replace("For\nNami-san", "For Nami-san")
    # Strip replacement character
    cleaned = cleaned.replace("\ufffd", "")
    # Audience mode sanitization
    cleaned = _sanitize_for_audience(cleaned, audience_mode)
    if len(cleaned) <= max_chars:
        return cleaned
    return _truncate_clean(cleaned, max_chars)


AUDIENCE_NAMI_PATTERNS: list[tuple[str, str]] = [
    # (pattern to match, replacement for non-nami modes)
    ("For Nami-san:", "For investors:"),
    ("For Nami-san", "For investors"),
    ("Essential insight for Nami-san:", "Essential insight for investors:"),
    ("Essential insight for Nami-san", "Essential insight for investors"),
    ("🧠 Namiさん向けの本質理解:", "🧠 投資家向けの本質理解:"),
    ("🧠 Namiさん向け解釈:", "🧠 投資家向け解釈:"),
    ("Nami-san takeaway", "Investor takeaway"),
    ("Nami insight", "Investor insight"),
    ("Nami takeaway", "Investor takeaway"),
    ("For Nami-san, this is a", "For investors, this is a"),
    ("For Nami-san:", "For investors:"),
    ("\ud83c\udfc6 Overall assessment for Nami-san", "\ud83c\udfc6 Overall assessment"),
    ("Namiさん向け", "投資家向け"),
    ("Nami-san", ""),  # standalone Nami-san → remove (catch-all, last)
]
MISSING_DATA_REPLACEMENTS: list[tuple[str, str]] = [
    ("Not retrieved from transcript", "Not verified from reviewed sources"),
    ("not retrieved from transcript", "not verified from reviewed sources"),
    ("Not retrieved", "Not disclosed"),
    ("not retrieved", "not disclosed"),
]


def _sanitize_for_audience(text: str, audience_mode: str) -> str:
    """Post-generation sanitizer: strip Nami language for non-nami modes,
    and normalize missing-data language."""
    
    # Missing-data normalization (all modes)
    for pattern, replacement in MISSING_DATA_REPLACEMENTS:
        text = text.replace(pattern, replacement)
    
    # Audience mode: strip Nami language for non-nami modes
    if audience_mode != "nami_personal":
        for pattern, replacement in AUDIENCE_NAMI_PATTERNS:
            text = text.replace(pattern, replacement)
    
    return text


def _truncate_clean(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text.strip()
    truncated = text[:max_chars].rsplit(" ", 1)[0].strip()
    return truncated


def _placeholder_section(section: str, reason: str) -> str:
    reason_map = {
        "primary_returned_no_content": "Unavailable from reviewed sources",
        "no_transcript": "Unavailable from reviewed sources",
        "no_content": "Unavailable from reviewed sources",
    }
    clean_reason = reason_map.get(reason, "Unavailable from reviewed sources")
    return f"## {section}\n\n- {clean_reason}."


def _company_website_from_metrics(metrics: Dict[str, Any]) -> str | None:
    for key in ("company_website", "website", "weburl", "official_website"):
        value = metrics.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _append_sources_section(
    report_markdown: str,
    transcript_url: str | None,
    company_website: str | None = None,
    transcript_source: str | None = None,
) -> str:
    if not transcript_url and not company_website:
        return report_markdown
    lines = [report_markdown.rstrip(), "", "## Sources", ""]
    if transcript_url:
        source_label = transcript_source or "Earnings Call Transcript"
        lines.append(f"- **Transcript:** [{source_label}]({transcript_url})")
    if company_website:
        lines.append(f"- **Official Website:** {company_website}")
    return "\n".join(lines) + "\n"


def _save_outputs(
    *,
    output_dir: str,
    request: DeepDiveRequest,
    company: str,
    report_markdown: str,
    sections: Dict[str, str],
    statuses: List[SectionStatus],
    warnings: List[str],
    transcript_meta: Dict[str, Any],
    transcript_url: str | None,
    transcript_text: str = "",
) -> Tuple[str, str]:
    report_dir = os.path.join(output_dir, "07_final_report")
    os.makedirs(report_dir, exist_ok=True)

    markdown_path = os.path.join(report_dir, "earnings_deep_dive.md")
    meta_path = os.path.join(report_dir, "earnings_deep_dive_meta.json")

    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(report_markdown)

    meta = {
        "ticker": request.ticker,
        "company": company,
        "quarter": request.quarter,
        "language": request.language,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "Codex CLI local",
        "max_tokens_per_call": MAX_CODEX_TOKENS,
        "sections": {status.name: status.model_dump() for status in statuses},
        "warnings": warnings,
        "transcript_url": transcript_url,
        "transcript": transcript_meta,
        "output_files": {
            "markdown": markdown_path,
            "meta": meta_path,
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, default=str)
    
    # Save verbatim transcript with source citation in 04_transcripts_and_management
    if transcript_text.strip():
        source_name = transcript_meta.get("primary_source") or transcript_meta.get("source") or "Unknown"
        source_url = transcript_url or ""
        _save_verbatim_transcript(
            output_dir=output_dir,
            ticker=request.ticker,
            transcript_text=transcript_text,
            source_name=source_name,
            source_url=source_url,
        )

    return markdown_path, meta_path


def _save_verbatim_transcript(
    output_dir: str,
    ticker: str,
    transcript_text: str,
    source_name: str,
    source_url: str,
) -> str:
    """Save the verbatim earnings call transcript with source citation."""
    trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
    os.makedirs(trans_dir, exist_ok=True)
    
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    # Sanitize source name for filename
    safe_source = re.sub(r"[^a-zA-Z0-9]", "_", source_name)[:30]
    filename = f"transcript_{ticker}_{safe_source}_{date_str}.txt"
    filepath = os.path.join(trans_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {ticker} — Earnings Call Transcript\n\n")
        f.write(f"**Source:** {source_name}\n")
        f.write(f"**URL:** {source_url}\n")
        f.write(f"**Ticker:** {ticker}\n")
        f.write(f"**Retrieved:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write("---\n\n")
        f.write("## Verbatim Transcript\n\n")
        f.write(transcript_text)
    
    logger.info(f"Verbatim transcript saved: {filepath} ({len(transcript_text)} chars, source={source_name})")
    return filepath
