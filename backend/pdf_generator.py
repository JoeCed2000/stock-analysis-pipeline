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

# Colors
GREEN = HexColor('#238636')
YELLOW = HexColor('#d29922')
RED = HexColor('#da3633')
DARK = HexColor('#0f1117')
LIGHT = HexColor('#e1e4e8')
MUTED = HexColor('#8b949e')
CARD_BG = HexColor('#1a1d27')


def generate_pdf(result, report_md: str, output_path: str) -> str:
    """Generate a PDF report from the analysis result and markdown report."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title=f"{result.ticker} — Stock Analysis Report"
    )

    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, textColor='#e1e4e8', spaceAfter=4)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14, textColor='#58a6ff', spaceBefore=12, spaceAfter=4)
    body_style = ParagraphStyle('Body2', parent=styles['Normal'], fontSize=9, textColor='#c9d1d9', leading=13)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, textColor='#8b949e')

    # Decision color
    decision_color = GREEN if "BUY" in result.decision and "PULLBACK" not in result.decision else \
                     YELLOW if "HOLD" in result.decision else RED

    # ── Header ──
    story.append(Paragraph(f"{result.company_name} ({result.ticker})", title_style))
    story.append(Spacer(1, 4))

    # Price line
    price_str = f"Cours: {result.price_native:.2f} {result.currency}" if result.price_native else "Cours: N/A"
    eur_str = f" | EUR: {result.price_eur:.2f} €" if result.price_eur else ""
    cap_str = f" | Capi: {result.market_cap/1e12:.2f}T" if result.market_cap else ""
    story.append(Paragraph(f"{price_str}{eur_str}{cap_str}", small_style))
    story.append(Paragraph(f"Date: {result.retrieved_at} | Secteur: {result.sector or 'N/A'}", small_style))
    story.append(Spacer(1, 8))

    # Decision badge
    story.append(Paragraph(
        f'<font color="{decision_color}"><b>{result.decision}</b></font> — Score: {result.scoring.total}/40 — Conviction: {result.conviction}',
        ParagraphStyle('Decision', parent=body_style, fontSize=12, textColor='#e1e4e8')
    ))
    story.append(Spacer(1, 8))

    # ── Key Phrase ──
    story.append(Paragraph(f"<i>{result.key_phrase}</i>", body_style))
    story.append(Spacer(1, 8))

    # ── Financial Data ──
    story.append(Paragraph("Données financières", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    fin = result.financials
    fin_data = [
        ["Chiffre d'affaires trim.", _fmt(fin.revenue_quarterly, result.currency)],
        ["Croissance YoY", _pct(fin.revenue_yoy_growth)],
        ["Chiffre d'affaires annuel", _fmt(fin.revenue_annual, result.currency)],
        ["Croissance annuelle", _pct(fin.revenue_annual_growth)],
        ["Marge brute", _pct(fin.gross_margin)],
        ["Marge opérationnelle", _pct(fin.operating_margin)],
        ["Résultat net", _fmt(fin.net_income, result.currency)],
        ["Free Cash Flow", _fmt(fin.free_cash_flow, result.currency)],
        ["Dette nette", _fmt(fin.net_debt, result.currency)],
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
    if mt.tone and "DONNÉE" not in mt.tone:
        story.append(Paragraph("Discours Management (10-K)", h2_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
        story.append(Paragraph(f"<b>Ton:</b> {mt.tone}", body_style))
        story.append(Paragraph(f"<b>Confiance:</b> {mt.confidence}", body_style))
        story.append(Paragraph(f"<b>Visibilité:</b> {mt.visibility}", body_style))
        if mt.concrete_promises:
            story.append(Paragraph("<b>Promesses concrètes:</b>", body_style))
            for p in mt.concrete_promises[:3]:
                story.append(Paragraph(f"  • {p[:150]}", small_style))
        story.append(Spacer(1, 6))

    # ── Risks ──
    story.append(Paragraph("Risques", h2_style))
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
    story.append(Paragraph("Valorisation", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Paragraph(
        f"P/E: {_fmt(val.pe_current)} | Forward P/E: {_fmt(val.pe_forward)} | PEG: {_fmt(val.peg_ratio)}",
        body_style
    ))
    story.append(Paragraph(f"Marge de sécurité: {val.margin_of_safety}", body_style))
    story.append(Spacer(1, 8))

    # ── Scoring ──
    story.append(Paragraph("Scoring (/40)", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    sc = result.scoring
    sc_data = [
        ["Croissance", _bar(sc.growth), str(sc.growth)],
        ["Rentabilité", _bar(sc.profitability), str(sc.profitability)],
        ["Solidité financière", _bar(sc.financial_strength), str(sc.financial_strength)],
        ["Moat", _bar(sc.moat), str(sc.moat)],
        ["Management", _bar(sc.management), str(sc.management)],
        ["Valorisation", _bar(sc.valuation_risk), str(sc.valuation_risk)],
        ["Géopolitique", _bar(sc.geopolitical_risk), str(sc.geopolitical_risk)],
        ["Momentum", _bar(sc.business_momentum), str(sc.business_momentum)],
        ["TOTAL", "", f"{sc.total}/40"],
    ]
    t2 = Table(sc_data, colWidths=[100, 100, 60])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('FONTNAME', (8, 0), (8, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t2)
    story.append(Spacer(1, 12))

    # ── Decision ──
    story.append(Paragraph("Décision finale", h2_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
    story.append(Paragraph(
        f'<font color="{decision_color}" size="14"><b>{result.decision}</b></font>',
        ParagraphStyle('Final', parent=body_style)
    ))
    story.append(Paragraph(f"Conditions pour renforcer: Amélioration du momentum, pullback de valorisation, guidance positive", small_style))
    story.append(Paragraph(f"Conditions pour vendre: Détérioration des fondamentaux, rupture de moat, risque géopolitique matérialisé", small_style))

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


def _bar(score):
    return "█" * score + "░" * (5 - score)
