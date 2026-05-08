"""Map sourced earnings metrics into the structured PDF render model."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from backend.earnings_deep_dive.report_model import (
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    SourceRef,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.template import TemplateLanguage, get_earnings_template


MISSING = "データ未取得"
MISSING_EN = "Not available"
NOT_DISCLOSED = "開示なし"
NOT_DISCLOSED_EN = "Not disclosed"
NOT_APPLICABLE = "該当なし"
NOT_APPLICABLE_EN = "N/A"
NOT_CALCULABLE = "計算不可"
NOT_CALCULABLE_EN = "Not calculable"
SOURCE_COMPANY = "Company filing / Calculated"
SOURCE_YFINANCE = "yfinance quarterly"

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
    return "jp" if value in ("jp", "ja") else "en"


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


def _source(*values: Any) -> str:
    return SOURCE_COMPANY if any(_has(value) for value in values) else MISSING_EN


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
    """Format a YoY percentage value that is already in percentage points (e.g., -4.4, 9.5)."""
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


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
    return "\n".join(kept).strip()


def _extract_segment_rows(metrics: FinancialMetrics, labels: tuple[str, ...]) -> list[list[str]]:
    rows: list[list[str]] = []
    segments = metrics.segments if isinstance(metrics.segments, dict) else {}
    segment_items = list(segments.items())[: len(labels)]

    for index, row_label in enumerate(labels):
        if index >= len(segment_items):
            rows.append([row_label, MISSING, MISSING, MISSING, MISSING])
            continue

        name, raw = segment_items[index]
        data = raw if isinstance(raw, dict) else {}
        revenue = data.get("revenue") if isinstance(data, dict) else None
        yoy = data.get("yoy") if isinstance(data, dict) else None
        # Compute YoY from revenue and prior year if not explicitly provided
        if not _has(yoy) and revenue is not None and isinstance(data, dict):
            prior = data.get("revenue_q_prior_year")
            if prior and revenue:
                try:
                    yoy = ((float(revenue) - float(prior)) / float(prior)) * 100
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
        driver = data.get("driver") if isinstance(data, dict) else None
        rows.append([
            str(name) if name else row_label,
            _money(revenue),
            _pct(yoy),
            str(driver) if _has(driver) else "Segment revenue contribution",
            _source(raw),
        ])
    return rows


def _rows_for_section(section_key: str, row_labels: tuple[str, ...], metrics: FinancialMetrics) -> list[list[str]]:
    if section_key == "EPS & Revenue":
        return [
            [
                row_labels[0],
                _eps(metrics.eps_estimate),
                _eps(metrics.eps_actual),
                _variance(metrics.eps_actual, metrics.eps_estimate, getattr(metrics, "eps_vs_estimate", None)),
                _yoy_pct(getattr(metrics, "eps_yoy", None)),
                _source(metrics.eps_estimate, metrics.eps_actual, getattr(metrics, "eps_vs_estimate", None), getattr(metrics, "eps_yoy", None)),
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
                row_labels[0],
                _money(metrics.gross_profit),
                _money(getattr(metrics, "gross_profit_prior_year", None)),
                _yoy_pct(getattr(metrics, "gross_profit_yoy", None)),
                metrics.gross_profit,
            ),
            (
                row_labels[1],
                _pct(metrics.gross_margin),
                _pct(getattr(metrics, "gross_margin_prior_year", None)),
                _yoy_pct(getattr(metrics, "gross_margin_yoy", None)),
                metrics.gross_margin,
            ),
            (
                row_labels[2],
                _money(metrics.opex),
                _money(getattr(metrics, "opex_prior_year", None)),
                _yoy_pct(getattr(metrics, "opex_yoy", None)),
                metrics.opex,
            ),
            (
                row_labels[3],
                _money(metrics.operating_income),
                _money(getattr(metrics, "operating_income_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_income_yoy", None)),
                metrics.operating_income,
            ),
            (
                row_labels[4],
                _pct(metrics.operating_margin),
                _pct(getattr(metrics, "operating_margin_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_margin_yoy", None)),
                metrics.operating_margin,
            ),
            (
                row_labels[5],
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
                quality,
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
        # If ALL metrics are unavailable (Finnhub free tier limitation), show 1 informative row
        if all(not _has(raw) for _, _, _, _, _, raw in rows):
            return [["Capital Efficiency metrics", "Finnhub free tier limit", MISSING, MISSING, MISSING, MISSING]]
        return result

    if section_key == "Segments":
        return _extract_segment_rows(metrics, row_labels)

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
        return [
            [row_labels[0], _multiple(metrics.pe_forward), _multiple(trailing_pe), "—", _source(metrics.pe_forward)],
            [row_labels[1], fwd_eps_display, _eps(getattr(metrics, "eps_estimate", None)), _yoy_pct(getattr(metrics, "eps_yoy", None)), _source(metrics.eps_estimate)],
        ]

    if section_key == "Backlog":
        backlog_value = _money(metrics.backlog) if _has(metrics.backlog) else NOT_APPLICABLE_EN
        backlog_source = _source(metrics.backlog) if _has(metrics.backlog) else "Company filing"
        return [
            [row_labels[0], backlog_value, "N/A" if not _has(metrics.backlog) else "—", "Not disclosed (company does not report backlog)" if not _has(metrics.backlog) else "—", backlog_source],
            [row_labels[1], NOT_DISCLOSED_EN if _has(metrics.backlog) else NOT_APPLICABLE_EN, "N/A", "Not disclosed", backlog_source],
        ]

    if section_key == "Guidance":
        guidance = metrics.guidance if _has(metrics.guidance) else MISSING_EN
        guidance_source = _source(metrics.guidance)
        rows = [
            [row_labels[0], guidance, "—", "Next quarter outlook", guidance_source],
            [row_labels[1], "Not guided", "N/A", "Margin guidance not provided", guidance_source],
            [row_labels[2], "Not guided", "N/A", "EPS guidance not provided", guidance_source],
        ]
        return [r for r in rows if r[1] != MISSING_EN] if len([r for r in rows if r[1] != MISSING_EN]) > 0 else rows[:1]

    if section_key == "Verdict":
        return _verdict_rows(metrics, row_labels)

    return [[label, *([MISSING] * 4)] for label in row_labels]


def _enrich_codex_table(
    codex_table: RenderedTable,
    section_key: str,
    section_rows: tuple[str, ...],
    metrics: FinancialMetrics,
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
    yf_rows = _rows_for_section(section_key, section_rows, metrics)
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
    _PURE_DASH_RE = _re.compile(r'^[—–\-\s]+$')  # Pure dashes
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
        return cell
    
    sanitized_rows: list[RenderedTableRow] = []
    for row in table.rows:
        new_cells = [_sanitize_cell(cell) for cell in row.cells]
        clean_label = _GARBAGE_RE.sub('—', _JP_GARBAGE_RE.sub('', row.label))
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
    if margin and margin != MISSING and not margin.startswith("データ"):
        risk_signal = f"Operating margin: {margin}"
    elif gross_margin and gross_margin != MISSING and not gross_margin.startswith("データ"):
        risk_signal = f"Gross margin: {gross_margin}"
    else:
        risk_signal = "Margin data not disclosed"
    try:
        margin_num = float(metrics.operating_margin) if metrics.operating_margin is not None else None
    except (TypeError, ValueError):
        margin_num = None
    risk_evidence = (
        f"Margin {margin}, {'below 15% threshold' if margin_num and margin_num < 15 else 'within healthy range'}"
        if margin_num is not None
        else f"PE Forward {pe}" if pe and pe != MISSING else "Watch valuation multiple"
    )
    risk_impact = (
        "Margin compression risk if costs rise faster than revenue"
        if margin_num is not None and margin_num < 15
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


def _verdict_rows(metrics: FinancialMetrics, row_labels: tuple[str, ...]) -> list[list[str]]:
    """Generate data-driven Verdict table from all available metrics."""
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
        if margin_num is not None and margin_num < 15
        else "Growth rate sustainability needs monitoring"
    )
    gd_assessment = (
        "Strong — revenue growth with margin support"
        if rev_yoy_num > 10 and (margin_num is None or margin_num >= 15)
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
    # Simple scoring: 0-5 scale
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

    return [
        [row_labels[0], eq_positive, eq_negative, eq_assessment, SOURCE_COMPANY],
        [row_labels[1], gd_positive, gd_negative, gd_assessment, SOURCE_COMPANY],
        [row_labels[2], val_positive, val_negative, val_assessment, SOURCE_COMPANY],
        [row_labels[3], f"Score: {score}/5", "See component assessments above", f"→ {verdict}", "Model + metrics"],
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
    if margin_num is not None and margin_num < 15: concerns.append("margin below 15%")
    if pe_num is not None and pe_num > 25: concerns.append("premium valuation")
    if rev_yoy_num <= 0: concerns.append("declining revenue")

    strength_str = ", ".join(strengths) if strengths else "no clear positives"
    concern_str = ", ".join(concerns) if concerns else "no major red flags"

    return (
        f"{evidence}\n\n"
        f"{ticker}'s Q shows {strength_str}. "
        f"Key watch items: {concern_str}. "
        f"Risk/reward is {'favorable' if verdict == 'BUY' else 'neutral' if verdict == 'HOLD' else 'unfavorable'} "
        f"at current levels → **{verdict}**."
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

    return (
        f"{ticker} 売上高{revenue}（{revenue_yoy}前年比）、EPS{eps_val}。"
        f"スコア{score}/5: {growth}、{cash}、バリュエーション{valuation}。"
        f"リスク: {risk_str}。→ **{verdict}**"
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
    fcf = _money(metrics.free_cash_flow)
    margin = _pct(metrics.operating_margin)
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
                    "⚠️ ローライト（懸念点）",
                    "",
                    "① 利益率の確認",
                    f"● 営業利益率: {margin}",
                    "👉 売上が伸びても利益率が弱い場合、株価評価は伸びにくくなります。",
                    "",
                    "② 未開示データ",
                    "● 未取得または未開示の項目は表で明示しています。",
                    "👉 空欄でごまかさず、次に確認すべき資料を明確にします。",
                    "",
                    "🧠 総合評価（Namiさん向け）",
                    "👉 まず売上、利益率、キャッシュの3点を見れば、この決算が本当に強いか判断しやすいです。",
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
                f"① Revenue signal: {revenue} with YoY growth of {revenue_yoy}.",
                f"● Free cash flow: {fcf}.",
                "👉 Investor read: focus on whether growth converts into durable cash and margin expansion.",
            ]
        )
    ]


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
        # Replace runs of 3+ question marks with "—"
        text = _GARBAGE_RE.sub('—', text)
        # Replace runs of 3+ JP/fullwidth chars (garbled leakage) with ""
        text = _JP_GARBAGE_RE.sub('', text)
        # Clean up resulting empty lines or double dashes
        text = _re.sub(r'\n\s*—\s*\n', '\n', text)
        return text

    sections: list[RenderedSection] = []
    
    # Sections where the LLM table is unreliable — use yfinance data directly.
    # The LLM analysis text is still used for prose below the table.
    _DATA_DRIVEN_SECTIONS = {
        "Operating Metrics", "Cash Flow", "Capital Efficiency",
        "Segments", "Guidance", "Backlog", "Verdict",
    }
    
    for section in template:
        analysis_text = analysis_by_key.get(section.key) or analysis_by_key.get(section.title)
        if analysis_text:
            analysis_text = _clean_prose(analysis_text)
        codex_table = _extract_markdown_table(analysis_text, section.table_columns) if analysis_text else None
        
        # For data-driven sections, ignore the LLM table and use yfinance rows directly.
        # The LLM prose is kept as analysis_items.
        if section.key in _DATA_DRIVEN_SECTIONS:
            rows = _rows_for_section(section.key, section.table_rows, metrics)
            table = RenderedTable(
                columns=list(section.table_columns),
                rows=[RenderedTableRow(
                    label=_GARBAGE_RE.sub('—', _JP_GARBAGE_RE.sub('', str(row[0]))),
                    cells=[str(cell) for cell in row[1:]],
                ) for row in rows],
            )
            table = _sanitize_table(table)
            analysis_items = [_analysis_without_table(analysis_text)] if analysis_text else []
        elif codex_table:
            table = _enrich_codex_table(codex_table, section.key, section.table_rows, metrics)
            table = _number_highlights_rows(table)
            table = _sanitize_table(table)
            analysis_items = [text for text in (_analysis_without_table(analysis_text),) if text]
        else:
            rows = _rows_for_section(section.key, section.table_rows, metrics)
            table = RenderedTable(
                columns=list(section.table_columns),
                rows=[RenderedTableRow(
                    label=_GARBAGE_RE.sub('—', _JP_GARBAGE_RE.sub('', str(row[0]))),
                    cells=[str(cell) for cell in row[1:]],
                ) for row in rows],
            )
            table = _sanitize_table(table)
            if analysis_text:
                analysis_items = [analysis_text]
            elif section.key == "Highlights":
                analysis_items = _default_highlights_analysis(report_language, metrics)
            else:
                analysis_items = []
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
    company_website_url = _metric_url(metrics, "company_website", "website", "weburl", "official_website")
    transcript_source = _metric_text(metrics, "transcript_source", "transcript_provider") or "Transcript"
    # Build transcript source entry — use the real source name and URL.
    # If no transcript was actually obtained, omit this source row entirely.
    sources = []
    if transcript_url or transcript_source not in ("Transcript", ""):
        transcript_label = f"Earnings Transcript — {transcript_source}"
        transcript_display_url = transcript_url or (
            f"https://seekingalpha.com/symbol/{ticker_clean}/earnings/transcripts"
            if "seeking alpha" in transcript_source.lower() else None
        )
        sources.append(SourceRef(
            label=transcript_label,
            url=transcript_display_url,
            note="Primary earnings transcript source" if transcript_display_url else MISSING,
        ))
    sources.append(SourceRef(
        label="Official Investor Relations",
        url=investor_relations_url,
        note="Press release / earnings presentation source" if investor_relations_url else MISSING,
    ))
    if company_website_url and company_website_url != investor_relations_url:
        sources.append(SourceRef(label="Official Website", url=company_website_url))
    press_release_url = _metric_url(metrics, "press_release_url")
    if press_release_url:
        sources.append(SourceRef(label="Press Release", url=press_release_url))
    presentation_url = _metric_url(metrics, "earnings_presentation_url", "presentation_url")
    if presentation_url:
        sources.append(SourceRef(label="Earnings Call Presentation", url=presentation_url))

    return EarningsDeepDiveReport(
        ticker=ticker_clean,
        company=company_name,
        quarter=quarter.strip() if quarter else "latest quarter",
        language=report_language,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        title=f"{company_name} ({ticker_clean}) - Earnings Deep-Dive",
        sections=sections,
        sources=sources,
    )
