"""
Company Overview PDF Generator — dedicated professional PDF renderer.

Replaces the primitive md_to_pdf() for Company Overview documents.
Produces client-ready investor profiles with:
- Executive Snapshot
- 14 structured sections
- Proper tables with column widths
- Source appendix
- Page numbers and footer
- Clean typography (no raw markdown)
"""

import os
import re
import html
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)

# ── Color palette ──────────────────────────────────────────────────────
DARK      = HexColor('#0d1117')
BLUE      = HexColor('#0969da')
GREEN     = HexColor('#1a7f37')
YELLOW    = HexColor('#9a6700')
RED       = HexColor('#cf222e')
MUTED     = HexColor('#57606a')
LIGHT_BG  = HexColor('#f6f8fa')
CARD_BG   = HexColor('#f0f3f5')
BORDER    = HexColor('#d0d7de')
HEADER_BG = HexColor('#1f2328')
WHITE     = white

PAGE_W, PAGE_H = A4
AVAILABLE_W = PAGE_W - 36*mm  # leftMargin=18mm + rightMargin=18mm


# ── Styles ─────────────────────────────────────────────────────────────

def _build_styles():
    """Build paragraph styles for the Company Overview PDF."""
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'COTitle', parent=base['Title'],
            fontSize=18, textColor=DARK, spaceAfter=6, leading=22, keepWithNext=1
        ),
        'subtitle': ParagraphStyle(
            'COSubtitle', parent=base['Normal'],
            fontSize=9, textColor=MUTED, spaceAfter=12, leading=12
        ),
        'h1': ParagraphStyle(
            'COH1', parent=base['Heading1'],
            fontSize=14, textColor=BLUE, spaceBefore=16, spaceAfter=8, leading=18, keepWithNext=1
        ),
        'h2': ParagraphStyle(
            'COH2', parent=base['Heading2'],
            fontSize=12, textColor=DARK, spaceBefore=10, spaceAfter=6, leading=16, keepWithNext=1
        ),
        'body': ParagraphStyle(
            'COBody', parent=base['Normal'],
            fontSize=9, textColor=DARK, leading=13, spaceAfter=4
        ),
        'body_small': ParagraphStyle(
            'COBodySmall', parent=base['Normal'],
            fontSize=8, textColor=MUTED, leading=11, spaceAfter=2
        ),
        'table_header': ParagraphStyle(
            'COTableHeader', parent=base['Normal'],
            fontSize=8, textColor=WHITE, leading=11, fontName='Helvetica-Bold'
        ),
        'table_cell': ParagraphStyle(
            'COTableCell', parent=base['Normal'],
            fontSize=8, textColor=DARK, leading=11
        ),
        'table_cell_small': ParagraphStyle(
            'COTableCellSmall', parent=base['Normal'],
            fontSize=7, textColor=MUTED, leading=10
        ),
        'card_label': ParagraphStyle(
            'COCardLabel', parent=base['Normal'],
            fontSize=7, textColor=MUTED, leading=9, fontName='Helvetica-Bold'
        ),
        'card_value': ParagraphStyle(
            'COCardValue', parent=base['Normal'],
            fontSize=10, textColor=DARK, leading=13, fontName='Helvetica-Bold'
        ),
        'bullet': ParagraphStyle(
            'COBullet', parent=base['Normal'],
            fontSize=9, textColor=DARK, leading=13, leftIndent=12, bulletIndent=0, spaceAfter=2
        ),
        'source_cell': ParagraphStyle(
            'COSourceCell', parent=base['Normal'],
            fontSize=7, textColor=MUTED, leading=9
        ),
    }


# ── Helpers ────────────────────────────────────────────────────────────

def _fmt(value, fmt_spec=",.0f", default="—"):
    """Format a numeric value safely."""
    if value is None:
        return default
    try:
        return f"{value:{fmt_spec}}"
    except (ValueError, TypeError):
        return str(value)


def _fmt_currency(value, default="—"):
    """Format to readable currency string."""
    if value is None:
        return default
    try:
        v = float(value)
        if abs(v) >= 1e12:
            return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:
            return f"${v/1e9:.1f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:.0f}M"
        return f"${v:,.0f}"
    except (ValueError, TypeError):
        return str(value)


def _fmt_pct(value, default="—"):
    """Format a ratio as percentage."""
    if value is None:
        return default
    try:
        return f"{float(value)*100:.1f}%"
    except (ValueError, TypeError):
        return str(value)


