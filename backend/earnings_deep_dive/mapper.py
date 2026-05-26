"""Map sourced earnings metrics into the structured PDF render model."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
import os
import re

from backend.earnings_deep_dive.report_model import (
    ChartData,
    ClaimSource,
    CompanyOverview,
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    SourceRef,
    # V2.7 structured section models
    ExecutiveSnapshot,
    FinancialMetrics as V27FinancialMetrics,
    ValuationSection,
    ValuationContextSection,
    PeerBenchmarkSection,
    DataQualitySection,
    GroundingLevel,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.template import TemplateLanguage, get_earnings_template

if TYPE_CHECKING:
    from backend.models import Scoring


MISSING = "Not available"
MISSING_JP = "データ未取得"
MISSING_EN = "Not available"
NOT_DISCLOSED = "開示なし"
NOT_DISCLOSED_EN = "Not disclosed"
NOT_APPLICABLE = "該当なし"
NOT_APPLICABLE_EN = "N/A"
NOT_CALCULABLE = "計算不可"
NOT_CALCULABLE_EN = "Not calculable"
SOURCE_COMPANY = "SEC Filing (10-Q/10-K) via EDGAR"
SOURCE_YFINANCE = "yfinance (Yahoo Finance)"
SOURCE_CONSENSUS = "Yahoo Finance (consensus)"

_PLACEHOLDER_PATTERNS = {
    "?", "N/A", "NA", "Not available", "データ未取得",
    "該当なし", "開示なし", "計算不可",
    "-", "--", "—", "–", "…", "...",
    "Consensus / company guide",
}

# Regex to strip parenthetical suffixes from labels:
# "Operating Cash Flow (OCF)" → "Operating Cash Flow"
# "EPS (adjusted)" → "EPS"
_PAREN_STRIP_RE = re.compile(r"\s*\([^)]*\)\s*")


def _is_placeholder(cell: str) -> bool:
    """Return True if a table cell is a placeholder that should be replaced with yfinance data."""
    stripped = cell.strip()
    return not stripped or stripped in _PLACEHOLDER_PATTERNS


def _language(value: str) -> TemplateLanguage:
    return "jp" if value == "jp" else "en"


def _metric_url(metrics: FinancialMetrics, *keys: str) -> str | None:
    extra = getattr(metrics, "model_extra", {}) or {}
    for key in keys:
        value = getattr(metrics, key, None)
        if value is None:
            value = extra.get(key)
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            return value.strip()
    return None


def _seeking_alpha_transcripts_url(ticker: str) -> str:
    return f"https://seekingalpha.com/symbol/{ticker.strip().upper()}/earnings/transcripts"


def _metric_text(metrics: FinancialMetrics, *keys: str) -> str | None:
    extra = getattr(metrics, "model_extra", {}) or {}
    for key in keys:
        value = getattr(metrics, key, None)
        if value is None:
            value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _has(value: Any) -> bool:
    return value is not None and value != ""


def _source(*values: Any, source_type: str = "sec_edgar") -> str:
    """Return source label. Use source_type='yfinance' for yfinance-derived data,
    'yfinance_consensus' for analyst consensus estimates (checks first value)."""
    if not any(_has(value) for value in values):
        return MISSING_EN
    if source_type == "yfinance_consensus":
        # Only label as consensus if the estimate (first value) is actually present;
        # otherwise fall through to standard SEC/company source for the actual.
        if _has(values[0]) if values else False:
            return SOURCE_CONSENSUS
        return SOURCE_COMPANY
    if source_type == "yfinance":
        return SOURCE_YFINANCE
    return SOURCE_COMPANY


def _source_descriptor(
    *values: Any,
    field: str | None = None,
    grounding: str = "direct_metric",
    source_type: str = "sec_edgar",
) -> dict:
    """Return a display string + structured source provenance for a table row.

    This replaces simple _source() strings with machine-readable metadata
    that enables claim→source traceability in the PDF appendix.
    """
    has_data = any(_has(value) for value in values)
    if source_type == "yfinance":
        display = SOURCE_YFINANCE if has_data else MISSING_EN
    elif source_type == "sec_edgar":
        display = SOURCE_COMPANY if has_data else MISSING_EN
    elif source_type == "transcript":
        display = "Earnings Transcript" if has_data else MISSING_EN
    elif source_type == "calculated":
        display = "Calculated from source data" if has_data else MISSING_EN
    else:
        display = source_type if has_data else MISSING_EN

    raw_value = None
    for v in values:
        if _has(v):
            raw_value = str(v)[:128]
            break

    return {
        "display": display,
        "field": field,
        "value": raw_value,
        "grounding": grounding,
        "source_type": source_type,
    }


def _source_display(sd: dict) -> str:
    """Derive the old Source column display text from a source descriptor."""
    return sd.get("display", MISSING_EN) if sd else MISSING_EN


def _money(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000_000:
        return f"{sign}${amount / 1_000_000_000_000:.2f}T"
    if amount >= 1_000_000_000:
        return f"{sign}${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f}M"
    return f"{sign}${amount:,.0f}"


def _eps(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) <= 1:
        number *= 100
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


def _multiple(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return str(value)


def _yoy_pct(value: Any) -> str:
    """Format a YoY percentage value — handles both ratios (0.25→25%) and percentage points (25→25%)."""
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) <= 1:
        number *= 100
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


def _yoy_pts(current: Any, prior: Any) -> str:
    """Format margin change in percentage points (e.g., 58.3% → 55.6% = +2.7 pts)."""
    if not _has(current) or not _has(prior):
        return MISSING
    try:
        current_val = float(current)
        prior_val = float(prior)
    except (TypeError, ValueError):
        return MISSING
    diff = current_val - prior_val
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.1f} pts"


def _yoy_comment(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MISSING
    if number > 0:
        return "improvement"
    if number < 0:
        return "decline"
    return "flat"


def _variance(actual: Any, estimate: Any, explicit: Any = None) -> str:
    if _has(explicit):
        return _pct(explicit)
    if not (_has(actual) and _has(estimate)):
        return MISSING
    try:
        actual_number = float(actual)
        estimate_number = float(estimate)
    except (TypeError, ValueError):
        return MISSING
    if estimate_number == 0:
        return NOT_CALCULABLE
    return _pct((actual_number - estimate_number) / abs(estimate_number))


def _clean_markdown_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`")).strip()


def _is_markdown_separator(cells: list[str]) -> bool:
    clean_cells = [cell.strip() for cell in cells if cell.strip()]
    return bool(clean_cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in clean_cells)


def _extract_markdown_table(markdown: str, expected_columns: tuple[str, ...]) -> RenderedTable | None:
    lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return None

    for index in range(len(lines) - 2):
        header = [_clean_markdown_cell(cell) for cell in lines[index].strip("|").split("|")]
        separator = [_clean_markdown_cell(cell) for cell in lines[index + 1].strip("|").split("|")]
        if len(header) < 2 or not _is_markdown_separator(separator):
            continue

        rows: list[RenderedTableRow] = []
        for raw in lines[index + 2:]:
            cells = [_clean_markdown_cell(cell) for cell in raw.strip("|").split("|")]
            if len(cells) != len(header):
                break
            if _is_markdown_separator(cells):
                continue
            rows.append(RenderedTableRow(label=cells[0], cells=cells[1:]))

        if rows:
            return RenderedTable(columns=header or list(expected_columns), rows=rows)

    return None


def _analysis_without_table(markdown: str) -> str:
    return "\n\n".join(_analysis_blocks_without_table(markdown))


def _analysis_blocks_without_table(markdown: str) -> list[str]:
    """Extract non-table prose as separate renderable blocks.

    The previous single-string extractor made one fragile paragraph out of the
    whole LLM section. Keeping blocks preserves lists and lets ReportLab split
    long commentary naturally.
    """
    kept: list[str] = []
    in_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            continue
        if in_table and not stripped:
            in_table = False
            continue
        if stripped.startswith("## "):
            continue
        kept.append(line)

    blocks: list[str] = []
    current: list[str] = []
    for line in kept:
        if line.strip():
            current.append(line.rstrip())
            continue
        if current:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = []
    if current:
        block = "\n".join(current).strip()
        if block:
            blocks.append(block)
    return blocks


def _parse_segments_from_prose(analysis_text: str) -> dict[str, dict]:
    """Extract segment revenue mentions from LLM analysis text.

    Parses patterns like:
    - "iPhone revenue of $57.0B grew 22%"
    - "Services revenue was $31.0B, up 16%"
    - "Mac contributed $8.4B (+6% YoY)"

    Returns dict of {segment_name: {revenue: float, yoy: float or None}}.
    """
    import re as _re3
    segments: dict[str, dict] = {}

    # Pattern: SegmentName revenue (of/was/at) $XX.X B/billion/M/million
    # Capture: name, amount, unit, optional YoY
    _REVENUE_RE = _re3.compile(
        r'(?P<name>[A-Z][\w\s&/\-]{2,30}?)\s+'
        r'(?:revenue|sales|contributed)\s+(?:of|was|at|reached|totaled)?\s*'
        r'\$?(?P<amount>[\d,.]+)\s*'
        r'(?P<unit>[BMK]|billion|million|thousand)',
        _re3.IGNORECASE,
    )

    _YOY_RE = _re3.compile(
        r'(?:up|down|grew|fell|increased|decreased)\s+(?P<yoy>[\d.]+)\s*%|'
        r'\(\s*[+]?(?P<yoy2>[\d.]+)\s*%\s*(?:YoY|year.over.year)?\)',
        _re3.IGNORECASE,
    )

    for match in _REVENUE_RE.finditer(analysis_text):
        name = match.group('name').strip().rstrip(',').strip()
        # Filter garbage names
        if len(name) < 2 or name.lower() in {'the', 'total', 'overall', 'combined', 'and'}:
            continue
        try:
            amount = float(match.group('amount').replace(',', ''))
        except ValueError:
            continue
        unit = match.group('unit').lower()
        if unit in ('b', 'billion'):
            amount *= 1e9
        elif unit in ('m', 'million'):
            amount *= 1e6
        elif unit in ('k', 'thousand'):
            amount *= 1e3

        # Try to find YoY near this match
        search_start = max(0, match.start() - 20)
        search_end = min(len(analysis_text), match.end() + 80)
        context = analysis_text[search_start:search_end]
        yoy = None
        yoy_match = _YOY_RE.search(context)
        if yoy_match:
            yoy_str = yoy_match.group('yoy') or yoy_match.group('yoy2')
            if yoy_str:
                try:
                    yoy = float(yoy_str)
                except ValueError:
                    pass

        # Keep largest revenue for each segment name
        name_lower = name.lower()
        if name_lower not in segments or amount > (segments[name_lower].get('revenue', 0) or 0):
            segments[name_lower] = {
                'name': name,
                'revenue': amount,
                'revenue_quarterly': amount,
                'yoy': yoy,
                'source': 'Transcript / LLM analysis',
            }

    return segments


def _extract_segment_rows(metrics: FinancialMetrics, labels: tuple[str, ...]) -> list[list[str]]:
    rows: list[list[str]] = []
    segments = metrics.segments if isinstance(metrics.segments, dict) else {}
    
    # ── P0: Period mismatch guard ──
    # If segment data is from 10-K (annual) while metrics are quarterly,
    # show "annual context only" instead of misleading quarterly table.
    _META_KEYS = {"product_segments", "total_revenue_quarterly", "deferred_revenue_1yr_pct", "source", "filing_date",
                  "period", "source_form", "_annual_context_only"}
    is_annual_context = segments.get("_annual_context_only", False) or segments.get("period") == "annual"
    total_seg = segments.get("total_revenue_quarterly")
    q_revenue = getattr(metrics, "revenue_actual", None) or getattr(metrics, "revenue_quarterly", None)
    # Secondary check: if segment total is >1.5x quarterly revenue, it's likely annual
    if (not is_annual_context and total_seg and q_revenue 
            and _has(total_seg) and _has(q_revenue)):
        try:
            if float(total_seg) > float(q_revenue) * 1.5:
                is_annual_context = True
        except (TypeError, ValueError):
            pass
    
    if is_annual_context:
        source_note = segments.get("source_form", "SEC filing")
        period_note = segments.get("period", "annual")
        note = f"Segment data from {source_note} ({period_note}) — annual context only, not comparable to quarterly metrics above"
        return [[labels[0], note, "—", "—", "—", "—", note]]
    segment_entries = [
        (k, v) for k, v in segments.items()
        if isinstance(v, dict) and k not in _META_KEYS
    ]
    segment_items = segment_entries[: len(labels)]
    # Detect garbled XBRL names: SEC text fragments, month abbreviations
    _GARBLED_EXACT = {"Sep", "Total"}
    _GARBLED_CONTAINS = ["generally", "consistent", "reportable", "As of", "than a year", "revenue of",
                         "September", "months ended", "fiscal year", "ended", "filing", "period"]
    def _is_garbled(name: str) -> bool:
        n = str(name)
        if n in _GARBLED_EXACT:
            return True
        for pat in _GARBLED_CONTAINS:
            if pat.lower() in n.lower():
                return True
        return False

    def _segment_display_name(xbrl_name: str, fallback_label: str) -> str:
        """Return the real XBRL segment name, or template fallback if garbled."""
        if not _is_garbled(str(xbrl_name)):
            return str(xbrl_name) if xbrl_name else fallback_label
        # XBRL name is garbled SEC text — use the generic template label
        return fallback_label

    # Compute total revenue for mix % calculation
    total_rev = segments.get("total_revenue_quarterly")
    if not _has(total_rev):
        total_rev = getattr(metrics, "revenue_actual", None) or getattr(metrics, "revenue_quarterly", None)

    for index, row_label in enumerate(labels):
        if index >= len(segment_items):
            rows.append([row_label, MISSING, MISSING, MISSING, MISSING, MISSING, MISSING])
            continue

        name, raw = segment_items[index]
        data = raw if isinstance(raw, dict) else {}
        revenue = data.get("revenue") if isinstance(data, dict) else None
        prior_year = data.get("revenue_q_prior_year") if isinstance(data, dict) else None
        yoy = data.get("yoy") if isinstance(data, dict) else None
        # Compute YoY from revenue and prior year if not explicitly provided
        if not _has(yoy) and revenue is not None and prior_year is not None and revenue and prior_year:
            try:
                yoy = ((float(revenue) - float(prior_year)) / float(prior_year)) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        # Compute mix % of total revenue
        mix_pct = None
        if _has(revenue) and _has(total_rev) and total_rev:
            try:
                mix_pct = (float(revenue) / float(total_rev)) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        driver = data.get("driver") if isinstance(data, dict) else None
        display_name = _segment_display_name(str(name), row_label)
        rows.append([
            display_name,
            _money(revenue),
            _money(prior_year),
            _pct(yoy),
            f"{mix_pct:.1f}%" if mix_pct is not None else MISSING,
            str(driver) if _has(driver) else "Segment revenue contribution",
            _source(raw),
        ])
    return rows


def _rows_for_section(section_key: str, row_labels: tuple[str, ...], metrics: FinancialMetrics, scoring: Optional['Scoring'] = None) -> list[list[str]]:
    if section_key == "EPS & Revenue":
        return [
            [
                row_labels[0],
                _eps(metrics.eps_estimate),
                _eps(metrics.eps_actual),
                _variance(metrics.eps_actual, metrics.eps_estimate, getattr(metrics, "eps_vs_estimate", None)),
                _yoy_pct(getattr(metrics, "eps_yoy", None)),
                _source(metrics.eps_estimate, metrics.eps_actual, getattr(metrics, "eps_vs_estimate", None), getattr(metrics, "eps_yoy", None), source_type="yfinance_consensus"),
            ],
            [
                row_labels[1],
                _money(getattr(metrics, "revenue_estimate", None)),
                _money(getattr(metrics, "revenue_actual", None)),
                _variance(getattr(metrics, "revenue_actual", None), getattr(metrics, "revenue_estimate", None)),
                _yoy_pct(getattr(metrics, "revenue_yoy", None)),
                _source(getattr(metrics, "revenue_estimate", None), getattr(metrics, "revenue_actual", None), getattr(metrics, "revenue_yoy", None)),
            ],
        ]

    if section_key == "Highlights":
        return _highlights_rows(metrics, row_labels)

    if section_key == "Operating Metrics":
        rows = (
            (
                row_labels[0],  # Revenue (new first row)
                _money(getattr(metrics, "revenue_actual", None) or getattr(metrics, "revenue_quarterly", None)),
                _money(getattr(metrics, "revenue_quarterly_prior_year", None)),
                _yoy_pct(getattr(metrics, "revenue_yoy", None)),
                getattr(metrics, "revenue_actual", None) or getattr(metrics, "revenue_quarterly", None),
            ),
            (
                row_labels[1],
                _money(metrics.gross_profit),
                _money(getattr(metrics, "gross_profit_prior_year", None)),
                _yoy_pct(getattr(metrics, "gross_profit_yoy", None)),
                metrics.gross_profit,
            ),
            (
                row_labels[2],
                _pct(metrics.gross_margin),
                _pct(getattr(metrics, "gross_margin_prior_year", None)),
                _yoy_pts(metrics.gross_margin, getattr(metrics, "gross_margin_prior_year", None)),
                metrics.gross_margin,
            ),
            (
                row_labels[3],
                _money(metrics.opex),
                _money(getattr(metrics, "opex_prior_year", None)),
                _yoy_pct(getattr(metrics, "opex_yoy", None)),
                metrics.opex,
            ),
            (
                row_labels[4],
                _money(metrics.operating_income),
                _money(getattr(metrics, "operating_income_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_income_yoy", None)),
                metrics.operating_income,
            ),
            (
                row_labels[5],
                _pct(metrics.operating_margin),
                _pct(getattr(metrics, "operating_margin_prior_year", None)),
                _yoy_pts(metrics.operating_margin, getattr(metrics, "operating_margin_prior_year", None)),
                metrics.operating_margin,
            ),
            (
                row_labels[6],
                _money(getattr(metrics, "net_income_quarterly", None)),
                _money(getattr(metrics, "net_income_quarterly_prior_year", None)),
                _yoy_pct(getattr(metrics, "net_income_yoy", None)),
                getattr(metrics, "net_income_quarterly", None),
            ),
        )
        return [[label, value, prior, yoy, _source(raw)] for label, value, prior, yoy, raw in rows]

    if section_key == "Cash Flow":
        def cash_flow_quality() -> str:
            if not (_has(metrics.free_cash_flow) and _has(metrics.operating_cash_flow)):
                return MISSING
            try:
                operating_cash_flow = float(metrics.operating_cash_flow)
                ratio = float(metrics.free_cash_flow) / operating_cash_flow if operating_cash_flow else None
            except (TypeError, ValueError):
                return MISSING
            if ratio is None:
                return MISSING
            if ratio > 0.8:
                return "good"
            if ratio >= 0.5:
                return "watch"
            return "weak"

        quality = cash_flow_quality()
        # Append FCF formula when both OCF and CapEx are available
        fcf_formula = ""
        if _has(metrics.free_cash_flow) and _has(metrics.operating_cash_flow) and _has(metrics.capex):
            try:
                ocf_val = float(metrics.operating_cash_flow)
                capex_val = float(metrics.capex)
                fcf_val = float(metrics.free_cash_flow)
                fcf_formula = f" (FCF = {_money(ocf_val)} OCF - {_money(abs(capex_val))} CapEx)"
            except (TypeError, ValueError):
                pass
        quality_display = quality + fcf_formula if quality != MISSING else quality
        rows = (
            (
                row_labels[0],
                _money(metrics.operating_cash_flow),
                _money(getattr(metrics, "operating_cash_flow_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_cash_flow_yoy", None)),
                "Operating",
                metrics.operating_cash_flow,
            ),
            (
                row_labels[1],
                _money(metrics.capex),
                _money(getattr(metrics, "capex_prior_year", None)),
                _yoy_pct(getattr(metrics, "capex_yoy", None)),
                "Investing",
                metrics.capex,
            ),
            (
                row_labels[2],
                _money(metrics.free_cash_flow),
                _money(getattr(metrics, "free_cash_flow_prior_year", None)),
                _yoy_pct(getattr(metrics, "free_cash_flow_yoy", None)),
                quality_display,
                metrics.free_cash_flow,
            ),
            (
                row_labels[3],
                _money(metrics.net_debt),
                _money(getattr(metrics, "net_debt_prior_year", None)),
                _yoy_pct(getattr(metrics, "net_debt_yoy", None)),
                "Leverage",
                metrics.net_debt,
            ),
        )
        return [[label, value, prior, yoy, q, _source(raw)] for label, value, prior, yoy, q, raw in rows]

    if section_key == "Capital Efficiency":
        rows = (
            (
                row_labels[0],
                _pct(metrics.roe),
                _pct(getattr(metrics, "roe_prior_year", None)),
                _yoy_pct(getattr(metrics, "roe_yoy", None)),
                _yoy_comment(getattr(metrics, "roe_yoy", None)),
                metrics.roe,
            ),
            (
                row_labels[1],
                _pct(metrics.rotce),
                _pct(getattr(metrics, "rotce_prior_year", None)),
                _yoy_pct(getattr(metrics, "rotce_yoy", None)),
                _yoy_comment(getattr(metrics, "rotce_yoy", None)),
                metrics.rotce,
            ),
            (
                row_labels[2],
                _pct(metrics.roa),
                _pct(getattr(metrics, "roa_prior_year", None)),
                _yoy_pct(getattr(metrics, "roa_yoy", None)),
                _yoy_comment(getattr(metrics, "roa_yoy", None)),
                metrics.roa,
            ),
            (
                row_labels[3],
                _pct(metrics.roic),
                _pct(getattr(metrics, "roic_prior_year", None)),
                _yoy_pct(getattr(metrics, "roic_yoy", None)),
                _yoy_comment(getattr(metrics, "roic_yoy", None)),
                metrics.roic,
            ),
            (
                row_labels[4],
                _money(metrics.buybacks),
                _money(getattr(metrics, "buybacks_prior_year", None)),
                _yoy_pct(getattr(metrics, "buybacks_yoy", None)),
                _yoy_comment(getattr(metrics, "buybacks_yoy", None)),
                metrics.buybacks,
            ),
            (
                row_labels[5],
                _money(metrics.dividends),
                _money(getattr(metrics, "dividends_prior_year", None)),
                _yoy_pct(getattr(metrics, "dividends_yoy", None)),
                _yoy_comment(getattr(metrics, "dividends_yoy", None)),
                metrics.dividends,
            ),
        )
        result = [[label, value, prior, yoy, comment, _source(raw)] for label, value, prior, yoy, comment, raw in rows]
        # Append total assets / equity to ROA / ROE comments if available
        if _has(metrics.total_assets):
            result[2][4] = str(result[2][4]) + f" (Assets: {_money(metrics.total_assets)})"
        if _has(metrics.equity):
            result[0][4] = str(result[0][4]) + f" (Equity: {_money(metrics.equity)})"
        # If ALL metrics are unavailable (Finnhub free tier limitation), show 1 informative row
        if all(not _has(raw) for _, _, _, _, _, raw in rows):
            return [["Capital Efficiency metrics", "Finnhub free tier limit", MISSING, MISSING, MISSING, MISSING]]
        return result

    if section_key == "Segments":
        return _extract_segment_rows(metrics, row_labels)

    if section_key == "Geographic Segments":
        # Most companies do NOT publish quarterly geographic revenue breakdowns.
        # Show the framework with "Not disclosed" and explain why.
        region_comment = "Not disclosed — geographic revenue breakdown not published in quarterly filings"
        return [
            [row_labels[0], NOT_DISCLOSED_EN, "N/A", "N/A", "N/A", region_comment],
            [row_labels[1], NOT_DISCLOSED_EN, "N/A", "N/A", "N/A", region_comment],
            [row_labels[2], NOT_DISCLOSED_EN, "N/A", "N/A", "N/A", region_comment],
            [row_labels[3], NOT_DISCLOSED_EN, "N/A", "N/A", "N/A", region_comment],
            [row_labels[4], NOT_DISCLOSED_EN, "N/A", "N/A", "N/A", region_comment],
        ]

    if section_key == "Forward P/E":
        trailing_pe = getattr(metrics, "pe_trailing", None)
        if trailing_pe is None:
            trailing_pe = getattr(metrics, "pe_current", None)
        # Forward EPS basis: annual EPS estimate used for the forward P/E
        fwd_eps_basis = _money(getattr(metrics, "eps_estimate", None))
        if not _has(metrics.eps_estimate) and _has(metrics.pe_forward) and _has(getattr(metrics, "price", None)):
            # Derive from P/E * price if we had price — use eps_estimate * 4 instead
            pass
        # Try to show the annualized estimate
        eps_annual = None
        if _has(metrics.eps_estimate):
            try:
                eps_annual = float(metrics.eps_estimate) * 4.0
            except (TypeError, ValueError):
                pass
        fwd_eps_display = _eps(eps_annual) if eps_annual else NOT_DISCLOSED_EN
        # Build enriched context column with trailing PE + analyst consensus
        context_parts = []
        if _has(trailing_pe):
            context_parts.append(f"Trailing: {_multiple(trailing_pe)}")
        consensus = getattr(metrics, "analyst_consensus", None)
        target = getattr(metrics, "analyst_target", None)
        count = getattr(metrics, "analyst_count", None)
        if consensus and isinstance(consensus, str) and consensus not in ("—", ""):
            consensus_label = consensus.replace("_", " ").title()
            if count:
                try:
                    consensus_label += f" ({int(count)} analysts)"
                except (TypeError, ValueError):
                    pass
            context_parts.append(f"Consensus: {consensus_label}")
        if _has(target):
            context_parts.append(f"Target: {_money(target)}")
        context = " | ".join(context_parts) if context_parts else "—"
        return [
            [row_labels[0], _multiple(metrics.pe_forward), context, "—", _source(metrics.pe_forward)],
            [row_labels[1], fwd_eps_display, _eps(getattr(metrics, "eps_estimate", None)), _yoy_pct(getattr(metrics, "eps_yoy", None)), _source(metrics.eps_estimate)],
        ]

    if section_key == "Backlog":
        backlog_value = _money(metrics.backlog) if _has(metrics.backlog) else NOT_APPLICABLE_EN
        backlog_source = _source(metrics.backlog) if _has(metrics.backlog) else SOURCE_COMPANY
        # Quantity/Quality framework — even when not disclosed, show proxies
        has_backlog = _has(metrics.backlog)
        return [
            [row_labels[0],
             backlog_value,
             "N/A" if not has_backlog else "—",
             "Not disclosed (company does not report backlog); use revenue guidance + Data Center growth trajectory as demand proxy" if not has_backlog else "—",
             backlog_source],
            [row_labels[1],
             NOT_APPLICABLE_EN if not has_backlog else NOT_DISCLOSED_EN,
             "N/A",
             "Inferred from hyperscaler capex commitments and supply chain constraints" if not has_backlog else "—",
             backlog_source],
        ]

    if section_key == "Guidance":
        guidance_text = metrics.guidance if _has(metrics.guidance) else MISSING_EN
        guidance_source = _source(metrics.guidance)
        
        # Revenue guidance — from revenue_estimate or guidance text
        rev_est = getattr(metrics, "revenue_estimate", None)
        rev_q = getattr(metrics, "revenue_quarterly", None)
        rev_growth = getattr(metrics, "revenue_yoy", None)
        
        rev_guidance = _money(rev_est) if _has(rev_est) else "Not guided"
        rev_qoq = ""
        if _has(rev_est) and _has(rev_q):
            try:
                qoq = (float(rev_est) - float(rev_q)) / float(rev_q) * 100
                rev_qoq = f"{qoq:+.1f}% QoQ"
            except (TypeError, ValueError, ZeroDivisionError):
                rev_qoq = "—"
        
        # EPS guidance
        eps_est = getattr(metrics, "eps_estimate", None)
        eps_guidance = f"${float(eps_est):.2f}" if _has(eps_est) else "Not guided"
        
        # Margin guidance — from transcript/press release
        gm = getattr(metrics, "gross_margin", None)
        gm_guidance = _pct(gm) if _has(gm) else "Not guided"
        
        rows = [
            ["Revenue", rev_guidance, rev_qoq or "—", "Consensus estimate", guidance_source if _has(rev_est) else SOURCE_COMPANY],
            ["GAAP Gross Margin", gm_guidance, "—", "Current quarter actual; forward guidance not separately disclosed", guidance_source],
            ["Non-GAAP Gross Margin", "Not disclosed", "—", "Non-GAAP margin guidance not provided in quarterly filings", SOURCE_COMPANY],
            ["GAAP OpEx", "Not disclosed", "—", "OpEx guidance not provided in quarterly filings", SOURCE_COMPANY],
            ["EPS (non-GAAP)", eps_guidance, "—", "Consensus estimate", guidance_source if _has(eps_est) else SOURCE_COMPANY],
            ["Diluted Shares", "Not disclosed", "—", "Share count guidance not provided", SOURCE_COMPANY],
        ]
        if _has(guidance_text) and isinstance(guidance_text, str) and len(guidance_text) > 10:
            rows.append(["Outlook context", guidance_text[:240] + ("…" if len(guidance_text) > 240 else ""), "—", "Full outlook text", guidance_source])
        return rows

    if section_key == "Verdict":
        return _verdict_rows(metrics, row_labels, scoring)

    return [[label, *([MISSING] * 4)] for label in row_labels]


def _enrich_codex_table(
    codex_table: RenderedTable,
    section_key: str,
    section_rows: tuple[str, ...],
    metrics: FinancialMetrics,
    scoring: Optional['Scoring'] = None,
) -> RenderedTable:
    """Enrich an LLM-generated table by replacing placeholder cells with yfinance data.

    The LLM often knows narrative values (Actual from transcript) but leaves Prior Year
    and YoY as ``?`` / ``—``.  This function merges the deterministic yfinance rows from
    ``_rows_for_section`` into the LLM table, cell by cell, wherever the LLM cell is a
    placeholder.

    Handles Japanese templates by also mapping JP row labels → EN labels so that
    yfinance data (always keyed by Japanese labels from the JP template) can match
    English labels typically produced by the LLM.
    """
    yf_rows = _rows_for_section(section_key, section_rows, metrics, scoring)
    if not yf_rows:
        return codex_table

    # Build lookup keyed by both the original label AND its English equivalent.
    jp_to_en = {
        "売上高": "revenue",
        "粗利益": "gross profit",
        "粗利益率": "gross margin",
        "営業費用": "opex",
        "営業利益": "operating income",
        "営業利益率": "operating margin",
        "純利益": "net income",
        "営業キャッシュフロー": "operating cash flow",
        "設備投資": "capex",
        "フリーキャッシュフロー": "free cash flow",
        "純負債": "net debt",
        "自社株買い": "buybacks",
        "配当": "dividends",
    }
    yf_lookup: dict[str, list[str]] = {}
    for row in yf_rows:
        original = row[0].strip()
        key = original.lower()
        yf_lookup[key] = row[1:]
        en = jp_to_en.get(original) or jp_to_en.get(key)
        if en:
            yf_lookup[en] = row[1:]

    # Fallback enrichment: common LLM-added labels that may appear in any section.
    # Matches are added only when the section-level lookup misses.
    def _add_fallback(label: str, fmt, raw, prior, yoy) -> None:
        if label not in yf_lookup:
            yf_lookup[label] = [fmt(raw), fmt(prior), _yoy_pct(yoy), _source(raw, prior, yoy)]

    _add_fallback("revenue", _money, getattr(metrics, "revenue_actual", None),
                  getattr(metrics, "revenue_quarterly_prior_year", None),
                  getattr(metrics, "revenue_yoy", None))
    _add_fallback("eps", _eps, getattr(metrics, "eps_actual", None),
                  getattr(metrics, "eps_prior_year", None),
                  getattr(metrics, "eps_yoy", None))

    def _label_key(raw: str) -> str:
        """Normalise a row label: lowercase, strip parentheticals, collapse whitespace."""
        base = raw.strip().lower()
        # Strip parenthetical like "EPS (adjusted)" → "eps"
        base = _PAREN_STRIP_RE.sub("", base).strip()
        return base

    enriched_rows: list[RenderedTableRow] = []
    for llm_row in codex_table.rows:
        llm_key = _label_key(llm_row.label)
        yf_cells = yf_lookup.get(llm_key)

        if yf_cells is None:
            enriched_rows.append(llm_row)
            continue

        merged_cells: list[str] = []
        for idx, llm_cell in enumerate(llm_row.cells):
            yf_cell = yf_cells[idx] if idx < len(yf_cells) else None
            if _is_placeholder(llm_cell) and yf_cell is not None and not _is_placeholder(yf_cell):
                merged_cells.append(yf_cell)
            else:
                merged_cells.append(llm_cell)

        enriched_rows.append(RenderedTableRow(label=llm_row.label, cells=merged_cells))

    return RenderedTable(columns=list(codex_table.columns), rows=enriched_rows)


def _number_highlights_rows(table: RenderedTable) -> RenderedTable:
    """Replace placeholder values in the Number column of Highlights tables with sequential numbers.
    
    The LLM fills the Number column with circled digits (①, ②), ?, or ?? because it doesn't
    know the sequence. This post-processing replaces any non-numeric placeholder with 1, 2, 3, ...
    
    CRITICAL: _extract_markdown_table stores the first column (Type) as row.label, so
    cells[0] corresponds to columns[1]. We must account for this label offset.
    """
    import re
    
    # Detect Highlights table by column headers
    cols = [c.lower().strip() for c in table.columns]
    if "number" not in cols:
        return table
    number_idx = cols.index("number")  # index in table.columns
    
    # Match any placeholder: ?, ??, ?, circled digits (①-⑳, ㉑-㉟), or other non-numeric
    _CIRCLED_DIGITS_RE = re.compile(r'^[①-⑳㉑-㉟⓵-⓾🄋-🄐?？?\s]+$')
    
    numbered_rows = []
    counter = 1
    for row in table.rows:
        cells = list(row.cells)
        # _extract_markdown_table stores column[0] as row.label; cells are columns[1:]
        # So the cell index for column N is N-1 in the cells array
        cell_idx = number_idx - 1
        if 0 <= cell_idx < len(cells):
            cell_val = cells[cell_idx].strip()
            # Replace if it's a placeholder or if it's purely non-numeric
            if _CIRCLED_DIGITS_RE.match(cell_val) or (cell_val and not cell_val.replace('.','').replace('-','').isdigit()):
                cells[cell_idx] = str(counter)
        numbered_rows.append(RenderedTableRow(label=row.label, cells=cells))
        counter += 1
    return RenderedTable(columns=list(table.columns), rows=numbered_rows)


def _sanitize_table(table: RenderedTable) -> RenderedTable:
    """Replace remaining placeholder cells with English equivalents.
    
    This runs AFTER _enrich_codex_table. Any cell still containing ``?``,
    ``—``, or ``データ未取得`` means neither yfinance nor the LLM could fill it.
    Replace with "Not available" for clarity.
    """
    import re as _re
    
    # Patterns that indicate a purely placeholder cell
    _PURE_Q_RE = _re.compile(r'^[?？\s]+$')  # Pure ? or ？ or spaces
    _PURE_DASH_RE = _re.compile(r'^[–\-\s]+$')  # Pure dashes (— intentionally kept as valid em dash)
    _JP_PLACEHOLDER_RE = _re.compile(r'[データ未取得開示該当計算不可なし]+')
    _GARBAGE_RE = _re.compile(r'[?？]{3,}')
    _JP_GARBAGE_RE = _re.compile(r'[\u3040-\u30ff\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]{3,}')
    
    def _sanitize_cell(cell: str) -> str:
        stripped = cell.strip()
        if not stripped:
            return MISSING_EN
        # Exact matches
        exact_map = {
            "?": MISSING_EN, "–": MISSING_EN, "-": MISSING_EN,
            "データ未取得": MISSING_EN, "開示なし": NOT_DISCLOSED_EN,
            "該当なし": NOT_APPLICABLE_EN, "計算不可": NOT_CALCULABLE_EN,
        }
        if stripped in exact_map:
            return exact_map[stripped]
        # Pure ? sequence (??? → Not available)
        if _PURE_Q_RE.match(stripped):
            return MISSING_EN
        # Pure — sequence
        if _PURE_DASH_RE.match(stripped):
            return MISSING_EN
        # Cell that is mostly Japanese placeholder chars + ?
        jp_chars = len(_JP_PLACEHOLDER_RE.findall(stripped))
        q_chars = stripped.count('?') + stripped.count('？')
        if jp_chars >= 3 or (q_chars >= 3 and jp_chars >= 1):
            return MISSING_EN
        # 🔴 Fix: LLM sometimes formats margins as "7499.67%" (ratio 0.7499 ×100 twice).
        # If a percentage >500%, it's likely a double-multiplied ratio — divide by 100.
        pct_match = re.match(r'^([+-]?\d{3,}(?:\.\d+)?)\s*%\s*$', stripped)
        if pct_match:
            try:
                pct_val = float(pct_match.group(1))
                if pct_val > 500:
                    corrected = pct_val / 100
                    return f"{corrected:.1f}%"
            except (ValueError, OverflowError):
                pass
        # 🔴 Fix: numbers formatted as % that are clearly not percentages (>1000%)
        # e.g. "214512725331.2%" is likely a dollar amount ($214.5B) with a stray % sign
        mega_pct = re.match(r'^([+-]?\d{7,}(?:\.\d+)?)\s*%\s*$', stripped)
        if mega_pct:
            try:
                big_val = float(mega_pct.group(1))
                if big_val > 10000:
                    return _money(big_val)  # treat as dollar amount, not percentage
            except (ValueError, OverflowError):
                pass
        return cell
    
    sanitized_rows: list[RenderedTableRow] = []
    for row in table.rows:
        new_cells = [_sanitize_cell(cell) for cell in row.cells]
        clean_label = _GARBAGE_RE.sub('—', row.label)
        sanitized_rows.append(RenderedTableRow(label=clean_label, cells=new_cells))
    return RenderedTable(columns=list(table.columns), rows=sanitized_rows)


def _to_pct_num(value: Any) -> float:
    """Normalize a raw yfinance value to a percentage number.
    
    yfinance returns ratios (0.7321 = 73.21%).  If the value is between
    -1 and 1 (exclusive), multiply by 100 to get percentage points.
    Otherwise assume it is already in percentage points.
    """
    if not _has(value):
        return 0.0
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    return num * 100.0 if -1.0 < num < 1.0 else num


def _highlights_rows(metrics: FinancialMetrics, row_labels: tuple[str, ...]) -> list[list[str]]:
    """Generate data-driven Highlights table rows from actual metrics."""
    revenue = _money(metrics.revenue_actual)
    revenue_yoy_str = _yoy_pct(metrics.revenue_yoy)
    eps_val = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    margin = _pct(metrics.operating_margin)
    gross_margin = _pct(metrics.gross_margin)
    pe = _multiple(metrics.pe_forward)

    # Determine signal directions from actual numbers
    rev_yoy_num = _to_pct_num(metrics.revenue_yoy)
    eps_beat = False
    try:
        eps_beat = float(metrics.eps_vs_estimate) > 0 if metrics.eps_vs_estimate is not None else False
    except (TypeError, ValueError):
        pass

    # Top positive: revenue growth + cash generation signal
    positive_signal = (
        f"Revenue {revenue}, {revenue_yoy_str} YoY"
    )
    positive_evidence = (
        f"EPS {eps_val}{' (beat)' if eps_beat else ''}, FCF {fcf}"
    )
    positive_impact = (
        "Revenue growth converting to cash flow — favorable"
        if rev_yoy_num > 0 and metrics.free_cash_flow and metrics.free_cash_flow > 0
        else "Revenue strength with monitored cash conversion"
    )

    # Top risk: margins or valuation
    if margin and margin != MISSING and margin != MISSING_JP and not margin.startswith("データ"):
        risk_signal = f"Operating margin: {margin}"
    elif gross_margin and gross_margin != MISSING and gross_margin != MISSING_JP and not gross_margin.startswith("データ"):
        risk_signal = f"Gross margin: {gross_margin}"
    else:
        risk_signal = "Margin data not disclosed"
    try:
        margin_num = float(metrics.operating_margin) if metrics.operating_margin is not None else None
    except (TypeError, ValueError):
        margin_num = None
    risk_evidence = (
        f"Margin {margin}, {'below 15% threshold' if margin_num and (margin_num * 100) < 15 else 'within healthy range'}"
        if margin_num is not None
        else f"PE Forward {pe}" if pe and pe != MISSING else "Watch valuation multiple"
    )
    risk_impact = (
        "Margin compression risk if costs rise faster than revenue"
        if margin_num is not None and (margin_num * 100) < 15
        else "Valuation risk if growth decelerates"
    )

    # Management tone: guidance and outlook
    guidance = getattr(metrics, "guidance", None)
    tone_signal = "Guidance provided" if guidance else "No specific guidance issued"
    tone_evidence = str(guidance)[:120] if guidance else "Refer to earnings call transcript"
    tone_impact = "Confidence in outlook" if guidance else "Neutral — await next guidance update"

    return [
        [row_labels[0], positive_signal, positive_evidence, positive_impact, SOURCE_COMPANY],
        [row_labels[1], risk_signal, risk_evidence, risk_impact, SOURCE_COMPANY],
        [row_labels[2], tone_signal, tone_evidence, tone_impact, SOURCE_COMPANY if guidance else "Earnings call transcript"],
    ]


def _verdict_rows(metrics: FinancialMetrics, row_labels: tuple[str, ...], scoring: Optional['Scoring'] = None) -> list[list[str]]:
    """Generate data-driven Verdict table from all available metrics.
    
    When a canonical Scoring object is provided, uses 6-category weighted scoring
    (total /40) for the overall verdict row. Otherwise falls back to simplified 0-5 scoring.
    """
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    eps_val = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    ocf = _money(metrics.operating_cash_flow)
    margin = _pct(metrics.operating_margin)
    roe = _pct(metrics.roe)
    roic = _pct(metrics.roic)
    pe = _multiple(metrics.pe_forward)
    net_debt = _money(metrics.net_debt)

    # ---- Earnings quality ----
    eps_beat = False
    try:
        eps_beat = float(metrics.eps_vs_estimate) > 0 if metrics.eps_vs_estimate is not None else False
    except (TypeError, ValueError):
        pass
    rev_num = metrics.revenue_actual
    try:
        rev_num = float(rev_num) if rev_num is not None else 0
    except (TypeError, ValueError):
        rev_num = 0
    ocf_num = metrics.operating_cash_flow
    try:
        ocf_num = float(ocf_num) if ocf_num is not None else 0
    except (TypeError, ValueError):
        ocf_num = 0
    cash_quality = "Strong" if ocf_num > 0 and rev_num > 0 else "Monitor"
    eq_positive = f"EPS {eps_val}{' beat' if eps_beat else ''}"
    eq_negative = "No material earnings red flags in reported data" if eps_beat else "EPS did not beat consensus"
    eq_assessment = "Solid — earnings backed by cash flow" if (eps_beat and cash_quality == "Strong") else "Adequate"

    # ---- Growth durability ----
    rev_yoy_num = _to_pct_num(metrics.revenue_yoy)
    try:
        margin_num = float(metrics.operating_margin) if metrics.operating_margin is not None else None
    except (TypeError, ValueError):
        margin_num = None
    gd_positive = f"Revenue {revenue}, {revenue_yoy} YoY"
    gd_negative = (
        f"Margin {margin} — watch for compression"
        if margin_num is not None and (margin_num * 100) < 15
        else "Growth rate sustainability needs monitoring"
    )
    gd_assessment = (
        "Strong — revenue growth with margin support"
        if rev_yoy_num > 10 and (margin_num is None or (margin_num * 100) >= 15)
        else "Moderate — growth present but margin/quality questions remain"
        if rev_yoy_num > 0
        else "Weak — declining revenue YoY"
    )

    # ---- Valuation ----
    try:
        pe_num = float(metrics.pe_forward) if metrics.pe_forward is not None else None
    except (TypeError, ValueError):
        pe_num = None
    val_positive = f"Forward P/E: {pe}" if pe_num is not None else "Valuation multiple not available"
    val_negative = (
        "Above 25x — growth must justify premium"
        if pe_num is not None and pe_num > 25
        else "Valuation appears reasonable for growth profile"
        if pe_num is not None
        else "Insufficient data for valuation assessment"
    )
    val_assessment = (
        "Rich — requires sustained high growth"
        if pe_num is not None and pe_num > 25
        else "Fair — growth-adjusted valuation is reasonable"
        if pe_num is not None
        else "Undetermined"
    )

    # ---- Overall verdict ----
    if scoring is not None:
        # Use canonical 6-category weighted scoring (total /40)
        score = scoring.total
        verdict = scoring.decision()
        score_display = (
            f"Score: {score}/40 "
            f"(FH:{scoring.financial_health}/10 Gr:{scoring.growth}/10 Va:{scoring.valuation}/8 "
            f"Mg:{scoring.management}/5 Mo:{scoring.moat}/4 Se:{scoring.sentiment}/3)"
        )
    else:
        # Fallback: simplified 0-5 scoring
        score = 0
        if eps_beat:
            score += 1
        if rev_yoy_num > 5:
            score += 1
        if rev_yoy_num > 15:
            score += 1
        if ocf_num > 0 and metrics.free_cash_flow and metrics.free_cash_flow > 0:
            score += 1
        if pe_num is not None and pe_num < 20:
            score += 1
        verdict = "BUY" if score >= 4 else "HOLD" if score >= 2 else "SELL"
        score_display = f"Score: {score}/5"

    return [
        [row_labels[0], eq_positive, eq_negative, eq_assessment, SOURCE_COMPANY],
        [row_labels[1], gd_positive, gd_negative, gd_assessment, SOURCE_COMPANY],
        [row_labels[2], val_positive, val_negative, val_assessment, SOURCE_COMPANY],
        [row_labels[3], score_display, "See component assessments above", f"\u2192 {verdict}", "Model + metrics"],
    ]


def _compute_final_verdict(ticker: str, metrics: FinancialMetrics) -> str:
    """Compute a concrete, data-driven final verdict sentence (English)."""
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    eps_val = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    margin = _pct(metrics.operating_margin)
    pe = _multiple(metrics.pe_forward)

    # Score
    score = 0
    try:
        eps_beat = float(metrics.eps_vs_estimate) > 0 if metrics.eps_vs_estimate is not None else False
    except (TypeError, ValueError):
        eps_beat = False
    rev_yoy_num = _to_pct_num(metrics.revenue_yoy)
    try:
        ocf_num = float(metrics.operating_cash_flow) if metrics.operating_cash_flow is not None else 0
    except (TypeError, ValueError):
        ocf_num = 0
    try:
        pe_num = float(metrics.pe_forward) if metrics.pe_forward is not None else None
    except (TypeError, ValueError):
        pe_num = None

    if eps_beat: score += 1
    if rev_yoy_num > 5: score += 1
    if rev_yoy_num > 15: score += 1
    if ocf_num > 0 and metrics.free_cash_flow and metrics.free_cash_flow > 0: score += 1
    if pe_num is not None and pe_num < 20: score += 1

    verdict = "BUY" if score >= 4 else "HOLD" if score >= 2 else "SELL"

    parts = [f"{ticker} reported revenue of {revenue}"]
    if rev_yoy_num != 0:
        parts.append(f"({revenue_yoy} YoY)")
    parts.append(f"with EPS of {eps_val}")

    if eps_beat:
        parts.append("and beat estimates.")
    else:
        parts.append(".")

    if fcf and fcf != MISSING:
        parts.append(f"Free cash flow was {fcf}")

    if margin and margin != MISSING:
        parts.append(f"and operating margin {margin}")

    if pe and pe != MISSING:
        parts.append(f"with forward P/E at {pe}.")

    # Combine evidence
    evidence = " ".join(parts)

    # Risk/reward synthesis
    strengths = []
    concerns = []
    if eps_beat: strengths.append("EPS beat")
    if rev_yoy_num > 10: strengths.append("strong revenue growth")
    if ocf_num > 0: strengths.append("positive cash flow")
    if pe_num is not None and pe_num < 20: strengths.append("reasonable valuation")

    try:
        margin_num = float(metrics.operating_margin) if metrics.operating_margin is not None else None
    except (TypeError, ValueError):
        margin_num = None
    if margin_num is not None and (margin_num * 100) < 15: concerns.append("margin below 15%")
    if pe_num is not None and pe_num > 25: concerns.append("premium valuation")
    if rev_yoy_num <= 0: concerns.append("declining revenue")

    strength_str = ", ".join(strengths) if strengths else "no clear positives"
    concern_str = ", ".join(concerns) if concerns else "no major red flags"

    scoring_note = (
        "\n\n📝 Scoring methodology: This 0-5 score is a simplified quick check "
        "based on 5 binary criteria (EPS beat, revenue growth, cash flow, valuation). "
        "The full dossier includes a multi-dimensional 0-40 scoring covering financial "
        "health, growth, valuation, management quality, competitive moat, and market sentiment."
    )

    return (
        f"{evidence}\n\n"
        f"{ticker}'s Q shows {strength_str}. "
        f"Key watch items: {concern_str}. "
        f"Risk/reward is {'favorable' if verdict == 'BUY' else 'neutral' if verdict == 'HOLD' else 'unfavorable'} "
        f"at current levels → **{verdict}**."
        f"{scoring_note}"
    )


def _compute_final_verdict_jp(ticker: str, metrics: FinancialMetrics) -> str:
    """Compute a concrete, data-driven final verdict sentence (Japanese)."""
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    eps_val = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    margin = _pct(metrics.operating_margin)
    pe = _multiple(metrics.pe_forward)

    score = 0
    try:
        eps_beat = float(metrics.eps_vs_estimate) > 0 if metrics.eps_vs_estimate is not None else False
    except (TypeError, ValueError):
        eps_beat = False
    rev_yoy_num = _to_pct_num(metrics.revenue_yoy)
    try:
        ocf_num = float(metrics.operating_cash_flow) if metrics.operating_cash_flow is not None else 0
    except (TypeError, ValueError):
        ocf_num = 0
    try:
        pe_num = float(metrics.pe_forward) if metrics.pe_forward is not None else None
    except (TypeError, ValueError):
        pe_num = None

    if eps_beat: score += 1
    if rev_yoy_num > 5: score += 1
    if rev_yoy_num > 15: score += 1
    if ocf_num > 0 and metrics.free_cash_flow and metrics.free_cash_flow > 0: score += 1
    if pe_num is not None and pe_num < 20: score += 1

    verdict = "BUY" if score >= 4 else "HOLD" if score >= 2 else "SELL"

    growth = "強い成長" if rev_yoy_num > 10 else "成長" if rev_yoy_num > 0 else "減収"
    cash = "堅調なキャッシュ創出" if ocf_num > 0 else "キャッシュ要確認"
    valuation = "割安" if pe_num is not None and pe_num < 20 else "妥当" if pe_num is not None and pe_num < 25 else "割高"
    risks = []
    if pe_num is not None and pe_num > 25: risks.append("高PER")
    if rev_yoy_num <= 0: risks.append("減収リスク")
    risk_str = "、".join(risks) if risks else "特になし"

    scoring_note = (
        "\n\n📝 スコアリング方法: この0-5スコアは5つの二値基準"
        "（EPSビート、売上成長、キャッシュフロー、バリュエーション）に基づく簡易チェックです。"
        "完全な評価は6カテゴリ（財務健全性、成長性、バリュエーション、経営品質、競争優位性、"
        "市場センチメント）による0-40の多次元スコアリングで行われます。"
    )

    return (
        f"{ticker} 売上高{revenue}（{revenue_yoy}前年比）、EPS{eps_val}。"
        f"スコア{score}/5: {growth}、{cash}、バリュエーション{valuation}。"
        f"リスク: {risk_str}。→ **{verdict}**"
        f"{scoring_note}"
    )


def _summary(language: TemplateLanguage, ticker: str, section_key: str, metrics: FinancialMetrics) -> str:
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    eps = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    pe = _multiple(metrics.pe_forward)

    if language == "jp":
        summaries = {
            "EPS & Revenue": f"👉 EPSは{eps}、売上高は{revenue}。予想比と前年比の両方を見て、成長の質を判断する局面です。",
            "Highlights": f"👉 {ticker} 売上高{revenue}（{revenue_yoy}前年比）、EPS{eps}。成長がキャッシュと利益率に波及しているかが焦点です。",
            "Operating Metrics": f"👉 売上高は{revenue}、前年比は{revenue_yoy}。利益率の変化が次の評価ポイントです。",
            "Cash Flow": f"👉 FCFは{fcf}。利益が現金に変わっているかを最優先で確認します。",
            "Capital Efficiency": "👉 ROE/ROICは資本効率を見る指標です。高い数値でもレバレッジや自社株買いの影響を分けて評価します。",
            "Segments": "👉 どのセグメントが成長を支えているかを見ると、次の四半期の注目点が見えます。",
            "Forward P/E": f"👉 予想PERは{pe}。成長率で正当化できるかが投資判断の分かれ目です。",
            "Backlog": "👉 受注残は事業によって重要度が違います。該当なし・開示なしの場合は無理に評価しません。",
            "Guidance": "👉 ガイダンスは次の期待値です。売上、利益率、EPSを分けて確認します。",
            "Verdict": f"👉 {_compute_final_verdict_jp(ticker, metrics)}",
        }
        return summaries.get(section_key, f"👉 {ticker}の決算は、確認できる数字と未開示項目を分けて評価します。")

    summaries = {
        "EPS & Revenue": f"{ticker} reported EPS of {eps} and revenue of {revenue}; the key investor question is whether the beat/miss is broad-based or one-off.",
        "Highlights": f"{ticker} Q: revenue {revenue} ({revenue_yoy} YoY), EPS {eps}. Focus on whether revenue growth converts into durable cash flow and margin expansion.",
        "Operating Metrics": f"Revenue was {revenue} with YoY growth of {revenue_yoy}; margin direction determines the quality of the growth.",
        "Cash Flow": f"Free cash flow was {fcf}; cash conversion and capex intensity show whether earnings are translating into owner cash.",
        "Capital Efficiency": "ROE, ROIC, and related returns indicate whether growth is creating value or simply consuming capital.",
        "Segments": "Segment trends identify which business lines are driving the quarter and where risk is concentrated.",
        "Forward P/E": f"Forward P/E is {pe}; valuation only works if growth and margin durability support it.",
        "Backlog": "Backlog is evaluated only when economically relevant and disclosed; otherwise it is marked not applicable or not disclosed.",
        "Guidance": "Guidance matters because it resets expectations for revenue, margin, EPS, and medium-term demand.",
        "Verdict": _compute_final_verdict(ticker, metrics),
    }
    return summaries.get(section_key, f"{ticker}'s section conclusion is based on concrete reported metrics and source traceability.")


def _default_highlights_analysis(language: TemplateLanguage, metrics: FinancialMetrics) -> list[str]:
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    eps = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    margin = _pct(metrics.operating_margin)
    pe = _multiple(metrics.pe_forward)
    if language == "jp":
        return [
            "\n".join(
                [
                    "🌟 ハイライト（良かった点）",
                    "",
                    "① 売上成長の確認",
                    f"● 売上高: {revenue} / 前年比: {revenue_yoy}",
                    "👉 成長が数字で確認できる場合、投資家は持続性と利益率への波及を見ます。",
                    "",
                    "② キャッシュ創出力",
                    f"● フリーキャッシュフロー: {fcf}",
                    "👉 利益が現金に変わっているかは、決算の質を見る重要ポイントです。",
                    "",
                    "③ EPSと利益の確認",
                    f"● EPS: {eps}",
                    "👉 予想比と前年比の両方を見て、成長が株主利益に届いているかを確認します。",
                    "",
                    "⚠️ ローライト（懸念点）",
                    "",
                    "① 利益率の確認",
                    f"● 営業利益率: {margin}",
                    "👉 売上が伸びても利益率が弱い場合、株価評価は伸びにくくなります。",
                    "",
                    "② バリュエーション",
                    f"● Forward P/E: {pe}",
                    "👉 成長が鈍化した場合、PERが高いほど株価の下振れリスクは大きくなります。",
                    "",
                    "③ 未開示データ",
                    "● 未取得または未開示の項目は表で明示しています。",
                    "👉 空欄でごまかさず、次に確認すべき資料を明確にします。",
                    "",
                    "🧠 総合評価（Namiさん向け）",
                    "👉 この決算の質は、売上成長・利益率・キャッシュ創出の3軸で判断します。すべてが同じ方向ならシグナルは強く、方向が分かれる場合は数字の質に注意が必要です。",
                    "",
                    "🎯 投資視点の一言",
                    "👉 良い決算でも、次のガイダンスとバリュエーションが合わなければ追いかけすぎに注意です。",
                ]
            )
        ]
    return [
        "\n".join(
            [
                "Highlights / Lowlights",
                "",
                "① Revenue growth",
                f"● Revenue: {revenue}; YoY growth: {revenue_yoy}.",
                "👉 Investor implication: the first test is whether reported growth is broad enough to support durable earnings power.",
                "",
                "② Earnings delivery",
                f"● EPS: {eps}.",
                "👉 Investor implication: EPS must be read against revenue growth and operating leverage, not as a standalone headline number.",
                "",
                "③ Cash conversion",
                f"● Free cash flow: {fcf}.",
                "👉 Investor implication: cash conversion confirms whether accounting earnings are turning into usable owner cash.",
                "",
                "⚠️ Lowlights / watch items",
                "",
                "① Margin durability",
                f"● Operating margin: {margin}.",
                "👉 If margin weakens while revenue grows, the market may discount the quality of the growth.",
                "",
                "② Valuation sensitivity",
                f"● Forward P/E: {pe}.",
                "👉 A higher multiple requires confidence that revenue growth, margin, and free cash flow can persist.",
                "",
                "③ Disclosure gaps",
                "● Items marked as Not available, Not disclosed, or N/A represent data limitations that should be verified against SEC filings before drawing investment conclusions.",
                "👉 Missing data is treated as a limitation, not as evidence for or against the company.",
                "",
                "🧠 Nami insight",
                "👉 Revenue, margin, and cash flow provide the three-way quality check on this quarter. When all three move together, the earnings signal is stronger; when they diverge, the risk is in execution quality rather than the headline growth rate.",
                "",
                "🎯 Investment takeaway",
                "👉 The quarter is investable when revenue growth, cash generation, and valuation are aligned; divergence in any pillar warrants caution on position sizing.",
            ]
        )
    ]


def _default_section_analysis(
    language: TemplateLanguage,
    ticker: str,
    section_key: str,
    metrics: FinancialMetrics,
) -> list[str]:
    """Deterministic fallback commentary when LLM prose is missing or too thin."""
    if section_key == "Highlights":
        return _default_highlights_analysis(language, metrics)

    revenue = _money(getattr(metrics, "revenue_actual", None) or getattr(metrics, "revenue_quarterly", None))
    revenue_yoy = _pct(getattr(metrics, "revenue_yoy", None))
    eps = _eps(getattr(metrics, "eps_actual", None))
    fcf = _money(getattr(metrics, "free_cash_flow", None))
    ocf = _money(getattr(metrics, "operating_cash_flow", None))
    capex = _money(getattr(metrics, "capex", None))
    gross_margin = _pct(getattr(metrics, "gross_margin", None))
    operating_margin = _pct(getattr(metrics, "operating_margin", None))
    net_income = _money(getattr(metrics, "net_income_quarterly", None) or getattr(metrics, "net_income", None))
    roe = _pct(getattr(metrics, "roe", None))
    roic = _pct(getattr(metrics, "roic", None))
    pe = _multiple(getattr(metrics, "pe_forward", None))
    backlog = _money(getattr(metrics, "backlog", None))
    guidance = _metric_text(metrics, "guidance") or NOT_DISCLOSED_EN

    if language == "jp":
        text = {
            "EPS & Revenue": f"🧠 EPSは{eps}、売上高は{revenue}、前年比は{revenue_yoy}です。予想比だけでなく、売上の伸びがEPSに届いているかを確認します。👉 数字が未取得の場合は推測せず、表のデータ未取得を前提に次の資料確認へ進みます。",
            "Operating Metrics": f"🧠 売上高{revenue}、粗利率{gross_margin}、営業利益率{operating_margin}、純利益{net_income}を同じ期間で見ます。👉 売上成長と利益率が同時に改善していれば質は高く、どちらかが弱い場合はコスト構造を確認します。",
            "Cash Flow": f"📌 FCF = OCF - CapEx。OCFは{ocf}、CapExは{capex}、FCFは{fcf}です。👉 利益が現金に変わっているかが最重要で、FCFが弱い場合は成長投資と一時要因を分けて確認します。",
            "Capital Efficiency": f"🧠 ROEは{roe}、ROICは{roic}です。👉 高い資本効率は強みですが、自社株買い、レバレッジ、資産圧縮の影響を分けて、事業そのものの収益力かを確認します。",
            "Segments": f"🧠 セグメント別売上は、どの事業が{ticker}の成長を支えているかを見るために使います。👉 表のセグメント売上、前年比、ドライバーを比較し、単一事業依存か複数事業の成長かを確認します。",
            "Forward P/E": f"🧠 Forward P/Eは{pe}です。👉 この倍率は単独では判断せず、売上成長{revenue_yoy}、利益率{operating_margin}、FCF{fcf}で正当化できるかを見ます。",
            "Backlog": f"🧠 Backlogは{backlog}です。👉 開示される業種では将来売上の視認性を示しますが、開示がない場合は無理に評価せず、ガイダンスや受注コメントを補助情報として扱います。",
            "Guidance": f"🧠 ガイダンス: {guidance}。👉 次四半期の売上、利益率、EPSの前提が現在の実績とつながっているかを確認し、強い実績でも弱い見通しなら評価を調整します。",
            "Verdict": f"🎯 {ticker}の判断は、売上{revenue}、EPS{eps}、FCF{fcf}、Forward P/E{pe}を同時に見ます。👉 良い決算でも、キャッシュとバリュエーションが支えなければ追いかけすぎに注意です。",
        }
        return [text.get(section_key, f"🧠 {ticker}の決算は、確認できる数字と未開示項目を分けて評価します。👉 推測は使わず、表とソースに戻って判断します。")]

    text = {
        "EPS & Revenue": f"🧠 EPS was {eps} and revenue was {revenue}, with YoY revenue growth of {revenue_yoy}. The commentary should separate the estimate surprise from the underlying growth signal: a beat is higher quality when revenue, EPS, and source-backed YoY data point in the same direction. 👉 If any estimate or actual is unavailable, it remains a data limitation rather than an inferred beat or miss.",
        "Operating Metrics": f"🧠 Operating quality is read through revenue of {revenue}, gross margin of {gross_margin}, operating margin of {operating_margin}, and net income of {net_income}. Strong revenue growth is more durable when it carries through to margins. 👉 If margins move against revenue, the issue is not demand alone but cost discipline and operating leverage.",
        "Cash Flow": f"📌 FCF = OCF - CapEx. Operating cash flow was {ocf}, capex was {capex}, and free cash flow was {fcf}. Cash flow is the check on earnings quality because it shows whether reported profit becomes usable cash. 👉 Weak FCF requires separating temporary working-capital timing from structural cash conversion pressure.",
        "Capital Efficiency": f"🧠 Capital efficiency uses ROE of {roe} and ROIC of {roic} to judge whether growth creates value. High returns are strongest when they come from operating profit rather than leverage, buybacks, or asset shrinkage. 👉 The investor read is to compare returns with reinvestment needs and cash generation before treating growth as value-accretive.",
        "Segments": f"🧠 Segment commentary identifies which business lines are carrying {ticker}'s quarter. The table should be read by revenue size, YoY direction, and stated driver rather than by one headline segment. 👉 A healthier quarter has multiple segments contributing; concentration in one segment raises execution risk for the next quarter.",
        "Forward P/E": f"🧠 The forward P/E is {pe}. Valuation is not a verdict by itself; it has to be tested against revenue growth of {revenue_yoy}, operating margin of {operating_margin}, and free cash flow of {fcf}. 👉 A premium multiple is acceptable only when forward guidance and cash conversion support the implied growth path.",
        "Backlog": f"🧠 Backlog is {backlog}. For companies where backlog is economically relevant, it is a visibility indicator for future revenue; for companies that do not disclose it, the correct treatment is not applicable or not disclosed. 👉 Do not infer backlog strength from revenue growth unless the company explicitly reports orders or remaining performance obligations.",
        "Guidance": f"🧠 Guidance reads as: {guidance}. This section resets expectations after the reported quarter by linking management's forward comments to revenue, margins, and EPS. 👉 Strong trailing results deserve a lower valuation weight if the next-quarter guide implies slowing demand or margin pressure.",
        "Verdict": f"🎯 The verdict combines revenue of {revenue}, EPS of {eps}, free cash flow of {fcf}, operating margin of {operating_margin}, and forward P/E of {pe}. The investment call should not rest on one metric. 👉 The risk/reward improves when growth, cash conversion, and valuation are aligned; it weakens when any one of those pillars breaks.",
    }
    audit = {
        "EPS & Revenue": f"● Audit read: tie each surprise back to the EPS and revenue rows before calling the quarter strong or weak. For {ticker}, a revenue beat without EPS leverage would point to cost pressure, while EPS strength without revenue support could be mix, tax, buybacks, or one-time items. 👉 The source-safe conclusion is the intersection of estimate variance, YoY growth, and management explanation.",
        "Operating Metrics": f"● Audit read: compare the income statement from top line to operating income. Revenue growth of {revenue_yoy} is more convincing when gross margin and operating margin move with it. If gross margin is stable but operating margin weakens, OpEx is the pressure point; if gross margin weakens first, pricing, mix, or input costs need source confirmation.",
        "Cash Flow": "● Audit read: cash conversion should reconcile earnings quality with balance-sheet movement. A quarter can show strong EPS while free cash flow lags because of working capital timing, inventory, receivables, or heavy capex. The PDF should therefore keep OCF, CapEx, and FCF separate instead of collapsing them into a single cash-flow judgment.",
        "Capital Efficiency": "● Audit read: returns on capital are useful only when the denominator is understood. ROE can rise because operations improved, because equity fell after buybacks, or because leverage increased. ROIC is the cleaner operating lens, but it still needs to be read beside cash generation and reinvestment requirements before assigning a quality premium.",
        "Segments": f"● Audit read: segment data prevents a misleading company-level conclusion. If one segment drives most of {ticker}'s growth, the next-quarter risk is concentration. If several segments grow with different drivers, the growth base is more resilient. Missing segment rows remain limitations and should not be filled with assumed business mix.",
        "Forward P/E": "● Audit read: valuation should be treated as conditional, not absolute. A low forward P/E can still be expensive if earnings estimates are falling, and a high multiple can be reasonable if growth durability and margins are improving. The sourced approach is to connect the multiple to forward EPS basis, guidance, and cash conversion.",
        "Backlog": "● Audit read: backlog is only meaningful when the company reports it in a consistent way. For software or subscription businesses, remaining performance obligations may be the closer proxy; for industrial companies, orders and book-to-bill may matter more. If none of those are disclosed, the correct conclusion is visibility not disclosed.",
        "Guidance": "● Audit read: guidance is the bridge between the reported quarter and valuation. The strongest setup is reported growth plus guidance that sustains or improves the run-rate. A weaker guide can offset a strong quarter because markets discount the future. Every guidance conclusion should name whether it came from company guidance, consensus, or transcript language.",
        "Verdict": "● Audit read: the final call should be reproducible from the report. A constructive verdict requires at least two confirming pillars, usually growth plus cash conversion or growth plus valuation support. A cautious verdict is appropriate when the table shows missing data, margin pressure, weak cash conversion, or a valuation that requires assumptions not present in the source dossier.",
    }
    checklist_focus = {
        "EPS & Revenue": "estimate variance, YoY revenue growth, EPS leverage, and the exact source for consensus versus actuals",
        "Operating Metrics": "gross margin, operating margin, OpEx discipline, net income conversion, and whether revenue growth carries through the income statement",
        "Cash Flow": "operating cash flow, capex, free cash flow, working-capital timing, and whether cash generation supports the EPS story",
        "Capital Efficiency": "ROE, ROIC, buybacks, dividends, leverage effects, and whether returns come from operations rather than balance-sheet mechanics",
        "Segments": "segment revenue, segment YoY growth, mix, business driver language, and concentration risk across the reported portfolio",
        "Forward P/E": "forward P/E, forward EPS basis, guidance support, growth durability, and whether the multiple embeds assumptions not proven by sources",
        "Backlog": "reported backlog, order intake, book-to-bill, remaining performance obligations, and the distinction between not applicable and not disclosed",
        "Guidance": "revenue guide, margin guide, EPS guide, management tone, and whether the forward view confirms or weakens the reported quarter",
        "Verdict": "growth, profitability, cash conversion, capital efficiency, valuation, and the unresolved data gaps that could change the conclusion",
    }
    checklist = (
        f"👉 Decision checklist: review {checklist_focus.get(section_key, 'the sourced table values and unresolved data gaps')} before using this section in the final investment call.\n"
        "① Confirm the table values reconcile to an explicit source row or listed document.\n"
        "② Separate confirmed data from interpretation; do not upgrade a missing field into a positive or negative claim.\n"
        "③ Compare the current quarter with the prior-year or consensus baseline shown in the table, because direction matters as much as the absolute number.\n"
        "④ Link the section back to the final verdict only when it changes growth durability, earnings quality, cash conversion, valuation, or forward visibility.\n"
        "⑤ Treat every Not available, Not disclosed, or N/A cell as an audit flag for the source dossier rather than as permission to infer a number."
    )
    source_walkthrough = (
        "🧠 Source walkthrough: start with the table row, then open the matching transcript, press release, presentation, SEC filing, or yfinance field named in the Source column. "
        "Write down whether the number is company-reported, consensus-derived, calculated by the pipeline, or unavailable. "
        "If the value is calculated, verify the numerator and denominator separately before relying on the result. "
        "If the source is management commentary rather than a numeric filing line, classify it as tone or guidance, not as a hard financial metric. "
        "This distinction matters because a PDF reader should be able to reproduce the conclusion without trusting hidden model reasoning. "
        "A strong section therefore contains three things: the reported value, the comparison baseline, and the investor implication. "
        "A weak section usually misses one of those pieces, and the final verdict should discount it until the source dossier fills the gap. "
        "🎯 Practical takeaway: promote this section in the investment view only when the data is sourced, the direction is clear, and the implication is material to future earnings or valuation."
    )
    return [
        text.get(section_key, f"🧠 {ticker}'s section view is based only on sourced metrics in the table. 👉 Missing values remain explicit limitations, and conclusions should be traceable to the source dossier before they are used in an investment decision."),
    ]


def _numbered_highlight_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+\.)\s+", text))


def _ensure_section_commentary(
    language: TemplateLanguage,
    ticker: str,
    section_key: str,
    metrics: FinancialMetrics,
    analysis_items: list[str],
) -> list[str]:
    cleaned = [item.strip() for item in analysis_items if item and item.strip()]
    combined = "\n".join(cleaned)
    fallback = _default_section_analysis(language, ticker, section_key, metrics)

    if section_key == "Highlights":
        has_required_structure = (
            _numbered_highlight_count(combined) >= 3
            and "🧠" in combined
            and "🎯" in combined
            and ("⚠" in combined or "Lowlight" in combined or "Lowlights" in combined)
        )
        if not has_required_structure:
            cleaned.extend(fallback)
    elif len(combined) <= 200:
        cleaned.extend(fallback)

    return cleaned


def _resolved_quarter_label(quarter: str, metrics: FinancialMetrics) -> str:
    requested = quarter.strip() if isinstance(quarter, str) else ""
    if requested and requested.lower() != "latest quarter":
        return requested
    explicit = _metric_text(
        metrics,
        "quarter",
        "fiscal_quarter",
        "reporting_quarter",
        "reporting_period",
        "period",
        "transcript_quarter",
    )
    if explicit and explicit.lower() != "latest quarter":
        return explicit
    # Fallback: derive from metrics available financial data, not calendar
    from datetime import date
    # Try to extract fiscal quarter from yfinance filing date in metrics
    filing_date = _metric_text(metrics, "filing_date", "latest_filing_date", "period_end_date")
    if filing_date:
        try:
            fd = date.fromisoformat(filing_date[:10])
            # Fiscal quarter: use the actual period end month/year from the filing
            fq = (fd.month - 1) // 3 + 1
            return f"FY{fd.year} Q{fq}"
        except (ValueError, TypeError):
            pass
    # Last resort: today's date but mark as estimated
    today = date.today()
    q = (today.month - 1) // 3 + 1
    return f"FY{today.year} Q{q} (est.)"


def build_earnings_deep_dive_report(
    *,
    ticker: str,
    company: str | None,
    quarter: str,
    metrics: FinancialMetrics,
    transcript_url: str | None = None,
    language: str = "en",
    section_analysis: dict[str, str] | None = None,
    generated_at: str | None = None,
    company_overview: dict | None = None,
    scoring: Optional['Scoring'] = None,
    yf_info: dict | None = None,
) -> EarningsDeepDiveReport:
    """Build the deterministic report model used by the PDF renderer."""
    report_language = _language(language)
    ticker_clean = ticker.strip().upper()
    company_name = company.strip() if isinstance(company, str) and company.strip() else ticker_clean
    template = get_earnings_template(report_language)
    analysis_by_key = section_analysis or {}

    # Sanitize prose: remove garbage ???? patterns and JP leakage from LLM output
    import re as _re
    _GARBAGE_RE = _re.compile(r'[?？]{3,}')
    _JP_GARBAGE_RE = _re.compile(r'[\u3040-\u30ff\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]{3,}')
    def _clean_prose(text: str) -> str:
        if not text:
            return text
        # ── Fix: strip null bytes from font rendering issues ──
        text = text.replace("\x00", "")
        # ── Fix: collapse line breaks that split key phrases ──
        text = text.replace('For\nNami-san', 'For Nami-san')
        text = text.replace('For\nNamiさん', 'For Namiさん')
        text = text.replace('For\nNami', 'For Nami')
        text = _re.sub(r'For\s+\n\s*Nami', 'For Nami', text)
        # Replace runs of 3+ question marks with "—"
        text = _GARBAGE_RE.sub('—', text)
        # Fix isolated question marks from LLM uncertainty (e.g., "missed by 16% ? a" → "missed by 16% — a")
        text = _re.sub(r'\s+\?\s+', ' — ', text)
        # Replace runs of 3+ JP/fullwidth chars (garbled leakage) with "" only for English mode
        if report_language == "en":
            text = _JP_GARBAGE_RE.sub('', text)
        # Clean up resulting empty lines or double dashes
        text = _re.sub(r'\n\s*—\s*\n', '\n', text)
        # 🔴 Fix: strip "One-line summary:" / "一言まとめ:" blockquotes — generic filler
        # Match both with and without blockquote prefix (>)
        text = _re.sub(r'(?:^|\n)\s*>?\s*(One-line summary|一言まとめ|投資視点の一言)\s*:?\s*[^\n]*\n?', '\n', text, flags=_re.MULTILINE)
        # 🔴 Fix: strip "[VALIDATED DATA: ...]" internal markers from prose
        text = _re.sub(r'\n?\s*\[VALIDATED DATA:[^\]]*\]\s*\n?', '\n', text)
        # 🔴 Fix: convert markdown bullet markers to proper bullets
        # Lines starting with "* " or "- " get converted to "• "
        text = _re.sub(r'(?m)^\s*\*\s+', '• ', text)
        text = _re.sub(r'(?m)^\s*-\s+', '• ', text)
        # Also handle bullets after a newline mid-paragraph
        text = _re.sub(r'\n\*\s+', '\n• ', text)
        text = _re.sub(r'\n-\s+', '\n• ', text)
        # 🔴 Fix: Balance markdown bold/italic markers — unclosed ** crashes ReportLab
        # Strip orphaned ** markers (odd count → remove last)
        bold_count = text.count('**')
        if bold_count % 2 == 1:
            text = text[::-1].replace('**', '', 1)[::-1]  # remove last occurrence
        # Strip all markdown bold/italic — PDF uses ReportLab formatting, not markdown
        text = _re.sub(r'(?<!\*)\*\*(?!\*)', '', text)  # ** → nothing
        text = _re.sub(r'(?<!\*)\*(?!\*)', '', text)     # * → nothing (italic)
        # 🔴 Fix: Strip markdown ## headers that leak from LLM output
        text = _re.sub(r"(?m)^##\s+[^\n]+\n?", "", text)
        # 🔴 Fix: LLM double-multiplied margins: "7499.67%" → divide by 100
        # Also rounds ALL percentages to 1 decimal to fix raw float leakage (e.g. 67.63265% → 67.6%)
        # 🔴 Fix: Replace circled digits ①-⑳ with (1)-(20) — PDF fonts lack these glyphs
        _CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
        _PAREN = ["(1)","(2)","(3)","(4)","(5)","(6)","(7)","(8)","(9)","(10)","(11)","(12)","(13)","(14)","(15)","(16)","(17)","(18)","(19)","(20)"]
        for i, ch in enumerate(_CIRCLED):
            text = text.replace(ch, _PAREN[i])
        def _fix_outlier_pct(m):
            try:
                val = float(m.group(1))
                # Decimal form (e.g. 0.0767 for ROE) → multiply by 100
                if abs(val) <= 1:
                    val *= 100
                # Double-multiplied (e.g. 7499.67%) → divide by 100
                if val > 500:
                    val /= 100
                return f"{val:.1f}%"
            except (ValueError, OverflowError):
                pass
            return m.group(0)
        text = _re.sub(r'([+-]?\d+(?:\.\d+)?)\s*%', _fix_outlier_pct, text)
        return text

    sections: list[RenderedSection] = []
    
    # Sections where the LLM table is unreliable — use yfinance data directly.
    # The LLM analysis text is still used for prose below the table.
    # EPS & Revenue and Forward P/E added 2026-05-08 because LLM
    # hallucinates — even with correct metrics in the prompt, it fills
    # the table cells with placeholders.
    _DATA_DRIVEN_SECTIONS = {
        "EPS & Revenue", "Forward P/E",
        "Operating Metrics", "Cash Flow", "Capital Efficiency",
        "Segments", "Geographic Segments", "Guidance", "Backlog", "Verdict",
        "Highlights",  # Prose-only — LLM table is suppressed, rich prose kept
    }
    
    for section in template:
        analysis_text = analysis_by_key.get(section.key) or analysis_by_key.get(section.title)
        rows: list[list[str]] = []
        if analysis_text:
            analysis_text = _clean_prose(analysis_text)
            # Strip echoed template question (LLM sometimes echoes it verbatim)
            if section.question and analysis_text.startswith(section.question):
                analysis_text = analysis_text[len(section.question):].strip()
            # Also strip any "Please X..." / "What X..." / "Question (EN): ..." instruction line at start
            import re as _re_strip
            analysis_text = _re_strip.sub(
                r"^(?:(?:question\s*\(EN\):\s*)|(?:please\s+\w+)|(?:what\s+\w+)|(?:how\s+(?:is|are|was|were|does|do|did|can|could|should|would|will|has|have)\b))[^\n]*\n?",
                "", analysis_text, count=1, flags=_re_strip.IGNORECASE
            ).strip()
        codex_table = _extract_markdown_table(analysis_text, section.table_columns) if analysis_text else None
        
        # For data-driven sections, ignore the LLM table and use yfinance rows directly.
        # The LLM prose is kept as analysis_items.
        if section.key in _DATA_DRIVEN_SECTIONS:
            rows = _rows_for_section(section.key, section.table_rows, metrics, scoring)
            table = RenderedTable(
                columns=list(section.table_columns),
                rows=[RenderedTableRow(
                    label=str(row[0]),
                    cells=[str(cell) for cell in row[1:]],
                ) for row in rows],
            )
            table = _sanitize_table(table)
            if codex_table and section.key != "Highlights":
                deterministic_is_sparse = all(
                    all(
                        str(cell).strip() in (
                            MISSING,
                            MISSING_EN,
                            NOT_APPLICABLE,
                            NOT_APPLICABLE_EN,
                            NOT_DISCLOSED,
                            NOT_DISCLOSED_EN,
                            NOT_CALCULABLE,
                            NOT_CALCULABLE_EN,
                            "—",
                            "",
                        )
                        for cell in row.cells
                    )
                    for row in table.rows
                )
                if deterministic_is_sparse:
                    table = _enrich_codex_table(codex_table, section.key, section.table_rows, metrics, scoring)
                    table = _number_highlights_rows(table)
                    table = _sanitize_table(table)
            analysis_items = _analysis_blocks_without_table(analysis_text) if analysis_text else []
            # ── Segments fallback: when XBRL is garbage (all rows NA), use LLM table ──
            if section.key == "Segments" and analysis_text:
                all_na = all(
                    all(str(c).lower() in ("not available", "—", "", "n/a") for c in row.cells)
                    for row in table.rows
                )
                if all_na:
                    # Priority 1: LLM-generated markdown table (most reliable)
                    if codex_table and codex_table.rows:
                        real_rows = [
                            r for r in codex_table.rows
                            if not r.label.strip().startswith("**")  # Skip total/bold rows
                            and not all(str(c).strip() in ("—", "", "Data not available in transcript") for c in r.cells)
                            and not r.label.strip().lower().startswith("total")  # Skip total rows
                            and r.label.strip().lower() not in ("segment / region", "segment")  # Skip embedded sub-table headers
                        ]
                        if real_rows:
                            # Remap LLM columns to template: Segment|Revenue|YoY|Driver|Source
                            # LLM has: Segment(label)|Revenue(c0)|Prior Year(c1)|YoY(c2)|Mix(c3)|Source(c4)
                            # Template needs: |Revenue|YoY|Driver|Source
                            remapped = []
                            for r in real_rows[:len(section.table_rows)]:
                                cells = r.cells
                                remapped.append(RenderedTableRow(
                                    label=r.label,
                                    cells=[
                                        cells[0] if len(cells) > 0 else "—",       # Revenue
                                        cells[2] if len(cells) > 2 else "—",       # YoY
                                        cells[3] if len(cells) > 3 else "—",       # Driver/Mix
                                        cells[4] if len(cells) > 4 else "—",       # Source
                                    ],
                                ))
                            # Fill remaining slots
                            for _ in range(len(remapped), len(section.table_rows)):
                                remapped.append(RenderedTableRow(
                                    label=section.table_rows[len(remapped)],
                                    cells=[NOT_APPLICABLE_EN] * 4,
                                ))
                            table = RenderedTable(
                                columns=list(section.table_columns),
                                rows=remapped,
                            )
                            table = _sanitize_table(table)
                    # Priority 2: prose parsing (regex-based)
                    if all_na and any(
                        str(c).lower() in ("not available", "—", "", "n/a")
                        for row in table.rows for c in row.cells
                    ):
                        parsed = _parse_segments_from_prose(analysis_text)
                        if parsed:
                            segment_names = list(parsed.keys())[:len(section.table_rows)]
                            yf_rows = []
                            for idx, seg_name in enumerate(segment_names):
                                seg = parsed[seg_name]
                                label = section.table_rows[idx] if idx < len(section.table_rows) else seg.get('name', seg_name)
                                yf_rows.append([
                                    label,
                                    _money(seg.get('revenue')),
                                    _pct(seg.get('yoy')),
                                    seg.get('driver', 'Segment revenue'),
                                    seg.get('source', 'LLM transcript analysis'),
                                ])
                            for idx in range(len(segment_names), len(section.table_rows)):
                                yf_rows.append([section.table_rows[idx], NOT_APPLICABLE_EN, NOT_APPLICABLE_EN, NOT_APPLICABLE_EN, NOT_APPLICABLE_EN])
                            table = RenderedTable(
                                columns=list(section.table_columns),
                                rows=[RenderedTableRow(label=str(r[0]), cells=[str(c) for c in r[1:]]) for r in yf_rows],
                            )
                            table = _sanitize_table(table)
        elif codex_table:
            table = _enrich_codex_table(codex_table, section.key, section.table_rows, metrics, scoring)
            table = _number_highlights_rows(table)
            table = _sanitize_table(table)
            analysis_items = _analysis_blocks_without_table(analysis_text)
        else:
            rows = _rows_for_section(section.key, section.table_rows, metrics, scoring)
            table = RenderedTable(
                columns=list(section.table_columns),
                rows=[RenderedTableRow(
                    label=str(row[0]),
                    cells=[str(cell) for cell in row[1:]],
                ) for row in rows],
            )
            table = _sanitize_table(table)
            if analysis_text:
                analysis_items = _analysis_blocks_without_table(analysis_text)
            else:
                analysis_items = []
        analysis_items = _ensure_section_commentary(
            report_language,
            ticker_clean,
            section.key,
            metrics,
            analysis_items,
        )
        # ── Data annotation injection: force LLM commentary to use table values ──
        if section.key in ("EPS & Revenue", "Forward P/E") and rows:
            value_col_idx = 2 if section.key == "EPS & Revenue" else 1  # "Actual" or "Current"
            if section.key == "EPS & Revenue" and len(rows) > 0 and len(rows[0]) > value_col_idx:
                eps_actual = rows[0][value_col_idx]
                if eps_actual and eps_actual not in (MISSING, MISSING_EN, NOT_APPLICABLE, NOT_APPLICABLE_EN, NOT_DISCLOSED, NOT_DISCLOSED_EN):
                    eps_note = f"EPS actual: {eps_actual} (validated from source data)"
                    if analysis_items:
                        analysis_items[-1] = analysis_items[-1] + "\n\n" + eps_note
                    else:
                        analysis_items = [eps_note]
            elif section.key == "Forward P/E" and len(rows) > 0 and len(rows[0]) > value_col_idx:
                pe_val = rows[0][value_col_idx]
                if pe_val and pe_val not in (MISSING, MISSING_EN, NOT_APPLICABLE, NOT_APPLICABLE_EN, NOT_DISCLOSED, NOT_DISCLOSED_EN, "—"):
                    # Replace LLM hallucination with the actual value.
                    # The LLM often claims "not provided" even when pe_forward is in metrics.
                    import re as _re2
                    pe_fact = f"The forward P/E is {pe_val}."
                    # 🔴 Fix: Check if ANY item already contains pe_fact BEFORE the loop.
                    # The old per-item check caused pe_fact injection into EVERY item,
                    # producing 5+ repetitions like "The forward P/E is 21.65x. (1)..."
                    # "The forward P/E is 21.65x. (2)..." etc.
                    _any_has_pe = any(pe_fact in (item or "") for item in analysis_items)
                    _first_nonempty_idx = next((i for i, item in enumerate(analysis_items) if item), 0)
                    for i, item in enumerate(analysis_items):
                        if not item:
                            continue
                        # Strip common LLM false claims about missing forward P/E.
                        # Handle markdown bold (**Not disclosed**) and plain variants.
                        item = _re2.sub(
                            r'(?i)(the\s+)?forward\s+p/?e\s+(ratio\s+)?is\s+\*{0,2}(not\s+(provided|disclosed|available|calculable|assessable|computable))\*{0,2}[^.]*\.',
                            pe_fact,
                            item,
                        )
                        item = _re2.sub(
                            r'(?i)(the\s+)?forward\s+p/?e\s+(ratio\s+)?cannot\s+be\s+(computed|calculated|assessed|determined)[^.]*\.',
                            pe_fact,
                            item,
                        )
                        # Also catch "The forward P/E ratio is not provided" with any formatting
                        item = _re2.sub(
                            r'(?i)the\s+forward\s+p/?e\s+(?:ratio\s+)?(?:is\s+)?\*{0,2}not\s+(provided|disclosed|available)\*{0,2}[^.]*\.',
                            pe_fact,
                            item,
                        )
                        # Only inject pe_fact if NO item in the entire analysis has it,
                        # and only into the first non-empty item, and only if the
                        # item doesn't already have it (regex may have fixed it above).
                        if not _any_has_pe and i == _first_nonempty_idx and pe_fact not in item:
                            item = pe_fact + " " + item
                        analysis_items[i] = item
                    # Also append the validated source note
                    pe_note = f"[Source: yfinance forwardPE = {pe_val}]"
                    if analysis_items:
                        analysis_items[-1] = analysis_items[-1] + "\n\n" + pe_note
        sections.append(
            RenderedSection(
                key=section.key,
                title=section.title,
                question=section.question,
                table=table,
                analysis=analysis_items,
                summary_label=section.summary_label,
                summary=_summary(report_language, ticker_clean, section.key, metrics),
            )
        )

    investor_relations_url = _metric_url(
        metrics,
        "investor_relations_url",
        "investors_url",
        "ir_url",
    )
    # 🔴 Fix: normalize known outdated / broken IR URLs to current official ones
    _IR_URL_FIXUPS = {
        # NVIDIA moved from phx.corporate-ir.net to investor.nvidia.com
        "phx.corporate-ir.net": "https://investor.nvidia.com",
    }
    if investor_relations_url:
        from urllib.parse import urlparse as _urlparse_ir
        try:
            domain_ir = _urlparse_ir(investor_relations_url).netloc
            for old_domain, new_url in _IR_URL_FIXUPS.items():
                if old_domain in domain_ir:
                    investor_relations_url = new_url
                    break
        except Exception:
            pass
    company_website_url = _metric_url(metrics, "company_website", "website", "weburl", "official_website")
    transcript_source = _metric_text(metrics, "transcript_source", "transcript_provider") or "Transcript"
    # Normalize: if source is a search engine, discovery tool, or the generic default, extract the real domain from URL
    if transcript_url and (
        transcript_source == "Transcript"
        or any(x in transcript_source.lower() for x in ("duckduckgo", "web search", "google", "bing"))
    ):
        from urllib.parse import urlparse
        try:
            domain = urlparse(transcript_url).netloc.replace("www.", "")
            # Map common domains to human-readable names
            DOMAIN_NAMES = {
                "fool.com": "Motley Fool",
                "seekingalpha.com": "Seeking Alpha",
                "finance.yahoo.com": "Yahoo Finance",
                "reuters.com": "Reuters",
                "bloomberg.com": "Bloomberg",
                "cnbc.com": "CNBC",
            }
            transcript_source = DOMAIN_NAMES.get(domain, domain.split(".")[0].title())
        except Exception:
            pass
    # Build transcript source entry — use the real source name and URL.
    # If no transcript was actually obtained, omit this source row entirely.
    sources = []
    source_counter = 1
    def _next_sid() -> str:
        nonlocal source_counter
        sid = f"S{source_counter}"
        source_counter += 1
        return sid
    if transcript_url or transcript_source not in ("Transcript", ""):
        transcript_label = f"Earnings Transcript — {transcript_source}"
        transcript_display_url = transcript_url or ""
        sources.append(SourceRef(
            source_id=_next_sid(),
            source_type="seeking_alpha",
            label=transcript_label,
            url=transcript_display_url,
            note="Primary earnings transcript source" if transcript_display_url else MISSING,
        ))
    sources.append(SourceRef(
        source_id=_next_sid(),
        source_type="ir_page",
        label="Official Investor Relations",
        url=investor_relations_url,
        note="Press release / earnings presentation source" if investor_relations_url else MISSING,
    ))
    if company_website_url and company_website_url != investor_relations_url:
        sources.append(SourceRef(
            source_id=_next_sid(), source_type="ir_page",
            label="Official Website", url=company_website_url))
    press_release_url = _metric_url(metrics, "press_release_url")
    if press_release_url:
        sources.append(SourceRef(
            source_id=_next_sid(), source_type="press_release",
            label="Press Release", url=press_release_url))
    presentation_url = _metric_url(metrics, "earnings_presentation_url", "presentation_url")
    if presentation_url:
        sources.append(SourceRef(
            source_id=_next_sid(), source_type="press_release",
            label="Earnings Call Presentation", url=presentation_url))

    # --- Data Sources (always relevant) ---
    sources.append(SourceRef(
        source_id=_next_sid(), source_type="yfinance",
        label="Financial Data",
        url=f"https://finance.yahoo.com/quote/{ticker_clean}",
        note="Price, estimates, and key metrics via yfinance"
    ))
    sources.append(SourceRef(
        source_id=_next_sid(), source_type="sec_edgar",
        label="SEC EDGAR Filings",
        url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker_clean}",
        note="10-K, 10-Q, and 8-K filings — primary data source"
    ))
    finnhub_api_key = os.environ.get("FINNHUB_API_KEY", "")
    if finnhub_api_key:
        sources.append(SourceRef(
            source_id=_next_sid(), source_type="finnhub",
            label="Finnhub",
            url="https://finnhub.io",
            note="Real-time estimates, transcripts, and SEC filings index"
        ))
    # Only add generic Seeking Alpha reference if we don't already have a specific transcript source
    if not transcript_url:
        sources.append(SourceRef(
            source_id=_next_sid(), source_type="seeking_alpha",
            label="Seeking Alpha Transcripts",
            url=f"https://seekingalpha.com/symbol/{ticker_clean}/earnings/transcripts",
            note="Earnings call transcripts (when available)"
        ))

    # Filter: skip Geographic Segments (never reported in quarterly filings)
    # and any truly empty sections
    def _skip_section(section) -> bool:
        if section.key == "Geographic Segments":
            return True
        rows = getattr(section.table, 'rows', [])
        if len(rows) == 0:
            return True
        if len(rows) == 1:
            cells = getattr(rows[0], 'cells', [])
            if all(str(c).strip() in ('', '-', '\u2014', 'No backlog', 'Not available', 'N/A')
                   for c in cells):
                return True
        return False

    next_earnings_date = _metric_text(metrics, "next_earnings_date")
    earnings_audio = _metric_url(metrics, "earnings_audio_url")

    # ── Chart data for PDF rendering ──
    chart_data = _build_chart_data(metrics, scoring)

    # ── Build claim→source traceability ──
    claim_sources = _build_claim_sources(sections, sources, metrics, ticker_clean)

    # ── V2.7 structured section models ──
    v27 = _build_v27_models(
        ticker=ticker_clean,
        company=company_name,
        quarter=quarter,
        metrics=metrics,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        company_overview=company_overview,
        scoring=scoring,
        sources=sources,
        next_earnings_date=next_earnings_date,
        yf_info=yf_info,
    )

    # ── Convert company_overview dict to CompanyOverview model ──
    co_model: CompanyOverview | None = None
    if company_overview:
        try:
            co_model = CompanyOverview(**company_overview)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"CompanyOverview model conversion failed for {ticker_clean}: {exc}")
            co_model = None

    return EarningsDeepDiveReport(
        ticker=ticker_clean,
        company=company_name,
        quarter=_resolved_quarter_label(quarter, metrics),
        language=report_language,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        title=f"{company_name} ({ticker_clean}) - Earnings Deep-Dive ({_resolved_quarter_label(quarter, metrics)})",
        sections=[s for s in sections if not _skip_section(s)],
        sources=sources,
        claim_sources=claim_sources,
        next_earnings_date=next_earnings_date,
        earnings_audio_url=earnings_audio,
        charts=chart_data,
        company_overview=co_model,
        # V2.7 structured section models
        executive_snapshot=v27["executive_snapshot"],
        financial_metrics=v27["financial_metrics"],
        valuation=v27["valuation"],
        valuation_context=v27["valuation_context"],
        peer_benchmark=v27["peer_benchmark"],
        data_quality=v27["data_quality"],
    )


# ── V2.7 Structured Section Model Builder ──────────────────────────────────


def _build_v27_models(
    *,
    ticker: str,
    company: str,
    quarter: str,
    metrics: FinancialMetrics,
    generated_at: str,
    company_overview: dict | None,
    scoring: Optional['Scoring'] = None,
    sources: list[SourceRef] | None = None,
    next_earnings_date: str | None = None,
    yf_info: dict | None = None,
) -> dict:
    """Build the 6 V2.7 structured section models from available data.

    Each model is optional — the PDF renderer gracefully handles None.
    Data sources:
    - ExecutiveSnapshot: company_overview + scoring + metrics
    - FinancialMetrics: old schemas.FinancialMetrics → V2.7 format
    - ValuationSection: PE, PEG, PS, PB, EV/EBITDA, FCF yield, dividend yield
    - ValuationContextSection: pending V2.4 endpoint integration
    - PeerBenchmarkSection: live V2.5 peer benchmark engine + curated universe
    - DataQualitySection: pending source freshness tracking
    """
    # ── Helpers ──
    def _fmt_usd(val: float | None) -> str | None:
        if val is None:
            return None
        try:
            v = float(val)
            abs_v = abs(v)
            if abs_v >= 1e12:
                return f"${v/1e12:,.2f}T"
            if abs_v >= 1e9:
                return f"${v/1e9:,.2f}B"
            if abs_v >= 1e6:
                return f"${v/1e6:,.2f}M"
            if abs_v >= 1e3:
                return f"${v/1e3:,.2f}K"
            return f"${v:,.2f}"
        except (TypeError, ValueError):
            return None

    def _fmt_pct(val: float | None) -> str | None:
        if val is None:
            return None
        try:
            # If val looks like an already-scaled percentage (e.g. 15.5 for 15.5%)
            if abs(float(val)) > 1:
                return f"{float(val):.1f}%"
            # Decimal form (0.155 for 15.5%)
            return f"{float(val)*100:.1f}%"
        except (TypeError, ValueError):
            return None

    def _mf(key: str) -> float | None:
        """Extract a float from the old metrics object (dict-like access)."""
        try:
            v = metrics.model_dump().get(key)
            if v is None or v == "Not disclosed" or v == "":
                return None
            return float(v)
        except (TypeError, ValueError):
            return None

    def _ms(key: str) -> str | None:
        """Extract a string from the old metrics object."""
        try:
            v = metrics.model_dump().get(key)
            if v is None or v == "":
                return None
            return str(v)
        except Exception:
            return None

    # ── 1. ExecutiveSnapshot ───────────────────────────────────────────────
    es = ExecutiveSnapshot(
        ticker=ticker,
        company_name=company,
        quarter=_resolved_quarter_label(quarter, metrics),
        generated_at=generated_at,
        next_earnings_date=next_earnings_date,
    )

    if company_overview:
        kf = company_overview.get("key_financials", {})
        cp = company_overview.get("company_profile", {})
        es.market_cap = _safe_float_ov(kf.get("market_cap"))
        es.market_cap_display = kf.get("market_cap_display")
        es.sector = cp.get("sector")
        es.industry = cp.get("industry")

    if scoring:
        try:
            es.verdict = scoring.decision() if callable(getattr(scoring, 'decision', None)) else str(getattr(scoring, 'verdict', '')) or None
        except Exception:
            pass
        es.decision_score = getattr(scoring, 'total', None)

    # ── 2. FinancialMetrics (V2.7) ─────────────────────────────────────────
    rev_actual = _mf("revenue_actual")
    rev_estimate = _mf("revenue_estimate")
    rev_beat = None
    rev_beat_display = None
    if rev_actual is not None and rev_estimate is not None and rev_estimate != 0:
        rev_beat = ((rev_actual - rev_estimate) / abs(rev_estimate)) * 100
        rev_beat_display = f"{rev_beat:+.1f}%"

    eps_actual = _mf("eps_actual")
    eps_beat = _mf("eps_vs_estimate")

    fm = V27FinancialMetrics(
        eps_actual=eps_actual,
        eps_actual_display=f"${eps_actual:,.2f}" if eps_actual is not None else None,
        eps_estimate=_mf("eps_estimate"),
        eps_estimate_display=_fmt_usd(_mf("eps_estimate")),
        eps_beat_pct=eps_beat,
        eps_beat_pct_display=_fmt_pct(eps_beat),
        revenue_actual=rev_actual,
        revenue_actual_display=_fmt_usd(rev_actual),
        revenue_estimate=rev_estimate,
        revenue_estimate_display=_fmt_usd(rev_estimate),
        revenue_beat_pct=rev_beat,
        revenue_beat_pct_display=rev_beat_display,
        gross_margin=_mf("gross_margin"),
        gross_margin_display=_fmt_pct(_mf("gross_margin")),
        operating_margin=_mf("operating_margin"),
        operating_margin_display=_fmt_pct(_mf("operating_margin")),
        net_margin=_mf("net_margin"),
        net_margin_display=_fmt_pct(_mf("net_margin")),
        revenue_growth_yoy=_mf("revenue_yoy"),
        revenue_growth_yoy_display=_fmt_pct(_mf("revenue_yoy")),
        eps_growth_yoy=_mf("eps_yoy"),
        eps_growth_yoy_display=_fmt_pct(_mf("eps_yoy")),
        fcf=_mf("free_cash_flow"),
        fcf_display=_fmt_usd(_mf("free_cash_flow")),
        sources=list(sources) if sources else [],
    )

    # ── 3. ValuationSection ────────────────────────────────────────────────
    pe_fwd = _mf("pe_forward")
    pe_ttm = _mf("pe_trailing")

    vs = ValuationSection(
        pe_trailing=pe_ttm,
        pe_trailing_display=f"{pe_ttm:.1f}x" if pe_ttm is not None else None,
        pe_forward=pe_fwd,
        pe_forward_display=f"{pe_fwd:.1f}x" if pe_fwd is not None else None,
        generated_at=generated_at,
    )

    # ── 4–6. Remaining sections (pending endpoint integration) ─────────────
    vc = _build_valuation_context(
        yf_info=yf_info, metrics=metrics, generated_at=generated_at,
    )
    pb = _build_peer_benchmark(
        ticker=ticker, yf_info=yf_info, metrics=metrics, generated_at=generated_at,
    )
    dq = DataQualitySection(generated_at=generated_at)  # timestamp only

    return {
        "executive_snapshot": es,
        "financial_metrics": fm,
        "valuation": vs,
        "valuation_context": vc,
        "peer_benchmark": pb,
        "data_quality": dq,
    }


def _build_valuation_context(
    *,
    yf_info: dict | None,
    metrics: FinancialMetrics | None,
    generated_at: str,
) -> ValuationContextSection:
    """Build ValuationContextSection from yfinance info dict + FinancialMetrics.

    Extracts 5 context signals (PEG, P/S, EV/EBITDA, P/FCF, FCF Yield) plus
    a narrative valuation_support summary.  All signals are nullable — the PDF
    renderer gracefully skips None rows.
    """
    vc = ValuationContextSection(
        generated_at=generated_at,
        currency="USD",
    )

    if not yf_info:
        return vc

    def _f(key: str) -> float | None:
        v = yf_info.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _label_peg(peg: float) -> str:
        if peg < 0:
            return "Negative Earnings"
        if peg < 1.0:
            return "Attractive (<1x)"
        if peg <= 2.0:
            return "Fair (1-2x)"
        return "Expensive (>2x)"

    def _label_vs_growth(ratio: float, growth_key: str = "revenueGrowth") -> str:
        """Heuristic: compare valuation ratio to growth rate."""
        growth = _f(growth_key)
        if growth is None:
            # Try earningsGrowth as fallback
            growth = _f("earningsGrowth")
        if growth is None or growth <= 0:
            return "N/A (no growth data)"
        # Ratio relative to growth: ratio/growth < 0.5 → attractive, > 1.5 → expensive
        ratio_to_growth = ratio / (growth * 100) if growth > 0 else float('inf')
        if ratio_to_growth < 0.5:
            return "Attractive vs Growth"
        if ratio_to_growth <= 1.0:
            return "Moderate vs Growth"
        if ratio_to_growth <= 1.5:
            return "Fair vs Growth"
        return "Expensive vs Growth"

    def _label_fcf_yield(pct: float) -> str:
        if pct >= 8.0:
            return "Strong (≥8%)"
        if pct >= 4.0:
            return "Moderate (4-8%)"
        if pct >= 2.0:
            return "Low (2-4%)"
        if pct > 0:
            return "Very Low (<2%)"
        return "Negative FCF"

    # ── 1. PEG Signal ────────────────────────────────────────────────
    peg = _f("pegRatio")
    if peg is not None:
        vc.peg_signal = peg
        vc.peg_signal_label = _label_peg(peg)
        # Build detail: "PEG X.XX = P/E XX.X / growth XX%"
        pe_ttm = _f("trailingPE")
        growth = _f("earningsGrowth") or _f("revenueGrowth")
        if pe_ttm and growth:
            vc.peg_signal_detail = f"P/E {pe_ttm:.1f}x / growth {growth*100:.0f}%"
        elif pe_ttm:
            vc.peg_signal_detail = f"P/E {pe_ttm:.1f}x"

    # ── 2. P/S vs Growth ─────────────────────────────────────────────
    ps = _f("priceToSalesTrailing12Months")
    if ps is not None:
        vc.ps_vs_growth_signal = ps
        vc.ps_vs_growth_label = _label_vs_growth(ps)

    # ── 3. EV/EBITDA vs Growth ───────────────────────────────────────
    ev_ebitda = _f("enterpriseToEbitda")
    if ev_ebitda is not None:
        vc.ev_ebitda_vs_growth_signal = ev_ebitda
        vc.ev_ebitda_vs_growth_label = _label_vs_growth(ev_ebitda)

    # ── 4. P/FCF vs Growth ───────────────────────────────────────────
    mcap = _f("marketCap")
    fcf = _f("freeCashflow")
    if mcap and fcf and mcap > 0 and fcf > 0:
        pfcf = mcap / fcf
        vc.pfcf_vs_growth_signal = pfcf
        vc.pfcf_vs_growth_label = _label_vs_growth(pfcf)

    # ── 5. FCF Yield ─────────────────────────────────────────────────
    if mcap and fcf and mcap > 0:
        fcf_yield_pct = (fcf / mcap) * 100
        vc.fcf_yield_signal = round(fcf_yield_pct, 2)
        vc.fcf_yield_label = _label_fcf_yield(fcf_yield_pct)

    # ── 6. Valuation Support Narrative ───────────────────────────────
    signals_present = sum(1 for s in [
        vc.peg_signal, vc.ps_vs_growth_signal,
        vc.ev_ebitda_vs_growth_signal, vc.pfcf_vs_growth_signal,
    ] if s is not None)

    if signals_present >= 3:
        # Build a concise narrative from the signals
        parts = []
        if vc.peg_signal is not None:
            parts.append(f"PEG {vc.peg_signal:.1f} ({vc.peg_signal_label})")
        if vc.fcf_yield_signal is not None:
            parts.append(f"FCF Yield {vc.fcf_yield_signal:.1f}%")
        vc.valuation_support = "; ".join(parts) if parts else None

        # Context summary: one-line synthesis
        attractive_count = sum(1 for label in [
            vc.peg_signal_label, vc.ps_vs_growth_label,
            vc.ev_ebitda_vs_growth_label, vc.pfcf_vs_growth_label,
        ] if label and "Attractive" in str(label))
        expensive_count = sum(1 for label in [
            vc.peg_signal_label, vc.ps_vs_growth_label,
            vc.ev_ebitda_vs_growth_label, vc.pfcf_vs_growth_label,
        ] if label and "Expensive" in str(label))

        if attractive_count > expensive_count:
            vc.context_summary = f"{attractive_count}/{signals_present} signals attractive — valuation has support at current levels"
        elif expensive_count > attractive_count:
            vc.context_summary = f"{expensive_count}/{signals_present} signals expensive — valuation demands high growth delivery"
        else:
            vc.context_summary = "Mixed valuation signals — no clear tilt"

    return vc


# ═══════════════════════════════════════════════════════════════════
#  V2.7 T5 — Peer Benchmark builder
# ═══════════════════════════════════════════════════════════════════


def _safe_f(val: Any) -> float | None:
    """Safe float conversion — NaN/inf tolerant."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _extract_peer_subject_metrics(
    yf_info: dict,
    _metrics: FinancialMetrics | None,  # unused for now; reserved for quality
) -> dict[str, float]:
    """Extract valuation multiples from yf_info for the subject ticker.

    Returns only non-None values so buildPeerBenchmarkSummary has clean input.
    """
    result: dict[str, float] = {}
    for metric_name, yf_key in [
        ("pe_ttm", "trailingPE"),
        ("pe_forward", "forwardPE"),
        ("peg_ratio", "pegRatio"),
        ("ps_ttm", "priceToSalesTrailing12Months"),
        ("pb_ratio", "priceToBook"),
        ("ev_ebitda", "enterpriseToEbitda"),
        ("total_debt", "totalDebt"),
    ]:
        v = _safe_f(yf_info.get(yf_key))
        if v is not None:
            result[metric_name] = v
    return result


