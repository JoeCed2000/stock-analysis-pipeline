"""Validate an earnings deep-dive PDF against the model contract.

This validator checks categories and structure, not example company values.
It intentionally does not assert Apple/SanDisk/GE Vernova numbers unless the
target company is one of those examples.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

try:
    import fitz
except ImportError:  # pragma: no cover - handled at runtime
    fitz = None


REQUIRED_SECTION_TERMS = (
    ("Earnings Documents", "決算資料"),
    ("EPS & Revenue", "EPS"),
    ("Highlights", "ハイライト"),
    ("Operating Metrics", "営業"),
    ("Cash Flow", "キャッシュ"),
    ("Capital Efficiency", "資本"),
    ("Segments", "セグメント"),
    ("Forward P/E", "PER"),
    ("Backlog", "受注"),
    ("Guidance", "ガイダンス"),
    ("Verdict", "総合評価"),
)

REQUIRED_CATEGORY_GROUPS = {
    "EPS": ("EPS",),
    "Revenue": ("Revenue", "売上", "売上高"),
    "Estimate": ("Estimate", "予想", "コンセンサス"),
    "Actual": ("Actual", "実績"),
    "YoY": ("YoY", "前年比", "前年同期比"),
    "Operating cash flow": ("Operating cash flow", "営業キャッシュフロー", "営業CF"),
    "CapEx": ("CapEx", "設備投資"),
    "Free cash flow": ("Free cash flow", "FCF", "フリーキャッシュフロー"),
    "ROE": ("ROE",),
    "ROIC": ("ROIC",),
    "Forward P/E": ("Forward P/E", "予想PER", "PER"),
    "Guidance": ("Guidance", "ガイダンス"),
}

REQUIRED_CONTENT_GROUPS = {
    # The Earnings Documents section is now a source-contract table
    # ("Used for" / "Target-company URL or status" headers), not the legacy
    # "General Questions for Earnings" prompt block removed from the layout.
    "Earnings documents source table": (
        "Used for", "用途",
        "Target-company URL or status", "企業URLまたはステータス",
    ),
    "Target source instructions": ("Candidate transcript source", "Transcript -", "Official Investor Relations"),
    "Highlights/lowlights Japanese style": ("ハイライト", "ローライト", "Nami", "投資視点"),
    "Cash flow formula": ("FCF", "OCF", "CapEx", "FCF = OCF", "フリーキャッシュフロー", "営業キャッシュフロー"),
    "Capital efficiency ratings": ("ROE", "ROTCE", "ROTE", "ROA", "ROIC"),
    "Backlog disposition": ("Backlog", "受注残", "該当なし", "開示なし"),
    "Guidance split": ("Guidance", "ガイダンス", "Medium-term", "中期"),
    "Final investor verdict": ("Verdict", "総合評価", "投資視点", "Final verdict"),
}

FORBIDDEN_GENERIC_PHRASES = (
    "is assessed from available sourced data",
    "Section unavailable",
    "Transcript missing",
    "DATA NOT AVAILABLE",
    "DONNÉE NON DISPONIBLE",
)

MODEL_EXAMPLES = {
    "GEV": ("GEV", "GE Vernova"),
    "AAPL": ("Apple", "$111.18B"),
    "SNDK": ("SanDisk",),
}

MISSING_LABELS = ("データ未取得", "開示なし", "該当なし", "計算不可")
SOURCE_ONLY_LABELS = ("会社開示", "コンセンサス", "計算ベース", "事業特性", "開示資料")
CRITICAL_DATA_SECTIONS = {
    "EPS & Revenue",
    "Operating Metrics",
    "Cash Flow",
    "Capital Efficiency",
    "Segments",
    "Forward P/E",
    "Guidance",
}
QUALITATIVE_DATA_SECTIONS = {"Guidance"}


@dataclass
class PdfValidationResult:
    passed: bool
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    model_page_count: int = 0


def _extract_text(path: Path) -> tuple[str, int]:
    if fitz is None:
        raise RuntimeError("PyMuPDF/fitz is required for PDF validation")
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc), len(doc)


def _report_text(structured_report: Any) -> str:
    if structured_report is None:
        return ""
    try:
        return structured_report.model_dump_json()
    except AttributeError:
        return str(structured_report)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    compact_text = re.sub(r"\s+", "", text)
    return any(
        term in text or re.sub(r"\s+", "", term) in compact_text
        for term in terms
    )


def _is_useful_data_cell(value: Any) -> bool:
    text = str(value).strip()
    if not text or text in MISSING_LABELS:
        return False
    return not any(label in text for label in SOURCE_ONLY_LABELS)


def _has_numeric_signal(value: Any) -> bool:
    text = str(value)
    return bool(re.search(r"[\d$¥€£%]", text))


def _table_is_mostly_empty(structured_report: Any) -> bool:
    if structured_report is None:
        return False
    critical_tables = 0
    empty_tables = 0
    for section in getattr(structured_report, "sections", []):
        if getattr(section, "key", "") not in CRITICAL_DATA_SECTIONS:
            continue
        table = getattr(section, "table", None)
        rows = list(getattr(table, "rows", []) or [])
        if not rows:
            continue
        critical_tables += 1
        useful_rows = 0
        for row in rows:
            cells = list(getattr(row, "cells", []) or [])
            metric_cells = cells[:-1] if len(cells) > 1 else cells
            if getattr(section, "key", "") in QUALITATIVE_DATA_SECTIONS:
                has_useful_data = any(_is_useful_data_cell(cell) for cell in metric_cells)
            else:
                has_useful_data = any(
                    _is_useful_data_cell(cell) and _has_numeric_signal(cell)
                    for cell in metric_cells
                )
            if has_useful_data:
                useful_rows += 1
        if useful_rows == 0:
            empty_tables += 1
    return critical_tables > 0 and empty_tables / critical_tables >= 0.35


def _has_source_url(structured_report: Any, text: str = "") -> bool:
    if structured_report is None:
        return "Transcript" in text and "http" in text
    for source in getattr(structured_report, "sources", []):
        label = str(getattr(source, "label", "")).lower()
        if "transcript -" in label and getattr(source, "url", None):
            return True
    return False


def _has_expected_earnings_sources(structured_report: Any, ticker: str, text: str = "") -> bool:
    expected_sa = f"https://seekingalpha.com/symbol/{ticker.upper()}/earnings/transcripts"
    if structured_report is None:
        has_transcript = "Transcript" in text and "http" in text
        has_earnings_documents = "Earnings Documents" in text or "決算資料" in text
        has_company_source = "Investor Relations" in text or "Official Website" in text
        return has_earnings_documents and has_transcript and has_company_source
    sources = list(getattr(structured_report, "sources", []) or [])
    has_transcript = any(
        "transcript" in str(getattr(source, "label", "")).lower()
        and bool(getattr(source, "url", None))
        for source in sources
    )
    has_company_source = any(
        "investor relations" in str(getattr(source, "label", "")).lower()
        or "official website" in str(getattr(source, "label", "")).lower()
        for source in sources
    )
    return has_transcript and has_company_source


def validate_pdf_against_model(
    *,
    generated_pdf: str | Path,
    model_pdf: str | Path,
    ticker: str,
    company: str,
    structured_report: Any = None,
) -> PdfValidationResult:
    generated_path = Path(generated_pdf)
    model_path = Path(model_pdf)
    issues: list[str] = []
    warnings: list[str] = []

    if not generated_path.exists():
        return PdfValidationResult(False, [f"Generated PDF not found: {generated_path}"])
    if not model_path.exists():
        return PdfValidationResult(False, [f"Model PDF not found: {model_path}"])

    text, page_count = _extract_text(generated_path)
    _, model_page_count = _extract_text(model_path)
    structured_text = _report_text(structured_report)
    combined = f"{text}\n{structured_text}"

    for english, japanese in REQUIRED_SECTION_TERMS:
        if english not in combined and japanese not in combined:
            issues.append(f"Missing required section/category: {english}")

    for category, terms in REQUIRED_CATEGORY_GROUPS.items():
        if not _has_any(combined, terms):
            issues.append(f"Missing expected data category: {category}")

    for category, terms in REQUIRED_CONTENT_GROUPS.items():
        if not _has_any(combined, terms):
            issues.append(f"Missing model-style content block: {category}")

    for phrase in FORBIDDEN_GENERIC_PHRASES:
        if phrase in combined:
            issues.append(f"Forbidden generic phrase present: {phrase}")

    target_tokens = {ticker.upper(), company.lower()}
    for example_ticker, examples in MODEL_EXAMPLES.items():
        if example_ticker == ticker.upper() or any(company.lower() in value.lower() for value in examples):
            continue
        for value in examples:
            if value in combined:
                issues.append(f"Model example leaked into target-company report: {value}")

    if not _has_any(combined, ("👉", "●", "①", "Nami")):
        issues.append("Japanese pedagogical markers are missing")

    if not _has_source_url(structured_report, combined):
        issues.append("Missing transcript/source URL in structured report")

    if not _has_expected_earnings_sources(structured_report, ticker, combined):
        issues.append("Missing target-company Earnings Documents source contract")

    if _table_is_mostly_empty(structured_report):
        issues.append("One or more required tables are mostly empty")

    # The model PDF is a layout example, not a page-for-page contract: the
    # client-approved conciseness revisions deliberately shrank sections, so
    # exact page parity can never hold. Block only on gross truncation (the
    # failure this check exists to catch); report other differences as a
    # non-blocking warning.
    min_page_count = 8
    if page_count < min_page_count:
        issues.append(
            f"Generated PDF page count {page_count} below minimum {min_page_count} — likely truncated"
        )
    elif page_count != model_page_count:
        warnings.append(
            f"Generated PDF page count {page_count} differs from model {model_page_count} (layout drift, non-blocking)"
        )

    return PdfValidationResult(
        passed=not issues,
        blocking_issues=issues,
        warnings=warnings,
        page_count=page_count,
        model_page_count=model_page_count,
    )


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-pdf", required=True)
    parser.add_argument("--model-pdf", default="docs/specs/modele.pdf")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--company", required=True)
    args = parser.parse_args()

    result = validate_pdf_against_model(
        generated_pdf=args.generated_pdf,
        model_pdf=args.model_pdf,
        ticker=args.ticker,
        company=args.company,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.passed else 1)
