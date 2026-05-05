"""Synchronous orchestrator for earnings call deep-dive generation."""
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from backend.earnings_deep_dive.errors import KimiFailureError, TranscriptMissingError, ValidationError
from backend.earnings_deep_dive.markdown import assemble_final_report
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
from backend.kimi_provider import kimi_chat
from backend.transcript_finder import find_transcripts


MAX_KIMI_TOKENS = 400
SECTION_MAX_CHARS = 2400

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
        "revenue_actual",
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
        warnings.append(str(exc))

    excerpts = {
        section: _extract_relevant_excerpt(transcript_text, SECTION_KEYWORDS[section])
        for section in SECTION_ORDER
    }

    for section in SECTION_ORDER:
        if not transcript_text:
            sections[section] = _placeholder_section(section, "Transcript missing")
            statuses.append(
                SectionStatus(
                    name=section,
                    status="placeholder",
                    attempts=0,
                    error="Transcript missing",
                    warnings=["Transcript missing; section was not sent to Kimi."],
                )
            )
            continue

        section_markdown, status = _generate_section(
            section=section,
            request=request,
            company=company,
            metrics=metrics,
            transcript_excerpt=excerpts[section],
        )
        sections[section] = section_markdown
        statuses.append(status)
        if status.status in {"failed", "placeholder"}:
            warnings.append(f"{section}: {status.error or 'section unavailable'}")

    report_markdown = assemble_final_report(sections, warnings=warnings)
    markdown_path, meta_path = _save_outputs(
        output_dir=output_dir,
        request=request,
        company=company,
        report_markdown=report_markdown,
        sections=sections,
        statuses=statuses,
        warnings=warnings,
        transcript_meta=transcript_meta,
    )

    return DeepDiveResponse(
        ticker=request.ticker,
        company=company,
        quarter=request.quarter,
        language=request.language,
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
) -> Tuple[str, SectionStatus]:
    last_error = ""
    sys_prompt = system_prompt(request.language)

    for attempt in (1, 2):
        prompt = build_prompt(
            section,
            request.language,
            request.ticker,
            company,
            request.quarter,
            _section_metrics(section, metrics),
            transcript_excerpt,
        )
        if attempt == 2:
            prompt += (
                "\nRetry instruction: fix the previous malformed output. "
                "Keep the exact required heading, avoid repeated lines, and follow table requirements.\n"
            )

        try:
            output = kimi_chat(prompt, system=sys_prompt, max_tokens=MAX_KIMI_TOKENS, temperature=0.0)
            if not output:
                raise KimiFailureError("Kimi returned no content")
            cleaned = _clean_section_output(output, request.max_section_chars)
            _validate_section(cleaned, section, request.language, request.max_section_chars)
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
    return {key: value for key, value in relevant.items() if value != "Not disclosed"} or {"data": "Not disclosed"}


def _load_transcript(request: DeepDiveRequest) -> Tuple[str, Dict[str, Any]]:
    if request.transcript_text and request.transcript_text.strip():
        return request.transcript_text.strip(), {"found": True, "source": "request.transcript_text"}

    results = find_transcripts(request.ticker, output_dir=request.output_dir)
    sources = results.get("sources", []) if isinstance(results, dict) else []
    transcript_text = _best_transcript_text(sources)
    if transcript_text:
        return transcript_text, {
            "found": True,
            "source_count": len(sources),
            "primary_source": _primary_source_name(sources),
        }
    raise TranscriptMissingError(f"No usable earnings call transcript found for {request.ticker}")


def _best_transcript_text(sources: Iterable[Dict[str, Any]]) -> str:
    best = ""
    for source in sources:
        text = source.get("text") or source.get("content") or source.get("transcript") or ""
        if isinstance(text, list):
            text = "\n".join(str(item) for item in text)
        if isinstance(text, str) and len(text.strip()) > len(best):
            best = text.strip()
    return best


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


def _validate_section(markdown: str, section: str, language: str, max_chars: int = SECTION_MAX_CHARS) -> None:
    if not validate_section_heading(markdown, section):
        raise ValidationError(f"Missing required heading: ## {section}")
    if detect_repetition_loop(markdown):
        raise ValidationError("Repetition loop detected")
    if section in TABLE_SECTIONS and not check_table_presence(markdown):
        raise ValidationError(f"Missing required markdown table for {section}")
    if is_bilingual(markdown, language):
        raise ValidationError("Bilingual output detected")
    if len(markdown) > max_chars:
        raise ValidationError(f"Section exceeds {max_chars} characters")


def _clean_section_output(output: str, max_chars: int) -> str:
    cleaned = output.strip().rstrip("!").rstrip()
    if len(cleaned) <= max_chars:
        return cleaned
    return _truncate_clean(cleaned, max_chars)


def _truncate_clean(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text.strip()
    truncated = text[:max_chars].rsplit(" ", 1)[0].strip()
    return truncated


def _placeholder_section(section: str, reason: str) -> str:
    reason_text = reason or "Section unavailable"
    return f"## {section}\n\n- Section unavailable. Not disclosed.\n- Reason: {reason_text}"


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
        "provider": "Kimi K2.6",
        "max_tokens_per_call": MAX_KIMI_TOKENS,
        "sections": {status.name: status.model_dump() for status in statuses},
        "warnings": warnings,
        "transcript": transcript_meta,
        "output_files": {
            "markdown": markdown_path,
            "meta": meta_path,
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, default=str)

    return markdown_path, meta_path