def _extract_peer_valuation_metrics_from_batch(
    batch: dict,
) -> dict[str, dict[str, float]]:
    """Extract valuation multiples from the peer batch snapshot.

    Returns: {TICKER: {metric_name: value}} — non-None values only.
    Mirrors the extraction logic in routes/peer_benchmark.py.
    """
    result: dict[str, dict[str, float]] = {}

    for peer_ticker, peer_data in batch.get("peers", {}).items():
        m: dict[str, float] = {}

        # ── Market snapshot fields ──
        if "market" in peer_data:
            market = peer_data["market"]
            for key in ("pe_ttm", "ps_ttm", "pb_ratio"):
                v = _safe_f(market.get(key))
                if v is not None:
                    m[key] = v

        # ── Valuation fields ──
        if "valuation" in peer_data:
            valn = peer_data["valuation"]
            # pe_current overrides market pe_ttm when available
            pe_cur = _safe_f(valn.get("pe_current"))
            if pe_cur is not None:
                m["pe_ttm"] = pe_cur
            pe_fwd = _safe_f(valn.get("pe_forward"))
            if pe_fwd is not None:
                m["pe_forward"] = pe_fwd
            peg = _safe_f(valn.get("peg_ratio"))
            if peg is not None:
                m["peg_ratio"] = peg
            td = _safe_f(valn.get("total_debt"))
            if td is not None:
                m["total_debt"] = td

        if m:
            result[peer_ticker] = m

    return result


