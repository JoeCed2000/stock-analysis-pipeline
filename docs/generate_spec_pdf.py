#!/usr/bin/env python3
"""Generate professional PDF for SA spec-fonctionnelle v1.1.

Reads docs/spec-fonctionnelle.md and generates docs/spec-fonctionnelle.pdf
in Nami-grade format with cover page, dark headers, tables, risk register, glossary.

Usage:
    cd /home/ced/codex-projects/stock-analysis-pipeline
    python3 docs/generate_spec_pdf.py
"""

import re
from pathlib import Path
from fpdf import FPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_MD = PROJECT_ROOT / "docs" / "spec-fonctionnelle.md"
OUTPUT_PDF = PROJECT_ROOT / "docs" / "spec-fonctionnelle.pdf"


def parse_spec(md_path: Path) -> dict:
    """Parse spec-fonctionnelle.md into structured sections."""
    text = md_path.read_text()

    # Extract metadata table (first table in file)
    meta = {}
    meta_match = re.findall(r'\|\s*(\w[\w\s]+?)\s*\|\s*(.+?)\s*\|', text[:800])
    for k, v in meta_match:
        meta[k.strip()] = v.strip()

    # Extract sections by ## headers
    sections = {}
    current_section = None
    current_content = []

    for line in text.split('\n'):
        if line.startswith('## ') and not line.startswith('### '):
            if current_section:
                sections[current_section] = '\n'.join(current_content)
            current_section = line[3:].strip()
            current_content = []
        elif current_section:
            current_content.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_content)

    # Parse tables from sections
    def extract_table(section_text, header_row=0):
        """Extract rows from markdown tables."""
        rows = []
        for line in section_text.split('\n'):
            if line.startswith('|') and not re.match(r'^\|[\s\-|]+\|$', line):
                cells = [c.strip() for c in line.split('|')[1:-1]]
                rows.append(cells)
        return rows

    # Parse risk register (section 11)
    risk_section = sections.get("11. Risques et décisions", "")
    risks = extract_table(risk_section)
    risk_rows = []
    for r in risks:
        if len(r) >= 5 and r[0].startswith('RSK-'):
            sev_map = {'Moyenne': 'Medium', 'Faible': 'Low', 'Élevée': 'High'}
            sev = sev_map.get(r[1], 'Medium')
            risk_rows.append((r[0], sev, r[1], r[2], r[3]))

    # Parse business rules (section 5)
    br_section = sections.get("5. Règles de gestion", "")
    br_rows = extract_table(br_section)

    # Parse glossary (section 13)
    glossary_section = sections.get("13. Glossaire", "")
    glossary_rows = extract_table(glossary_section)

    # Parse pipeline (section 3)
    pipe_section = sections.get("3. Pipeline d'analyse (9 étapes)", "")
    pipe_rows = extract_table(pipe_section)

    # Parse NFR (section 6)
    nfr_section = sections.get("6. Exigences non fonctionnelles", "")
    nfr_rows = extract_table(nfr_section)

    # Parse acceptance criteria (section 12)
    ga_section = sections.get("12. Critères d'acceptation globaux", "")
    ga_rows = extract_table(ga_section)

    # Parse scope (section 1.2)
    scope_section = sections.get("1. Périmètre et définitions", "")
    scope_rows = extract_table(scope_section)

    return {
        'meta': meta,
        'sections': sections,
        'risks': risk_rows,
        'business_rules': br_rows,
        'glossary': glossary_rows,
        'pipeline': pipe_rows,
        'nfr': nfr_rows,
        'acceptance': ga_rows,
        'scope': scope_rows,
    }


class SpecPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.set_auto_page_break(True, 22)
        self.add_font('D', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        self.add_font('D', 'B', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
        self.add_font('D', 'I', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf')
        self.add_font('DM', '', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')
        self.D = (15, 23, 42)
        self.A = (34, 211, 238)
        self.B = (51, 65, 85)
        self.L = (248, 250, 252)
        self.W = (255, 255, 255)
        self.ROSE = (251, 113, 133)
        self.AMBER = (251, 191, 36)

    def header(self):
        if self.page_no() > 1:
            self.set_font('D', 'B', 7)
            self.set_text_color(*self.B)
            self.cell(0, 4, 'Stock Analysis Pipeline — Spécification Fonctionnelle v1.1', align='L')
            self.cell(0, 4, f'p.{self.page_no()}', align='R', new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*self.A)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

    def footer(self):
        if self.page_no() > 1:
            self.set_y(-16)
            self.set_font('D', 'I', 6)
            self.set_text_color(*self.B)
            self.cell(0, 8, 'Confidentiel — 2026-05-19', align='C')

    def cover(self, title, subtitle, meta_items, abstract):
        self.add_page()
        self.ln(50)
        self.set_fill_color(*self.A)
        self.rect(self.l_margin, 75, 45, 3, 'F')
        self.set_font('D', 'B', 28)
        self.set_text_color(*self.D)
        for line in title.split('\n'):
            self.cell(0, 12, line, new_x="LMARGIN", new_y="NEXT")
        self.set_font('D', '', 14)
        self.set_text_color(*self.B)
        self.cell(0, 8, subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(6)
        self.set_font('D', '', 9)
        for label, value in meta_items:
            self.set_text_color(*self.B)
            self.cell(38, 6, label + ':')
            self.set_text_color(*self.D)
            self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        y = self.get_y()
        self.set_fill_color(*self.L)
        self.rect(self.l_margin, y, self.w - 2 * self.l_margin, 40, 'F')
        self.set_xy(self.l_margin + 6, y + 5)
        self.set_font('D', 'I', 9)
        self.set_text_color(*self.B)
        self.multi_cell(self.w - 2 * self.l_margin - 12, 5, abstract)

    def sec_title(self, num, title):
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*self.D)
        self.set_text_color(*self.W)
        self.set_font('D', 'B', 11)
        self.rect(self.l_margin, y, self.w - 2 * self.l_margin, 7, 'F')
        self.set_xy(self.l_margin + 4, y + 1)
        self.cell(0, 5, f'{num}.  {title}')
        self.set_y(y + 9)
        self.set_text_color(*self.D)

    def sub_title(self, title):
        self.ln(1)
        self.set_font('D', 'B', 9)
        self.set_text_color(*self.D)
        self.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text, sz=8):
        self.set_font('D', '', sz)
        self.set_text_color(*self.B)
        self.multi_cell(self.w - 2 * self.l_margin, 4.5, text)
        self.ln(0.5)

    def bullet(self, text, sz=8):
        self.set_font('D', '', sz)
        self.set_text_color(*self.B)
        self.cell(4, 4.5, '\u2022')
        self.multi_cell(self.w - 2 * self.l_margin - 4, 4.5, text)

    def table(self, headers, rows, col_w=None):
        if col_w is None:
            col_w = [(self.w - 2 * self.l_margin) / len(headers)] * len(headers)
        self.set_font('D', 'B', 6.5)
        self.set_fill_color(*self.D)
        self.set_text_color(*self.W)
        for h, w in zip(headers, col_w):
            self.cell(w, 5, ' ' + h, fill=True)
        self.ln()
        self.set_font('D', '', 6.5)
        self.set_text_color(*self.B)
        for i, row in enumerate(rows):
            self.set_fill_color(245, 247, 250) if i % 2 == 0 else self.set_fill_color(*self.W)
            for cell, w in zip(row, col_w):
                # Truncate to fit
                text = str(cell)
                max_chars = max(1, int(w / 2.2))
                self.cell(w, 4.5, ' ' + text[:max_chars], fill=True)
            self.ln()
        self.ln(1)

    def info_box(self, title, items):
        self.ln(1)
        self.set_font('D', 'B', 8)
        self.set_text_color(*self.D)
        approx_h = 7 + len(items) * 5 + 3
        # Check if enough room on page
        if self.get_y() + approx_h > self.h - 25:
            self.add_page()
        y = self.get_y()
        self.set_fill_color(240, 249, 255)
        self.set_draw_color(*self.A)
        self.rect(self.l_margin, y, self.w - 2 * self.l_margin, approx_h, 'DF')
        self.set_xy(self.l_margin + 5, y + 2)
        self.cell(0, 4, title, new_x="LMARGIN", new_y="NEXT")
        self.set_font('D', '', 7)
        self.set_text_color(*self.B)
        for item in items:
            self.set_x(self.l_margin + 5)
            self.cell(3, 4, '\u2022')
            self.cell(0, 4, item, new_x="LMARGIN", new_y="NEXT")
        self.set_y(y + approx_h + 2)

    def risk_table(self, risks):
        for rid, sev, sev_label, desc, mitigation in risks:
            self.ln(1)
            sc = self.ROSE if sev == 'High' else self.AMBER if sev == 'Medium' else self.A
            self.set_fill_color(*sc)
            self.set_text_color(*self.W)
            self.set_font('D', 'B', 6)
            self.cell(14, 4, f' {sev} ', fill=True)
            self.set_text_color(*self.D)
            self.set_font('D', 'B', 8)
            self.set_x(self.l_margin + 17)
            self.cell(self.w - 2 * self.l_margin - 17, 4, f'{rid} ({sev_label}):', new_x="LMARGIN", new_y="NEXT")
            self.set_font('D', '', 7)
            self.set_text_color(*self.B)
            self.set_x(self.l_margin)
            self.multi_cell(self.w - 2 * self.l_margin, 4, f'Risque: {desc}')
            self.set_font('D', 'I', 7)
            self.set_x(self.l_margin)
            self.multi_cell(self.w - 2 * self.l_margin, 4, f'Mitigation: {mitigation}')

    def glossary(self, terms):
        for term, definition in terms:
            self.set_font('D', 'B', 8)
            self.set_text_color(*self.D)
            self.cell(35, 4.5, term)
            self.set_font('D', '', 7)
            self.set_text_color(*self.B)
            self.multi_cell(self.w - 2 * self.l_margin - 35, 4, definition)
            self.ln(0.3)


def build():
    data = parse_spec(SPEC_MD)
    meta = data['meta']

    pdf = SpecPDF()
    pdf.set_margin(20)

    # ── COVER PAGE ──
    pdf.cover(
        title='Stock Analysis\nPipeline',
        subtitle='Spécification Fonctionnelle v1.1',
        meta_items=[
            ('Projet', meta.get('Projet', 'Stock Analysis Pipeline')),
            ('Version', meta.get('Version', '1.1')),
            ('Nature', meta.get('Nature', 'Testable, auditable, vérifiable')),
            ('Statut', 'Review externe complétée (Codex + Hermes)'),
            ('Auteurs', 'Hermes + Codex CLI'),
            ('Date', '2026-05-19'),
        ],
        abstract=(
            'Pipeline d\'analyse fondamentale automatisé pour investisseurs particuliers. '
            'Analyse en 9 étapes : collecte de données financières (yfinance, Finnhub, EDGAR, '
            'Seeking Alpha, Tavily, Alpha Vantage), scoring BUY/HOLD/SELL sur 40 points, '
            'génération de PDF deep-dive (10-14 pages) et dossier ZIP auditable. '
            'Support multilingue EN/JP/bilingual. Déploiement WSL2 + Cloudflare Tunnel.'
        )
    )

    # ── 1. PÉRIMÈTRE ──
    pdf.add_page()
    pdf.sec_title('1', 'Périmètre et définitions')

    pdf.sub_title('1.1  Acteurs')
    pdf.table(
        ['ID', 'Acteur', 'Description'],
        [('ACT-001', 'Investisseur principal', 'Utilisateur unique, investisseur particulier francophone'),
         ('ACT-002', 'Auditeur externe', 'Vérifie la conformité des analyses produites'),
         ('ACT-003', 'Veilleur automatique', 'Cron jobs Hermes de monitoring')],
        [25, 60, 85]
    )

    pdf.sub_title('1.2  Périmètre fonctionnel')
    scope_rows = [r for r in data['scope'] if r[0].startswith('IN-') or r[0].startswith('OUT-')]
    ins = [r for r in scope_rows if r[0].startswith('IN-')]
    outs = [r for r in scope_rows if r[0].startswith('OUT-')]

    pdf.body_text('Inclus :', sz=8)
    for r in ins[:9]:
        pdf.bullet(f'{r[0]} — {r[1]}', sz=7)

    pdf.ln(2)
    pdf.body_text('Hors périmètre :', sz=8)
    for r in outs:
        pdf.bullet(f'{r[0]} — {r[1]}', sz=7)

    # ── 2. USE CASES ──
    pdf.sec_title('2', 'Exigences fonctionnelles')
    ucs = [
        ('UC-001', 'Analyser un ticker', 'ACT-001', 'Saisie ticker + clic Analyze → PDF + ZIP'),
        ('UC-002', 'Consulter le PDF deep-dive', 'ACT-001', 'Clic View Full Report → PDF 5 sections'),
        ('UC-003', 'Télécharger le ZIP', 'ACT-001', 'Clic Download ZIP → .zip (PDF + JSON)'),
        ('UC-004', 'Batch analysis', 'ACT-001', 'Upload CSV ≤ 10 tickers → traitement séquentiel'),
        ('UC-005', 'Feedback et correction', 'ACT-001', 'Envoi feedback → horodatage + réanalyse'),
        ('UC-006', 'Health check système', 'ACT-003', 'Cron 15 min → /api/health + auto-recovery'),
    ]
    pdf.table(
        ['ID', 'Use Case', 'Acteur', 'Résumé'],
        ucs,
        [22, 55, 22, 71]
    )

    # Acceptance criteria
    pdf.sub_title('Critères d\'acceptation')
    ga_rows = data['acceptance']
    if ga_rows:
        pdf.table(
            ['ID', 'Critère', 'Méthode', 'Seuil'],
            [r[:4] for r in ga_rows if r[0].startswith('GA-')],
            [21, 67, 52, 30]
        )

    # ── 3. PIPELINE ──
    pdf.sec_title('3', 'Pipeline d\'analyse (9 étapes)')
    pipe_rows = data['pipeline']
    if pipe_rows:
        pdf.table(
            ['Étape', 'ID', 'Module', 'Sources'],
            [(r[0], r[1], r[2], r[4]) for r in pipe_rows if r[0].isdigit()],
            [12, 25, 63, 70]
        )

    # ── 4. SCHÉMAS DE DONNÉES ──
    pdf.sec_title('4', 'Schémas de données')

    pdf.sub_title('4.1  Scoring (40 points)')
    pdf.info_box('Catégories de scoring', [
        'Financial Health [0-10] — Dette, liquidité, cash flow',
        'Growth [0-10] — Croissance CA, BNA',
        'Valuation [0-8] — PER, PEG, P/B, EV/EBITDA',
        'Management [0-5] — Tone analysis, insider trades',
        'Moat [0-4] — Marge, part de marché',
        'Sentiment [0-3] — News, analystes',
        'BUY si ≥ 28 | HOLD si 18-27 | SELL si < 18 | INSUFFISANT si < 3 sources',
    ])

    pdf.sub_title('4.2  AnalysisResult')
    pdf.body_text(
        'Chaque analyse produit un AnalysisResult contenant : ticker, timestamp ISO 8601, '
        'status (running/completed/error), score, company_profile, financial_data, '
        'management_tone, risks (≤ 20), valuation, sources (≥ 1, score désactivé si < 3), '
        'pdf_path, dossier_path.', sz=7
    )

    pdf.sub_title('4.3  FinancialData')
    pdf.body_text(
        'market_cap, revenue (TTM), net_income, eps, pe_ratio, peg_ratio, debt_to_equity, '
        'current_ratio, free_cash_flow, dividend_yield, revenue_growth_yoy (%), '
        'gross_margin (%), operating_margin. Tous nullable sauf ticker.', sz=7
    )

    # ── 5. BUSINESS RULES ──
    pdf.sec_title('5', 'Règles de gestion')
    br_rows = data['business_rules']
    if br_rows:
        pdf.table(
            ['ID', 'Règle', 'Condition', 'Testable'],
            [(r[0], r[1][:55], r[2][:40], r[4]) for r in br_rows if r[0].startswith('BR-')],
            [20, 55, 65, 30]
        )

    # ── 6. NFR ──
    pdf.sec_title('6', 'Exigences non fonctionnelles')
    nfr_rows = data['nfr']
    if nfr_rows:
        pdf.table(
            ['ID', 'Catégorie', 'Exigence', 'Cible'],
            [(r[0], r[1], r[2][:60], r[3]) for r in nfr_rows if r[0].startswith('NFR-')],
            [22, 30, 88, 30]
        )

    # ── 7. OBSERVABILITÉ ──
    pdf.sec_title('7', 'Observabilité et audit')
    pdf.body_text(
        'Événements de log structurés : pipeline.start, pipeline.step (1-9), pipeline.complete, '
        'pipeline.error, source.fetch, source.rate_limit, pdf.render, api.request. '
        'Niveaux : INFO pour le flux nominal, WARN pour les rate limits, ERROR pour les échecs, '
        'DEBUG pour les appels sources.'
    )
    pdf.body_text(
        'Métriques exposées : /api/health (uptime), /api/traceability/{ticker} (sources), '
        '/api/batch/{job_id}/status, /api/admin/recent-searches, /api/admin/search-stats.'
    )

    # ── 8. CONFIDENTIALITÉ ──
    pdf.sec_title('8', 'Politique de confidentialité')
    pdf.body_text(
        'Le pipeline utilise des LLM externes pour la synthèse narrative (étape 7). '
        'Les données transmises sont exclusivement des données financières publiques. '
        'Aucune PII dans les prompts. Secrets API stockés dans .env, jamais transmis. '
        'Logs sans contenu de prompts complets. Cache local effaçable sans impact. '
        'Toute analyse est regénérable (données sources conservées). Usage personnel uniquement.'
    )

    # ── 9. RÉTENTION ET RESTAURATION ──
    pdf.sec_title('9', 'Rétention et restauration')
    pdf.sub_title('9.1  Rétention')
    pdf.table(
        ['Artefact', 'Emplacement', 'Rétention'],
        [('Analyse JSON', 'analyses/{ticker}_{timestamp}/', 'Illimitée'),
         ('PDF deep-dive', 'analyses/{ticker}_{timestamp}/', 'Illimitée'),
         ('ZIP dossier', 'analyses/{ticker}_{timestamp}/', 'Illimitée'),
         ('Cache financier', 'backend/cache/', 'Volatil'),
         ('Logs', 'backend/logs/', 'Rotation manuelle')],
        [60, 60, 50]
    )

    pdf.sub_title('9.2  Modes de défaillance')
    pdf.table(
        ['Défaillance', 'Symptôme', 'Récupération', 'Délai'],
        [('Tunnel CF down', 'HTTP 530/1033', 'systemctl restart cloudflared-tunnel', '< 2 min'),
         ('Backend down', 'Connection refused', 'uvicorn main:app --port 8780', '< 5 min'),
         ('API rate limit', '429', 'Backoff exponentiel (auto)', '< 30s'),
         ('Build frontend manquant', '404 JS/CSS', 'npm run build', '< 2 min'),
         ('Port occupé', 'Address in use', 'lsof + kill PID', '< 1 min')],
        [35, 35, 70, 30]
    )

    # ── 10. CONTRAINTES ──
    pdf.sec_title('10', 'Contraintes')
    pdf.table(
        ['ID', 'Contrainte', 'Impact'],
        [('C-001', 'yfinance ~5 req/s', 'Délai batch'),
         ('C-002', 'Finnhub 60 req/min', 'News/earnings limités'),
         ('C-003', 'Alpha Vantage 25 req/j', 'Transcripts limités'),
         ('C-004', 'Tavily 1000 req/mois', 'IR enrichment limité'),
         ('C-005', 'Cloudflare Tunnel', 'Auth X-API-Key obligatoire'),
         ('C-006', 'WSL2 uniquement', 'Pas de containerisation'),
         ('C-007', 'React bundle JS', 'Cache-busting obligatoire'),
         ('C-008', 'Seeking Alpha scraping', 'Source fragile')],
        [21, 74, 75]
    )

    # ── 11. RISQUES ──
    pdf.sec_title('11', 'Risques et décisions')
    risks = data['risks']
    if risks:
        pdf.risk_table(risks)

    pdf.sub_title('Décisions d\'architecture')
    pdf.bullet('ADR-001 : Stack Python/FastAPI + React/Vite + ReportLab + Cloudflare Tunnel')
    pdf.bullet('ADR-002 : Scoring rules-based (40 pts, 6 catégories) plutôt que ML')

    # ── 12. GLOSSAIRE ──
    pdf.sec_title('12', 'Glossaire')
    glossary_rows = data['glossary']
    if glossary_rows:
        pdf.glossary([(r[0], r[1]) for r in glossary_rows if r[0] and not r[0].startswith('--')])

    # ── SAVE ──
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT_PDF))
    print(f'✅ PDF generated: {OUTPUT_PDF} ({pdf.page_no()} pages)')


if __name__ == '__main__':
    build()
