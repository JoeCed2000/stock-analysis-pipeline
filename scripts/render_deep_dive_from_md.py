#!/usr/bin/env python3
"""Render an earnings deep-dive PDF from an existing earnings_deep_dive.md.

Re-uses the LLM sections already on disk — no LLM call. Mirrors the render
block of GET /api/report/{ticker}/pdf (backend/main.py): fresh metrics from
get_yahoo_data, IR enrichment, company overview, two-stage pre-render
validation, then render_earnings_deep_dive_pdf. The existing PDF (if any) is
moved to a .bak file before the new one lands (the GET endpoint only
regenerates when the PDF is absent from the resolved directory).

Usage:
    python scripts/render_deep_dive_from_md.py \
        analyses/<dossier>/07_final_report/earnings_deep_dive.md \
        --ticker NVDA --quarter "FY2026 Q1" [--lang en]

--quarter must be the tag of the ORIGINAL request: the mapper's prose repair
replaces that tag with the authoritative fiscal label wherever it leaked.
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Canonical .md headings (deep_dive_validator normalization) → template keys.
HEADING_TO_KEY = {
    "EPS & Revenue": "EPS & Revenue",
    "Highlights & Lowlights": "Highlights",
    "Operating Metrics": "Operating Metrics",
    "Cash Flow": "Cash Flow",
    "Capital Efficiency": "Capital Efficiency",
    "Segments": "Segments",
    "Forward P/E": "Forward P/E",
    "Backlog Quality": "Backlog",
    "Guidance": "Guidance",
    "Verdict": "Verdict",
}


def parse_sections(md_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for part in re.split(r"(?m)^## ", md_text)[1:]:
        heading, _, body = part.partition("\n")
        key = HEADING_TO_KEY.get(heading.strip())
        if key:
            sections[key] = body.strip()
    return sections


async def amain() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("md_path", type=Path)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--quarter", required=True,
                    help="quarter tag of the original request")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    md_path = args.md_path.resolve()
    if not md_path.exists():
        print(f"ERROR: {md_path} not found", file=sys.stderr)
        return 1
    ticker = args.ticker.strip().upper()
    report_dir = md_path.parent
    pdf_path = report_dir / "earnings_deep_dive.pdf"
    meta_path = report_dir / "earnings_deep_dive_meta.json"

    # Heading normalization + validation verdict on the source markdown.
    from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive
    passed, issues = validate_deep_dive(str(md_path))
    if not passed:
        print(f"ERROR: markdown validation failed: {issues}", file=sys.stderr)
        return 1

    sections = parse_sections(md_path.read_text(encoding="utf-8"))
    if len(sections) < 8:
        print(f"ERROR: only {len(sections)} sections parsed: {sorted(sections)}",
              file=sys.stderr)
        return 1

    transcript_url = None
    if meta_path.exists():
        try:
            transcript_url = json.loads(meta_path.read_text()).get("transcript_url")
        except Exception:
            pass

    from backend.sources_collector import get_yahoo_data
    from backend.pipeline import (
        _deep_dive_metrics, _investor_relations_url, _company_website,
        _extract_next_earnings_from_ir, _extract_audio_webcast_from_ir,
    )
    from backend.models import AnalysisResult

    q_data = get_yahoo_data(ticker)
    if not q_data:
        print("ERROR: yahoo data unavailable", file=sys.stderr)
        return 1
    dummy = AnalysisResult(
        ticker=ticker,
        company_name=q_data.get("company_name", ticker),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        price=q_data.get("price"),
        currency=q_data.get("currency", "USD"),
        sector=q_data.get("sector"),
    )
    metrics = _deep_dive_metrics(dummy, q_data)
    fiscal_label = getattr(metrics, "fiscal_period_label", None)
    print(f"fiscal_period_label: {fiscal_label}")

    website = _company_website(q_data)
    investor_relations = _investor_relations_url(q_data)
    if investor_relations:
        metrics = metrics.model_copy(update={"investor_relations_url": investor_relations})
        next_earnings = _extract_next_earnings_from_ir(investor_relations, ticker)
        if next_earnings:
            metrics = metrics.model_copy(update={"next_earnings_date": next_earnings})
        audio_url = _extract_audio_webcast_from_ir(investor_relations, ticker)
        if audio_url:
            metrics = metrics.model_copy(update={"earnings_audio_url": audio_url})
    if website:
        metrics = metrics.model_copy(update={"company_website": website})

    company_overview = None
    try:
        from backend.company_overview import get_company_overview
        company_overview = await get_company_overview(ticker, language=args.lang)
    except Exception as e:
        print(f"WARNING: company overview skipped: {e}", file=sys.stderr)

    from backend.earnings_deep_dive.pre_render_validator import (
        validate_pre_render, annotate_sections_with_warnings, format_validation_error,
    )
    from backend.earnings_deep_dive.mapper import (
        build_earnings_deep_dive_report, effective_section_analysis,
    )
    from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf

    # Stage 1 — diagnostic on raw sections (annotates, never blocks).
    raw_val = validate_pre_render(ticker=ticker, quarter=args.quarter,
                                  metrics=metrics, section_analysis=sections)
    if raw_val.warnings:
        sections = annotate_sections_with_warnings(sections, raw_val)

    report_model = build_earnings_deep_dive_report(
        ticker=ticker,
        company=dummy.company_name,
        quarter=args.quarter,
        metrics=metrics,
        transcript_url=transcript_url,
        language=args.lang,
        section_analysis=sections,
        company_overview=company_overview,
        yf_info=q_data.get("_raw_info"),
    )

    # Stage 2 — BLOCKING gate on the normalized content actually rendered.
    pre_val = validate_pre_render(ticker=ticker, quarter=args.quarter,
                                  metrics=metrics,
                                  section_analysis=effective_section_analysis(report_model))
    if pre_val.errors:
        print(format_validation_error(pre_val, ticker), file=sys.stderr)
        return 1

    if pdf_path.exists():
        bak = pdf_path.with_name(
            f"earnings_deep_dive.pdf.bak.{datetime.now():%Y%m%d_%H%M%S}")
        pdf_path.rename(bak)
        print(f"previous PDF moved to {bak.name}")
    render_earnings_deep_dive_pdf(report_model, str(pdf_path))
    print(f"rendered: {pdf_path} ({pdf_path.stat().st_size} bytes)")

    validation_path = report_dir / "deep_dive_validation.json"
    validation_path.write_text(json.dumps({
        "passed": passed,
        "issues": issues,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"validation written: {validation_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