def _compute_peer_labels(
    benchmarks: dict,
) -> dict[str, str | None]:
    """Aggregate benchmark results into 3 category labels + summary.

    Returns:
        {val_label, val_detail, growth_label, growth_detail,
         qual_label, qual_detail, summary}
    """
    valuation_set = {"pe_ttm", "ps_ttm", "pb_ratio", "ev_ebitda",
                     "pe_forward", "peg_ratio"}
    growth_set = {"eps_growth", "revenue_growth", "ebitda_growth", "fcf_growth"}
    quality_set = {"gross_margin", "operating_margin", "net_margin",
                   "roic", "roe", "roa", "fcf_yield",
                   "debt_to_equity", "total_debt"}

    def _categorize(metric_set: set, label: str) -> tuple[str | None, str | None]:
        relevant = {k: v for k, v in benchmarks.items()
                    if k in metric_set and v.get("status") == "available"}
        if not relevant:
            return (f"No {label} peer data", None)

        above = sum(1 for b in relevant.values()
                    if "Above" in str(b.get("label", "")))
        below = sum(1 for b in relevant.values()
                    if "Below" in str(b.get("label", "")))
        total = len(relevant)

        # Build per-metric detail string (labels are self-describing)
        detail_parts = []
        for k, b in sorted(relevant.items()):
            lbl = b.get("label", "N/A")
            detail_parts.append(lbl)
        detail = "; ".join(detail_parts) if detail_parts else None

        if above > below:
            return (f"Above Peer Median ({above}/{total})", detail)
        elif below > above:
            return (f"Below Peer Median ({below}/{total})", detail)
        else:
            return (f"In Line with Peers", detail)

    val_label, val_detail = _categorize(valuation_set, "Valuation")
    growth_label, growth_detail = _categorize(growth_set, "Growth")
    qual_label, qual_detail = _categorize(quality_set, "Quality")

    # ── One-line summary ──
    available = sum(1 for b in benchmarks.values()
                    if b.get("status") == "available")
    parts = []
    if val_label:
        parts.append(f"Valuation: {val_label}")
    if growth_label and "No " not in str(growth_label):
        parts.append(f"Growth: {growth_label}")
    summary = (f"Benchmark across {available} metrics vs peer group. "
               + ". ".join(parts)) if (parts and available > 0) else None

    return {
        "val_label": val_label,
        "val_detail": val_detail,
        "growth_label": growth_label,
        "growth_detail": growth_detail,
        "qual_label": qual_label,
        "qual_detail": qual_detail,
        "summary": summary,
    }


