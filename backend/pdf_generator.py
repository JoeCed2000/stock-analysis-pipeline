"""PDF report generator using reportlab."""
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# Colors — dark-on-white palette for print/PDF readability
GREEN = HexColor('#1a7f37')
YELLOW = HexColor('#9a6700')
RED = HexColor('#cf222e')
DARK = HexColor('#0d1117')
LIGHT = HexColor('#1f2328')
MUTED = HexColor('#57606a')
CARD_BG = HexColor('#f6f8fa')


def generate_pdf(result, report_md: str, output_path: str) -> str:
    """Generate a PDF report from the analysis result and markdown report."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=25*mm,  # Increased bottom margin for footer
        title=f"{result.ticker} — Stock Analysis Report"
    )

    # ── Footer callback ──
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(HexColor('#57606a'))
        footer_text = (
            "⚠️ Auto-generated report. Data marked 'NOT AVAILABLE' = unsourced. "
            "Verify sources before making decisions. This is not investment advice."
        )
        canvas.drawString(20*mm, 12*mm, footer_text)
        canvas.drawRightString(A4[0] - 20*mm, 12*mm, f"Page {doc.page}")
        canvas.restoreState()

    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, textColor='#0d1117', spaceAfter=4)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, textColor='#0969da', spaceBefore=12, spaceAfter=4)
    body_style = ParagraphStyle('Body2', parent=styles['Normal'], fontSize=9, textColor='#1f2328', leading=13)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, textColor='#57606a')

    # Decision color
    decision_color = GREEN if "BUY" in result.decision and "PULLBACK" not in result.decision else \
                     YELLOW if "HOLD" in result.decision else RED

    # ── Header ──
    story.append(Paragraph(f"{result.company_name} ({result.ticker})", title_style))
    story.append(Spacer(1, 4))

    # Price line
    price_str = f"Price: {result.price_native:.2f} {result.currency}" if result.price_native else "Price: N/A"
    eur_str = f" | EUR: {result.price_eur:.2f} €" if result.price_eur else ""
    cap_str = f" | Mkt Cap: {result.market_cap/1e12:.2f}T" if result.market_cap else ""
    story.append(Paragraph(f"{price_str}{eur_str}{cap_str}", small_style))
    story.append(Paragraph(f"Date: {result.retrieved_at} | Sector: {result.sector or 'N/A'}", small_style))
    story.append(Spacer(1, 8))

    # Decision badge
    story.append(Paragraph(
        f'<font color="{decision_color}"><b>{result.decision}</b></font> — Score: {result.scoring.total}/40 — Conviction: {result.conviction}',
        ParagraphStyle('Decision', parent=body_style, fontSize=12, textColor='#0d1117')
    ))
    story.append(Spacer(1, 8))

    # ── Key Phrase ──
    story.append(Paragraph(f"<i>{result.key_phrase}</i>", body_style))
    story.append(Spacer(1, 8))

    # ── Financial Data ──
    story.append(Paragraph("Financial Data", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    fin = result.financials
    fin_data = [
        ["Quarterly Revenue", _fmt(fin.revenue_quarterly, result.currency)],
        ["YoY Growth", _pct(fin.revenue_yoy_growth)],
        ["Annual Revenue", _fmt(fin.revenue_annual, result.currency)],
        ["Annual Growth", _pct(fin.revenue_annual_growth)],
        ["Gross Margin", _pct(fin.gross_margin)],
        ["Operating Margin", _pct(fin.operating_margin)],
        ["Net Income", _fmt(fin.net_income, result.currency)],
        ["Free Cash Flow", _fmt(fin.free_cash_flow, result.currency)],
        ["Net Debt", _fmt(fin.net_debt, result.currency)],
    ]
    t = Table(fin_data, colWidths=[120, 200])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('TEXTCOLOR', (1, 0), (1, -1), LIGHT),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # ── Management Tone ──
    mt = result.management_tone
    if mt.tone and "NOT AVAIL" not in mt.tone and "DONNÉE" not in mt.tone:
        story.append(Paragraph("Management Tone (10-K)", h2_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
        story.append(Paragraph(f"<b>Tone:</b> {mt.tone}", body_style))
        story.append(Paragraph(f"<b>Confidence:</b> {mt.confidence}", body_style))
        story.append(Paragraph(f"<b>Visibility:</b> {mt.visibility}", body_style))
        if mt.concrete_promises:
            story.append(Paragraph("<b>Concrete promises:</b>", body_style))
            for p in mt.concrete_promises[:3]:
                story.append(Paragraph(f"  • {p[:150]}", small_style))
        story.append(Spacer(1, 6))

    # ── Risks ──
    story.append(Paragraph("Risks", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    for r in result.risks[:8]:
        sev_color = RED if r.severity == "high" else YELLOW if r.severity == "medium" else MUTED
        story.append(Paragraph(
            f'<font color="{sev_color}">●</font> <b>{r.category}:</b> {r.description[:120]}',
            ParagraphStyle('Risk', parent=body_style, fontSize=9, leading=12)
        ))
    story.append(Spacer(1, 8))

    # ── Valuation ──
    val = result.valuation
    story.append(Paragraph("Valuation", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Paragraph(
        f"P/E: {_fmt(val.pe_current)} | Forward P/E: {_fmt(val.pe_forward)} | PEG: {_fmt(val.peg_ratio)}",
        body_style
    ))
    story.append(Paragraph(f"Margin of Safety: {val.margin_of_safety}", body_style))
    story.append(Spacer(1, 8))

    # ── Scoring ──
    story.append(Paragraph("Scoring (/40)", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    sc = result.scoring
    # 6 canonical categories with variable max values (Growth 10, Financial Health 10, Valuation 8, Management 5, Moat 4, Sentiment 3)
    sc_data = [
        ["Growth", _bar(sc.growth, 10), f"{sc.growth}/10"],
        ["Financial Health", _bar(sc.financial_health, 10), f"{sc.financial_health}/10"],
        ["Valuation", _bar(sc.valuation, 8), f"{sc.valuation}/8"],
        ["Management", _bar(sc.management, 5), f"{sc.management}/5"],
        ["Moat", _bar(sc.moat, 4), f"{sc.moat}/4"],
        ["Sentiment", _bar(sc.sentiment, 3), f"{sc.sentiment}/3"],
        ["TOTAL", "", f"{sc.total}/40"],
    ]
    t2 = Table(sc_data, colWidths=[100, 100, 60])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('FONTNAME', (6, 0), (6, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t2)
    story.append(Spacer(1, 12))

    # ── Decision ──
    story.append(Paragraph("Final Decision", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Paragraph(
        f'<font color="{decision_color}" size="14"><b>{result.decision}</b></font>',
        ParagraphStyle('Final', parent=body_style)
    ))
    story.append(Paragraph(f"Conditions to add: Improved momentum, valuation pullback, positive guidance", small_style))
    story.append(Paragraph(f"Conditions to sell: Deteriorating fundamentals, moat erosion, materialized geopolitical risk", small_style))

    # ── Disclaimer ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Paragraph("Disclaimer", h2_style))
    story.append(Paragraph(
        "This document is auto-generated by the Stock Analysis Pipeline. "
        "It does not constitute investment advice, a buy/sell recommendation, "
        "or a solicitation. Data is sourced from public records (SEC EDGAR 10-K/10-Q, "
        "Yahoo Finance, Finnhub, Seeking Alpha, The Motley Fool) and may contain errors. "
        "All investment decisions are your sole responsibility.",
        small_style
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Analysis generated on {result.retrieved_at} | Ticker: {result.ticker} | "
        f"Score: {result.scoring.total}/40 | Decision: {result.decision}",
        ParagraphStyle('MetaFooter', parent=small_style, fontSize=7)
    ))

    # Register footer callback
    doc.onPage = add_footer
    doc.build(story)
    return output_path


def _fmt(val, unit=""):
    if val is None: return "N/A"
    if isinstance(val, float):
        if abs(val) > 1e9: return f"{val/1e9:.1f}B {unit}"
        if abs(val) > 1e6: return f"{val/1e6:.1f}M {unit}"
        return f"{val:.2f} {unit}"
    return str(val)


def _pct(val):
    if val is None: return "N/A"
    return f"{val*100:.1f}%"


def _bar(score, max_val=5):
    """Render a proportional bar of width max_val chars."""
    clamped = max(0, min(score, max_val))
    return "█" * clamped + "░" * (max_val - clamped)


def md_to_pdf(md_path: str, pdf_path: str, title: str = "") -> str:
    """Convert a markdown file to a simple PDF using reportlab.
    No weasyprint needed — works on Render free tier."""
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    
    # Read markdown content
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title=title or os.path.basename(md_path)
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Simple markdown → paragraphs
    title_style = ParagraphStyle('MDTitle', parent=styles['Title'], fontSize=16, textColor='#0d1117', spaceAfter=8)
    h2_style = ParagraphStyle('MDH2', parent=styles['Heading2'], fontSize=12, textColor='#0969da', spaceBefore=8, spaceAfter=4)
    body_style = ParagraphStyle('MDBody', parent=styles['Normal'], fontSize=9, textColor='#1f2328', leading=13)
    
    import re
    
    def _md_to_xml(text: str) -> str:
        """Convert basic markdown formatting to XML for ReportLab Paragraph."""
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)  # bold
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)      # italic
        return text
    
    in_table = False
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 2))
            continue
        
        if stripped.startswith("# ") and not stripped.startswith("## "):
            story.append(Paragraph(stripped[2:], title_style))
        elif stripped.startswith("## "):
            story.append(Paragraph(stripped[3:], h2_style))
        elif stripped.startswith("|"):
            # Skip markdown tables for simplicity — they're in the main PDF
            continue
        elif stripped.startswith("**") and ":**" in stripped:
            # Key-value line: "**Key:** value" → <b>Key:</b> value
            kv = _md_to_xml(stripped)
            story.append(Paragraph(kv, body_style))
        else:
            story.append(Paragraph(_md_to_xml(stripped), body_style))
    
    doc.build(story)
    return pdf_path