def _clean_text(text, default=""):
    """Strip forbidden/internal markers and return clean client-safe text."""
    if not text or not isinstance(text, str):
        return default

    t = text.strip()

    # Strip explicit internal pipeline language (legacy hard markers)
    for marker in [
        "LLM synthesis was unavailable",
        "could not be reliably synthesized",
        "transcript-level validation",
        "requires transcript-level",
        "fallback dataset",
        "LLM synthesis unavailable",
        "because LLM synthesis",
    ]:
        t = t.replace(marker, "")

    # Remove control characters (except common whitespace separators)
    t = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", t)

    # Remove common internal/template/debug wrappers conservatively
    t = re.sub(r"<\|[^|\n]{1,80}\|>", " ", t)  # e.g. <|assistant|>, <|raw|>
    t = re.sub(r"\{\{\s*(?:debug|internal|raw|template|placeholder)[^{}]{0,120}\}\}", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\[\[\s*(?:debug|internal|raw|template|placeholder)[^\]]{0,120}\]\]", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\[(?:DEBUG|INTERNAL|RAW|TEMPLATE)\]", " ", t)

    # Normalize accidental inline source/debug prefixes while preserving payload text
    t = re.sub(
        r"\b(?:source|src|debug)\s*:\s*(?:yfinance|finnhub|edgar|seeking\s*alpha|tavily|alpha\s*vantage)\b",
        "",
        t,
        flags=re.IGNORECASE,
    )

    # Clean separator noise left by marker removal
    t = re.sub(r"\s*\|\s*\|\s*", " | ", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)

    return t.strip() or default


def _soft_wrap_text(text: str) -> str:
    """Insert soft-break opportunities for long tokens."""
    if not text:
        return ""
    wrapped = str(text)
    for token in ('/', '-', '_', '.', ':'):
        wrapped = wrapped.replace(token, f"{token}\u200b")
    return wrapped


def _card_value_text(label: str, value: Any) -> str:
    """Normalize and wrap card values for compact first-page rendering."""
    raw = "—" if value is None else str(value)
    raw = _clean_text(raw, default="—")
    if label == "Website" and raw not in {'—', ''}:
        raw = re.sub(r'^https?://', '', raw, flags=re.IGNORECASE)
    return _soft_wrap_text(raw)


def _estimate_card_font_size(text: str, base: int = 9) -> int:
    """Reduce font size for long values to keep first-page metrics readable."""
    length = len(text or "")
    if length > 90:
        return max(7, base - 2)
    if length > 60:
        return max(8, base - 1)
    return base


def _section(title: str, story: list, styles: dict, level: int = 1):
    """Add a section heading to the story."""
    style = styles['h1'] if level == 1 else styles['h2']
    story.append(Paragraph(title, style))


def _para(text: str, story: list, styles: dict):
    """Add a body paragraph."""
    t = _clean_text(text)
    if t:
        story.append(Paragraph(t, styles['body']))


def _bullet(text: str, story: list, styles: dict):
    """Add a bullet point."""
    t = _clean_text(text)
    if t:
        story.append(Paragraph(f"• {t}", styles['bullet']))


def _bullets(items: list, story: list, styles: dict, max_items: int = 10):
    """Add multiple bullet points."""
    for item in items[:max_items]:
        if isinstance(item, str):
            _bullet(item, story, styles)
        elif isinstance(item, dict):
            _bullet(item.get('text', str(item)), story, styles)


def _hr(story: list):
    """Add a thin horizontal rule."""
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 4))


def _make_table(headers: list, rows: list, col_widths: list = None,
                styles: dict = None, header_bg=HEADER_BG) -> Table:
    """Create a styled table with safer wrapping for dense cells."""
    if styles is None:
        return Table([headers] + rows)

    th_style = styles.get('table_header')
    tc_style = styles.get('table_cell')
    tc_small = styles.get('table_cell_small') or tc_style

    data = [[Paragraph(html.escape(str(h)), th_style) for h in headers]]
    for row in rows:
        row_cells = []
        for idx, cell in enumerate(row):
            text = _soft_wrap_text(_clean_text(str(cell), default='—'))
            width_hint = col_widths[idx] if col_widths and idx < len(col_widths) else None
            compact_col = width_hint is not None and width_hint < (AVAILABLE_W * 0.20)
            style = tc_small if compact_col or len(text) > 70 else tc_style
            row_cells.append(Paragraph(html.escape(text), style))
        data.append(row_cells)

    if col_widths is None:
        available = PAGE_W - 40*mm
        col_widths = [available / len(headers)] * len(headers)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('BACKGROUND', (0, 1), (-1, -1), WHITE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('WORDWRAP', (0, 0), (-1, -1), 'CJK'),
    ]))
    return t


