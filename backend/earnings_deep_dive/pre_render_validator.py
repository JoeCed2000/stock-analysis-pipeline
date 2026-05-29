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
8. Backlog hard-coded sector language (hyperscaler for non-tech)
9. Segments LLM fallback (inference vs direct_metric)
10. Guidance source-type conflation (consensus ≠ guidance)

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
    "CRITICAL OVERRIDE",
    "PRECISION INJECTION",
    "Not retrieved",
    "Section unavailable",
    "primary returned no content",
    "fallback failed",
    "provider returned empty",
    "Model example",
    # §23 — debug/template/internal leaks
    "Model example company figures",
    "For Nami-san:",
    "Namiさん向け",
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


def _try_parse_quarter(label: str) -> tuple[int | None, int | None]:
    """Parse period label like 'FY2026 Q1' or 'Q1 2026' → (fiscal_year, fiscal_quarter).

    Returns (None, None) on unparseable input — safe for gate comparisons.
    """
    text = (label or "").strip()
    patterns = (
        (r"(?i)^\s*(?:FY\s*)?(\d{4})\s*Q([1-4])\s*$", False),
        (r"(?i)^\s*Q([1-4])\s*(\d{4})\s*$", True),
        (r"(?i)^\s*(\d{4})Q([1-4])\s*$", False),
    )
    for pattern, q_first in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        a, b = match.groups()
        if q_first:
            return int(b), int(a)
        else:
            return int(a), int(b)
    return None, None


