"""Post-render PDF quality gate for client-facing SA artifacts.

This module complements ``pre_render_validator``:
- pre_render_validator checks generated section text before PDF rendering;
- this gate checks final PDF artifacts and audit metadata before delivery.

The input shape intentionally matches docs/pdf-audits/*-raw.json so the gate can
be unit-tested without regenerating expensive analyses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Severity = Literal["defect", "warning", "allowed"]
AudienceMode = Literal["generic", "nami_personalized", "internal_debug"]

DEEP_MIN_BYTES = 10_000
COMPANY_MIN_BYTES = 8_000
KEY_METRIC_MISMATCH_PCT = 10.0

REQUIRED_ARTIFACTS = ("deep_en", "deep_jp", "company")
INTERNAL_MARKERS = (
    "source: yfinance",
    "source:yfinance",
    "eps_actual",
    "eps_estimate",
    "eps_surprise_pct",
    "revenue_actual",
    "revenue_estimate",
    "revenue_yoy",
    "free_cash_flow",
    "pe_forward",
    "raw provider",
    "LLM synthesis",
    "validation failed",
    "FORBIDDEN_MARKERS",
)
NULL_MARKERS = ("NaN", "null", "None", "undefined", "DATA NOT AVAILABLE")
NAMI_MARKERS = ("Nami", "Nami-san", "Namiさん", "Nami様")
EXPECTED_DEEP_SECTIONS = (
    "Financial Metrics",
    "Valuation",
    "Operating Metrics",
    "Cash Flow",
    "Capital Efficiency",
    "Management",
    "Risks",
    "Sources",
)


@dataclass(frozen=True)
class PdfQualityFinding:
    """A deterministic post-render PDF quality finding."""

    rule_id: str
    severity: Severity
    ticker: str
    artifact: str
    message: str
    observed: Any = None
    expected: Any = None
    evidence_path: str | None = None
    audience_mode: AudienceMode = "generic"


@dataclass(frozen=True)
class PdfQualityResult:
    findings: list[PdfQualityFinding]

    @property
    def defects(self) -> list[PdfQualityFinding]:
        return [f for f in self.findings if f.severity == "defect"]

    @property
    def warnings(self) -> list[PdfQualityFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def allowed(self) -> list[PdfQualityFinding]:
        return [f for f in self.findings if f.severity == "allowed"]

    @property
    def passed(self) -> bool:
        return not self.defects


def _as_bool(value: Any) -> bool:
    return bool(value) is True


def _as_number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _add(
    findings: list[PdfQualityFinding],
    rule_id: str,
    severity: Severity,
    ticker: str,
    artifact: str,
    message: str,
    *,
    observed: Any = None,
    expected: Any = None,
    evidence_path: str | None = None,
    audience_mode: AudienceMode = "generic",
) -> None:
    findings.append(
        PdfQualityFinding(
            rule_id=rule_id,
            severity=severity,
            ticker=ticker,
            artifact=artifact,
            message=message,
            observed=observed,
            expected=expected,
            evidence_path=evidence_path,
            audience_mode=audience_mode,
        )
    )


def _artifact_required(audit: dict[str, Any], key: str) -> bool:
    expected = audit.get("expected_artifacts") or {}
    spec = expected.get(key) if isinstance(expected, dict) else None
    if isinstance(spec, dict) and spec.get("required") is False and spec.get("reason"):
        return False
    return key in REQUIRED_ARTIFACTS


def validate_pdf_audit(
    audit: dict[str, Any],
    *,
    audience_mode: AudienceMode = "generic",
    requested_tickers: list[str] | None = None,
) -> PdfQualityResult:
    """Validate final PDF audit metadata.

    Args:
        audit: Raw audit dictionary, usually loaded from docs/pdf-audits/*raw.json.
        audience_mode: generic (strict), nami_personalized, or internal_debug.
        requested_tickers: Optional explicit ticker list that must be present.
    """
    findings: list[PdfQualityFinding] = []
    tickers = audit.get("tickers")
    if not isinstance(tickers, dict):
        _add(findings, "PDFQA-001", "defect", "*", "*", "Missing tickers envelope", observed=type(tickers).__name__, expected="dict", audience_mode=audience_mode)
        return PdfQualityResult(findings)

    required_tickers = requested_tickers or list(tickers.keys())
    for ticker in required_tickers:
        ticker_obj = tickers.get(ticker)
        if not isinstance(ticker_obj, dict):
            _add(findings, "PDFQA-001", "defect", ticker, "*", "Requested ticker missing from audit", observed=None, expected="ticker object", audience_mode=audience_mode)
            continue
        analysis_dir = ticker_obj.get("analysis_dir")
        if not analysis_dir or not str(analysis_dir).startswith("/"):
            _add(findings, "PDFQA-001", "defect", ticker, "*", "Missing absolute analysis_dir", observed=analysis_dir, expected="absolute path", audience_mode=audience_mode)

        artifacts = ticker_obj.get("artifacts") or {}
        if not isinstance(artifacts, dict):
            _add(findings, "PDFQA-002", "defect", ticker, "*", "Missing artifacts dictionary", observed=type(artifacts).__name__, expected="dict", audience_mode=audience_mode)
            continue

        for key in REQUIRED_ARTIFACTS:
            if key not in artifacts:
                severity: Severity = "defect" if _artifact_required(audit, key) else "warning"
                _add(findings, "PDFQA-002", severity, ticker, key, "Required PDF artifact missing", observed=None, expected="artifact metadata", audience_mode=audience_mode)
                continue
            _validate_artifact(findings, ticker, key, artifacts[key] or {}, audience_mode=audience_mode)

        _validate_raw_compare(findings, ticker, ticker_obj.get("raw_compare") or {}, audience_mode=audience_mode)

    return PdfQualityResult(findings)


def _validate_artifact(
    findings: list[PdfQualityFinding],
    ticker: str,
    key: str,
    artifact: dict[str, Any],
    *,
    audience_mode: AudienceMode,
) -> None:
    min_bytes = COMPANY_MIN_BYTES if key == "company" else DEEP_MIN_BYTES
    evidence_path = artifact.get("path") or artifact.get("file") or artifact.get("evidence_path")

    if not _as_bool(artifact.get("exists")):
        _add(findings, "PDFQA-003", "defect", ticker, key, "Artifact file does not exist", observed=artifact.get("exists"), expected=True, evidence_path=evidence_path, audience_mode=audience_mode)
    if not _as_bool(artifact.get("is_pdf")):
        _add(findings, "PDFQA-003", "defect", ticker, key, "Artifact is not a valid PDF", observed=artifact.get("is_pdf"), expected=True, evidence_path=evidence_path, audience_mode=audience_mode)
    size = _as_number(artifact.get("size"))
    if size is None or size < min_bytes:
        _add(findings, "PDFQA-003", "defect", ticker, key, "Artifact size is below sanity threshold", observed=size, expected=f">= {min_bytes} bytes", evidence_path=evidence_path, audience_mode=audience_mode)
    errors = artifact.get("errors") or []
    if errors:
        _add(findings, "PDFQA-003", "defect", ticker, key, "PDF extraction/render errors present", observed=errors[:3] if isinstance(errors, list) else errors, expected="no errors", evidence_path=evidence_path, audience_mode=audience_mode)

    pages = _as_number(artifact.get("pages"))
    if key.startswith("deep_"):
        expected_range = (10, 45 if key == "deep_jp" else 40)
    else:
        expected_range = (3, 12)
    if pages is None or pages < expected_range[0] or pages > expected_range[1]:
        _add(findings, "PDFQA-004", "defect", ticker, key, "Page count outside professional PDF range", observed=pages, expected=f"{expected_range[0]}-{expected_range[1]} pages", evidence_path=evidence_path, audience_mode=audience_mode)

    lang = artifact.get("lang") or {}
    jp_ratio = _as_number(lang.get("jp_ratio") if isinstance(lang, dict) else None)
    if key == "deep_jp" and (jp_ratio is None or jp_ratio < 0.30):
        _add(findings, "PDFQA-005", "defect", ticker, key, "Japanese deep-dive does not contain enough Japanese text", observed=jp_ratio, expected=">= 0.30", evidence_path=evidence_path, audience_mode=audience_mode)
    if key == "deep_en" and jp_ratio is not None and jp_ratio > 0.05:
        _add(findings, "PDFQA-005", "defect", ticker, key, "English deep-dive contains too much Japanese text", observed=jp_ratio, expected="<= 0.05", evidence_path=evidence_path, audience_mode=audience_mode)

    _validate_counts(findings, ticker, key, artifact.get("forbidden_counts") or {}, audience_mode=audience_mode, evidence_path=evidence_path)
    _validate_placeholders(findings, ticker, key, artifact.get("placeholder_counts") or {}, evidence_path=evidence_path, audience_mode=audience_mode)
    _validate_sections(findings, ticker, key, artifact.get("sections_present") or {}, evidence_path=evidence_path, audience_mode=audience_mode)
    _validate_sources(findings, ticker, key, artifact, evidence_path=evidence_path, audience_mode=audience_mode)
    _validate_rendered_pages(findings, ticker, key, artifact, evidence_path=evidence_path, audience_mode=audience_mode)


def _validate_counts(
    findings: list[PdfQualityFinding],
    ticker: str,
    key: str,
    counts: dict[str, Any],
    *,
    audience_mode: AudienceMode,
    evidence_path: str | None,
) -> None:
    for marker, raw_count in counts.items():
        count = int(_as_number(raw_count) or 0)
        if count <= 0:
            continue
        marker_lower = marker.lower()
        if any(m.lower() == marker_lower for m in NAMI_MARKERS):
            if audience_mode == "nami_personalized":
                _add(findings, "PDFQA-006", "allowed", ticker, key, "Nami personalization explicitly allowed", observed={marker: count}, expected="configured personalized audience", evidence_path=evidence_path, audience_mode=audience_mode)
            elif audience_mode == "internal_debug":
                _add(findings, "PDFQA-006", "warning", ticker, key, "Nami personalization visible in internal debug artifact", observed={marker: count}, expected="review debug-only audience", evidence_path=evidence_path, audience_mode=audience_mode)
            else:
                _add(findings, "PDFQA-006", "defect", ticker, key, "Personalized Nami wording leaked into generic PDF", observed={marker: count}, expected="0", evidence_path=evidence_path, audience_mode=audience_mode)
        elif any(m.lower() == marker_lower for m in NULL_MARKERS):
            severity: Severity = "warning" if audience_mode == "internal_debug" else "defect"
            _add(findings, "PDFQA-007", severity, ticker, key, "Null/debug marker visible in PDF", observed={marker: count}, expected="0", evidence_path=evidence_path, audience_mode=audience_mode)
        elif any(m.lower() in marker_lower for m in INTERNAL_MARKERS) or marker.startswith("S") and marker[1:].isdigit():
            severity = "allowed" if audience_mode == "internal_debug" else "defect"
            _add(findings, "PDFQA-008", severity, ticker, key, "Internal source/provider label visible in client PDF", observed={marker: count}, expected="0", evidence_path=evidence_path, audience_mode=audience_mode)


def _validate_placeholders(
    findings: list[PdfQualityFinding],
    ticker: str,
    key: str,
    counts: dict[str, Any],
    *,
    evidence_path: str | None,
    audience_mode: AudienceMode,
) -> None:
    for marker, raw_count in counts.items():
        count = int(_as_number(raw_count) or 0)
        if count <= 0 or marker == "—":
            continue
        severity: Severity = "warning"
        if marker in {"DATA NOT AVAILABLE", "No data", "Not available"}:
            severity = "defect"
        _add(findings, "PDFQA-009", severity, ticker, key, "Missing-data placeholder visible in final PDF", observed={marker: count}, expected="explained data limitation or omitted field", evidence_path=evidence_path, audience_mode=audience_mode)


def _validate_sections(
    findings: list[PdfQualityFinding],
    ticker: str,
    key: str,
    sections_present: dict[str, Any],
    *,
    evidence_path: str | None,
    audience_mode: AudienceMode,
) -> None:
    if not key.startswith("deep_") or not sections_present:
        return
    missing = [section for section in EXPECTED_DEEP_SECTIONS if sections_present.get(section) is False]
    if missing:
        _add(findings, "PDFQA-010", "defect", ticker, key, "Required financial sections missing from deep-dive PDF", observed=missing, expected=list(EXPECTED_DEEP_SECTIONS), evidence_path=evidence_path, audience_mode=audience_mode)


def _validate_sources(
    findings: list[PdfQualityFinding],
    ticker: str,
    key: str,
    artifact: dict[str, Any],
    *,
    evidence_path: str | None,
    audience_mode: AudienceMode,
) -> None:
    links = int(_as_number(artifact.get("links")) or 0)
    min_links = 1 if key == "company" else 5
    if links < min_links:
        _add(findings, "PDFQA-011", "defect", ticker, key, "Insufficient source URLs in final PDF", observed=links, expected=f">= {min_links} HTTP(S) URLs", evidence_path=evidence_path, audience_mode=audience_mode)


def _validate_rendered_pages(
    findings: list[PdfQualityFinding],
    ticker: str,
    key: str,
    artifact: dict[str, Any],
    *,
    evidence_path: str | None,
    audience_mode: AudienceMode,
) -> None:
    rendered = artifact.get("rendered_pages") or []
    if key.startswith("deep_") and not rendered:
        _add(findings, "PDFQA-012", "warning", ticker, key, "No rendered-page smoke screenshots attached to audit", observed=rendered, expected="at least first pages rendered to PNG", evidence_path=evidence_path, audience_mode=audience_mode)


def _validate_raw_compare(
    findings: list[PdfQualityFinding],
    ticker: str,
    raw_compare: dict[str, Any],
    *,
    audience_mode: AudienceMode,
) -> None:
    for metric, payload in raw_compare.items():
        if not isinstance(payload, dict):
            continue
        delta = _as_number(payload.get("delta_pct"))
        if delta is None:
            continue
        if abs(delta) > KEY_METRIC_MISMATCH_PCT:
            _add(
                findings,
                "PDFQA-013",
                "defect",
                ticker,
                "company",
                "Company Overview key financial differs materially from canonical Yahoo snapshot",
                observed={metric: payload},
                expected=f"abs(delta_pct) <= {KEY_METRIC_MISMATCH_PCT}",
                audience_mode=audience_mode,
            )


def format_pdf_quality_result(result: PdfQualityResult) -> str:
    """Human-readable summary for logs/API responses."""
    status = "PASS" if result.passed else "BLOCKED"
    lines = [f"PDF quality gate: {status} ({len(result.defects)} defects, {len(result.warnings)} warnings)"]
    for finding in result.findings:
        if finding.severity == "allowed":
            continue
        lines.append(
            f"- [{finding.severity.upper()}] {finding.rule_id} {finding.ticker}/{finding.artifact}: "
            f"{finding.message} (observed={finding.observed!r}, expected={finding.expected!r})"
        )
    return "\n".join(lines)
