"""
Pre-render validator — inserted between deep-dive generation and PDF build.

Validates:
- No "Not available" in section text
- Quarter consistency (quarter=None → flagged)
- Number consistency vs source metrics (±5%)
- Score-commentary alignment in Verdict
- Non-blocking: always returns, never raises on bad input
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Forbidden patterns ─────────────────────────────────────────────────────

FORBIDDEN_MARKERS = [
    "Not available",
    "DATA NOT AVAILABLE",
    "DONNÉE NON DISPONIBLE",
    "DONNÃ‰E NON DISPONIBLE",
]

# ── Negative sentiment keywords for contradiction detection ────────────────

NEGATIVE_PHRASES = [
    "negative outlook",
    "sell immediately",
    "avoid this stock",
    "avoiding this stock",
    "destroy",
    "crash",
    "collapse",
    "implode",
    "headwinds",
    "deteriorating",
    "underperform",
    "sell-off",
    "downgrade",
    "bearish",
    "risk-off",
    "overvalued",
    "bubble",
    "short this",
    "dump this",
]

# ── Number extraction patterns ─────────────────────────────────────────────

# Match monetary amounts: $82.9B, $50M, $3.46
# The suffix [BMK] must be word-delimited to avoid false B-match on "beat", "million", etc.
MONEY_RE = re.compile(
    r'\$[\d,]+\.?\d*\s*[BMK]?(?=[\s,;.)\]]|$)',
    re.IGNORECASE,
)

# ── Score extraction pattern ───────────────────────────────────────────────

SCORE_RE = re.compile(r'[Ss]core\s*:\s*(\d+)\s*/\s*10')


@dataclass
class ValidationWarning:
    """A single validation issue found in the deep-dive."""
    check: str          # e.g. "quarter_missing", "not_available", "number_mismatch"
    section: str        # Which section the issue was found in
    detail: str         # Human-readable description
    severity: str = "warning"  # "warning" or "error"


@dataclass
class ValidationResult:
    """Result of the pre-render validation pass."""
    passed: bool
    warnings: List[ValidationWarning] = field(default_factory=list)


def validate_pre_render(
    ticker: str,
    quarter: Optional[str],
    metrics: Any,
    section_analysis: Optional[Dict[str, str]],
) -> ValidationResult:
    """Validate deep-dive content before PDF rendering.

    Performs 4 checks:
    1. Quarter presence — flags if quarter is None
    2. Forbidden markers — scans for "Not available" etc.
    3. Number consistency — compares text values to metrics (±5%)
    4. Score-commentary alignment — detects contradictions

    Always returns a ValidationResult — never raises on bad input.
    """
    warnings: List[ValidationWarning] = []

    # Normalize inputs
    _sec = section_analysis or {}
    if not isinstance(_sec, dict):
        _sec = {}

    # ── Check 1: Quarter present ───────────────────────────────────────────

    if not quarter or not str(quarter).strip():
        warnings.append(ValidationWarning(
            check="quarter_missing",
            section="(global)",
            detail=f"Quarter is None or empty — deep-dive title/sections will show 'Not available'",
        ))

    # ── Check 2: Forbidden markers in section text ─────────────────────────

    for section_name, text in _sec.items():
        if not isinstance(text, str):
            continue
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                warnings.append(ValidationWarning(
                    check="not_available",
                    section=section_name,
                    detail=f"'{marker}' found in section '{section_name}'",
                ))
                break  # One marker per section is enough

    # ── Check 3: Number consistency vs source metrics (±5%) ────────────────

    # Build a map of metric name → value for known metric fields
    metric_map: Dict[str, float] = {}
    if metrics is not None:
        for field_name in dir(metrics):
            if field_name.startswith('_'):
                continue
            try:
                value = getattr(metrics, field_name)
                if isinstance(value, (int, float)) and value is not True and value is not False:
                    metric_map[field_name] = float(value)
            except Exception:
                pass

    for section_name, text in _sec.items():
        if not isinstance(text, str):
            continue
        money_matches = MONEY_RE.findall(text)
        for money_str in money_matches:
            parsed = _parse_money(money_str)
            if parsed is None:
                continue
            # Compare against known metrics
            for metric_name, metric_val in metric_map.items():
                if metric_val == 0:
                    continue
                pct_diff = abs(parsed - metric_val) / abs(metric_val)
                if pct_diff <= 0.05:
                    break  # Close enough — not a mismatch
            else:
                # No metric matched within 5% — but only warn if we found SOME metrics
                # and this number looks like one of them (B-scale for revenue, small for EPS)
                if metric_map:  # Only warn if we have metrics to compare against
                    pass  # We can't easily tell which metric this corresponds to
                    # Better: check if this number is plausible for ANY metric
                    # For now, conservative: only flag if clearly mismatched
                    # We'll only flag revenue/eps mismatches explicitly matched
                    continue

    # More targeted: check revenue and EPS numbers specifically
    revenue_actual = metric_map.get("revenue_actual")
    eps_actual = metric_map.get("eps_actual")
    eps_estimate = metric_map.get("eps_estimate")  # Also check estimate — text may cite consensus

    for section_name, text in _sec.items():
        if not isinstance(text, str):
            continue
        money_matches = MONEY_RE.findall(text)
        for money_str in money_matches:
            parsed = _parse_money(money_str)
            if parsed is None:
                continue

            # Check if this is a revenue number (B-scale, >1B)
            if revenue_actual and revenue_actual > 1_000_000 and parsed > 1_000_000:
                pct_diff = abs(parsed - revenue_actual) / abs(revenue_actual)
                if pct_diff > 0.05:
                    warnings.append(ValidationWarning(
                        check="number_mismatch",
                        section=section_name,
                        detail=(
                            f"Revenue mismatch: text says {money_str} "
                            f"(≈${parsed:,.0f}), "
                            f"metrics have ${revenue_actual:,.0f} "
                            f"({pct_diff:.1%} off)"
                        ),
                    ))

            # Check if this is an EPS number (small, <1000)
            if eps_actual and eps_actual < 1000 and parsed < 1000 and parsed > 0.01:
                # Check against both actual and estimate — text may reference consensus
                vs_actual = abs(parsed - eps_actual) / abs(eps_actual)
                vs_estimate = (
                    abs(parsed - eps_estimate) / abs(eps_estimate)
                    if eps_estimate and eps_estimate != 0
                    else 999.0  # No estimate → skip this comparison
                )
                if vs_actual > 0.05 and vs_estimate > 0.05:
                    # Doesn't match either → flag as mismatch
                    warnings.append(ValidationWarning(
                        check="number_mismatch",
                        section=section_name,
                        detail=(
                            f"EPS mismatch: text says {money_str} "
                            f"(≈${parsed:.2f}), "
                            f"metrics have actual=${eps_actual:.2f}"
                            + (f", estimate=${eps_estimate:.2f}" if eps_estimate else "")
                            + f" ({min(vs_actual, vs_estimate):.1%} off)"
                        ),
                    ))

    # ── Check 4: Score-commentary contradiction ───────────────────────────

    verdict_text = _sec.get("Verdict", "")
    if isinstance(verdict_text, str) and verdict_text.strip():
        # Extract score
        score_match = SCORE_RE.search(verdict_text)
        if score_match:
            score = int(score_match.group(1))
            if score >= 6:  # Positive score
                text_lower = verdict_text.lower()
                negative_count = sum(
                    1 for phrase in NEGATIVE_PHRASES if phrase.lower() in text_lower
                )
                if negative_count >= 2:
                    warnings.append(ValidationWarning(
                        check="score_commentary_contradiction",
                        section="Verdict",
                        detail=(
                            f"Score is {score}/10 (positive) but {negative_count} "
                            f"negative phrases found in Verdict text "
                            f"(e.g. 'sell immediately', 'crash', 'avoid')"
                        ),
                    ))

    # ── Determine pass/fail ────────────────────────────────────────────────

    passed = len(warnings) == 0

    if not passed:
        logger.warning(
            f"[{ticker}] Pre-render validation: {len(warnings)} issue(s) "
            f"in {len({w.section for w in warnings})} section(s)"
        )

    return ValidationResult(passed=passed, warnings=warnings)


def _parse_money(text: str) -> Optional[float]:
    """Parse a monetary string like '$82.9B' or '$3.46' into a float.

    Returns None if parsing fails.
    """
    if not text.startswith('$'):
        return None

    num_part = text[1:].replace(',', '').strip()

    multiplier = 1.0
    last_char = num_part[-1].upper() if num_part else ''
    if last_char == 'B':
        multiplier = 1_000_000_000.0
        num_part = num_part[:-1]
    elif last_char == 'M':
        multiplier = 1_000_000.0
        num_part = num_part[:-1]
    elif last_char == 'K':
        multiplier = 1_000.0
        num_part = num_part[:-1]

    try:
        return float(num_part) * multiplier
    except (ValueError, TypeError):
        return None