# ── Footer callback ────────────────────────────────────────────────────

def _add_page_footer(canvas, doc, company_name: str, ticker: str, generated_at: str):
    """Draw footer on every page."""
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(MUTED)
    footer = (
        f"{company_name} ({ticker}) — General Company Information for Investors "
        f"| Generated: {generated_at} | Page {doc.page}"
    )
    canvas.drawString(20*mm, 12*mm, footer)
    canvas.restoreState()


# ── Main PDF generator ─────────────────────────────────────────────────

def generate_company_overview_pdf(
    output_path: str,
    ticker: str,
    company_name: str,
    overview: Dict[str, Any],
    yf_data: Dict[str, Any],
    metrics_ledger: List[Dict[str, Any]] = None,
    source_registry: List[Dict[str, Any]] = None,
    language: str = "en",
) -> str:
    """Generate a professional Company Overview PDF for investors.

    Args:
        output_path: Where to write the PDF
        ticker: Stock symbol
        company_name: Full company name
        overview: Structured company overview from get_company_overview()
        yf_data: Raw Yahoo Finance data for metrics
        metrics_ledger: Optional pre-built metrics ledger
        source_registry: Optional pre-built source registry
        language: 'en' or 'jp'

    Returns:
        Path to the generated PDF
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    is_jp = language.lower() == 'jp'
    generated_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    title = f"{company_name} ({ticker}) — General Company Information for Investors"

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=15*mm, bottomMargin=22*mm,
        title=title
    )

    styles = _build_styles()
    story: list = []

    # ── Title page header ──────────────────────────────────────────────
    story.append(Paragraph(title, styles['title']))
    story.append(Paragraph(
        f"Generated: {generated_at} | Data as of: {_fmt_date(yf_data)} | Language: {'JP' if is_jp else 'EN'}",
        styles['subtitle']
    ))
    _hr(story)

    # ── 1. Executive Snapshot ──────────────────────────────────────────
    _render_executive_snapshot(story, styles, ticker, company_name, overview, yf_data, is_jp)

    # ── 2. Company Overview ────────────────────────────────────────────
    _render_company_overview_section(story, styles, overview, is_jp)

    # ── 3. How the Company Makes Money ─────────────────────────────────
    _render_revenue_model(story, styles, overview, is_jp)

    # ── 4. Business Segments & End Markets ─────────────────────────────
    _render_segments(story, styles, overview, is_jp)

    # ── 5. Main Growth Drivers ─────────────────────────────────────────
    _render_growth_drivers(story, styles, overview, is_jp)

    # ── 6. Competitive Advantages / Moats ──────────────────────────────
    _render_moats(story, styles, overview, is_jp)

    # ── 7. Key Metrics / KPIs ──────────────────────────────────────────
    _render_kpis(story, styles, overview, yf_data, metrics_ledger, is_jp)

    # ── 8. Business Risks ──────────────────────────────────────────────
    _render_risks(story, styles, overview, is_jp)

    # ── 9. Competitors ─────────────────────────────────────────────────
    _render_competitors(story, styles, overview, is_jp)

    # ── 10. Strengths Relative to Competitors ──────────────────────────
    _render_strengths(story, styles, overview, is_jp)

    # ── 11. Weaknesses Relative to Competitors ─────────────────────────
    _render_weaknesses(story, styles, overview, is_jp)

    # ── 12. CEO Leadership Style & Long-Term Vision ────────────────────
    _render_ceo_vision(story, styles, overview, is_jp)

    # ── 13. Investor Takeaway ──────────────────────────────────────────
    _render_takeaway(story, styles, overview, is_jp)

    # ── 14. Sources & Data Quality ─────────────────────────────────────
    _render_sources(story, styles, source_registry, yf_data, is_jp)

    # ── Build PDF ──────────────────────────────────────────────────────
    doc.build(
        story,
        onFirstPage=lambda c, d: _add_page_footer(c, d, company_name, ticker, generated_at),
        onLaterPages=lambda c, d: _add_page_footer(c, d, company_name, ticker, generated_at),
    )
    return output_path


# ── Section renderers ──────────────────────────────────────────────────

def _fmt_date(yf_data: dict) -> str:
    """Extract a meaningful data date from yfinance data."""
    # Try to find last fiscal year end or most recent data point
    for key in ('lastFiscalYearEnd', 'mostRecentQuarter', 'dateShortInterest'):
        val = yf_data.get(key)
        if val:
            return str(val)[:10]
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _safe_ov(key: str, overview: dict, default: str = "") -> str:
    """Safely get a string from the overview."""
    val = overview.get(key)
    if val is None:
        return default
    if isinstance(val, str):
        return _clean_text(val) or default
    if isinstance(val, (int, float)):
        return str(val)
    return default


def _safe_ov_list(key: str, overview: dict) -> list:
    """Safely get a list from the overview."""
    val = overview.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        return [val]
    return []



def _key_financials_provenance(overview: dict) -> dict:
    """Return canonical key_financials provenance fields if available."""
    provenance = overview.get('key_financials_provenance', {}) if isinstance(overview, dict) else {}
    if not isinstance(provenance, dict) or provenance.get('schema_version') != 1:
        return {}
    fields = provenance.get('fields', {})
    return fields if isinstance(fields, dict) else {}


def _canonical_financial_metric(overview: dict, field: str) -> dict:
    """Resolve one canonical financial metric for PDF rendering.

    The PDF renderer must not silently fall back to yf_data/raw provider keys: backend
    provenance is the contract. Missing or blocked provenance is rendered visibly as
    "Not available" with the reason/source attached.
    """
    fields = _key_financials_provenance(overview)
    provenance = fields.get(field) if isinstance(fields, dict) else None
    if isinstance(provenance, dict):
        return {
            'field': field,
            'status': provenance.get('status', 'unavailable'),
            'value': provenance.get('normalized_value'),
            'display': provenance.get('display_value') or 'Not available',
            'period': provenance.get('period') or '—',
            'source': _format_metric_source(provenance),
            'reason_code': provenance.get('reason_code'),
        }

    fin = overview.get('key_financials', {}) if isinstance(overview, dict) else {}
    value = fin.get(field) if isinstance(fin, dict) else None
    display = fin.get(f'{field}_display') if isinstance(fin, dict) else None
    if value is not None or display:
        return {
            'field': field,
            'status': 'legacy_no_provenance',
            'value': value,
            'display': display or str(value),
            'period': '—',
            'source': 'Company overview payload (legacy, no provenance)',
            'reason_code': 'missing_provenance',
        }
    return {
        'field': field,
        'status': 'unavailable',
        'value': None,
        'display': 'Not available',
        'period': '—',
        'source': 'Canonical provenance missing',
        'reason_code': 'missing_provenance',
    }


def _format_metric_source(provenance: dict) -> str:
    """Human-readable source label from a provenance row."""
    status = provenance.get('status')
    selected = provenance.get('selected_source')
    path = provenance.get('selected_path')
    reason = provenance.get('reason_code')
    labels = {
        'ledger': 'Internal financial ledger',
        'yahoo_snapshot': 'Yahoo Finance snapshot',
        'computed': 'Computed from canonical components',
        'llm_output': 'LLM output (non-authoritative)',
    }
    if status == 'selected' and selected:
        base = labels.get(selected, selected)
        return f"{base} ({path})" if path else base
    if status == 'blocked':
        return f"Blocked: {reason or 'source mismatch'}"
    if status == 'unavailable':
        return f"Not available: {reason or 'source absent'}"
    return reason or selected or 'Canonical provenance'


def _metric_display(overview: dict, field: str) -> str:
    """Shortcut for card display values."""
    return _canonical_financial_metric(overview, field)['display']

def _render_executive_snapshot(story, styles, ticker, company_name, overview, yf_data, is_jp):
    """Render the Executive Snapshot section with key metrics grid."""
    h = "エグゼクティブ・スナップショット" if is_jp else "Executive Snapshot"
    _section(h, story, styles)

    # Extract data
    profile = overview.get('company_profile', {}) or {}
    sector = profile.get('sector') or yf_data.get('sector', '—')
    industry = profile.get('industry') or yf_data.get('industry', '—')
    hq = profile.get('headquarters') or yf_data.get('headquarters', '—')
    ceo_name = ""
    # 1) Try to extract CEO from Spark overview (most reliable)
    ceo_style = overview.get('ceo_leadership_style', '') or ''
    if ceo_style and ceo_style != 'N/A':
        import re as _re
        m = _re.search(r'CEO\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', ceo_style)
        if m:
            ceo_name = m.group(1)
    # 2) Fall back to yfinance companyOfficers (via _raw_info) for identity only
    if not ceo_name:
        raw_info = yf_data.get('_raw_info', {}) or {}
        officers = raw_info.get('companyOfficers', []) or []
        for o in officers:
            if o and isinstance(o, dict) and ('chief executive' in (o.get('title') or '').lower() or 'ceo' in (o.get('title') or '').lower()):
                ceo_name = o.get('name', '')
                break
    exchange = yf_data.get('exchange', '—')
    country = profile.get('country') or yf_data.get('country', '—')

    # Build metrics card as a table. Financial metrics intentionally consume
    # canonical backend provenance only; no hidden yf_data fallbacks here.
    data_date = _fmt_date(yf_data)
    cards = [
        ("Company", company_name, "Name"),
        ("Ticker", ticker, "Symbol"),
        ("Exchange", exchange, "Market"),
        ("Sector", sector, "Classification"),
        ("Industry", industry, "Classification"),
        ("CEO", ceo_name or "Not identified", "Leadership"),
        ("Headquarters", hq, "Location"),
        ("Country", country, "Location"),
        ("Market Cap", _metric_display(overview, 'market_cap'), _canonical_financial_metric(overview, 'market_cap')['source']),
        ("Revenue (TTM)", _metric_display(overview, 'revenue'), _canonical_financial_metric(overview, 'revenue')['source']),
        ("P/E (Trailing)", _metric_display(overview, 'pe_ratio'), _canonical_financial_metric(overview, 'pe_ratio')['source']),
        ("52W Range", f"{_metric_display(overview, '52w_low')} — {_metric_display(overview, '52w_high')}", "Canonical provenance"),
        ("Employees", _fmt(profile.get('employees') or yf_data.get('fullTimeEmployees'), ',') , "Profile"),
        ("Website", profile.get('website') or yf_data.get('website', '—'), "Profile"),
        ("Data as of", data_date, "Retrieved"),
    ]

    # 2-column card layout
    half = (AVAILABLE_W - 8) / 2
    card_data = []
    for i in range(0, len(cards), 2):
        row = []
        for j in range(2):
            if i + j < len(cards):
                label, value, source = cards[i + j]
                value_txt = _card_value_text(label, value)
                source_txt = _clean_text(str(source), default="Canonical provenance")
                value_size = _estimate_card_font_size(value_txt, base=9)
                row.append(Paragraph(
                    f'<font color="#57606a" size="7"><b>{label}</b></font><br/>'
                    f'<font size="{value_size}">{html.escape(value_txt)}</font><br/>'
                    f'<font color="#57606a" size="6">{html.escape(source_txt)}</font>',
                    styles['body']
                ))
            else:
                row.append(Paragraph("", styles['body']))
        card_data.append(row)

    t = Table(card_data, colWidths=[half, half])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('BACKGROUND', (0, 0), (-1, -1), CARD_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('WORDWRAP', (0, 0), (-1, -1), 'CJK'),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))

    # Investor summary bullets
    investor_bullets = _get_investor_summary(overview, yf_data, is_jp)
    if investor_bullets:
        h3 = "投資家向けサマリー" if is_jp else "Investor Summary"
        story.append(Paragraph(f"<b>{h3}</b>", styles['body']))
        for b in investor_bullets[:5]:
            _bullet(b, story, styles)


def _get_investor_summary(overview, yf_data, is_jp) -> list:
    """Generate investor summary bullets from available data."""
    bullets = []
    bp = overview.get('business_description', '')
    if bp:
        # Split on sentence boundaries, preserving abbreviations like U.S. / Inc.
        import re as _re
        sents = _re.split(r'(?<=[.!?])\s+', bp.replace('\n', ' '))
        sents = [s.strip() for s in sents if s.strip() and len(s.strip()) > 3]
        bullets.append(' '.join(sents[:2]))

    rev = _canonical_financial_metric(overview, 'revenue')
    rev_g = _canonical_financial_metric(overview, 'revenue_growth')
    if rev.get('value') is not None and rev_g.get('value') is not None:
        bullets.append(f"Revenue of {rev['display']} with {rev_g['display']} YoY growth.")
    mc = _canonical_financial_metric(overview, 'market_cap')
    if mc.get('value') is not None:
        bullets.append(f"Market capitalization of {mc['display']}.")

    inv_takeaway = overview.get('investor_takeaway', '')
    if inv_takeaway:
        # Truncate to first 2-3 sentences for executive summary (detailed version on page 2+)
        import re as _re
        takeaway_sents = _re.split(r'(?<=[.!?])\s+', inv_takeaway.replace('\n', ' '))
        takeaway_sents = [s.strip() for s in takeaway_sents if s.strip() and len(s.strip()) > 10]
        short_takeaway = ' '.join(takeaway_sents[:3])
        bullets.append(short_takeaway)
    return bullets


def _render_company_overview_section(story, styles, overview, is_jp):
    """Render the detailed Company Overview narrative."""
    h = "会社概要" if is_jp else "Company Overview"
    _section(h, story, styles)
    desc = _safe_ov('business_description', overview)
    if desc:
        # Split into paragraphs
        for para in desc.split('\n\n'):
            p = _clean_text(para)
            if p and len(p) > 20:
                story.append(Paragraph(p, styles['body']))


def _render_revenue_model(story, styles, overview, is_jp):
    """Render how the company makes money."""
    h = "収益モデル" if is_jp else "How the Company Makes Money"
    _section(h, story, styles)
    rm = _safe_ov('revenue_model', overview)
    if rm:
        story.append(Paragraph(rm, styles['body']))


def _render_segments(story, styles, overview, is_jp):
    """Render business segments & end markets section."""
    h = "事業セグメント・エンドマーケット" if is_jp else "Business Segments & End Markets"
    _section(h, story, styles)

    segments = _safe_ov_list('business_segments', overview)
    if segments:
        # Filter out non-segment entries
        real_segs = []
        for s in segments:
            s_str = str(s).strip()
            # Skip number words, sector/industry labels, generic messages
            if s_str.lower() in {'one', 'two', 'three', 'four', 'five', 'six'}:
                continue
            if s_str.startswith('Primary sector exposure:') or s_str.startswith('Core industry:'):
                continue
            if 'not available' in s_str.lower():
                continue
            if s_str:
                real_segs.append(s_str)

        if real_segs:
            headers = ["Segment" if not is_jp else "セグメント", "Description" if not is_jp else "説明"]
            rows = []
            for s in real_segs[:8]:
                # Try to split on common delimiters for segment/description
                if ':' in s:
                    parts = s.split(':', 1)
                    rows.append([parts[0].strip(), parts[1].strip()])
                elif ' — ' in s:
                    parts = s.split(' — ', 1)
                    rows.append([parts[0].strip(), parts[1].strip()])
                else:
                    rows.append([s, ''])
            if rows:
                w2 = AVAILABLE_W * 0.65
                w1 = AVAILABLE_W - w2
                t = _make_table(headers, rows, [w1, w2], styles)
                story.append(t)
        else:
            _para("Segment details are being refined. Refer to company filings for official segment reporting.", story, styles)
    else:
        _para("Segment data not available. Refer to the company's 10-K or annual report for official segment reporting.", story, styles)


def _render_growth_drivers(story, styles, overview, is_jp):
    """Render main growth drivers."""
    h = "主な成長ドライバー" if is_jp else "Main Growth Drivers"
    _section(h, story, styles)

    drivers = _safe_ov_list('growth_drivers', overview)
    # Filter out generic "revenue growth signal" style entries
    real = [d for d in drivers if isinstance(d, str) and
            'revenue growth signal' not in d.lower() and
            'earnings growth signal' not in d.lower() and
            'enterprise footprint' not in d.lower() and
            'currently unavailable' not in d.lower() and
            'not available' not in d.lower()]
    if real:
        _bullets(real, story, styles)
    elif drivers:
        _bullets(drivers, story, styles)
    else:
        _para("Growth driver analysis not available from current data sources.", story, styles)


def _render_moats(story, styles, overview, is_jp):
    """Render competitive advantages / moats."""
    h = "競争優位性・モート" if is_jp else "Competitive Advantages / Moats"
    _section(h, story, styles)

    moats = _safe_ov_list('moats', overview)
    real = [m for m in moats if isinstance(m, str) and
            'industry positioning' not in m.lower() and
            'brand and distribution reach' not in m.lower() and
            'additional qualitative evidence' not in m.lower() and
            'not available' not in m.lower()]
    if real:
        _bullets(real, story, styles)
    elif moats:
        _bullets(moats, story, styles)
    else:
        _para("Moat analysis not available from current data sources.", story, styles)


def _render_kpis(story, styles, overview, yf_data, metrics_ledger, is_jp):
    """Render key metrics / KPIs section."""
    h = "主要指標・KPI" if is_jp else "Key Metrics / KPIs"
    _section(h, story, styles)

    # Build a unified metrics table from canonical provenance only. This prevents
    # hidden renderer-level fallbacks from showing values that backend provenance
    # rejected or could not reconcile.
    rows = []
    headers = ["Metric" if not is_jp else "指標", "Value" if not is_jp else "値",
               "Period" if not is_jp else "期間", "Source" if not is_jp else "ソース"]

    metric_specs = [
        ("Market Cap", "market_cap"),
        ("Revenue", "revenue"),
        ("Revenue Growth (YoY)", "revenue_growth"),
        ("Gross Margin", "gross_margin"),
        ("Operating Margin", "operating_margin"),
        ("Net Income", "net_income"),
        ("Free Cash Flow", "free_cash_flow"),
        ("P/E (Trailing)", "pe_ratio"),
        ("P/E (Forward)", "pe_forward"),
        ("PEG Ratio", "peg_ratio"),
        ("Beta", "beta"),
        ("Dividend Yield", "dividend_yield"),
        ("52W Low", "52w_low"),
        ("52W High", "52w_high"),
    ]

    for name, field in metric_specs:
        metric = _canonical_financial_metric(overview, field)
        value = metric.get('display') or 'Not available'
        source = metric.get('source') or 'Canonical provenance'
        rows.append([name, value, metric.get('period') or '—', source])

    if rows:
        w_name = AVAILABLE_W * 0.26
        w_val = AVAILABLE_W * 0.20
        w_period = AVAILABLE_W * 0.16
        w_source = AVAILABLE_W * 0.38
        t = _make_table(headers, rows, [w_name, w_val, w_period, w_source], styles)
        story.append(t)
    else:
        _para("Key metrics not available from current data sources.", story, styles)


def _render_risks(story, styles, overview, is_jp):
    """Render business risks section."""
    h = "事業リスク" if is_jp else "Business Risks"
    _section(h, story, styles)

    risks = _safe_ov_list('business_risks', overview)
    real = [r for r in risks if isinstance(r, str) and
            'transcript-level' not in r.lower() and
            'require further analysis' not in r.lower() and
            'not available' not in r.lower()]
    if real:
        _bullets(real, story, styles)
    elif risks:
        _bullets(risks, story, styles)
    else:
        _para("Business risk analysis not available from current data sources.", story, styles)


def _render_competitors(story, styles, overview, is_jp):
    """Render competitors section with table."""
    h = "競合企業" if is_jp else "Competitors"
    _section(h, story, styles)

    competitors = overview.get('competitors', []) or []
    if competitors:
        headers = ["Competitor", "Category", "Why Relevant", "Competitive Pressure"]
        rows = []
        for c in competitors[:10]:
            if isinstance(c, dict):
                name = c.get('competitor_name', '—')
                text = c.get('text_en', '')
                adv = c.get('competitive_advantage', '')
                rows.append([
                    name,
                    c.get('category', _infer_category(name, overview)),
                    text[:200] if text else '—',
                    adv[:200] if adv else '—',
                ])
            elif isinstance(c, str):
                rows.append([c, '—', '—', '—'])
        if rows:
            w_name = AVAILABLE_W * 0.15
            w_cat = AVAILABLE_W * 0.18
            w_why = AVAILABLE_W * 0.37
            w_pressure = AVAILABLE_W * 0.30
            t = _make_table(headers, rows, [w_name, w_cat, w_why, w_pressure], styles)
            story.append(t)
    else:
        _para("Competitor data not available. Refer to the company's 10-K for competitive landscape.", story, styles)


def _infer_category(competitor_name: str, overview: dict) -> str:
    """Infer competitor category from name and sector."""
    name_l = competitor_name.lower()
    sector = (overview.get('company_profile', {}) or {}).get('sector', '').lower()
    if 'technology' in sector or 'semiconductor' in sector or 'gpu' in name_l or 'chip' in name_l:
        return 'Semiconductors / AI'
    if 'cloud' in name_l.lower() or 'aws' in name_l.lower() or 'azure' in name_l.lower():
        return 'Cloud / Hyperscaler'
    return 'Same sector'


def _render_strengths(story, styles, overview, is_jp):
    """Render strengths relative to competitors."""
    h = "競合に対する強み" if is_jp else "Strengths Relative to Competitors"
    _section(h, story, styles)
    s = _safe_ov('strengths_vs_competitors', overview)
    if s:
        story.append(Paragraph(s, styles['body']))


def _render_weaknesses(story, styles, overview, is_jp):
    """Render weaknesses relative to competitors."""
    h = "競合に対する弱み" if is_jp else "Weaknesses Relative to Competitors"
    _section(h, story, styles)
    w = _safe_ov('weaker_areas_vs_competitors', overview)
    if w:
        story.append(Paragraph(w, styles['body']))


def _render_ceo_vision(story, styles, overview, is_jp):
    """Render CEO leadership style & long-term vision."""
    h = "CEOのリーダーシップスタイルと長期ビジョン" if is_jp else "CEO Leadership Style & Long-Term Vision"
    _section(h, story, styles)

    ceo = _safe_ov('ceo_leadership_style', overview)
    if ceo:
        story.append(Paragraph(f"<b>Leadership Style:</b> {ceo}", styles['body']))

    vision = _safe_ov('long_term_vision', overview)
    if vision:
        story.append(Paragraph(f"<b>Long-Term Vision:</b> {vision}", styles['body']))


def _render_takeaway(story, styles, overview, is_jp):
    """Render investor takeaway."""
    h = "投資家向け要点" if is_jp else "Investor Takeaway"
    _section(h, story, styles)
    t = _safe_ov('investor_takeaway', overview)
    if t:
        story.append(Paragraph(t, styles['body']))


def _render_sources(story, styles, source_registry, yf_data, is_jp):
    """Render Sources & Data Quality appendix."""
    h = "ソース・データ品質" if is_jp else "Sources & Data Quality"
    _section(h, story, styles)

    headers = ["Source", "Type", "Provider", "Fields Used", "Status"]
    rows = []

    # Build source list from available data
    sources = source_registry or _build_default_source_registry(yf_data)

    for s in sources[:20]:
        rows.append([
            s.get('human_label', s.get('source_name', '—')),
            s.get('source_type', 'provider'),
            s.get('provider', '—'),
            ', '.join(s.get('fields_used', []))[:100] or '—',
            s.get('status', 'used'),
        ])

    if rows:
        w_name = AVAILABLE_W * 0.22
        w_type = AVAILABLE_W * 0.14
        w_prov = AVAILABLE_W * 0.18
        w_fields = AVAILABLE_W * 0.24
        w_status = AVAILABLE_W * 0.22
        t = _make_table(headers, rows, [w_name, w_type, w_prov, w_fields, w_status], styles)
        story.append(t)

    # Data quality note
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<i>Data quality: Auto-generated from structured data providers. "
        "Always verify with official company filings (10-K, 10-Q, investor relations) "
        "before making investment decisions. This is not investment advice.</i>",
        styles['body_small']
    ))


def _build_default_source_registry(yf_data: dict) -> list:
    """Build a default source registry from yfinance metadata."""
    sources = []
    provider = "Yahoo Finance"
    status = "used"

    fields_used = [k for k, v in yf_data.items() if v is not None and k not in
                   ('_raw', 'companyOfficers', 'description')]
    if fields_used:
        sources.append({
            'human_label': 'Yahoo Finance — Market & Financial Data',
            'source_type': 'financial_data',
            'provider': provider,
            'fields_used': fields_used[:20],
            'status': status,
        })

    # Check for description source
    if yf_data.get('description'):
        sources.append({
            'human_label': 'Yahoo Finance — Company Description',
            'source_type': 'company_description',
            'provider': provider,
            'fields_used': ['description'],
            'status': status,
        })

    # Add SEC filing note
    sources.append({
        'human_label': 'SEC EDGAR — 10-K / 10-Q Filings',
        'source_type': 'regulatory_filing',
        'provider': 'SEC',
        'fields_used': ['financial statements, business description, risk factors, MD&A'],
        'status': 'referenced',
    })

    sources.append({
        'human_label': 'Company Investor Relations',
        'source_type': 'investor_relations',
        'provider': 'Company website',
        'fields_used': ['earnings releases, presentations, shareholder letters'],
        'status': 'referenced',
    })

    return sources
