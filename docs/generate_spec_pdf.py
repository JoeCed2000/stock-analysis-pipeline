#!/usr/bin/env python3
"""Generate comprehensive professional PDF for SA spec-fonctionnelle v1.1.

Target: 15-20 pages with full content — not compressed summaries.
Every use case, every scenario, every data schema, every rule rendered properly.

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


class SpecPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.set_auto_page_break(True, 20)
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
        self.GREEN = (34, 197, 94)
        self._current_sec = 0

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
        self.ln(45)
        self.set_fill_color(*self.A)
        self.rect(self.l_margin, 70, 50, 3.5, 'F')
        self.set_font('D', 'B', 30)
        self.set_text_color(*self.D)
        for line in title.split('\n'):
            self.cell(0, 13, line, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font('D', '', 15)
        self.set_text_color(*self.B)
        self.cell(0, 8, subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        self.set_font('D', '', 9)
        for label, value in meta_items:
            self.set_text_color(*self.B)
            self.cell(40, 6, label + ':')
            self.set_text_color(*self.D)
            self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        y = self.get_y()
        self.set_fill_color(*self.L)
        h = 45
        self.rect(self.l_margin, y, self.w - 2 * self.l_margin, h, 'F')
        self.set_xy(self.l_margin + 7, y + 6)
        self.set_font('D', 'I', 9)
        self.set_text_color(*self.B)
        self.multi_cell(self.w - 2 * self.l_margin - 14, 5.5, abstract)

    def section(self, title):
        self._current_sec += 1
        self.ln(4)
        y = self.get_y()
        self.set_fill_color(*self.D)
        self.set_text_color(*self.W)
        self.set_font('D', 'B', 12)
        bar_h = 8
        self.rect(self.l_margin, y, self.w - 2 * self.l_margin, bar_h, 'F')
        self.set_xy(self.l_margin + 5, y + 1.5)
        self.cell(0, 5, f'{self._current_sec}.  {title}')
        self.set_y(y + bar_h + 3)
        self.set_text_color(*self.D)

    def subsection(self, title):
        self.ln(2)
        self.set_font('D', 'B', 10)
        self.set_text_color(*self.D)
        self.set_x(self.l_margin)
        self.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text, sz=9):
        self.set_font('D', '', sz)
        self.set_text_color(*self.B)
        self.set_x(self.l_margin)
        self.multi_cell(self.w - 2 * self.l_margin, 5, text)
        self.ln(1)

    def bullet(self, text, sz=9):
        self.set_font('D', '', sz)
        self.set_text_color(*self.B)
        self.set_x(self.l_margin + 3)
        self.cell(4, 5, '\u2022')
        self.multi_cell(self.w - 2 * self.l_margin - 7, 5, text)

    def number_bullet(self, num, text, sz=9):
        self.set_font('D', '', sz)
        self.set_text_color(*self.B)
        self.set_x(self.l_margin + 3)
        self.cell(8, 5, f'{num}.')
        self.multi_cell(self.w - 2 * self.l_margin - 11, 5, text)

    def code_block(self, text, sz=7.5):
        self.ln(1)
        lines = text.strip().split('\n')
        self.set_fill_color(*self.L)
        self.set_font('DM', '', sz)
        self.set_text_color(*self.D)
        y = self.get_y()
        block_h = len(lines) * 4.2 + 5
        if y + block_h > self.h - 20:
            self.add_page()
            y = self.get_y()
        self.rect(self.l_margin + 4, y, self.w - 2 * self.l_margin - 8, block_h, 'F')
        self.set_xy(self.l_margin + 7, y + 2.5)
        for line in lines:
            self.cell(0, 4.2, line, new_x="LMARGIN", new_y="NEXT")
            self.set_x(self.l_margin + 7)
        self.set_y(y + block_h + 2)

    def table(self, headers, rows, col_w=None, sz=7.5):
        if col_w is None:
            col_w = [(self.w - 2 * self.l_margin) / len(headers)] * len(headers)
        self.set_font('D', 'B', sz)
        self.set_fill_color(*self.D)
        self.set_text_color(*self.W)
        for h, w in zip(headers, col_w):
            self.cell(w, 5.5, ' ' + str(h), fill=True)
        self.ln()
        self.set_font('D', '', sz)
        self.set_text_color(*self.B)
        for i, row in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(245, 247, 250)
            else:
                self.set_fill_color(*self.W)
            for cell, w in zip(row, col_w):
                text = str(cell)
                max_chars = max(1, int(w / 2.5))
                self.cell(w, 5, ' ' + text[:max_chars], fill=True)
            self.ln()
        self.ln(1.5)

    def info_box(self, title, items):
        self.ln(1)
        y = self.get_y()
        self.set_font('D', 'B', 9)
        self.set_text_color(*self.D)
        self.set_x(self.l_margin + 4)
        # Estimate height
        h = 8 + 3 + len(items) * 5.5
        if y + h > self.h - 20:
            self.add_page()
            y = self.get_y()
        self.set_fill_color(240, 249, 255)
        self.set_draw_color(*self.A)
        self.rect(self.l_margin, y, self.w - 2 * self.l_margin, h, 'DF')
        self.set_xy(self.l_margin + 6, y + 2.5)
        self.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
        self.set_font('D', '', 8)
        self.set_text_color(*self.B)
        for item in items:
            self.set_x(self.l_margin + 6)
            self.cell(4, 5, '\u2022')
            self.multi_cell(self.w - 2 * self.l_margin - 14, 5, item)
        self.set_y(y + h + 3)

    def scenario(self, sid, text):
        """Render a Given/When/Then scenario."""
        self.ln(1)
        self.set_font('D', 'B', 8)
        self.set_text_color(*self.D)
        self.set_x(self.l_margin + 2)
        self.cell(0, 5, sid, new_x="LMARGIN", new_y="NEXT")
        self.set_font('D', '', 8)
        self.set_text_color(*self.B)
        self.set_x(self.l_margin + 2)
        # Clean up markdown formatting
        clean = text.replace('**', '').replace('> ', '').strip()
        self.multi_cell(self.w - 2 * self.l_margin - 4, 4.5, clean)
        self.ln(0.5)

    def risk_item(self, rid, sev, title, desc, mitigation):
        self.ln(2)
        sc = self.ROSE if sev == 'High' else self.AMBER if sev == 'Medium' else self.GREEN
        self.set_fill_color(*sc)
        self.set_text_color(*self.W)
        self.set_font('D', 'B', 7)
        self.cell(16, 5, f' {sev} ', fill=True)
        self.set_text_color(*self.D)
        self.set_font('D', 'B', 9)
        self.set_x(self.l_margin + 19)
        self.cell(self.w - 2 * self.l_margin - 19, 5, f'{rid} — {title}', new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_font('D', '', 8)
        self.set_text_color(*self.B)
        self.set_x(self.l_margin)
        self.multi_cell(self.w - 2 * self.l_margin, 4.5, f'Risque : {desc}')
        self.set_font('D', 'I', 8)
        self.set_x(self.l_margin)
        self.multi_cell(self.w - 2 * self.l_margin, 4.5, f'Mitigation : {mitigation}')

    def glossary(self, terms):
        for term, definition in terms:
            if not term or term.startswith('--'):
                continue
            self.set_font('D', 'B', 9)
            self.set_text_color(*self.D)
            self.cell(38, 5, term)
            self.set_font('D', '', 8)
            self.set_text_color(*self.B)
            self.set_x(self.l_margin + 40)
            self.multi_cell(self.w - 2 * self.l_margin - 40, 4.5, definition)
            self.ln(0.5)


def parse_spec(text):
    """Parse spec sections and tables."""
    lines = text.split('\n')
    
    # Extract metadata
    meta = {}
    in_meta = False
    for line in lines[:15]:
        if 'Métadonnée' in line:
            in_meta = True
            continue
        if in_meta and line.startswith('|') and '---' not in line:
            parts = [c.strip() for c in line.split('|')[1:-1]]
            if len(parts) >= 2:
                meta[parts[0]] = parts[1]
        if in_meta and not line.startswith('|'):
            break

    return meta


def extract_table_rows(section_lines, header_skip=0):
    """Extract rows from markdown table."""
    rows = []
    header_count = 0
    for line in section_lines:
        if line.startswith('|') and not re.match(r'^\|[\s\-:]+\|', line) and not re.match(r'^\|[\s\-|]+\|$', line):
            if header_count < header_skip:
                header_count += 1
                continue
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and any(c for c in cells):
                rows.append(cells)
    return rows


def build():
    text = SPEC_MD.read_text()
    meta = parse_spec(text)
    lines = text.split('\n')

    pdf = SpecPDF()
    pdf.set_margin(20)

    # ═══════ COVER ═══════
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
            'Analyse en 9 étapes : collecte de données financières multi-sources (yfinance, Finnhub, '
            'EDGAR, Seeking Alpha, Tavily, Alpha Vantage), scoring BUY/HOLD/SELL sur 40 points '
            'répartis en 6 catégories, génération de PDF deep-dive professionnel (10-14 pages, '
            'format Nami-grade) et dossier ZIP auditable. Support multilingue EN/JP/bilingual. '
            'Déploiement WSL2 + Cloudflare Tunnel avec health check et auto-recovery.'
        )
    )

    # ═══════ 1. PÉRIMÈTRE ═══════
    pdf.add_page()
    pdf.section('Périmètre et définitions')

    pdf.subsection('1.1  Acteurs')
    pdf.table(
        ['ID', 'Acteur', 'Description', 'Compétences'],
        [
            ('ACT-001', 'Investisseur principal', 'Utilisateur unique, investisseur francophone', 'Analyse financière, tickers US'),
            ('ACT-002', 'Auditeur externe', 'Vérifie la conformité des analyses', 'Contrôle qualité'),
            ('ACT-003', 'Veilleur automatique', 'Cron jobs Hermes de monitoring', 'Aucune (système)'),
        ],
        [25, 42, 63, 40]
    )

    pdf.subsection('1.2  Périmètre fonctionnel — Inclus')
    pdf.table(
        ['ID', 'Élément', 'Justification'],
        [
            ('IN-001', 'Analyse fondamentale par ticker (9 étapes)', 'Cœur du produit'),
            ('IN-002', 'Scoring BUY/HOLD/SELL (40 pts, 6 catégories)', 'Décision d\'investissement'),
            ('IN-003', 'PDF deep-dive formaté (10-14p, ReportLab)', 'Livrable principal'),
            ('IN-004', 'Dossier ZIP téléchargeable (PDF + JSON)', 'Auditabilité'),
            ('IN-005', 'Sélection langue EN/JP/bilingual', 'Usage international'),
            ('IN-006', 'Batch analysis API (upload CSV) — UI v1.2', 'Efficacité'),
            ('IN-007', 'Feedback utilisateur horodaté avec correction', 'Amélioration continue'),
            ('IN-008', 'Collecte IR sites (dates earnings, webcasts)', 'Enrichissement données'),
            ('IN-009', 'Health check + monitoring + auto-recovery', 'Production'),
        ],
        [22, 80, 68]
    )

    pdf.subsection('1.3  Hors périmètre')
    pdf.table(
        ['ID', 'Élément', 'Raison'],
        [
            ('OUT-001', 'Trading automatisé', 'Analyse seulement, pas exécution'),
            ('OUT-002', 'Données temps réel (streaming)', 'Fondamentale uniquement'),
            ('OUT-003', 'Screening de marché (scanner)', 'Analyse individuelle par ticker'),
            ('OUT-004', 'API publique / multi-utilisateur', 'Usage personnel'),
            ('OUT-005', 'Backtesting de stratégies', 'Projet séparé (hedge-fund-local)'),
        ],
        [22, 70, 78]
    )

    # ═══════ 2. USE CASES ═══════
    pdf.section('Exigences fonctionnelles')

    pdf.subsection('UC-001 — Analyser un ticker')
    pdf.body('Acteur : ACT-001 | Déclencheur : Saisie ticker + clic « Analyze » | Postcondition : PDF + ZIP disponibles')
    pdf.scenario('Scénario nominal (AC-001)',
        'Given le backend est actif sur le port 8780, and les 6 API externes (yfinance, Finnhub, EDGAR, Seeking Alpha, Tavily, Alpha Vantage) sont accessibles, and le ticker AAPL est valide. '
        'When l\'utilisateur saisit « AAPL » et clique « Analyze ». '
        'Then le pipeline exécute les 9 étapes séquentiellement, and un PDF deep-dive ≥ 10 pages est généré, and le score est affiché avec BUY/HOLD/SELL, and le bouton « Download ZIP » est actif.')
    pdf.scenario('Scénario ticker invalide (AC-002)',
        'Given le backend est actif. When l\'utilisateur saisit « ZZZZYX ». Then le système retourne un message d\'erreur dans les 30 secondes, and aucune analyse n\'est stockée.')
    pdf.scenario('Scénario API source partiellement down (AC-003)',
        'Given le backend est actif, and l\'API Seeking Alpha est indisponible. When l\'utilisateur analyse NVDA. Then les données encore disponibles sont collectées (≥ 3 sources), and les sections manquantes affichent « DONNÉE NON DISPONIBLE », and le score est calculé avec les sources disponibles.')

    pdf.subsection('UC-002 — Consulter le PDF deep-dive')
    pdf.body('Acteur : ACT-001 | Déclencheur : Clic « View Full Report » | Précondition : Analyse complète disponible')
    pdf.scenario('Scénario nominal (AC-004)',
        'Given une analyse de NVDA est terminée. When l\'utilisateur clique « View Full Report ». Then un PDF s\'ouvre dans le navigateur, and le PDF contient les 5 sections majeures (Synthèse, Scoring, Finances, Management, Risques), and le header bar est dark (#2A2A2A), and les callout boxes bleues (#2563EB) sont visibles.')
    pdf.scenario('Scénario donnée manquante (AC-005)',
        'Given l\'analyse de TSLA est terminée, and le transcript Q3 est indisponible. When l\'utilisateur ouvre le PDF. Then la section transcript affiche « DONNÉE NON DISPONIBLE », and aucune donnée n\'est inventée.')

    pdf.subsection('UC-003 — Télécharger le dossier ZIP')
    pdf.body('Acteur : ACT-001 | Déclencheur : Clic « Download ZIP » | Précondition : Analyse complète disponible')
    pdf.scenario('Scénario nominal (AC-006)',
        'Given une analyse de NVDA est terminée. When l\'utilisateur clique « Download ZIP ». Then un fichier .zip est téléchargé, and le ZIP contient au minimum : deep_dive_report.pdf, analysis.json, sources.json.')

    pdf.subsection('UC-004 — Batch analysis')
    pdf.body('Acteur : ACT-001 | Déclencheur : Upload CSV + clic « Batch Analyze » | Précondition : CSV valide avec ≤ 10 tickers')
    pdf.scenario('Scénario nominal (AC-007)',
        'Given un CSV contenant 3 tickers (AAPL, MSFT, GOOGL). When l\'utilisateur uploade le CSV et lance le batch. Then les 3 tickers sont traités séquentiellement, and un job_id est retourné, and le statut est consultable via GET /api/batch/{job_id}/status.')

    pdf.subsection('UC-005 — Feedback et correction')
    pdf.body('Acteur : ACT-001 | Déclencheur : Envoi d\'un feedback | Précondition : Une analyse existe pour le ticker')
    pdf.scenario('Scénario nominal (AC-008)',
        'Given une analyse de NVDA avec score 32/40 est affichée. When l\'utilisateur envoie un feedback « Score surévalué, PER trop bas ». Then le feedback est horodaté (timestamp + message), and la réanalyse prend en compte le feedback.')

    pdf.subsection('UC-006 — Health check système')
    pdf.body('Acteur : ACT-003 (Veilleur automatique) | Déclencheur : Toutes les 15 minutes | Précondition : Cron job actif')
    pdf.scenario('Scénario nominal (AC-009)',
        'Given le backend tourne sur le port 8780. When le cron job appelle GET /api/health. Then le endpoint retourne 200 avec {"status":"healthy","uptime":<N>}, and si le code est ≠ 200, le script auto-recovery est déclenché.')

    # ═══════ 3. PIPELINE ═══════
    pdf.section('Pipeline d\'analyse (9 étapes)')
    pdf.body('Le pipeline exécute 9 étapes séquentielles pour chaque ticker. Chaque étape a des dépendances de sources documentées et des fallbacks en cas d\'indisponibilité.')
    pdf.table(
        ['Étape', 'ID', 'Module', 'Entrée', 'Sortie', 'Sources'],
        [
            ('1', 'PIP-001', 'Profil entreprise', 'Ticker', 'CompanyProfile', 'yfinance'),
            ('2', 'PIP-002', 'Collecte données', 'Ticker, profile', 'FinancialData', 'yfinance + Finnhub + EDGAR'),
            ('3', 'PIP-003', 'Transcripts earnings', 'Ticker', 'Transcript[]', 'Seeking Alpha + Tavily'),
            ('4', 'PIP-004', 'Dépôts SEC', 'Ticker', 'SECFilings', 'EDGAR (edgartools)'),
            ('5', 'PIP-005', 'Analyse management', 'Transcript[]', 'ManagementTone', 'LLM local/externe'),
            ('6', 'PIP-006', 'Scoring (40 pts)', 'FinancialData + Tone + Risques', 'Scoring', 'Calcul déterministe'),
            ('7', 'PIP-007', 'Synthèse LLM', 'Toutes données', 'DeepDiveReport', 'DeepSeek / GPT'),
            ('8', 'PIP-008', 'Génération PDF', 'DeepDiveReport', 'PDF (10-14p)', 'ReportLab'),
            ('9', 'PIP-009', 'Archivage', 'PDF + sources', 'ZIP + analyses/', 'Disque local'),
        ],
        [10, 22, 34, 30, 30, 44]
    )

    # ═══════ 4. DATA SCHEMAS ═══════
    pdf.section('Schémas de données')

    pdf.subsection('4.1  Scoring (40 points)')
    pdf.body('Le scoring est calculé de manière déterministe à partir des données collectées. Aucun ML — règles explicites et auditables.')
    pdf.code_block(
        'Scoring {\n'
        '    total:               int ∈ [0, 40]\n'
        '    financial_health:    int ∈ [0, 10]   // Dette, liquidité, cash flow\n'
        '    growth:              int ∈ [0, 10]   // Croissance CA, BNA\n'
        '    valuation:           int ∈ [0, 8]    // PER, PEG, P/B, EV/EBITDA\n'
        '    management:          int ∈ [0, 5]    // Tone analysis, insider trades\n'
        '    moat:                int ∈ [0, 4]    // Marge, part de marché\n'
        '    sentiment:           int ∈ [0, 3]    // News, analystes\n'
        '    recommendation:      enum["BUY","HOLD","SELL"]\n'
        '    summary:             str (≤ 300 car.)\n'
        '}'
    )
    pdf.info_box('Seuils de recommandation', [
        'BUY si total ≥ 28/40',
        'HOLD si total entre 18 et 27/40',
        'SELL si total < 18/40',
        'INSUFFISANT si < 3 sources valides (pas de recommandation)',
    ])

    pdf.subsection('4.2  AnalysisResult')
    pdf.code_block(
        'AnalysisResult {\n'
        '    ticker:              str (1-5 car., uppercase)\n'
        '    timestamp:           datetime (ISO 8601)\n'
        '    status:              enum["running","completed","error"]\n'
        '    score:               Scoring | null\n'
        '    company_profile:     dict\n'
        '    financial_data:      FinancialData\n'
        '    management_tone:     ManagementTone | null\n'
        '    risks:               RiskItem[] (≤ 20)\n'
        '    valuation:           ValuationData\n'
        '    sources:             Source[] (≥1, idéalement ≥5)\n'
        '    pdf_path:            str | null\n'
        '    dossier_path:        str | null\n'
        '}'
    )

    pdf.subsection('4.3  FinancialData')
    pdf.code_block(
        'FinancialData {\n'
        '    ticker:              str\n'
        '    market_cap:          float | null    // USD\n'
        '    revenue:             float | null    // TTM, USD\n'
        '    net_income:          float | null\n'
        '    eps:                 float | null\n'
        '    pe_ratio:            float | null\n'
        '    peg_ratio:           float | null\n'
        '    debt_to_equity:      float | null\n'
        '    current_ratio:       float | null\n'
        '    free_cash_flow:      float | null\n'
        '    dividend_yield:      float | null\n'
        '    revenue_growth_yoy:  float | null    // %\n'
        '    gross_margin:        float | null    // %\n'
        '    operating_margin:    float | null    // %\n'
        '}'
    )

    pdf.subsection('4.4  Source')
    pdf.code_block(
        'Source {\n'
        '    type:    enum["yfinance","finnhub","edgar","seeking_alpha",'
        '"tavily","alpha_vantage","web"]\n'
        '    name:    str\n'
        '    url:     str | null\n'
        '    retrieved_at:  datetime\n'
        '    status:  enum["success","partial","failed"]\n'
        '    data_points:   int\n'
        '}'
    )

    pdf.subsection('4.5  DeepDiveReport')
    pdf.code_block(
        'DeepDiveReport {\n'
        '    ticker:        str\n'
        '    quarter:       str           // "2025-Q3"\n'
        '    generated_at:  datetime\n'
        '    sections:      Section[]\n'
        '    metadata:      {model, tokens, cost_usd}\n'
        '}\n'
        'Section {\n'
        '    title:         str\n'
        '    content:       str           // Markdown → PDF\n'
        '    sources:       str[]\n'
        '    confidence:    enum["high","medium","low"]\n'
        '}'
    )

    pdf.subsection('4.6  Feedback')
    pdf.code_block(
        'Feedback {\n'
        '    id:              str (UUID v4)\n'
        '    ticker:          str\n'
        '    timestamp:       datetime\n'
        '    message:         str (≤ 2000 car.)\n'
        '    correction_type: enum["score","data","missing","other"]\n'
        '    processed:       bool\n'
        '    applied_at:      datetime | null\n'
        '}'
    )

    # ═══════ 5. BUSINESS RULES ═══════
    pdf.section('Règles de gestion')
    pdf.body('Les 9 règles de gestion (BR-001 à BR-009) définissent le comportement attendu du pipeline dans toutes les conditions. Chaque règle est testable et vérifiable.')
    pdf.table(
        ['ID', 'Règle', 'Condition', 'Comportement attendu', 'Test'],
        [
            ('BR-001', 'Pas d\'invention', 'Source retourne null/erreur', 'Afficher « DONNÉE NON DISPONIBLE »', '✅'),
            ('BR-002', 'Score min 3 sources', '< 3 sources valides', 'Score = null, « INSUFFISANT »', '✅'),
            ('BR-003', 'PDF 5 sections', 'Génération PDF', 'Synthèse, Scoring, Finances, Mgmt, Risques', '✅'),
            ('BR-004', 'Archivage obligatoire', 'Analyse terminée', 'Sauvegarder dans analyses/{ticker}_{ts}/', '✅'),
            ('BR-005', 'Feedback → réanalyse', 'Feedback non traité', 'Réanalyse après application feedback', '✅'),
            ('BR-006', 'Rate limit cascade', 'API retourne 429', 'Backoff 1s/2s/4s/8s, max 3 retries', '✅'),
            ('BR-007', 'Timeout source', '> 30s sans réponse', 'Abandonner source, continuer avec autres', '✅'),
            ('BR-008', 'Batch max 10 tickers', 'Batch upload', 'Rejeter si > 10 avec message erreur', '✅'),
            ('BR-009', 'Cache invalidation', 'Cache > 1h ou refresh forcé', 'Invalider et re-collecter', '✅'),
        ],
        [16, 36, 40, 48, 10]
    )

    # ═══════ 6. NFR ═══════
    pdf.section('Exigences non fonctionnelles')
    pdf.table(
        ['ID', 'Catégorie', 'Exigence', 'Cible', 'Mesure'],
        [
            ('NFR-001', 'Performance', 'Analyse complète', '< 5 min', 'Chrono pipeline'),
            ('NFR-002', 'Performance', 'Affichage PDF', '< 2 s', 'Latence HTTP'),
            ('NFR-003', 'Disponibilité', 'API health', '99% uptime', 'Health check (15 min)'),
            ('NFR-004', 'Sécurité', 'Auth write endpoints', 'X-API-Key obligatoire', '401 si absent'),
            ('NFR-005', 'Fiabilité', 'Données manquantes', 'Pas d\'invention', 'Audit visuel PDF'),
            ('NFR-006', 'Observabilité', 'Logs structurés', 'Tous endpoints + pipeline', 'JSON logs + timestamp'),
            ('NFR-007', 'Résilience', 'Rate limit APIs', 'Retry/backoff auto', 'BR-006'),
            ('NFR-008', 'Maintenabilité', 'Couverture de tests', '≥ 60% pipeline', 'pytest --cov'),
            ('NFR-009', 'Sécurité', 'Secrets', '.env uniquement, .gitignore', 'Scan pre-commit'),
        ],
        [22, 28, 42, 28, 50]
    )

    # ═══════ 7. OBSERVABILITÉ ═══════
    pdf.section('Observabilité et audit')

    pdf.subsection('7.1  Événements de log')
    pdf.body('Chaque étape du pipeline émet un événement de log structuré avec niveau, champs et contexte. Les logs permettent de reconstituer l\'intégralité du cycle de vie d\'une analyse sans accéder au serveur.')
    pdf.table(
        ['Événement', 'Niveau', 'Champs', 'Trigger'],
        [
            ('pipeline.start', 'INFO', 'ticker, timestamp', 'Début analyse'),
            ('pipeline.step', 'INFO', 'ticker, step (1-9), duration_ms', 'Fin de chaque étape'),
            ('pipeline.complete', 'INFO', 'ticker, total_ms, score, sources', 'Analyse terminée'),
            ('pipeline.error', 'ERROR', 'ticker, step, error_type, msg', 'Erreur étape'),
            ('source.fetch', 'DEBUG', 'source_type, ticker, ms, status', 'Après appel API'),
            ('source.rate_limit', 'WARN', 'source_type, retry_after_ms', 'API retourne 429'),
            ('pdf.render', 'INFO', 'ticker, pages, size_kb, ms', 'PDF généré'),
            ('api.request', 'INFO', 'method, path, status, ms', 'Chaque requête HTTP'),
        ],
        [38, 14, 62, 56]
    )

    pdf.subsection('7.2  Métriques exposées')
    pdf.table(
        ['Métrique', 'Endpoint', 'Type'],
        [
            ('Uptime secondes', '/api/health', 'HealthResponse'),
            ('Nombre sources par ticker', '/api/traceability/{ticker}', 'JSON'),
            ('Statut batch job', '/api/batch/{job_id}/status', 'JSON'),
            ('Recherches récentes', '/api/admin/recent-searches', 'JSON'),
            ('Stats recherche', '/api/admin/search-stats', 'JSON'),
        ],
        [60, 70, 40]
    )

    # ═══════ 8. PRIVACY ═══════
    pdf.section('Politique de confidentialité')
    pdf.body('Le pipeline utilise des LLM externes pour la synthèse narrative (étape 7). Les données transmises sont exclusivement des données financières publiques (ticker, chiffres trimestriels, transcripts publics). Aucune donnée personnelle (PII) n\'est incluse dans les prompts.')
    pdf.table(
        ['ID', 'Principe', 'Implémentation'],
        [
            ('PR-001', 'Données transmises au LLM', 'Uniquement données publiques (SEC, transcripts, prix de marché)'),
            ('PR-002', 'Pas de PII', 'Aucune donnée personnelle dans les prompts LLM'),
            ('PR-003', 'Secrets API', 'Stockés dans .env, jamais transmis aux LLM'),
            ('PR-004', 'Logs', 'Ne contiennent pas les prompts LLM complets (résumé seulement)'),
            ('PR-005', 'Cache local', 'Stocké dans backend/cache/, effaçable sans impact fonctionnel'),
            ('PR-006', 'Réversibilité', 'Toute analyse peut être regénérée (données sources conservées)'),
            ('PR-007', 'Consentement', 'Usage personnel uniquement, pas de partage avec des tiers'),
        ],
        [22, 52, 96]
    )

    # ═══════ 9. RETENTION & RECOVERY ═══════
    pdf.section('Rétention et restauration')

    pdf.subsection('9.1  Rétention des analyses')
    pdf.table(
        ['Artefact', 'Emplacement', 'Rétention'],
        [
            ('Analyse JSON', 'analyses/{ticker}_{timestamp}/', 'Illimitée (disque local)'),
            ('PDF deep-dive', 'analyses/{ticker}_{timestamp}/', 'Illimitée'),
            ('ZIP dossier complet', 'analyses/{ticker}_{timestamp}/', 'Illimitée'),
            ('Cache financier', 'backend/cache/', 'Volatil (invalidé sur refresh)'),
            ('Logs', 'backend/logs/', 'Rotation manuelle'),
        ],
        [48, 72, 50]
    )

    pdf.subsection('9.2  Modes de défaillance et procédures de récupération')
    pdf.body('Le système est conçu pour la résilience : chaque mode de défaillance a une procédure de récupération documentée avec un délai cible.')
    pdf.table(
        ['Défaillance', 'Symptôme', 'Récupération', 'Délai'],
        [
            ('Tunnel CF down', 'HTTP 530/1033', 'systemctl --user restart cloudflared-tunnel', '< 2 min'),
            ('Backend down', 'Connection refused :8780', 'uvicorn main:app --port 8780', '< 5 min'),
            ('API source rate limit', '429', 'Backoff exponentiel automatique', '< 30s'),
            ('API source down', 'Timeout 30s', 'Skip source, continuer ≥ 3 sources', 'Auto'),
            ('Build frontend manquant', '404 JS/CSS', 'cd frontend && npm run build', '< 2 min'),
            ('Double prefix CF', '/stock-analysis/stock-analysis/', 'Accéder via sa.cedlabusa.net/', 'Immédiat'),
            ('Port 8780 occupé', 'Address already in use', 'lsof -i :8780 → kill <PID>', '< 1 min'),
            ('Mémoire WSL saturée', 'OOM kill', 'wsl --shutdown + redémarrage', '< 3 min'),
            ('Crash pipeline', 'Erreur 500', 'Supprimer analyse partielle, relancer', '—'),
        ],
        [30, 42, 62, 16]
    )

    pdf.subsection('9.3  Vérification post-restauration')
    pdf.code_block(
        '# 1. Backend health\n'
        'curl -s -w "%{http_code}" https://sa.cedlabusa.net/api/health\n'
        '\n'
        '# 2. Frontend reachable\n'
        'browser_navigate → https://sa.cedlabusa.net\n'
        '\n'
        '# 3. Analyse test\n'
        'saisir "AAPL" → lancer analyse → vérifier PDF + ZIP'
    )

    # ═══════ 10. CONSTRAINTS ═══════
    pdf.section('Contraintes')
    pdf.body('Le pipeline opère dans un environnement contraint (APIs gratuites, WSL2, Cloudflare Tunnel). Ces contraintes sont documentées pour anticiper les limitations.')
    pdf.table(
        ['ID', 'Contrainte', 'Type', 'Impact'],
        [
            ('C-001', 'yfinance ~5 req/s informel', 'Technique', 'Délai entre tickers batch'),
            ('C-002', 'Finnhub free tier (60 req/min)', 'Source', 'Limitation collecte news/earnings'),
            ('C-003', 'Alpha Vantage free (25 req/j)', 'Source', 'Transcripts limités'),
            ('C-004', 'Tavily API (1000 req/mois)', 'Source', 'IR enrichment limité'),
            ('C-005', 'Cloudflare Tunnel exposition', 'Sécurité', 'Auth X-API-Key obligatoire'),
            ('C-006', 'WSL2 backend uniquement', 'Déploiement', 'Pas de containerisation, pas de scaling'),
            ('C-007', 'React buildé en bundle JS', 'Frontend', 'Cache-busting obligatoire'),
            ('C-008', 'Seeking Alpha HTML scraping', 'Source', 'Fragile, dépend structure HTML'),
        ],
        [22, 58, 24, 66]
    )

    # ═══════ 11. RISKS ═══════
    pdf.section('Risques et décisions')

    pdf.subsection('11.1  Risques identifiés')
    pdf.risk_item('RSK-001', 'Medium', 'API Seeking Alpha bloque le scraping',
        'L\'API Seeking Alpha peut bloquer le scraping HTML à tout moment, rendant les transcripts indisponibles.',
        'Fallback Alpha Vantage + Tavily pour les transcripts. Diversification des sources.')
    pdf.risk_item('RSK-002', 'Low', 'yfinance change l\'API',
        'L\'API non documentée de yfinance peut changer sans préavis, cassant la collecte de données fondamentales.',
        'Finnhub + EDGAR en fallback pour les données critiques. Monitoring des changements d\'API.')
    pdf.risk_item('RSK-003', 'Low', 'Double bookkeeping financier',
        'Les données enrichies par SEC EDGAR mettaient à jour financials (modèle Pydantic) mais pas fin (dict utilisé par le scorer), produisant des scores erronés.',
        'Fixé (commit 3cf8f9b) : sync automatique EDGAR → financials ET fin. Test de régression en place.')
    pdf.risk_item('RSK-004', 'Low', 'Quick tunnel au lieu de named tunnel',
        'Le tunnel Cloudflare éphémère (quick) ne sert pas le domaine stable sa.cedlabusa.net.',
        'Auto-recovery détecte le quick tunnel et bascule automatiquement sur le named tunnel.')
    pdf.risk_item('RSK-005', 'Low', 'Indentation bug PDF renderer',
        'L\'ajout d\'une fonction helper après la fonction render avec un corps indenté de 4 espaces peut absorber le code de fermeture dans la fonction helper, rendant le renderer silencieusement None.',
        'Fixé (commit af2b3df) : toutes les fonctions helper définies AVANT la fonction render. Linter configuré.')
    pdf.risk_item('RSK-006', 'Medium', 'Mémoire WSL insuffisante',
        'WSL2 a une mémoire limitée. Au-delà de 3 batchs simultanés, risque de OOM kill par Windows.',
        'Batch limité à 10 tickers max. Nettoyage après chaque analyse. Surveillance mémoire.')

    pdf.subsection('11.2  Décisions d\'architecture')
    pdf.bullet('ADR-001 : Stack Python/FastAPI + React/Vite + ReportLab + Cloudflare Tunnel — choisi pour la rapidité de développement et le déploiement sans infrastructure cloud.')
    pdf.bullet('ADR-002 : Scoring rules-based (40 pts, 6 catégories) plutôt que ML — choisi pour l\'auditabilité et la transparence. Chaque point du score est traçable jusqu\'à sa source.')

    # ═══════ 12. ACCEPTANCE CRITERIA ═══════
    pdf.section('Critères d\'acceptation globaux')
    pdf.table(
        ['ID', 'Critère', 'Méthode', 'Seuil'],
        [
            ('GA-001', 'Analyse NVDA complète', 'Chronomètre', '< 5 min'),
            ('GA-002', 'PDF ≥ 10 pages, émojis visibles', 'Audit visuel', '100% des pages'),
            ('GA-003', 'ZIP contient PDF + analysis.json + sources.json', 'Extraction manuelle', '3 fichiers min'),
            ('GA-004', 'API health retourne 200', 'curl -s -w "%{http_code}"', '200'),
            ('GA-005', 'Tests pipeline passent', 'pytest tests/ -v', '0 échec'),
            ('GA-006', 'Aucune donnée inventée', 'Audit sources vs PDF', '0 invention'),
            ('GA-007', 'Frontend accessible', 'browser_navigate', 'Page load < 5s'),
            ('GA-008', 'Feedback enregistré', 'POST /api/feedback → GET /api/admin/feedback', 'Message horodaté'),
            ('GA-009', 'Erreur ticker invalide', 'Saisir ZZZZYX', 'Message erreur < 30s'),
            ('GA-010', 'Rate limit géré', 'Simuler 429 yfinance', 'Retry auto, skip après 3'),
        ],
        [22, 58, 50, 40]
    )

    # ═══════ 13. GLOSSARY ═══════
    pdf.section('Glossaire')
    pdf.glossary([
        ('Ticker', 'Symbole boursier (ex: AAPL, NVDA, MSFT) — 1 à 5 caractères, uppercase.'),
        ('Deep-dive', 'Analyse narrative enrichie générée par LLM à partir des données financières collectées.'),
        ('Scoring', 'Note sur 40 points répartis en 6 catégories, déterminant la recommandation BUY/HOLD/SELL.'),
        ('BUY', 'Recommandation d\'achat — score ≥ 28/40.'),
        ('HOLD', 'Recommandation de conservation — score entre 18 et 27/40.'),
        ('SELL', 'Recommandation de vente — score < 18/40.'),
        ('INSUFFISANT', 'Pas de recommandation — moins de 3 sources de données valides.'),
        ('EDGAR', 'Electronic Data Gathering, Analysis, and Retrieval — base de dépôts SEC (USA).'),
        ('Callout box', 'Encadré coloré dans le PDF mettant en valeur une information clé (bleu #2563EB).'),
        ('Quick tunnel', 'Tunnel Cloudflare éphémère sans nom de domaine stable (debug uniquement).'),
        ('Named tunnel', 'Tunnel Cloudflare permanent avec nom de domaine configuré (production).'),
        ('CacheBustingStaticFiles', 'Classe FastAPI qui ajoute Cache-Control: no-cache aux fichiers statiques.'),
        ('Finnhub', 'API financière US gratuite (60 req/min) — prix, secteurs, market cap, actualités.'),
        ('Seeking Alpha', 'Plateforme d\'analyse financière — transcripts de earnings calls (scraping HTML).'),
        ('Tavily', 'API de recherche web optimisée pour AI agents (1000 req/mois gratuites).'),
        ('Alpha Vantage', 'API financière gratuite (25 req/jour) — données fondamentales et transcripts.'),
    ])

    # ═══════ SAVE ═══════
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT_PDF))
    print(f'✅ PDF generated: {OUTPUT_PDF} ({pdf.page_no()} pages)')


if __name__ == '__main__':
    build()