def _build_peer_benchmark(
    *,
    ticker: str,
    yf_info: dict | None,
    metrics: FinancialMetrics | None,
    generated_at: str,
) -> PeerBenchmarkSection:
    """Build PeerBenchmarkSection from V2.5 peer benchmark infrastructure.

    Calls the curated peer universe + pure-function benchmark engine to
    compute relative valuation, growth, and quality labels vs the peer group.
    Gracefully handles missing data — returns an empty-but-valid section on
    any failure (peer universe unavailable, network error, insufficient peers).
    """
    import logging
    logger = logging.getLogger(__name__)

    pb = PeerBenchmarkSection(currency="USD", generated_at=generated_at)

    if not yf_info:
        return pb

    try:
        from backend.peer_batch import get_peer_benchmark_snapshot
        from backend.peer_universe import get_peers
        from backend.peer_benchmark import buildPeerBenchmarkSummary

        # 1. Peer universe
        peer_info = get_peers(ticker)
        if peer_info.get("status") == "unavailable":
            return pb

        pb.peer_group = peer_info.get("group_label")
        pb.peer_tickers = list(peer_info.get("peers", []))

        # 2. Batch snapshot (5-min in-memory cache)
        batch = get_peer_benchmark_snapshot(ticker)
        if batch.get("status") in ("unavailable", "error"):
            return pb
        if batch.get("sample_size", 0) < 2:
            return pb

        # 3. Subject + peer metrics
        subject = _extract_peer_subject_metrics(yf_info, metrics)
        peers = _extract_peer_valuation_metrics_from_batch(batch)

        if not subject or len(peers) < 2:
            return pb

        # Keep only metrics present in both subject AND at least 1 peer
        common = {k for k in subject if any(k in p for p in peers.values())}
        if len(common) < 2:
            return pb
        subject_filtered = {k: subject[k] for k in common}

        # 4. Pure-function benchmark engine
        result = buildPeerBenchmarkSummary(ticker, subject_filtered, peers)
        benchmarks = result.get("benchmarks", {})

        # 5. Category labels + summary
        labels = _compute_peer_labels(benchmarks)
        pb.relative_valuation_label = labels["val_label"]
        pb.relative_valuation_detail = labels["val_detail"]
        pb.relative_growth_label = labels["growth_label"]
        pb.relative_growth_detail = labels["growth_detail"]
        pb.relative_quality_label = labels["qual_label"]
        pb.relative_quality_detail = labels["qual_detail"]
        pb.benchmark_summary = labels["summary"]

    except Exception:
        logger.exception("_build_peer_benchmark failed for %s", ticker)

    return pb


