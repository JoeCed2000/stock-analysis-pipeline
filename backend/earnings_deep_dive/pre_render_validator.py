"""
Pre-render validator — HARD GATE inserted between deep-dive generation and PDF build.

BLOCKING RULES (error severity → PDF build fails):
1. Segment coherence: any individual segment revenue > total quarterly revenue
2. FY label enforcement: annual data used in quarterly section without FY label
3. Cross-section contradiction: EPS/Revenue BEAT/MISS direction flips across sections

NON-BLOCKING RULES (warning severity → ⚠️ flag, build continues):
4. Quarter missing
5. Forbidden markers ("Not available", "DATA NOT AVAILABLE")
6. Number consistency vs source metrics (±5%)
7. Score-commentary alignment in Verdict

Always returns a ValidationResult — never raises on bad input.
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

# ── BEAT/MISS detection patterns ──────────────────────────────────────────

# Positive: "beat", "beat consensus", "exceeded", "above estimates", "surpassed"
BEAT_PATTERNS = [
    re.compile(r'\b(beat|beats|beaten)\s+(consensus|estimates?|expectations?|guidance)\b', re.IGNORECASE),
    re.compile(r'\b(exceeded|exceed|surpassed|surpassed|outperformed)\s+(consensus|estimates?|expectations?)\b', re.IGNORECASE),
    re.compile(r'\b(above|ahead\s+of)\s+(consensus|estimates?|expectations?)\b', re.IGNORECASE),
    re.compile(r'\b(strong\s+beat|solid\s+beat|clean\s+beat|big\s+beat)\b', re.IGNORECASE),
    re.compile(r'\bbeat\b.*\b(by\s+\d|on\s+both|top\s+and\s+bottom)\b', re.IGNORECASE),
]

# Negative: "miss", "missed consensus", "below estimates", "fell short"
MISS_PATTERNS = [
    re.compile(r'\b(miss|misses|missed)\s+(consensus|estimates?|expectations?|guidance)\b', re.IGNORECASE),
    re.compile(r'\b(below|fell\s+short\s+of|trailing|lagging)\s+(consensus|estimates?|expectations?)\b', re.IGNORECASE),
    re.compile(r'\b(did\s+not\s+(beat|meet|reach)|failed\s+to\s+(beat|meet|reach))\s+(consensus|estimates?)\b', re.IGNORECASE),
    re.compile(r'\b(disappointed|disappointing|weak|miss)\b.*\b(quarter|results?|earnings?|revenue)\b', re.IGNORECASE),
]

# ── Number extraction patterns ─────────────────────────────────────────────

MONEY_RE = re.compile(
    r'\$[\d,]+\.?\d*\s*[BMK]?(?=[\s,;.)\]]|$)',
    re.IGNORECASE,
)

# Match FY references: "FY26", "FY2026", "fiscal year 2026", "FY 26"
FY_REFERENCE_RE = re.compile(
    r'\bFY\s*\d{2,4}\b|\bfiscal\s+year\s+\d{4}\b|\bFiscal\s+\d{4}\b',
    re.IGNORECASE,
)

# ── Score extraction pattern ───────────────────────────────────────────────

SCORE_RE = re.compile(r'[Ss]core\s*:\s*(\d+)\s*/\s*10')


@dataclass
class ValidationWarning:
    """A single validation issue found in the deep-dive."""
    check: str          # e.g. "quarter_missing", "not_available", "segment_coherence"
    section: str        # Which section the issue was found in
    detail: str         # Human-readable description
    severity: str = "warning"  # "error" (blocks PDF build) or "warning" (non-blocking)


@dataclass
class ValidationResult:
    """Result of the pre-render validation pass.

    passed = no errors (warnings don't block the build).
    """
    passed: bool
    warnings: List[ValidationWarning] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationWarning]:
        """Only blocking errors."""
        return [w for w in self.warnings if w.severity == "error"]

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len([w for w in self.warnings if w.severity == "warning"])


def _parse_money(text: str) -> Optional[float]:
    """Parse a monetary string like '$82.9B' or '$3.46' into a float."""
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


def _detect_eps_direction(text: str) -> Optional[str]:
    """Detect EPS beat/miss direction from text.

    Returns "BEAT", "MISS", or None if undetermined.
    """
    if not text:
        return None
    has_beat = any(p.search(text) for p in BEAT_PATTERNS)
    has_miss = any(p.search(text) for p in MISS_PATTERNS)

    if has_beat and not has_miss:
        return "BEAT"
    elif has_miss and not has_beat:
        return "MISS"
    elif has_beat and has_miss:
        return "CONFLICT"  # Both detected — ambiguous
    return None


def _detect_revenue_direction(text: str) -> Optional[str]:
    """Detect revenue beat/miss direction from text."""
    return _detect_eps_direction(text)  # Same patterns work for revenue


def _extract_segment_revenues(metrics: Any) -> Dict[str, float]:
    """Extract individual segment revenues from metrics.segments dict.

    Returns {segment_name: revenue_float}.
    """
    segments = {}
    try:
        raw = getattr(metrics, 'segments', None)
        if not isinstance(raw, dict):
            return segments
    except Exception:
        return segments

    _META_KEYS = {"product_segments", "total_revenue_quarterly", "deferred_revenue_1yr_pct",
                  "source", "filing_date", "period", "source_form", "_annual_context_only"}
    for key, value in raw.items():
        if key in _META_KEYS:
            continue
        if isinstance(value, dict):
            rev = value.get("revenue") or value.get("revenue_quarterly")
            if rev is not None:
                try:
                    segments[str(key)] = float(rev)
                except (TypeError, ValueError):
                    pass
    return segments


def _extract_total_quarterly_revenue(metrics: Any) -> Optional[float]:
    """Extract total quarterly revenue from metrics."""
    try:
        segments = getattr(metrics, 'segments', None)
        if isinstance(segments, dict):
            total = segments.get("total_revenue_quarterly")
            if total is not None:
                return float(total)
    except (TypeError, ValueError):
        pass
    try:
        rev = getattr(metrics, 'revenue_actual', None)
        if rev is not None:
            return float(rev)
    except (TypeError, ValueError):
        pass
    try:
        rev = getattr(metrics, 'revenue_quarterly', None)
        if rev is not None:
            return float(rev)
    except (TypeError, ValueError):
        pass
    return None


def _is_annual_context(metrics: Any) -> bool:
    """Check if segment data is from annual (10-K) rather than quarterly (10-Q)."""
    try:
        segments = getattr(metrics, 'segments', None)
        if isinstance(segments, dict):
            if segments.get("_annual_context_only"):
                return True
            if segments.get("period") == "annual":
                return True
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════════════════
# MAIN VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════


def validate_pre_render(
    ticker: str,
    quarter: Optional[str],
    metrics: Any,
    section_analysis: Optional[Dict[str, str]],
) -> ValidationResult:
    """Validate deep-dive content before PDF rendering.

    HARD RULES (error → blocks PDF build):
    1. Segment coherence: individual segment > total quarterly revenue
    2. FY label: annual data in quarterly section without FY label
    3. Cross-section contradiction: EPS/Revenue direction flips

    SOFT RULES (warning → ⚠️ flag, build continues):
    4. Quarter missing
    5. Forbidden markers
    6. Number consistency vs source metrics
    7. Score-commentary alignment

    Always returns a ValidationResult — never raises on bad input.
    """
    warnings: List[ValidationWarning] = []

    # Normalize inputs
    _sec = section_analysis or {}
    if not isinstance(_sec, dict):
        _sec = {}

    # ── RULE 1 (BLOCKING): Segment coherence ────────────────────────────

    segment_revenues = _extract_segment_revenues(metrics)
    total_revenue = _extract_total_quarterly_revenue(metrics)

    if segment_revenues and total_revenue and total_revenue > 0:
        seg_sum = sum(segment_revenues.values())
        # Check individual segments vs total
        for seg_name, seg_rev in segment_revenues.items():
            if seg_rev > total_revenue * 1.01:  # 1% tolerance for rounding
                pct_of_total = (seg_rev / total_revenue) * 100
                warnings.append(ValidationWarning(
                    check="segment_coherence",
                    section="Segments",
                    detail=(
                        f"FATAL: Segment '{seg_name}' revenue (${seg_rev:,.0f}) exceeds "
                        f"total quarterly revenue (${total_revenue:,.0f}) — "
                        f"that's {pct_of_total:.0f}% of total. "
                        f"This means segment data is from a different period (likely annual 10-K) "
                        f"and was not properly flagged as annual context."
                    ),
                    severity="error",
                ))

        # Also check if sum of all segments significantly exceeds total
        if seg_sum > total_revenue * 1.20:  # 20% tolerance — segments often don't sum exactly
            warnings.append(ValidationWarning(
                check="segment_sum_overflow",
                section="Segments",
                detail=(
                    f"FATAL: Sum of all segments (${seg_sum:,.0f}) exceeds "
                    f"total quarterly revenue (${total_revenue:,.0f}) by "
                    f"{((seg_sum/total_revenue)-1)*100:.0f}%. "
                    f"Segment data is annual. Set _annual_context_only=True in metrics.segments."
                ),
                severity="error",
            ))

    # ── RULE 2 (BLOCKING): FY label enforcement ────────────────────────

    is_annual = _is_annual_context(metrics)
    eps_rev_text = _sec.get("EPS & Revenue", "")

    if is_annual and isinstance(eps_rev_text, str) and eps_rev_text:
        # Check if the EPS & Revenue section mentions quarterly without FY disclaimers
        has_quarterly_marker = bool(re.search(
            r'\bQ[1-4]\b|\bquarterly\b|\bquarter\b|\b3\s*month', eps_rev_text, re.IGNORECASE
        ))
        has_fy_label = bool(FY_REFERENCE_RE.search(eps_rev_text))
        has_annual_label = bool(re.search(
            r'\bannual\b|\bfull\s*year\b|\bfiscal\s+year\b', eps_rev_text, re.IGNORECASE
        ))

        if has_quarterly_marker and not (has_fy_label or has_annual_label):
            warnings.append(ValidationWarning(
                check="fy_label_missing",
                section="EPS & Revenue",
                detail=(
                    "FATAL: Annual segment data is being used but the EPS & Revenue section "
                    "uses quarterly language ('Q1', 'quarterly') without FY/Annual labels. "
                    "Add '(FY annual)' or 'fiscal year' explicitly when using annual data."
                ),
                severity="error",
            ))

    # Also check Segments section for FY label
    seg_text = _sec.get("Segments", "")
    if is_annual and isinstance(seg_text, str) and seg_text:
        has_q_ref = bool(re.search(r'\bQ[1-4]\b|\bquarter\b', seg_text, re.IGNORECASE))
        has_fy = bool(FY_REFERENCE_RE.search(seg_text)) or bool(re.search(
            r'\bannual\b', seg_text, re.IGNORECASE
        ))
        if has_q_ref and not has_fy:
            warnings.append(ValidationWarning(
                check="fy_label_missing",
                section="Segments",
                detail=(
                    "FATAL: Segments section uses quarterly references ('Q1', 'quarter') "
                    "but segment data is annual. Must include FY/Annual label."
                ),
                severity="error",
            ))

    # ── RULE 3 (BLOCKING): Cross-section EPS/Revenue contradiction ─────

    # Detect direction in EPS & Revenue section
    eps_rev_dir_eps = _detect_eps_direction(eps_rev_text)
    eps_rev_dir_rev = _detect_revenue_direction(eps_rev_text)

    # Detect direction in Verdict section
    verdict_text = _sec.get("Verdict", "")
    verdict_dir_eps = _detect_eps_direction(verdict_text)
    verdict_dir_rev = _detect_revenue_direction(verdict_text)

    # Check EPS contradiction
    if eps_rev_dir_eps and verdict_dir_eps:
        if eps_rev_dir_eps == "BEAT" and verdict_dir_eps == "MISS":
            warnings.append(ValidationWarning(
                check="eps_direction_contradiction",
                section="Verdict",
                detail=(
                    "FATAL: EPS & Revenue says EPS BEAT consensus, "
                    "but Verdict says EPS MISSED. These MUST agree."
                ),
                severity="error",
            ))
        elif eps_rev_dir_eps == "MISS" and verdict_dir_eps == "BEAT":
            warnings.append(ValidationWarning(
                check="eps_direction_contradiction",
                section="Verdict",
                detail=(
                    "FATAL: EPS & Revenue says EPS MISSED consensus, "
                    "but Verdict says EPS BEAT. These MUST agree."
                ),
                severity="error",
            ))

    # Check Revenue contradiction
    if eps_rev_dir_rev and verdict_dir_rev:
        if eps_rev_dir_rev == "BEAT" and verdict_dir_rev == "MISS":
            warnings.append(ValidationWarning(
                check="revenue_direction_contradiction",
                section="Verdict",
                detail=(
                    "FATAL: EPS & Revenue says Revenue BEAT consensus, "
                    "but Verdict says Revenue MISSED. These MUST agree."
                ),
                severity="error",
            ))
        elif eps_rev_dir_rev == "MISS" and verdict_dir_rev == "BEAT":
            warnings.append(ValidationWarning(
                check="revenue_direction_contradiction",
                section="Verdict",
                detail=(
                    "FATAL: EPS & Revenue says Revenue MISSED consensus, "
                    "but Verdict says Revenue BEAT. These MUST agree."
                ),
                severity="error",
            ))

    # Also check Highlights section for contradictions
    highlights_text = _sec.get("Highlights", "")
    highlights_dir_eps = _detect_eps_direction(highlights_text)
    if eps_rev_dir_eps and highlights_dir_eps:
        if eps_rev_dir_eps == "BEAT" and highlights_dir_eps == "MISS":
            warnings.append(ValidationWarning(
                check="eps_direction_contradiction",
                section="Highlights",
                detail=(
                    "FATAL: EPS & Revenue says EPS BEAT, "
                    "but Highlights says EPS MISSED. These MUST agree."
                ),
                severity="error",
            ))
        elif eps_rev_dir_eps == "MISS" and highlights_dir_eps == "BEAT":
            warnings.append(ValidationWarning(
                check="eps_direction_contradiction",
                section="Highlights",
                detail=(
                    "FATAL: EPS & Revenue says EPS MISSED, "
                    "but Highlights says EPS BEAT. These MUST agree."
                ),
                severity="error",
            ))

    # ── RULE 4 (warning): Quarter present ──────────────────────────────

    if not quarter or not str(quarter).strip():
        warnings.append(ValidationWarning(
            check="quarter_missing",
            section="(global)",
            detail="Quarter is None or empty — deep-dive title/sections will show 'Not available'",
        ))

    # ── RULE 5 (warning): Forbidden markers ────────────────────────────

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
                break

    # ── RULE 6 (warning): Number consistency ───────────────────────────

    metric_map: Dict[str, float] = {}
    if metrics is not None:
        try:
            raw = metrics.model_dump()
        except Exception:
            raw = {}
        for field_name, value in raw.items():
            if field_name.startswith('_'):
                continue
            if isinstance(value, (int, float)) and value is not True and value is not False:
                metric_map[field_name] = float(value)

    revenue_actual = metric_map.get("revenue_actual")
    eps_actual = metric_map.get("eps_actual")
    eps_estimate = metric_map.get("eps_estimate")

    for section_name, text in _sec.items():
        if not isinstance(text, str):
            continue
        money_matches = MONEY_RE.findall(text)
        for money_str in money_matches:
            parsed = _parse_money(money_str)
            if parsed is None:
                continue

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

            if eps_actual and eps_actual < 1000 and parsed < 1000 and parsed > 0.01:
                vs_actual = abs(parsed - eps_actual) / abs(eps_actual)
                vs_estimate = (
                    abs(parsed - eps_estimate) / abs(eps_estimate)
                    if eps_estimate and eps_estimate != 0
                    else 999.0
                )
                if vs_actual > 0.05 and vs_estimate > 0.05:
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

    # ── RULE 7 (warning): Score-commentary alignment ───────────────────

    if isinstance(verdict_text, str) and verdict_text.strip():
        score_match = SCORE_RE.search(verdict_text)
        if score_match:
            score = int(score_match.group(1))
            if score >= 6:
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

    # ── Determine pass/fail ────────────────────────────────────────────

    errors = [w for w in warnings if w.severity == "error"]
    passed = len(errors) == 0

    if not passed:
        error_details = "\n  ".join(e.detail for e in errors)
        logger.error(
            f"[{ticker}] PRE-RENDER HARD FAIL: {len(errors)} blocking error(s), "
            f"{len(warnings) - len(errors)} warning(s)\n"
            f"  {error_details}"
        )
    elif warnings:
        logger.warning(
            f"[{ticker}] Pre-render validation: {len(warnings)} warning(s) "
            f"in {len({w.section for w in warnings})} section(s) — "
            f"build proceeds with ⚠️ flags"
        )

    return ValidationResult(passed=passed, warnings=warnings)


def annotate_sections_with_warnings(
    section_analysis: Dict[str, str],
    validation: ValidationResult,
) -> Dict[str, str]:
    """Inject ⚠️ markers into section_analysis text for sections with warnings.

    Returns a new dict with ⚠️ prepended to affected section text.
    Pass-through: returns original if no warnings or validation passed.
    Side-effect-free: never mutates the input dict.
    """
    if not validation.warnings:
        return section_analysis

    annotated = dict(section_analysis)
    warned_sections = {w.section for w in validation.warnings}

    for section_name in warned_sections:
        if section_name in annotated and isinstance(annotated[section_name], str):
            text = annotated[section_name]
            if not text.startswith("⚠️"):
                annotated[section_name] = f"⚠️ {text}"

    return annotated


def format_validation_error(validation: ValidationResult, ticker: str) -> str:
    """Format blocking validation errors as a human-readable message for API response."""
    if validation.passed:
        return ""
    lines = [
        f"🚫 PDF build blocked for {ticker} — {validation.error_count} data contract violation(s):",
        "",
    ]
    for i, err in enumerate(validation.errors, 1):
        lines.append(f"  {i}. [{err.check}] {err.detail}")
    return "\n".join(lines)
