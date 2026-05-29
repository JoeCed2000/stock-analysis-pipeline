"""
SA Quality Gates — reusable validators that block export when Critical/High issues exist.

Usage:
    from backend.quality_gates import run_all_gates, GateResult
    results = run_all_gates(report, metrics_ledger, source_registry)
    for r in results:
        if r.severity in ("critical", "high") and not r.passed:
            raise GateBlockedError(r)

Corrections.txt sections implemented:
  - 23: SA_NO_INTERNAL_LEAKS_GATE
  - 22: SA_METRIC_ABSENCE_HANDLING_GATE
  - 5:  SA_REPORT_SOURCE_INTEGRITY_GATE
  - 21: SA_DATA_QUALITY_TRUTHFULNESS_GATE
  - 29: SA_FINAL_PDF_CLIENT_READY_GATE
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    severity: str  # critical, high, medium, low
    section: str
    message: str
    details: List[str] = field(default_factory=list)


# ── Internal leak patterns (Section 23) ──

FORBIDDEN_PDF_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern, severity, description)
    (r"CRITICAL\s+OVERRIDE", "critical", "CRITICAL OVERRIDE leaked into output"),
    (r"primary\s+returned\s+no\s+content", "high", "Debug reason leaked: 'primary returned no content'"),
    (r"Model\s+example\s+company\s+figures", "high", "Internal instruction leaked: 'Model example company figures'"),
    (r"For\s+Nami-san", "high", "Nami-personal language in client report"),
    (r"Nami\s+insight|Nami\s+takeaway", "high", "Nami-personal label in client report"),
    (r"fallback\s+failed", "medium", "Internal fallback error leaked"),
    (r"yfinance\s+key", "medium", "Raw provider key 'yfinance key' leaked"),
    (r"Section\s+unavailable", "high", "'Section unavailable' in final output"),
    (r"Reason:", "high", "'Reason:' debug prefix in final output"),
    (r"\bnull\b", "high", "Literal 'null' in final output"),
    (r"\bNone\b", "high", "Literal 'None' in final output"),
    (r"\bNaN\b", "high", "Literal 'NaN' in final output"),
    (r"\bundefined\b", "high", "Literal 'undefined' in final output"),
    (r"provider\s+returned\s+empty", "medium", "Internal provider error leaked"),
    (r"🧠\s*Nami", "high", "Nami emoji/label in client report"),
]


def validate_no_internal_leaks(text_content: str) -> GateResult:
    """Section 23: Check that no debug/internal/instruction text leaks into the PDF."""
    findings = []
    for pattern, severity, description in FORBIDDEN_PDF_PATTERNS:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        if matches:
            findings.append(f"[{severity}] {description}: found {len(matches)} match(es)")

    criticals = [f for f in findings if "[critical]" in f.lower()]
    highs = [f for f in findings if "[high]" in f.lower()]

    if criticals:
        return GateResult(
            gate_name="SA_NO_INTERNAL_LEAKS_GATE",
            passed=False,
            severity="critical",
            section="23",
            message=f"{len(criticals)} critical leak(s), {len(highs)} high",
            details=findings,
        )
    if highs:
        return GateResult(
            gate_name="SA_NO_INTERNAL_LEAKS_GATE",
            passed=False,
            severity="high",
            section="23",
            message=f"{len(highs)} high-severity leak(s)",
            details=findings,
        )
    return GateResult(
        gate_name="SA_NO_INTERNAL_LEAKS_GATE",
        passed=True,
        severity="low",
        section="23",
        message="No internal leaks detected",
        details=[],
    )


# ── Missing-data language (Section 22) ──

FORBIDDEN_MISSING_PATTERNS = [
    # Standalone "Not available" without context
    (r"^\s*Not available\s*$", "high", "Standalone 'Not available' (no context)"),
    (r"^\s*Not Available\s*$", "high", "Standalone 'Not Available' (no context)"),
    # Raw N/A (should be "Not applicable")
    (r"^\s*N/A\s*$", "medium", "Standalone 'N/A' (use 'Not applicable')"),
    # Debug reasons
    (r"Reason:\s*primary", "high", "Debug reason 'Reason: primary...'"),
    (r"Section unavailable", "high", "'Section unavailable'"),
]


def validate_missing_data_language(text_content: str) -> GateResult:
    """Section 22: Validate that missing-data language is professional."""
    findings = []
    for pattern, severity, description in FORBIDDEN_MISSING_PATTERNS:
        matches = re.findall(pattern, text_content, re.IGNORECASE | re.MULTILINE)
        if matches:
            findings.append(f"[{severity}] {description}: found {len(matches)} match(es)")

    if not findings:
        return GateResult(
            gate_name="SA_METRIC_ABSENCE_HANDLING_GATE",
            passed=True,
            severity="low",
            section="22",
            message="Missing-data language is professional",
        )

    has_high = any("[high]" in f.lower() for f in findings)
    return GateResult(
        gate_name="SA_METRIC_ABSENCE_HANDLING_GATE",
        passed=False,
        severity="high" if has_high else "medium",
        section="22",
        message=f"{len(findings)} issue(s) with missing-data language",
        details=findings,
    )


# ── Source integrity (Section 5) ──

FORBIDDEN_SOURCE_PATTERNS = [
    (r"investor\.\w+\.com/home/default\.aspx", "high",
     "Investor-relations portal URL cited as primary transcript source"),
    (r"source_id.*S\d+(?!.*mapping)", "medium",
     "Source code like 'S1' without visible mapping"),
    (r"yfinance\s+key", "medium",
     "Raw provider key 'yfinance key' exposed"),
]


def validate_source_integrity(text_content: str) -> GateResult:
    """Section 5: Validate source URLs and labels are client-ready."""
    findings = []
    for pattern, severity, description in FORBIDDEN_SOURCE_PATTERNS:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        if matches:
            findings.append(f"[{severity}] {description}: found {len(matches)} match(es)")

    if not findings:
        return GateResult(
            gate_name="SA_REPORT_SOURCE_INTEGRITY_GATE",
            passed=True,
            severity="low",
            section="5",
            message="Source URLs and labels are client-ready",
        )

    has_high = any("[high]" in f.lower() for f in findings)
    return GateResult(
        gate_name="SA_REPORT_SOURCE_INTEGRITY_GATE",
        passed=False,
        severity="high" if has_high else "medium",
        section="5",
        message=f"{len(findings)} source integrity issue(s)",
        details=findings,
    )


# ── Data Quality truthfulness (Section 21) ──

def validate_data_quality_truthfulness(
    data_quality_text: str,
    missing_critical_metrics: int = 0,
    contradiction_count: int = 0,
) -> GateResult:
    """Section 21: Data Quality must not claim 100 when metrics are missing."""
    findings = []

    # Check if completeness claims 100 despite missing metrics
    if missing_critical_metrics > 0:
        match_100 = re.search(r"Completeness.*?(\d+)/?100", data_quality_text)
        if match_100:
            findings.append(
                f"[critical] Completeness claims 100 but {missing_critical_metrics} critical metric(s) missing"
            )

    if contradiction_count > 0:
        findings.append(
            f"[high] {contradiction_count} source/metric contradiction(s) found"
        )

    if not findings:
        return GateResult(
            gate_name="SA_DATA_QUALITY_TRUTHFULNESS_GATE",
            passed=True,
            severity="low",
            section="21",
            message="Data Quality scorecard is truthful",
        )

    has_critical = any("[critical]" in f.lower() for f in findings)
    return GateResult(
        gate_name="SA_DATA_QUALITY_TRUTHFULNESS_GATE",
        passed=False,
        severity="critical" if has_critical else "high",
        section="21",
        message=f"{len(findings)} Data Quality truthfulness issue(s)",
        details=findings,
    )


# ── Final client-ready gate (Section 29) ──

def run_all_gates(
    pdf_text: str,
    data_quality_text: str = "",
    missing_critical_metrics: int = 0,
    contradiction_count: int = 0,
) -> List[GateResult]:
    """Run all quality gates against the generated PDF text.

    Returns a list of GateResult objects. Any Critical or High failure means
    the PDF should be blocked from client export.
    """
    results = [
        validate_no_internal_leaks(pdf_text),
        validate_missing_data_language(pdf_text),
        validate_source_integrity(pdf_text),
        validate_data_quality_truthfulness(
            data_quality_text or pdf_text,
            missing_critical_metrics,
            contradiction_count,
        ),
    ]
    return results


def is_client_ready(results: List[GateResult]) -> bool:
    """Return True if no Critical or High issues remain."""
    for r in results:
        if not r.passed and r.severity in ("critical", "high"):
            return False
    return True


def gate_summary(results: List[GateResult]) -> str:
    """Format a one-line gate summary."""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    criticals = sum(1 for r in results if not r.passed and r.severity == "critical")
    highs = sum(1 for r in results if not r.passed and r.severity == "high")
    status = "✅ CLIENT-READY" if is_client_ready(results) else "❌ BLOCKED"
    return f"{status} — {passed}/{len(results)} gates passed, {criticals}C/{highs}H remaining"