def _safe_float_ov(val: Any) -> float | None:
    """Safely convert a value from company_overview dict to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _build_chart_data(metrics: Any, scoring: Optional['Scoring'] = None) -> ChartData | None:
    """Extract pre-computed chart data from FinancialMetrics and optional Scoring."""
    try:
        raw = metrics.model_dump() if hasattr(metrics, 'model_dump') else {}
    except Exception:
        return None

    def _get(key: str):
        val = raw.get(key)
        if val is None or val == "Not disclosed" or val == "":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    eps_actual = _get("eps_actual")
    eps_estimate = _get("eps_estimate")
    eps_vs_pct = None
    if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
        eps_vs_pct = (eps_actual - eps_estimate) / abs(eps_estimate)

    rev_actual = _get("revenue_actual")
    rev_estimate = _get("revenue_estimate")
    rev_vs_pct = None
    if rev_actual is not None and rev_estimate is not None and rev_estimate != 0:
        rev_vs_pct = (rev_actual - rev_estimate) / abs(rev_estimate)

    gross_margin = _get("gross_margin")
    operating_margin = _get("operating_margin")
    pe_forward = _get("pe_forward")
    fcf = _get("free_cash_flow")
    roic = _get("roic")
    sector = raw.get("sector")
    industry = raw.get("industry")

    # ── Scoring fields from canonical Scoring model ──
    scoring_financial_health: float | None = None
    scoring_growth: float | None = None
    scoring_valuation: float | None = None
    scoring_management: float | None = None
    scoring_moat: float | None = None
    scoring_sentiment: float | None = None
    scoring_total: int | None = None
    scoring_decision: str | None = None

    if scoring is not None:
        scoring_financial_health = float(scoring.financial_health)
        scoring_growth = float(scoring.growth)
        scoring_valuation = float(scoring.valuation)
        scoring_management = float(scoring.management)
        scoring_moat = float(scoring.moat)
        scoring_sentiment = float(scoring.sentiment)
        scoring_total = scoring.total
        scoring_decision = scoring.decision()

    return ChartData(
        eps_actual=eps_actual,
        eps_estimate=eps_estimate,
        eps_vs_pct=eps_vs_pct,
        revenue_actual=rev_actual,
        revenue_estimate=rev_estimate,
        revenue_vs_pct=rev_vs_pct,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        pe_forward=pe_forward,
        fcf=fcf,
        roic=roic,
        sector=sector,
        industry=industry,
        scoring_financial_health=scoring_financial_health,
        scoring_growth=scoring_growth,
        scoring_valuation=scoring_valuation,
        scoring_management=scoring_management,
        scoring_moat=scoring_moat,
        scoring_sentiment=scoring_sentiment,
        scoring_total=scoring_total,
        scoring_decision=scoring_decision,
    )


def _build_claim_sources(
    sections: list[RenderedSection],
    sources: list[SourceRef],
    metrics: Any,
    ticker: str,
) -> list[ClaimSource]:
    """Build claim→source traceability from section data and source bibliography.

    For each section with a populated table, create ClaimSource entries linking
    key financial figures back to their data sources. This is deterministic
    table provenance — LLM prose claims are out of scope for V1.
    """
    claim_sources: list[ClaimSource] = []
    claim_counter = 1
    # Build lookup tables from the source bibliography
    sid_to_source = {s.source_id: s for s in sources if s.source_id}
    type_to_sid = {}
    for s in sources:
        if s.source_type and s.source_id:
            # Keep the FIRST source_id for each type (avoid overwriting)
            type_to_sid.setdefault(s.source_type, s.source_id)

    # Map section keys to their primary source types
    SECTION_SOURCE_MAP = {
        "EPS & Revenue": "yfinance",
        "Operating Metrics": "sec_edgar",
        "Cash Flow": "sec_edgar",
        "Capital Efficiency": "sec_edgar",
        "Forward P/E": "yfinance",
        "Guidance": "yfinance",
        "Backlog": "sec_edgar",
        "Segments": "sec_edgar",
        "Margins": "sec_edgar",
        "Risks": "sec_edgar",  # sourced from filing narrative
        "Verdict": "sec_edgar",  # synthesis — no single source
    }

    for section in sections:
        sk = section.key
        source_type = SECTION_SOURCE_MAP.get(sk, "sec_edgar")
        sid = type_to_sid.get(source_type, "S?")
        source_ref = sid_to_source.get(sid)

        # Generate claim entries for each table row with concrete data
        for row in section.table.rows:
            if not row.cells or len(row.cells) < 2:
                continue
            # Skip placeholder rows — check ALL cells, not just the label
            skip_row = False
            for cell in row.cells:
                if any(marker in str(cell) for marker in ("N/A", "Not available", "Not disclosed", "Not calculable")):
                    skip_row = True
                    break
            if skip_row:
                continue

            # Determine grounding level
            grounding: str = "direct_metric"
            confidence: str | None = "high"
            if sk in ("Verdict", "Risks", "Highlights"):
                grounding = "inference"
                confidence = "low"
            elif sk == "Guidance":
                grounding = "inference"  # guidance is inherently forward-looking
                confidence = "medium"
            elif sk == "Segments":
                # Segments may be LLM-parsed — lower confidence
                confidence = "medium"

            claim_id = f"{sk[:3].upper()}-{claim_counter:03d}"
            claim_counter += 1

            # Build claim_text from the row label + first cell value
            row_label = row.label or ""
            cell_val = row.cells[0] if len(row.cells) > 0 else ""
            claim_text_val = f"{row_label}: {cell_val}" if row_label and cell_val else None

            claim_sources.append(ClaimSource(
                claim_id=claim_id,
                section=sk,
                claim_text=claim_text_val,
                source_type=source_type,
                source_name=source_ref.label if source_ref else source_type,
                source_id=sid,
                source_url=source_ref.url if source_ref else None,
                source_field=row.source_field or row.label.lower().replace(" ", "_"),
                source_value=cell_val if cell_val else None,
                grounding=grounding,  # type: ignore
                confidence=confidence,
            ))

    return claim_sources