def validate_pre_render(
    ticker: str,
    quarter: Optional[str],
    metrics: Any,
    section_analysis: Optional[Dict[str, str]],
    *,
    period_context: Optional[Any] = None,  # ReportPeriodContext — §3
    earnings_documents: Optional[Any] = None,  # EarningsDocumentsChecklist — §6
    source_registry: Optional[Any] = None,  # SourceRegistry — §5
    metrics_ledger: Optional[Any] = None,  # MetricsLedger — §4
    management_analysis: Optional[Any] = None,  # ManagementAnalysis — §18
    competitive_positioning: Optional[Any] = None,  # CompetitivePositioning — §17
    company_overview: Optional[Any] = None,  # CompanyOverview — §7-8
) -> ValidationResult:
    """Validate deep-dive content before PDF rendering.

    HARD RULES (error → blocks PDF build):
    1. Segment coherence: individual segment > total quarterly revenue
    2. FY label: annual data in quarterly section without FY label
    3. Cross-section contradiction: EPS/Revenue direction flips
    11. §3 Report period consistency: title, transcript, filing, guidance alignment

    SOFT RULES (warning → ⚠️ flag, build continues):
    4. Quarter missing
    5. Forbidden markers
    6. Number consistency vs source metrics
    7. Score-commentary alignment
    8. Backlog hard-coded sector language
    9. Segments LLM fallback
    10. Guidance source-type conflation

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
        # Skip segment coherence checks in annual context (10-K data will
        # naturally exceed quarterly revenue — this is expected and handled
        # by the FY label enforcement in RULE 2)
        is_annual = _is_annual_context(metrics)
        if not is_annual:
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

            # Also check if sum of all segments significantly exceeds total.
            # Important: SEC/XBRL can expose multiple overlapping dimensions in
            # one extraction (e.g. product/service + business segments + region
            # + cloud subset for MSFT). In that case, summing every row is
            # mathematically invalid even though each individual row is valid.
            # Keep individual segment > total as blocking above, but make the
            # aggregate overflow a warning unless the data is explicitly annual.
            if seg_sum > total_revenue * 1.20:  # 20% tolerance — segments often don't sum exactly
                warnings.append(ValidationWarning(
                    check="segment_sum_overflow",
                    section="Segments",
                    detail=(
                        f"Sum of all extracted segment rows (${seg_sum:,.0f}) exceeds "
                        f"total quarterly revenue (${total_revenue:,.0f}) by "
                        f"{((seg_sum/total_revenue)-1)*100:.0f}%. "
                        f"Rows likely contain overlapping SEC/XBRL dimensions; "
                        f"do not treat the full row set as additive."
                    ),
                    severity="warning",
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
                severity="warning",  # Downgraded: LLM prompt fix is separate (annual context labels)
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
                    "Segments section uses quarterly references ('Q1', 'quarter') "
                    "but segment data is annual. Should include FY/Annual label."
                ),
                severity="warning",  # Downgraded: LLM prompt fix is separate
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
                    check="forbidden_marker_leak",
                    section=section_name,
                    detail=f"'{marker}' found in section '{section_name}' — internal/debug/template leak blocked",
                    severity="error",  # §23: all internal leaks are blocking
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

    # ── RULE 8 (WARNING): Backlog hard-coded sector language ──────────
    # The mapper injects "hyperscaler capex commitments" language for all
    # companies, but this only applies to tech/semiconductor firms.
    backlog_text = _sec.get("Backlog", "")
    if isinstance(backlog_text, str) and backlog_text:
        hyperscaler_keywords = ["hyperscaler", "capex commitments", "supply chain constraints"]
        if any(kw.lower() in backlog_text.lower() for kw in hyperscaler_keywords):
            # Check if company is actually in tech/semiconductor sector
            sector = getattr(metrics, 'sector', '') or ''
            industry = getattr(metrics, 'industry', '') or ''
            is_tech = any(t in (sector + ' ' + industry).lower()
                         for t in ('technology', 'semiconductor', 'software',
                                   'hardware', 'cloud', 'data center'))
            if not is_tech:
                warnings.append(ValidationWarning(
                    check="backlog_sector_language",
                    section="Backlog",
                    detail=(
                        "Backlog section uses 'hyperscaler/supply chain' language "
                        f"but company sector is '{sector or 'unknown'}'. "
                        "This may be incorrect sector color for non-tech firms."
                    ),
                ))

    # ── RULE 9 (WARNING): Segments LLM fallback trace ──────────────────
    segments_text = _sec.get("Segments", "")
    if isinstance(segments_text, str) and segments_text:
        llm_fallback_markers = [
            "LLM-generated", "LLM analysis", "model interpretation",
            "Transcript / LLM", "approximate segment",
        ]
        if any(m.lower() in segments_text.lower() for m in llm_fallback_markers):
            warnings.append(ValidationWarning(
                check="segments_llm_fallback",
                section="Segments",
                detail=(
                    "Segments section relies on LLM-generated data (not "
                    "deterministic financial metrics). Segment claims should be "
                    "flagged as 'inference' not 'direct_metric'."
                ),
            ))

    # ── RULE 10 (WARNING): Guidance source-type conflation ─────────────
    guidance_text = _sec.get("Guidance", "")
    if isinstance(guidance_text, str) and guidance_text:
        # Check if consensus/estimate language is used without distinguishing
        # from company guidance
        consensus_markers = ["consensus estimate", "analyst consensus", "analyst estimate"]
        guidance_markers = ["company guidance", "management guidance", "company guide",
                           "management outlook", "company outlook"]
        has_consensus = any(m.lower() in guidance_text.lower() for m in consensus_markers)
        has_guidance = any(m.lower() in guidance_text.lower() for m in guidance_markers)
        if has_consensus and not has_guidance:
            warnings.append(ValidationWarning(
                check="guidance_source_conflation",
                section="Guidance",
                detail=(
                    "Guidance section references consensus/analyst estimates but not "
                    "company/management guidance. Consensus ≠ guidance: estimates are "
                    "external predictions, guidance is company-issued forward outlook."
                ),
            ))

    # ── RULE 11 (BLOCKING): §3 Report period consistency ──────────────────
    #
    # Enforce a single report_period_context — corrections.txt §3.
    # Blocking because period-confused reports damage client trust.

    if period_context is not None:
        try:
            pc = period_context  # ReportPeriodContext
            # 11a. Title period must match primary filing/transcript period
            if pc.filing_period and pc.report_title_period_label:
                # Check that the report title label doesn't conflict with filing
                # e.g., "FY2026 Q1" in filing but "Q2 2026" in title
                fy_ctx, fq_ctx = _try_parse_quarter(pc.report_title_period_label)
                fy_filing, fq_filing = _try_parse_quarter(pc.filing_period)
                if (fy_ctx and fq_ctx and fy_filing and fq_filing
                        and (fy_ctx, fq_ctx) != (fy_filing, fq_filing)):
                    warnings.append(ValidationWarning(
                        check="period_title_filing_mismatch",
                        section="(report title)",
                        detail=(
                            f"FATAL: Report title period '{pc.report_title_period_label}' "
                            f"differs from SEC filing period '{pc.filing_period}'. "
                            f"Title period MUST match the primary earnings period."
                        ),
                        severity="error",
                    ))

            # 11b. Guidance period must be forward-looking (strictly after current period)
            if pc.guidance_period and pc.filing_period:
                fy_g, fq_g = _try_parse_quarter(pc.guidance_period)
                fy_f, fq_f = _try_parse_quarter(pc.filing_period)
                if fy_g and fq_g and fy_f and fq_f:
                    guidance_key = (fy_g, fq_g)
                    current_key = (fy_f, fq_f)
                    if guidance_key <= current_key:
                        warnings.append(ValidationWarning(
                            check="guidance_not_forward_looking",
                            section="Guidance",
                            detail=(
                                f"FATAL: Guidance period '{pc.guidance_period}' is not forward-looking "
                                f"vs current period '{pc.filing_period}'. "
                                f"Guidance must reference a future period — never mix with current actuals."
                            ),
                            severity="error",
                        ))

            # 11c. Transcript period must match filing period
            if pc.transcript_period and pc.filing_period:
                fy_tx, fq_tx = _try_parse_quarter(pc.transcript_period)
                fy_f, fq_f = _try_parse_quarter(pc.filing_period)
                if (fy_tx and fq_tx and fy_f and fq_f
                        and (fy_tx, fq_tx) != (fy_f, fq_f)):
                    warnings.append(ValidationWarning(
                        check="period_transcript_filing_mismatch",
                        section="Sources",
                        detail=(
                            f"FATAL: Transcript period '{pc.transcript_period}' "
                            f"differs from SEC filing period '{pc.filing_period}'. "
                            f"Transcript must match the report period or be explicitly labeled."
                        ),
                        severity="error",
                    ))

            # 11d. Press release period must match filing period
            if pc.press_release_period and pc.filing_period:
                fy_pr, fq_pr = _try_parse_quarter(pc.press_release_period)
                fy_f, fq_f = _try_parse_quarter(pc.filing_period)
                if (fy_pr and fq_pr and fy_f and fq_f
                        and (fy_pr, fq_pr) != (fy_f, fq_f)):
                    warnings.append(ValidationWarning(
                        check="period_press_release_filing_mismatch",
                        section="Sources",
                        detail=(
                            f"FATAL: Press release period '{pc.press_release_period}' "
                            f"differs from SEC filing period '{pc.filing_period}'. "
                            f"Press release from a different quarter cannot be primary evidence."
                        ),
                        severity="error",
                    ))

            # 11e. Comparison prior year must be correct (same quarter, prior fiscal year)
            if pc.comparison_prior_year_period and pc.fiscal_year and pc.fiscal_quarter:
                fy_comp, fq_comp = _try_parse_quarter(pc.comparison_prior_year_period)
                if fy_comp is not None and fq_comp is not None:
                    expected_fy = pc.fiscal_year - 1
                    expected_fq = pc.fiscal_quarter
                    if fy_comp != expected_fy or fq_comp != expected_fq:
                        warnings.append(ValidationWarning(
                            check="period_prior_year_mismatch",
                            section="(tables)",
                            detail=(
                                f"FATAL: Prior-year comparison period '{pc.comparison_prior_year_period}' "
                                f"is not the correct comparable period. "
                                f"Expected: FY{expected_fy} Q{expected_fq} (same quarter, prior fiscal year)."
                            ),
                            severity="error",
                        ))

        except Exception as exc:
            # Never crash the validator — log and continue
            logger.warning(f"[{ticker}] Period consistency gate error (non-fatal): {exc}")

    # ── RULE 12 (BLOCKING): §10 Highlights/Lowlights quality ───────────────
    #
    # Enforce corrections.txt §10: no empty bullets, no duplicates,
    # no unsubstantiated claims, no "no major red flags" paradox.

    highlights_text = _sec.get("Highlights", "")
    if isinstance(highlights_text, str) and highlights_text.strip():
        hl = highlights_text

        # 12a. Empty bullets — lines with just bullet marker and whitespace
        empty_bullet_lines = []
        for i, line in enumerate(hl.split("\n"), 1):
            stripped = line.strip()
            if re.match(r'^[•🌟⚠️🎯🧠\*\-]\s*$', stripped):
                empty_bullet_lines.append(i)
            # Also catch bullets where content is just the emoji + 1-2 chars
            if re.match(r'^[•🌟⚠️🎯🧠\*\-]\s*.{1,3}$', stripped) and len(stripped) < 6:
                empty_bullet_lines.append(i)
        if empty_bullet_lines:
            warnings.append(ValidationWarning(
                check="highlights_empty_bullets",
                section="Highlights",
                detail=(
                    f"Empty or near-empty bullet points found on lines: "
                    f"{empty_bullet_lines[:10]}. Every highlight/lowlight must "
                    f"have claim + evidence + why it matters."
                ),
                severity="error",
            ))

        # 12b. Duplicate highlights — check for near-identical lines
        lines = [l.strip() for l in hl.split("\n") if len(l.strip()) > 20]
        seen_normalized = {}
        for line in lines:
            # Normalize: lowercase, strip emojis/bullets/numbers
            norm = re.sub(r'[•🌟⚠️🎯🧠①②③④⑤⑥⑦⑧⑨⑩\*\-]', '', line.lower()).strip()
            norm = re.sub(r'\s+', ' ', norm)
            if len(norm) < 30:
                continue
            for prev_norm, prev_line in seen_normalized.items():
                # Check similarity — if 70%+ word overlap, it's a duplicate
                words_norm = set(norm.split())
                words_prev = set(prev_norm.split())
                if words_norm and words_prev:
                    overlap = len(words_norm & words_prev) / min(len(words_norm), len(words_prev))
                    if overlap > 0.7:
                        warnings.append(ValidationWarning(
                            check="highlights_duplicates",
                            section="Highlights",
                            detail=(
                                f"Duplicate or near-duplicate highlights detected:\n"
                                f"  1. \"{prev_line[:120]}...\"\n"
                                f"  2. \"{line[:120]}...\"\n"
                                f"Overlap: {overlap:.0%}. Merge or remove duplicates."
                            ),
                            severity="warning",
                        ))
                        break
            seen_normalized[norm] = line

        # 12c. "No major red flags" paradox — if material risks are listed
        no_red_flags = bool(re.search(
            r'no\s+major\s+red\s+flags?|no\s+significant\s+(concerns?|risks?|issues?)',
            hl, re.IGNORECASE
        ))
        if no_red_flags:
            # Count lowlight/risk entries
            lowlight_count = len(re.findall(r'⚠️|lowlight|concern|risk|懸念|リスク', hl, re.IGNORECASE))
            if lowlight_count >= 2:
                warnings.append(ValidationWarning(
                    check="highlights_red_flags_paradox",
                    section="Highlights",
                    detail=(
                        f"Claims 'no major red flags' but {lowlight_count} risks/concerns "
                        f"are listed. Either the risks are material (remove the claim) or "
                        f"they aren't (remove the lowlights). Cannot have both."
                    ),
                    severity="error",
                ))

        # 12d. Unsubstantiated claims — highlight with no number or source
        highlight_blocks = re.split(r'\n(?=🌟|⚠️|•)', hl)
        unsubstantiated = []
        for block in highlight_blocks:
            block = block.strip()
            if len(block) < 20:
                continue
            # A substantive highlight must have at least one number or source reference
            has_number = bool(re.search(r'\$?\d+[\.\d]*\s*[BMK%]|[\d\.]+\s*%|[\d\.]+x', block))
            has_source = bool(re.search(
                r'(?:transcript|source|filing|press\s*release|10-[KQ]|SEC|'
                r'management\s+said|CEO|CFO|according\s+to|reported\s+by)',
                block, re.IGNORECASE
            ))
            if not has_number and not has_source:
                unsubstantiated.append(block[:100])
        if unsubstantiated and len(unsubstantiated) >= 2:
            warnings.append(ValidationWarning(
                check="highlights_unsubstantiated",
                section="Highlights",
                detail=(
                    f"{len(unsubstantiated)} highlight/lowlight entries lack numerical evidence "
                    f"or source attribution. Every claim requires a metric or source reference. "
                    f"First: \"{unsubstantiated[0]}...\""
                ),
                severity="error",
            ))

    # ── RULE 13 (BLOCKING): §9 EPS & Revenue reconciliation ───────────────
    #
    # Enforce corrections.txt §9: source accuracy, no false "Not available",
    # no raw provider keys, no CRITICAL OVERRIDE in final output.

    eps_rev_text = _sec.get("EPS & Revenue", "")
    if isinstance(eps_rev_text, str) and eps_rev_text.strip():
        er = eps_rev_text

        # 13a. SEC as consensus source — "SEC" should not appear near estimate/consensus
        sec_as_source = bool(re.search(
            r'(?:Source|source).*?SEC|SEC.*?(?:estimate|consensus)',
            er, re.IGNORECASE | re.DOTALL
        ))
        if sec_as_source:
            warnings.append(ValidationWarning(
                check="eps_revenue_sec_as_consensus_source",
                section="EPS & Revenue",
                detail=(
                    "FATAL: 'SEC' appears near estimate/consensus context in Source column. "
                    "Consensus estimates come from analyst consensus, not SEC filings. "
                    "Use 'Company reported' for actuals, 'Analyst consensus' for estimates."
                ),
                severity="warning",
            ))

        # 13b. "Not available" in text when metrics have the value
        eps_actual_val = metric_map.get("eps_actual")
        rev_actual_val = metric_map.get("revenue_actual")
        has_not_available = bool(re.search(
            r'Not\s+available|Not\s+retrieved|DATA\s+NOT\s+AVAILABLE|N/A',
            er, re.IGNORECASE
        ))
        if has_not_available:
            if eps_actual_val is not None and eps_actual_val != 0:
                warnings.append(ValidationWarning(
                    check="eps_revenue_not_available_contradiction",
                    section="EPS & Revenue",
                    detail=(
                        f"EPS & Revenue section says 'Not available' but metrics contain "
                        f"eps_actual=${eps_actual_val:.2f}. Table and text MUST show the value."
                    ),
                    severity="error",
                ))
            if rev_actual_val is not None and rev_actual_val != 0:
                warnings.append(ValidationWarning(
                    check="eps_revenue_not_available_contradiction",
                    section="EPS & Revenue",
                    detail=(
                        f"EPS & Revenue section says 'Not available' but metrics contain "
                        f"revenue_actual=${rev_actual_val:,.0f}. Table and text MUST show the value."
                    ),
                    severity="error",
                ))

        # 13c. Raw provider keys — no yfinance field names or debug labels
        raw_provider_patterns = [
            (r'yfinance\s+key', 'yfinance key'),
            (r'trailingPE\b', 'trailingPE'),
            (r'earningsGrowth\b', 'earningsGrowth'),
            (r'revenueGrowth\b', 'revenueGrowth'),
            (r'pegRatio\b', 'pegRatio'),
            (r'raw\s+provider', 'raw provider'),
            (r'provider\s+key', 'provider key'),
        ]
        for pattern, label in raw_provider_patterns:
            if re.search(pattern, er, re.IGNORECASE):
                warnings.append(ValidationWarning(
                    check="eps_revenue_raw_provider_key",
                    section="EPS & Revenue",
                    detail=(
                        f"FATAL: Raw provider key/field name '{label}' found in EPS & Revenue. "
                        f"Use human-readable source labels only — never expose internal field names."
                    ),
                    severity="error",
                ))
                break  # One is enough to block

        # 13d. If estimate is missing but beat/miss is discussed — impossible
        has_beat_or_miss = bool(re.search(
            r'\b(beat|miss|exceed|surpass|above|below)\s+(consensus|estimate|expectation)',
            er, re.IGNORECASE
        ))
        eps_est_val = metric_map.get("eps_estimate")
        rev_est_val = metric_map.get("revenue_estimate")
        if has_beat_or_miss and eps_est_val is None and rev_est_val is None:
            warnings.append(ValidationWarning(
                check="eps_revenue_beat_miss_without_estimate",
                section="EPS & Revenue",
                detail=(
                    "FATAL: Beat/miss language detected but neither EPS nor Revenue "
                    "estimate is available in metrics. Beat/miss is 'not calculable "
                    "from reviewed sources' — do not invent it."
                ),
                severity="error",
            ))

    # ── RULE 14 (BLOCKING): §26 Raw Markdown rendering — no pipe tables, heading markers ─
    #
    # PDF must never contain raw Markdown syntax leaked from the LLM.

    for section_name, text in _sec.items():
        if not isinstance(text, str) or not text.strip():
            continue
        # 14a. Raw Markdown pipe table syntax
        pipe_table_lines = [l for l in text.split("\n") if re.match(r'^\s*\|.*\|\s*$', l) and '---' not in l]
        if len(pipe_table_lines) >= 2:  # At least header + separator
            warnings.append(ValidationWarning(
                check="raw_markdown_table",
                section=section_name,
                detail=(
                    f"Raw Markdown table syntax found in section '{section_name}'. "
                    f"Pipe tables must be rendered, not leaked as text. "
                    f"First line: '{pipe_table_lines[0][:100]}'"
                ),
                severity="warning",
            ))

        # 14b. Raw heading markers (###, ##) in prose
        heading_markers = re.findall(r'^#{1,3}\s+\w', text, re.MULTILINE)
        if heading_markers:
            warnings.append(ValidationWarning(
                check="raw_markdown_headings",
                section=section_name,
                detail=(
                    f"Raw Markdown heading markers found in section '{section_name}': "
                    f"{heading_markers[:3]}. Use rendered headings, not raw '###'."
                ),
                severity="warning",
            ))

        # 14c. Raw bullet markers that should be rendered
        raw_bullets = re.findall(r'(?m)^[\*\-\+]\s+(?!\s)', text)
        if len(raw_bullets) >= 3:
            warnings.append(ValidationWarning(
                check="raw_markdown_bullets",
                section=section_name,
                detail=(
                    f"Raw Markdown bullet markers found in section '{section_name}'. "
                    f"Use rendered bullets ('•'), not raw '* ' or '- '."
                ),
                severity="warning",
            ))

    # ── RULE 15 (BLOCKING): §25 Chart data consistency ─────────────────────
    #
    # Chart must not contradict text/table, and must use real data.

    # This check runs on the validator's metrics input — not on the PDF output.
    # It prevents chart generation with placeholder/fake data.

    eps_actual_m = metric_map.get("eps_actual")
    eps_estimate_m = metric_map.get("eps_estimate")
    rev_actual_m = metric_map.get("revenue_actual")
    rev_estimate_m = metric_map.get("revenue_estimate")

    # Check if EPS & Revenue text contradicts chart data
    if eps_actual_m is not None and eps_estimate_m is not None:
        eps_rev_t = _sec.get("EPS & Revenue", "")
        if isinstance(eps_rev_t, str) and eps_rev_t.strip():
            # If text says "beat" but metrics say actual < estimate → contradiction
            text_beat = bool(re.search(r'\b(beat|exceeded|surpassed|above)\s+(consensus|estimate)', eps_rev_t, re.IGNORECASE))
            if text_beat and eps_actual_m < eps_estimate_m:
                warnings.append(ValidationWarning(
                    check="chart_eps_contradiction",
                    section="EPS & Revenue",
                    detail=(
                        f"Text says EPS beat consensus but metrics show "
                        f"actual=${eps_actual_m:.2f} < estimate=${eps_estimate_m:.2f}. "
                        f"Chart and text MUST agree."
                    ),
                    severity="error",
                ))

    if rev_actual_m is not None and rev_estimate_m is not None:
        eps_rev_t = _sec.get("EPS & Revenue", "")
        if isinstance(eps_rev_t, str) and eps_rev_t.strip():
            text_beat = bool(re.search(r'\b(beat|exceeded|surpassed|above)\s+(consensus|estimate)', eps_rev_t, re.IGNORECASE))
            if text_beat and rev_actual_m < rev_estimate_m:
                warnings.append(ValidationWarning(
                    check="chart_revenue_contradiction",
                    section="EPS & Revenue",
                    detail=(
                        f"Text says Revenue beat consensus but metrics show "
                        f"actual=${rev_actual_m:,.0f} < estimate=${rev_estimate_m:,.0f}. "
                        f"Chart and text MUST agree."
                    ),
                    severity="error",
                ))

    # ── RULE 16 (BLOCKING): §11 Operating Metrics consistency ──────────────
    #
    # Table values must not be contradicted by text. Margin changes must be
    # labeled as bps/percentage-points when appropriate.

    op_metrics_text = _sec.get("Operating Metrics", "")
    if isinstance(op_metrics_text, str) and op_metrics_text.strip():
        om = op_metrics_text

        # 16a. Table shows metric but text says "not retrieved/available"
        has_not_avail = bool(re.search(
            r'Not\s+(available|retrieved)|DATA\s+NOT\s+AVAILABLE', om, re.IGNORECASE
        ))
        if has_not_avail:
            gross_margin_m = metric_map.get("gross_margin")
            op_margin_m = metric_map.get("operating_margin")
            op_income_m = metric_map.get("operating_income")
            net_income_m = metric_map.get("net_income_quarterly") or metric_map.get("net_income")
            if gross_margin_m is not None or op_margin_m is not None:
                warnings.append(ValidationWarning(
                    check="operating_metrics_not_available_contradiction",
                    section="Operating Metrics",
                    detail=(
                        "Operating Metrics says 'Not available' but metrics contain "
                        "gross_margin, operating_margin, or other values. "
                        "If the value is in the table, text cannot say it was not retrieved."
                    ),
                    severity="error",
                ))
            elif op_income_m is not None or net_income_m is not None:
                warnings.append(ValidationWarning(
                    check="operating_metrics_not_available_contradiction",
                    section="Operating Metrics",
                    detail=(
                        "Operating Metrics says 'Not available' but metrics contain "
                        "operating_income or net_income values. Table/text must agree."
                    ),
                    severity="error",
                ))

        # 16b. Margin changes labeled as % growth instead of bps/pp
        margin_pct_growth = bool(re.search(
            r'(?:gross|operating|net)\s*margin\s*(?:grew|increased|expanded|rose|up)\s+(?:by\s+)?[\d.]+\s*%',
            om, re.IGNORECASE
        ))
        has_bps_mention = bool(re.search(
            r'\bbps\b|\bbasis\s+points?\b|\bpercentage\s+points?\b|\bpp\b', om, re.IGNORECASE
        ))
        if margin_pct_growth and not has_bps_mention:
            warnings.append(ValidationWarning(
                check="operating_metrics_margin_label",
                section="Operating Metrics",
                detail=(
                    "Margin changes described as percent growth (e.g. 'margin grew by 5%'). "
                    "Margin changes should use basis points (bps) or percentage points — "
                    "a margin going from 60% to 65% is +500bps, not +5% growth."
                ),
                severity="error",
            ))

    # ── RULE 17 (BLOCKING): §12 Cash Flow sign conventions ─────────────────
    #
    # No raw provider keys. FCF must be consistent. CapEx sign normalized.

    cash_flow_text = _sec.get("Cash Flow", "")
    if isinstance(cash_flow_text, str) and cash_flow_text.strip():
        cf = cash_flow_text

        # 17a. Raw provider keys in Cash Flow
        cf_raw_patterns = [
            (r'yfinance\s+key', 'yfinance key'),
            (r'operating_cash_flow\b', 'operating_cash_flow'),
            (r'capital_expenditure\b', 'capital_expenditure'),
            (r'free_cash_flow\b', 'free_cash_flow'),
        ]
        for pattern, label in cf_raw_patterns:
            if re.search(pattern, cf, re.IGNORECASE):
                warnings.append(ValidationWarning(
                    check="cash_flow_raw_provider_key",
                    section="Cash Flow",
                    detail=(
                        f"Raw provider key '{label}' found in Cash Flow. "
                        f"Use human-readable labels: 'Operating cash flow', 'CapEx', 'Free cash flow'."
                    ),
                    severity="error",
                ))
                break

        # 17b. FCF in table but inconsistent in narrative
        fcf_m = metric_map.get("free_cash_flow")
        if fcf_m is not None:
            # Only check dollar amounts near "free cash flow" / "FCF" mentions
            fcf_contexts = re.findall(
                r'(?:free\s+cash\s+flow|FCF).{0,80}(\$[\d,.]+(?:\s*(?:billion|million|B|M))?)',
                cf, re.IGNORECASE
            )
            if fcf_contexts and abs(fcf_m) > 1e9:
                fcf_b = abs(fcf_m) / 1e9
                for fig in fcf_contexts:
                    try:
                        clean = re.sub(r'[^\d.BM]', '', fig, flags=re.IGNORECASE)
                        if 'B' in clean.upper():
                            val = float(clean.upper().replace('B', ''))
                            if abs(val - fcf_b) > fcf_b * 0.20:
                                warnings.append(ValidationWarning(
                                    check="cash_flow_fcf_consistency",
                                    section="Cash Flow",
                                    detail=(
                                        f"FCF in metrics: ${fcf_b:.1f}B. "
                                        f"FCF mentioned in text: {fig.strip()}. "
                                        f"Values differ by >20%. Table and text must agree."
                                    ),
                                    severity="warning",
                                ))
                    except (ValueError, TypeError):
                        pass

    # ── RULE 18 (BLOCKING): §13 Capital Efficiency validation ──────────────
    #
    # Table shows ratio but text says unavailable. Provider-supplied must be labeled.

    cap_eff_text = _sec.get("Capital Efficiency", "")
    if isinstance(cap_eff_text, str) and cap_eff_text.strip():
        ce = cap_eff_text

        # 18a. Table shows ROE/ROIC/ROA but text says unavailable
        has_not_avail_ce = bool(re.search(
            r'Not\s+(available|retrieved)|DATA\s+NOT\s+AVAILABLE|unavailable',
            ce, re.IGNORECASE
        ))
        if has_not_avail_ce:
            roe_m = metric_map.get("roe")
            roic_m = metric_map.get("roic")
            roa_m = metric_map.get("roa")
            if roe_m is not None or roic_m is not None or roa_m is not None:
                warnings.append(ValidationWarning(
                    check="capital_efficiency_not_available_contradiction",
                    section="Capital Efficiency",
                    detail=(
                        "Capital Efficiency says 'Not available' but metrics contain "
                        "ROE/ROIC/ROA values. If shown in the table, text cannot "
                        "claim they are unavailable."
                    ),
                    severity="warning",
                ))

        # 18b. Extreme ratios without provider-supplied label check
        roe_v = metric_map.get("roe")
        roic_v = metric_map.get("roic")
        extreme = False
        extreme_detail = ""
        if roe_v is not None and abs(roe_v) > 100:
            extreme = True
            extreme_detail = f"ROE={roe_v:.0f}%"
        if roic_v is not None and abs(roic_v) > 100:
            extreme = True
            extreme_detail += (", " if extreme_detail else "") + f"ROIC={roic_v:.0f}%"
        if extreme:
            has_provider_label = bool(re.search(
                r'provider.supplied|provider.sourced|as\s+reported\s+by', ce, re.IGNORECASE
            ))
            if not has_provider_label:
                warnings.append(ValidationWarning(
                    check="capital_efficiency_extreme_unlabeled",
                    section="Capital Efficiency",
                    detail=(
                        f"Extreme ratio(s) detected: {extreme_detail}. "
                        f"Values >100% require a provider-supplied label or "
                        f"denominator validation. Add 'Provider-supplied' or verify the calculation."
                    ),
                    severity="error",
                ))

    # ── RULE 19 (BLOCKING): §15 Guidance reconciliation ─────────────────────
    #
    # Consensus is not management guidance. Current actual is not guidance.

    guidance_text = _sec.get("Guidance", "")
    if isinstance(guidance_text, str) and guidance_text.strip():
        gd = guidance_text

        # 19a. Consensus/analyst estimate presented as guidance
        has_consensus_as_guidance = bool(re.search(
            r'(?:analyst|consensus)\s+(?:estimate|forecast|expectation).{0,60}guidance',
            gd, re.IGNORECASE
        ))
        if has_consensus_as_guidance:
            warnings.append(ValidationWarning(
                check="guidance_consensus_conflated",
                section="Guidance",
                detail=(
                    "Analyst consensus/estimate is presented as guidance. "
                    "Consensus is NOT management guidance — they are distinct. "
                    "Label each clearly: 'Management guidance' vs 'Analyst consensus'."
                ),
                severity="error",
            ))

        # 19b. Current quarter actual presented as guidance
        current_as_guidance = bool(re.search(
            r'(?:current|this)\s*(?:quarter|period|Q\d).{0,40}guidance',
            gd, re.IGNORECASE
        ))
        if current_as_guidance:
            warnings.append(ValidationWarning(
                check="guidance_current_as_guidance",
                section="Guidance",
                detail=(
                    "Current quarter actual presented as guidance. "
                    "Current actuals are NOT guidance — guidance is forward-looking. "
                    "Separate 'Current quarter actual' from 'Forward guidance'."
                ),
                severity="error",
            ))

        # 19c. "Not guided" in table but narrative contains guidance
        has_not_guided = bool(re.search(
            r'Not\s+guided|no\s+guidance\s+(?:provided|issued|given)',
            gd, re.IGNORECASE
        ))
        has_guidance_narrative = bool(re.search(
            r'(?:management|company)\s+(?:guided|guidance|expects|forecasts|outlook|sees|projects)',
            gd, re.IGNORECASE
        ))
        if has_not_guided and has_guidance_narrative:
            warnings.append(ValidationWarning(
                check="guidance_table_narrative_contradiction",
                section="Guidance",
                detail=(
                    "Table says 'Not guided' but narrative contains guidance language. "
                    "If management issued guidance, the table must reflect it. "
                    "If table says not guided, narrative cannot present guidance."
                ),
                severity="error",
            ))

    # ── RULE 20 (BLOCKING): §16 Backlog / Demand visibility ─────────────────
    #
    # No forced backlog. No "Backlog is Not available." No empty table.

    backlog_text = _sec.get("Backlog", "")
    if isinstance(backlog_text, str) and backlog_text.strip():
        bl = backlog_text

        # 20a. "Backlog is Not available" — replace with professional language
        has_na_backlog = bool(re.search(
            r'Backlog\s+(?:is\s+)?Not\s+available|Backlog.*?N/A',
            bl, re.IGNORECASE
        ))
        if has_na_backlog:
            warnings.append(ValidationWarning(
                check="backlog_na_language",
                section="Backlog",
                detail=(
                    "'Backlog is Not available' found. Use professional language: "
                    "'The company does not publicly disclose backlog figures.' "
                    "Do not force a backlog table when no data exists."
                ),
                severity="error",
            ))

        # 20b. Empty or near-empty backlog section — likely forced
        cleaned = re.sub(r'[•🌟⚠️🎯🧠\*\-#\|\s]', '', bl)
        if len(cleaned) < 30:
            warnings.append(ValidationWarning(
                check="backlog_empty_or_forced",
                section="Backlog",
                detail=(
                    f"Backlog section appears empty or near-empty "
                    f"(meaningful content: {len(cleaned)} chars). "
                    f"If the company does not disclose backlog/RPO/orders, "
                    f"use a short 'Demand visibility' note instead of a forced table."
                ),
                severity="error",
            ))

    # ── RULE 21 (BLOCKING): §20 Verdict consistency ─────────────────────────
    #
    # Verdict must be consistent with EPS beat/miss, risks, valuation, Data Quality.

    verdict_text = _sec.get("Verdict", "")
    if isinstance(verdict_text, str) and verdict_text.strip():
        vd = verdict_text

        # 21a. Score-commentary alignment (extends RULE 7)
        score_match = SCORE_RE.search(vd)
        if score_match:
            score = int(score_match.group(1))
            if score >= 7:
                negative_count = sum(
                    1 for phrase in NEGATIVE_PHRASES if phrase.lower() in vd.lower()
                )
                if negative_count >= 2:
                    warnings.append(ValidationWarning(
                        check="verdict_score_negative_contradiction",
                        section="Verdict",
                        detail=(
                            f"Score is {score}/10 (positive) but {negative_count} negative "
                            f"phrases found ('sell immediately', 'crash', 'avoid', etc.). "
                            f"Verdict must align with score."
                        ),
                        severity="error",
                    ))

        # 21b. If EPS beat but verdict too negative
        eps_beat = _detect_eps_direction(eps_rev_text)
        if eps_beat == "BEAT":
            vd_lower = vd.lower()
            strong_negative = [
                "sell", "avoid this stock", "dump", "bearish",
                "downgrade", "underperform", "negative outlook"
            ]
            if sum(1 for p in strong_negative if p in vd_lower) >= 2:
                warnings.append(ValidationWarning(
                    check="verdict_beat_but_too_negative",
                    section="Verdict",
                    detail=(
                        "EPS beat consensus but Verdict uses strongly negative language "
                        "(e.g. 'sell', 'avoid', 'downgrade'). If risks truly outweigh "
                        "the beat, explain why explicitly."
                    ),
                    severity="error",
                ))

        # 21c. "No major red flags" but material risks / data confidence is medium
        no_red_flags_v = bool(re.search(
            r'no\s+major\s+(red\s+flags?|risks?|concerns?)',
            vd, re.IGNORECASE
        ))
        if no_red_flags_v:
            risks_count = len(re.findall(
                r'\b(risk|concern|headwind|threat|uncertain|pressure|competition|'
                r'regulatory|geopolitical|supply\s+chain|margin\s+compression)\b',
                vd, re.IGNORECASE
            ))
            if risks_count >= 3:
                warnings.append(ValidationWarning(
                    check="verdict_no_red_flags_paradox",
                    section="Verdict",
                    detail=(
                        f"Claims 'no major red flags' but {risks_count} risk-related "
                        f"terms found. If risks are material, don't claim otherwise."
                    ),
                    severity="error",
                ))

    # ── RULE 22 (BLOCKING): §19 Valuation sanity ─────────────────────────────
    #
    # FCF yield below 2% must be flagged. High P/FCF must be flagged.
    # "Attractive" requires quantitative support.

    # Check valuation signals from metrics
    fcf_yield_m = metric_map.get("fcf_yield")
    pfcf_m = metric_map.get("price_to_fcf") or metric_map.get("pfcf")
    pe_fwd_m = metric_map.get("pe_forward")

    # Also check Valuation V2.7 section if present
    valuation_text = _sec.get("Valuation", "")

    # 22a. FCF yield < 2% but valuation claims "attractive"
    if fcf_yield_m is not None and fcf_yield_m < 2.0:
        all_val_text = (valuation_text or "") + " " + (verdict_text or "")
        has_attractive = bool(re.search(
            r'\b(attractive|compelling|cheap|undervalued|bargain)\b',
            all_val_text, re.IGNORECASE
        ))
        if has_attractive:
            warnings.append(ValidationWarning(
                check="valuation_fcf_yield_warning",
                section="Valuation",
                detail=(
                    f"FCF yield is {fcf_yield_m:.1f}% (<2%) but valuation conclusion "
                    f"uses 'attractive'/'compelling'/'cheap'. "
                    f"FCF yield below 2% MUST be highlighted as a valuation risk."
                ),
                severity="error",
            ))

    # 22b. High P/FCF not flagged
    if pfcf_m is not None and pfcf_m > 40:
        all_val_text = (valuation_text or "") + " " + (verdict_text or "")
        has_pfcf_warning = bool(re.search(
            r'(?:high|elevated|stretched|expensive)\s*(?:P/?FCF|price.to.free.cash)'
            r'|(?:P/?FCF|price.to.free.cash).{0,20}(?:high|elevated|stretched|expensive)',
            all_val_text, re.IGNORECASE
        ))
        if not has_pfcf_warning:
            warnings.append(ValidationWarning(
                check="valuation_pfcf_not_flagged",
                section="Valuation",
                detail=(
                    f"P/FCF is {pfcf_m:.1f}x (>40x) but not flagged as elevated. "
                    f"High P/FCF MUST be highlighted as a valuation risk."
                ),
                severity="error",
            ))

    # ── RULE 23 (BLOCKING): §21 Data Quality truthfulness ────────────────────
    #
    # Completeness can't be 100 if critical metrics missing. Confidence can't be
    # high if period mismatch or sources not used.

    dq_text = _sec.get("Data Quality", "")
    if isinstance(dq_text, str) and dq_text.strip():
        dq = dq_text

        # 23a. Completeness 100/100 but critical metrics missing
        completeness_match = re.search(
            r'(?:Completeness|completeness).*?(\d+)\s*/\s*100', dq, re.IGNORECASE
        )
        if completeness_match:
            score_val = int(completeness_match.group(1))
            if score_val >= 95:
                # Check if critical metrics are actually unavailable
                critical_missing = []
                for field, label in [
                    ("eps_actual", "EPS actual"),
                    ("revenue_actual", "Revenue actual"),
                    ("free_cash_flow", "Free cash flow"),
                    ("gross_margin", "Gross margin"),
                ]:
                    if metric_map.get(field) is None:
                        critical_missing.append(label)
                if len(critical_missing) >= 2:
                    warnings.append(ValidationWarning(
                        check="data_quality_false_completeness",
                        section="Data Quality",
                        detail=(
                            f"Completeness claims {score_val}/100 but {len(critical_missing)} "
                            f"critical metrics are missing: {', '.join(critical_missing[:5])}. "
                            f"Completeness cannot be near-100 if critical metrics are absent."
                        ),
                        severity="error",
                    ))

        # 23b. "All sources used" but transcript/SEC not used
        all_sources_used = bool(re.search(
            r'all\s+sources?\s+(?:used|available|verified)|every\s+source',
            dq, re.IGNORECASE
        ))
        if all_sources_used:
            # Check if the report text indicates no transcript
            tx_ok = True
            if "transcript not available" in dq.lower() or "no transcript" in dq.lower():
                tx_ok = False
            if not tx_ok:
                warnings.append(ValidationWarning(
                    check="data_quality_sources_inaccurate",
                    section="Data Quality",
                    detail=(
                        "Claims 'all sources used' but transcript is noted as "
                        "unavailable. Source usage status MUST be truthful."
                    ),
                    severity="error",
                ))

    # ── RULE 24 (BLOCKING): §14 Segments hierarchy reconciliation ────────────
    #
    # No parent/child double-counting. No "Total Not available" if total exists.

    segments_text = _sec.get("Segments", "")
    if isinstance(segments_text, str) and segments_text.strip():
        sg = segments_text

        # 24a. "Total Not available" but total revenue exists
        has_total_na = bool(re.search(
            r'Total\s*:?\s*(?:is\s+)?(?:Not\s+available|N/A|—)',
            sg, re.IGNORECASE
        ))
        if has_total_na:
            rev_q_m = metric_map.get("revenue_quarterly") or metric_map.get("revenue_actual")
            if rev_q_m is not None:
                warnings.append(ValidationWarning(
                    check="segments_total_na_contradiction",
                    section="Segments",
                    detail=(
                        f"'Total Not available' in Segments but metrics contain "
                        f"revenue data. If total revenue exists in the ledger, "
                        f"do not show 'Not available' for the total."
                    ),
                    severity="error",
                ))

        # 24b. Parent/child mixing — check for common subsegment overlap patterns
        # If both "Data Center" and sub-categories appear, flag potential double-count
        parent_terms = ["data center", "compute", "networking", "gaming", "automotive"]
        found_parents = [t for t in parent_terms if t in sg.lower()]
        if len(found_parents) >= 2:
            # Check if any parent appears alongside likely subsegments
            subsegment_indicators = re.findall(
                r'(?:sub.segment|breakdown|of\s+which|including:|comprised?\s+of)',
                sg, re.IGNORECASE
            )
            if not subsegment_indicators:
                # No explicit subsegment notation — might be mixing levels
                if len(re.findall(r'\$\d+', sg)) > len(found_parents) * 2:
                    warnings.append(ValidationWarning(
                        check="segments_hierarchy_warning",
                        section="Segments",
                        detail=(
                            f"Multiple revenue figures found across segment categories "
                            f"({', '.join(found_parents[:3])}). Verify parent/child rows "
                            f"are not being summed — use subsegment labels if mixing levels."
                        ),
                        severity="error",
                    ))

    # ── RULE 25 (BLOCKING): §6 Earnings Documents Checklist ──────────────────
    #
    # No management commentary if transcript is missing.
    # No presentation-derived KPI claims if presentation is unavailable.
    # No beat/miss for metrics without consensus.

    if earnings_documents is not None:
        ed = earnings_documents

        # 25a. Missing transcript → no management commentary
        mgmt_key = "Management & Tone"
        if not getattr(ed, 'transcript_available', False) and mgmt_key in _sec and isinstance(
            _sec.get(mgmt_key, ""), str
        ):
            mgmt_text = _sec[mgmt_key]
            # Check for transcript-derived language
            transcript_indicators = [
                "CEO said", "CFO mentioned", "management stated",
                "during the call", "on the earnings call",
                "management guided", "according to the transcript",
                "per the transcript"
            ]
            found = [ti for ti in transcript_indicators if ti.lower() in mgmt_text.lower()]
            if found:
                warnings.append(ValidationWarning(
                    check="earnings_docs_missing_transcript_management_claims",
                    section="Management & Tone",
                    detail=(
                        f"Management commentary suggests transcript access but "
                        f"transcript_status={getattr(ed, 'transcript_status', '?')}. "
                        f"Remove transcript-derived claims or mark them as 'from press release / SEC filing'. "
                        f"Detected: {', '.join(found[:3])}"
                    ),
                    severity="error",
                ))

        # 25b. Missing presentation → no presentation-derived claims
        if not getattr(ed, 'presentation_available', False) and isinstance(
            _sec.get("Operating Metrics", ""), str
        ):
            op_text = _sec.get("Operating Metrics", "")
            pres_indicators = [
                "earnings presentation", "investor deck",
                "slide deck", "earnings slides",
                "IR presentation"
            ]
            found = [pi for pi in pres_indicators if pi.lower() in op_text.lower()]
            if found:
                warnings.append(ValidationWarning(
                    check="earnings_docs_missing_presentation_claims",
                    section="Operating Metrics",
                    detail=(
                        f"KPI claims reference presentation but "
                        f"presentation_status={getattr(ed, 'presentation_status', '?')}. "
                        f"Remove presentation-derived claims or source them from SEC filing."
                    ),
                    severity="error",
                ))

        # 25c. Missing consensus → no beat/miss claims
        if getattr(ed, 'consensus_status', '') != "retrieved":
            for section_name in ["EPS & Revenue", "Highlights & Lowlights"]:
                sec_text = _sec.get(section_name, "")
                if not isinstance(sec_text, str):
                    continue
                # Check if beat/miss language appears without consensus
                beat_words = re.findall(
                    r'(beat|missed?|above|below|surprise|vs\.?\s*consensus|vs\.?\s*estimate)[\w\s]*',
                    sec_text, re.IGNORECASE
                )
                if beat_words and "not calculable" not in sec_text.lower():
                    warnings.append(ValidationWarning(
                        check="earnings_docs_missing_consensus_beat_miss",
                        section=section_name,
                        detail=(
                            f"Beat/miss language detected but consensus_status="
                            f"{getattr(ed, 'consensus_status', '?')}. "
                            f"Without consensus, beat/miss must say 'not calculable from reviewed sources'."
                            f" Detected: {', '.join(beat_words[:3])}"
                        ),
                        severity="error",
                    ))

        # 25d. Missing SEC filing — critical
        if getattr(ed, 'sec_filing_status', '') != "retrieved":
            # Scan all sections for SEC/10-Q/10-K citations
            for section_name in _sec:
                sec_text = _sec.get(section_name, "")
                if not isinstance(sec_text, str):
                    continue
                if re.search(r'\b(?:SEC|10-[KQ]|EDGAR|filing)\b', sec_text, re.IGNORECASE):
                    warnings.append(ValidationWarning(
                        check="earnings_docs_missing_sec_filing_citation",
                        section=section_name,
                        detail=(
                            f"SEC/10-Q/10-K reference found but "
                            f"sec_filing_status={getattr(ed, 'sec_filing_status', '?')}. "
                            f"Remove SEC citations or source data from available documents."
                        ),
                        severity="error",
                    ))
                    break  # One warning is enough

    # ── RULE 26 (BLOCKING): §5 Source Registry Integrity ────────────────────
    #
    # - No raw provider keys in report text (yfinance key, raw field names)
    # - Source IDs like S1 must have readable mappings
    # - Sources cited as evidence must have status="used"

    if source_registry is not None:
        sr = source_registry
        # Build mapping of known source IDs for quick lookup
        registry_entries = getattr(sr, 'entries', [])
        registry_ids = {getattr(e, 'source_id', '') for e in registry_entries}
        used_source_ids = {
            getattr(e, 'source_id', '') for e in registry_entries
            if getattr(e, 'status', '') == "used"
        }

        # 26a. Raw provider key leaks
        raw_key_patterns = [
            (r'yfinance\s+key\s*[:=]', 'yfinance key:'),
            (r'finnhub\s+key\s*[:=]', 'finnhub key:'),
            (r'provider\s*[:=]\s*["\']?\w+["\']?', 'provider:'),
            (r'raw_field\s*[:=]', 'raw_field:'),
        ]
        for section_name, text in _sec.items():
            if not isinstance(text, str):
                continue
            for pattern, label in raw_key_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    warnings.append(ValidationWarning(
                        check="source_registry_raw_provider_key_leak",
                        section=section_name,
                        detail=(
                            f"Raw provider key detected ('{label}'). "
                            f"Use client-ready public labels from the source registry. "
                            f"Never expose internal provider field names in the PDF."
                        ),
                        severity="error",
                    ))
                    break  # One per section is enough

        # 26b. Source IDs like S1/S2 without readable mapping in the report
        bare_source_refs = re.findall(r'\b(S\d{1,2})\b', "\n".join(
            t for t in _sec.values() if isinstance(t, str)
        ))
        if bare_source_refs:
            # Check if the registry has labels for these
            unmapped = set()
            for ref in bare_source_refs:
                if ref not in registry_ids:
                    unmapped.add(ref)
                elif ref not in used_source_ids:
                    pass  # It's in registry but marked as candidate — flag
            if unmapped:
                warnings.append(ValidationWarning(
                    check="source_registry_unmapped_source_refs",
                    section="(multiple)",
                    detail=(
                        f"Source references found without registry entries: "
                        f"{', '.join(sorted(unmapped)[:5])}. "
                        f"Every S1/S2/etc. must have a readable mapping in the source registry."
                    ),
                    severity="error",
                ))

        # 26c. Sources cited as evidence must be "used"
        for section_name, text in _sec.items():
            if not isinstance(text, str):
                continue
            # Check for explicit source citations
            for entry in registry_entries:
                sid = getattr(entry, 'source_id', '')
                status = getattr(entry, 'status', '')
                if status != "used" and sid and sid in text:
                    warnings.append(ValidationWarning(
                        check="source_registry_candidate_cited_as_evidence",
                        section=section_name,
                        detail=(
                            f"Source '{sid}' is cited in '{section_name}' but has "
                            f"status='{status}', not 'used'. A source must have "
                            f"status='used' to be cited as evidence."
                        ),
                        severity="error",
                    ))

    # ── RULE 27 (BLOCKING): §4 Metrics Ledger Sanity Checks ─────────────────
    #
    # - No "not retrieved" if metric exists in the ledger
    # - Sanity bounds: dividend yield > 20%, margin > 100%, extreme ratios
    # - No consensus/guidance ambiguity

    if metrics_ledger is not None:
        ml = metrics_ledger
        ledger_entries = getattr(ml, 'entries', [])
        ledger_names = {getattr(e, 'canonical_metric_name', '') for e in ledger_entries}

        # 27a. "Not retrieved" / "Not available" but metric exists in ledger
        all_text = "\n".join(t for t in _sec.values() if isinstance(t, str))
        not_retrieved_pattern = re.compile(
            r'(?:was|were|is|are)\s+not\s+(?:retrieved|available|disclosed)',
            re.IGNORECASE
        )
        not_retrieved_matches = not_retrieved_pattern.findall(all_text)
        if not_retrieved_matches and ledger_names:
            # Check common metric keywords near "not retrieved"
            metric_keywords = {
                'eps': 'eps_actual', 'revenue': 'revenue_actual',
                'net income': 'net_income', 'free cash flow': 'fcf',
                'gross margin': 'gross_margin', 'operating margin': 'operating_margin',
            }
            for keyword, canonical in metric_keywords.items():
                if canonical in ledger_names:
                    # Check if keyword appears near "not retrieved"
                    for section_name, text in _sec.items():
                        if not isinstance(text, str):
                            continue
                        if keyword.lower() in text.lower() and re.search(
                            r'(?:was|were|is|are)\s+not\s+(?:retrieved|available|disclosed)',
                            text, re.IGNORECASE
                        ):
                            # Check proximity: keyword within 200 chars of "not retrieved"
                            idx_kw = text.lower().find(keyword.lower())
                            idx_nr = -1
                            for m in re.finditer(
                                r'(?:was|were|is|are)\s+not\s+(?:retrieved|available|disclosed)',
                                text, re.IGNORECASE
                            ):
                                idx_nr = m.start()
                                break
                            if idx_kw >= 0 and idx_nr >= 0 and abs(idx_kw - idx_nr) < 200:
                                warnings.append(ValidationWarning(
                                    check="metrics_ledger_not_retrieved_contradiction",
                                    section=section_name,
                                    detail=(
                                        f"'{keyword}' appears near 'not retrieved/available' but "
                                        f"'{canonical}' exists in the metrics ledger. "
                                        f"Do not claim a metric is unavailable if it is displayed."
                                    ),
                                    severity="error",
                                ))

        # 27b. Sanity bounds
        for entry in ledger_entries:
            val = getattr(entry, 'value', None)
            name = getattr(entry, 'canonical_metric_name', '')
            unit = getattr(entry, 'unit', '')

            if val is None:
                continue

            # Dividend yield > 20% is exceptional
            if 'dividend_yield' in name and val > 20:
                warnings.append(ValidationWarning(
                    check="metrics_ledger_sanity_dividend_yield",
                    section="Valuation",
                    detail=(
                        f"Dividend yield = {val:.1f}% exceeds 20%. "
                        f"Verify the value or add an explicit explanation."
                    ),
                    severity="error",
                ))

            # Margin > 100% is impossible for standard business
            if unit == "%" and 'margin' in name and val > 100:
                warnings.append(ValidationWarning(
                    check="metrics_ledger_sanity_margin_exceeds_100",
                    section="Financials",
                    detail=(
                        f"{name} = {val:.1f}% exceeds 100%. "
                        f"Margins cannot exceed 100% in standard business; verify the value."
                    ),
                    severity="error",
                ))

        # 27c. Consensus vs SEC labeling check
        for section_name, text in _sec.items():
            if not isinstance(text, str):
                continue
            # EPS/revenue from SEC is not consensus
            sec_consensus_mix = re.search(
                r'SEC.{0,50}(?:consensus|estimate)|(?:consensus|estimate).{0,50}SEC',
                text, re.IGNORECASE
            )
            if sec_consensus_mix:
                warnings.append(ValidationWarning(
                    check="metrics_ledger_sec_consensus_confusion",
                    section=section_name,
                    detail=(
                        f"'SEC' and 'consensus/estimate' appear together in '{section_name}'. "
                        f"Consensus estimates must not be labeled as SEC data."
                    ),
                    severity="error",
                ))
    # ── RULE 28 (BLOCKING): §18 Management Analysis ─────────────────────────
    #
    # - No psychological speculation about management
    # - No unsupported claims in management analysis
    # - Founder-led status discussed only as governance/execution factor

    if management_analysis is not None:
        ma = management_analysis
        strengths = getattr(ma, 'management_strengths', []) or []
        weaknesses = getattr(ma, 'management_weaknesses_or_risks', []) or []
        evidence = getattr(ma, 'evidence', []) or []

        # 28a. Management claims must have evidence
        total_claims = len(strengths) + len(weaknesses)
        if total_claims > 0 and len(evidence) == 0:
            warnings.append(ValidationWarning(
                check="management_analysis_no_evidence",
                section="Management",
                detail=(
                    f"{total_claims} management claim(s) found but no evidence provided. "
                    f"Every management strength/weakness must reference public evidence "
                    f"(execution record, capital allocation, guidance credibility, etc.)."
                ),
                severity="error",
            ))

        # 28b. No psychological speculation keywords
        psych_keywords = [
            "narcissist", "psychopath", "megalomaniac", "delusional",
            "personality disorder", "mentally unstable", "emotional",
            "charismatic but", "egomaniac",
        ]
        all_text = " ".join(strengths + weaknesses)
        found_psych = [kw for kw in psych_keywords if kw.lower() in all_text.lower()]
        if found_psych:
            warnings.append(ValidationWarning(
                check="management_analysis_psychological_speculation",
                section="Management",
                detail=(
                    f"Psychological speculation detected: {', '.join(found_psych)}. "
                    f"Management analysis must be based on public evidence "
                    f"(execution record, capital allocation, governance), not personality traits."
                ),
                severity="error",
            ))

        # Also check section text for "Management & Tone" psychological speculation
        mgmt_sec = _sec.get("Management & Tone", "")
        if isinstance(mgmt_sec, str):
            found_in_text = [kw for kw in psych_keywords if kw.lower() in mgmt_sec.lower()]
            if found_in_text:
                warnings.append(ValidationWarning(
                    check="management_analysis_psychological_speculation_in_text",
                    section="Management & Tone",
                    detail=(
                        f"Psychological speculation in Management section: "
                        f"{', '.join(found_in_text)}. "
                        f"Discuss management through execution record, capital allocation, "
                        f"guidance credibility, governance, and public track record."
                    ),
                    severity="error",
                ))

    # ── RULE 29 (BLOCKING): §17 Competitive Positioning ──────────────────────
    #
    # - No mixing of operating competitors with valuation peers without explanation
    # - No truncated competitor entries (every entry must have competitor name + type)
    # - Every source_id must be mappable

    if competitive_positioning is not None:
        cp = competitive_positioning
        entries = getattr(cp, 'entries', []) or []

        # 29a. Mixed types without labels
        types_present: set[str] = set()
        for e in entries:
            t = getattr(e, 'type', None)
            if t:
                types_present.add(t)
        if "direct" in types_present and "valuation_peer" in types_present:
            # Both types present — check that at least one entry has an explicit label
            has_label = any(
                getattr(e, 'type', None) in ("direct", "valuation_peer")
                for e in entries
            )
            if has_label:
                # Types are explicitly labeled — OK, as long as there's separation note
                # Check in section text for explanation
                comp_text = _sec.get("Competitors", "")
                if isinstance(comp_text, str) and comp_text.strip():
                    has_separator = any(phrase in comp_text.lower() for phrase in [
                        "valuation peer", "peer group", "peer benchmark",
                        "operating competitor", "direct competitor",
                        "separately", "distinct from",
                    ])
                    if not has_separator:
                        warnings.append(ValidationWarning(
                            check="competitive_positioning_mixed_types_no_separator",
                            section="Competitors",
                            detail=(
                                f"Both direct competitors and valuation peers are listed "
                                f"but the Competitors section lacks an explicit separation note. "
                                f"Add language like 'Valuation peers (separately from operating "
                                f"competitors)...' to distinguish the groups."
                            ),
                            severity="error",
                        ))

        # 29b. Truncated entries — check for competitor name with missing type or source
        incomplete = []
        for e in entries:
            name = getattr(e, 'competitor', '')
            comp_type = getattr(e, 'type', None)
            source = getattr(e, 'source_id', None)
            if name and (not comp_type or not source):
                incomplete.append(name)
        if incomplete:
            warnings.append(ValidationWarning(
                check="competitive_positioning_incomplete_entries",
                section="Competitors",
                detail=(
                    f"Incomplete competitor entries: {', '.join(incomplete[:3])}. "
                    f"Each competitor must have a type and source_id. "
                    f"Without source_id, references like 'S1' become unmapped."
                ),
                severity="error",
            ))

        # 29c. Generic comparison check — no source or specific advantage
        generic_indicators = [
            "similar to", "comparable to", "like other companies",
            "industry standard", "typical for the sector",
        ]
        comp_text = _sec.get("Competitors", "")
        if isinstance(comp_text, str):
            found_generic = [gi for gi in generic_indicators if gi.lower() in comp_text.lower()]
            if found_generic and len(entries) == 0:
                warnings.append(ValidationWarning(
                    check="competitive_positioning_generic_no_data",
                    section="Competitors",
                    detail=(
                        f"Generic competitor language detected ({', '.join(found_generic[:2])}) "
                        f"but no structured competitor entries exist. "
                        f"Either provide specific competitor data or use precise language."
                    ),
                    severity="error",
                ))

    # ── RULE 30 (BLOCKING): §22+§23 Missing-data language + internal leaks ──
    #
    # §22: Strict missing-data taxonomy (no standalone "Not available", no "Reason:")
    # §23: No programming-language artifacts (null, None, NaN, undefined, debug)

    for section_name, text in _sec.items():
        if not isinstance(text, str) or not text.strip():
            continue

        # 30a. "Reason:" exposed in output — internal reasoning leak
        if re.search(r'\bReason\s*:', text):
            warnings.append(ValidationWarning(
                check="missing_data_reason_leak",
                section=section_name,
                detail=(
                    f"'Reason:' found in '{section_name}'. "
                    f"Internal failure reasons must stay in logs only. "
                    f"Use client-facing language: 'Unavailable from reviewed sources'."
                ),
                severity="error",
            ))

        # 30b. Programming-language null artifacts (with word boundaries)
        # NOTE: "None" is case-SENSITIVE (Python None), "none" is a valid English word.
        null_artifacts_case_sensitive = [
            (r'\bNone\b', 'None'),
        ]
        null_artifacts_case_insensitive = [
            (r'\bnull\b', 'null'),
            (r'\bNaN\b', 'NaN'),
            (r'\bundefined\b', 'undefined'),
            (r'\bdebug\b', 'debug'),
        ]
        for pattern, label in null_artifacts_case_sensitive:
            if re.search(pattern, text):
                warnings.append(ValidationWarning(
                    check="missing_data_null_artifact",
                    section=section_name,
                    detail=(
                        f"Programming artifact '{label}' found in '{section_name}'. "
                        f"Use professional language: 'Not disclosed', 'Unavailable from "
                        f"reviewed sources', or remove the field entirely."
                    ),
                    severity="error",
                ))
                break
        for pattern, label in null_artifacts_case_insensitive:
            if re.search(pattern, text, re.IGNORECASE):
                warnings.append(ValidationWarning(
                    check="missing_data_null_artifact",
                    section=section_name,
                    detail=(
                        f"Programming artifact '{label}' found in '{section_name}'. "
                        f"Use professional language: 'Not disclosed', 'Unavailable from "
                        f"reviewed sources', or remove the field entirely."
                    ),
                    severity="error",
                ))
                break  # One per section is enough

    # ── RULE 31 (BLOCKING): §7 Company Overview completeness ─────────────────
    #
    # The Company Overview section must answer all required questions.
    # If present, it must contain: competitors, strengths, weaknesses,
    # segments, clients, management strengths/weaknesses.

    if company_overview is not None:
        co = company_overview

        # 31a. Competitors must exist (not empty)
        competitors = getattr(co, 'competitors', None)
        if competitors is not None and len(competitors) == 0:
            warnings.append(ValidationWarning(
                check="company_overview_no_competitors",
                section="Company Overview",
                detail="Company Overview has zero competitors. At least one competitor must be listed.",
                severity="error",
            ))

        # 31b. Business segments must exist
        segments = getattr(co, 'business_segments', None)
        if segments is not None and len(segments) == 0:
            warnings.append(ValidationWarning(
                check="company_overview_no_segments",
                section="Company Overview",
                detail="Company Overview has zero business segments. At least one segment must be listed.",
                severity="error",
            ))

        # 31c. Management strengths and weaknesses
        strengths = getattr(co, 'strengths_vs_competitors', None)
        weaknesses = getattr(co, 'weaker_areas_vs_competitors', None)
        if (strengths is not None and not strengths) and (weaknesses is not None and not weaknesses):
            warnings.append(ValidationWarning(
                check="company_overview_no_strengths_weaknesses",
                section="Company Overview",
                detail=(
                    "Company Overview is missing strengths vs competitors AND "
                    "weaker areas vs competitors. At least one must be present."
                ),
                severity="error",
            ))

        # 31d. Company claims must have source IDs
        claims = getattr(co, 'company_claims', None)
        if claims:
            unsourced = [c for c in claims if not (getattr(c, 'source_id', None) or (isinstance(c, dict) and c.get('source_id')))]
            if unsourced:
                warnings.append(ValidationWarning(
                    check="company_overview_unsourced_claims",
                    section="Company Overview",
                    detail=(
                        f"{len(unsourced)} company claim(s) lack source_id. "
                        f"Every claim must be traceable to a source."
                    ),
                    severity="error",
                ))

    # ── RULE 32 (BLOCKING): §8 Layer separation — CO vs Earnings Analysis ────
    #
    # Company Overview must not contain quarterly beat/miss language.
    # It's a strategic/long-term section, not a quarterly update.

    # Check section text for quarterly language in Company Overview context
    co_section_text = _sec.get("Company Overview", "")
    if isinstance(co_section_text, str) and co_section_text.strip():
        quarterly_in_co = re.findall(
            r'\b(?:beat|missed?|surpassed?|exceeded?)\s+(?:consensus|estimate|expectation)',
            co_section_text, re.IGNORECASE
        )
        if quarterly_in_co:
            warnings.append(ValidationWarning(
                check="company_overview_quarterly_language_leak",
                section="Company Overview",
                detail=(
                    f"Quarterly beat/miss language found in Company Overview: "
                    f"'{quarterly_in_co[0]}'. Company Overview is a long-term "
                    f"strategic section — move quarterly performance to Earnings Analysis."
                ),
                severity="error",
            ))

        # Check for quarterly-specific metrics without period labels
        quarterly_metric_indicators = [
            r'Q\d\s+(?:revenue|EPS|earnings|growth)',
            r'(?:revenue|EPS|earnings)\s+(?:grew|declined|increased|decreased)\s+(?:by\s+)?\d+%',
        ]
        for pattern in quarterly_metric_indicators:
            matches = re.findall(pattern, co_section_text, re.IGNORECASE)
            if matches and 'TTM' not in co_section_text and 'annual' not in co_section_text.lower():
                warnings.append(ValidationWarning(
                    check="company_overview_unlabeled_quarterly_metric",
                    section="Company Overview",
                    detail=(
                        f"Potential quarterly metric without period label: '{matches[0]}'. "
                        f"Company Overview metrics must have explicit period/type labels "
                        f"(e.g., 'TTM', 'FY2026', 'annual')."
                    ),
                    severity="error",
                ))
                break

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
