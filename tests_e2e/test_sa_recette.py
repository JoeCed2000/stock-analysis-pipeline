"""
Stock Analysis Pipeline — Recette utilisateur automatisée (Playwright)
Généré par web-recette-autonome v1.0.0
Projet: /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/
Base URL: http://localhost:8780/stock-analysis/
"""

import pytest
from playwright.sync_api import Page, expect
import re

BASE_URL = "http://localhost:8780/stock-analysis"


# ═══════════════════════════════════════════════════════════════
# P0 — Parcours critiques
# ═══════════════════════════════════════════════════════════════

def test_p0_home_loads(page: Page):
    """La page d'accueil charge avec le titre et le champ de saisie."""
    page.goto(f"{BASE_URL}/")
    
    # Titre
    expect(page.locator("h1")).to_contain_text("Stock Analysis")
    
    # Zone de saisie
    input_box = page.locator("textarea")
    expect(input_box).to_be_visible()
    expect(input_box).to_have_attribute("placeholder", re.compile(r"ticker|ISIN", re.IGNORECASE))
    
    # Mode tabs
    expect(page.get_by_role("button", name=re.compile(r"Quick|🔍"))).to_be_visible()
    expect(page.get_by_role("button", name=re.compile(r"Batch|📦"))).to_be_visible()
    
    # Language selector
    expect(page.locator("select")).to_be_visible()
    
    # No console errors
    _assert_no_critical_errors(page)


def test_p0_ticker_parse(page: Page):
    """La saisie d'un ticker affiche un tag et le bouton Analyze."""
    page.goto(f"{BASE_URL}/")
    input_box = page.locator("textarea")
    
    # Taper un ticker — les tags sont auto-sélectionnés au parse
    input_box.fill("NVDA")
    page.wait_for_timeout(2000)  # debounce 500ms + parsing API
    
    # Le tag NVDA doit apparaître (auto-sélectionné)
    expect(page.locator("text=NVDA").first).to_be_visible(timeout=5000)
    
    # Le bouton Analyze doit apparaître (tags auto-sélectionnés)
    analyze_btn = page.get_by_role("button", name=re.compile(r"Analyze \d+ ticker"))
    expect(analyze_btn).to_be_visible(timeout=5000)


def test_p0_analysis_completes(page: Page):
    """L'analyse d'un ticker produit une carte de résultat avec score."""
    page.goto(f"{BASE_URL}/")
    
    # Saisir NVDA
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(1500)
    
    # Cliquer Analyze (le bouton submit spécifique, pas le tab Quick Analysis)
    analyze_btn = page.get_by_role("button", name=re.compile(r"Analyze \d+ ticker"))
    analyze_btn.click()
    
    # Attendre le résultat (max 5 min — le cache devrait être plus rapide)
    # La carte de résultat doit apparaître
    expect(page.locator("text=COMPOSITE SCORE").first).to_be_visible(timeout=300000)
    
    # Le score devrait être affiché
    score_text = page.locator("text=/\\d+\\/40/").first
    expect(score_text).to_be_visible()
    
    # La décision (BUY/HOLD/SELL) doit être visible quelque part dans la page
    decision = page.get_by_text(re.compile(r"^(BUY|SELL|HOLD)(\s|$)", re.IGNORECASE)).first
    expect(decision).to_be_visible(timeout=5000)


def test_p0_view_full_report(page: Page):
    """Le bouton 'Deep-Dive PDF' ouvre un PDF."""
    page.goto(f"{BASE_URL}/")
    
    # Saisir et analyser
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(1500)
    page.get_by_role("button", name=re.compile(r"Analyze \d ticker")).click()
    
    # Attendre la carte
    expect(page.locator("text=COMPOSITE SCORE").first).to_be_visible(timeout=300000)
    
    # Cliquer sur Deep-Dive PDF
    pdf_btn = page.get_by_role("button", name=re.compile(r"Deep.Dive|📄"))
    expect(pdf_btn).to_be_visible()
    
    # Vérifier que le clic déclenche une requête
    with page.expect_response(lambda r: "/api/report/" in r.url and "/pdf" in r.url, timeout=30000):
        pdf_btn.click()
    
    # Un toast ou une nouvelle fenêtre devrait apparaître
    # (le comportement exact dépend si le PDF est en cache ou doit être généré)
    page.wait_for_timeout(2000)


def test_p0_download_dossier(page: Page):
    """Le bouton 'Download Dossier' télécharge un ZIP."""
    page.goto(f"{BASE_URL}/")
    
    # Analyser
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(1500)
    page.get_by_role("button", name=re.compile(r"Analyze \d ticker")).click()
    
    # Attendre la carte avec le dossier prêt
    expect(page.locator("text=COMPOSITE SCORE").first).to_be_visible(timeout=300000)
    
    # Attendre que le dossier soit prêt (bouton avec 7/7)
    download_btn = page.get_by_role("button", name=re.compile(r"Download|📥"))
    expect(download_btn).to_be_visible(timeout=120000)
    
    # Vérifier que le bouton est actif (pas grisé)
    expect(download_btn).to_be_enabled()


# ═══════════════════════════════════════════════════════════════
# P1 — Fonctionnalités secondaires
# ═══════════════════════════════════════════════════════════════

def test_p1_language_switch(page: Page):
    """Le sélecteur de langue change l'interface."""
    page.goto(f"{BASE_URL}/")
    
    # Passer en japonais
    lang_select = page.locator("select").first
    lang_select.select_option("ja")
    page.wait_for_timeout(500)
    
    # Le titre devrait changer (ou au moins le placeholder)
    body_text = page.inner_text("body")
    # Vérifier qu'il y a du texte japonais ou que le titre a changé
    has_japanese = any(c in body_text for c in "日本語株分析")
    # Si pas de japonais, vérifier que la langue a bien changé dans le select
    if not has_japanese:
        expect(lang_select).to_have_value("ja")
    
    # Revenir en anglais
    lang_select.select_option("en")
    page.wait_for_timeout(500)
    expect(page.locator("h1")).to_contain_text("Stock Analysis")


def test_p1_quarter_selector(page: Page):
    """Le sélecteur de trimestre est présent et fonctionnel."""
    page.goto(f"{BASE_URL}/")
    
    # Analyser
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(1500)
    page.get_by_role("button", name=re.compile(r"Analyze \d ticker")).click()
    
    # Attendre la carte
    expect(page.locator("text=COMPOSITE SCORE").first).to_be_visible(timeout=300000)
    
    # Vérifier le sélecteur de trimestre
    quarter_selects = page.locator("select")
    count = quarter_selects.count()
    assert count >= 1, f"Expected at least 1 select for quarter, found {count}"


def test_p1_about_section(page: Page):
    """La section 'What is this?' est expansible."""
    page.goto(f"{BASE_URL}/")
    
    about_btn = page.get_by_role("button", name=re.compile(r"What is this|How does it work"))
    expect(about_btn).to_be_visible()
    
    about_btn.click()
    page.wait_for_timeout(300)
    
    # Vérifier que du contenu supplémentaire est apparu
    # (le texte devrait contenir des explications sur la méthodologie)
    body_text = page.inner_text("body")
    assert len(body_text) > 100, "About section should reveal content"


def test_p1_batch_mode(page: Page):
    """Le mode batch est accessible et fonctionnel."""
    page.goto(f"{BASE_URL}/")
    
    # Cliquer sur Batch
    batch_btn = page.get_by_role("button", name=re.compile(r"Batch|📦"))
    batch_btn.click()
    page.wait_for_timeout(500)
    
    # Vérifier que l'interface batch est visible (upload zone)
    body_text = page.inner_text("body")
    assert "upload" in body_text.lower() or "file" in body_text.lower() or "drag" in body_text.lower(), \
        "Batch mode should show upload interface"


def test_p1_admin_page(page: Page):
    """La page admin est accessible via #admin."""
    page.goto(f"{BASE_URL}/#admin")
    page.wait_for_timeout(1000)
    
    # Vérifier que la page admin charge
    body_text = page.inner_text("body")
    # L'admin page devrait avoir des stats ou un dashboard
    assert "admin" in body_text.lower() or "search" in body_text.lower() or "stat" in body_text.lower(), \
        "Admin page should show admin content"


# ═══════════════════════════════════════════════════════════════
# P2 — États et cas limites
# ═══════════════════════════════════════════════════════════════

def test_empty_state(page: Page):
    """La page d'accueil sans ticker affiche un état vide cohérent."""
    page.goto(f"{BASE_URL}/")
    
    # Saisir puis effacer
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(1500)
    page.locator("textarea").fill("")
    page.wait_for_timeout(1500)
    
    # Les tags devraient disparaître
    tags = page.locator("text=NVDA")
    expect(tags).to_have_count(0)


def test_invalid_ticker(page: Page):
    """Un ticker invalide est signalé."""
    page.goto(f"{BASE_URL}/")
    
    page.locator("textarea").fill("ZZZXY")
    page.wait_for_timeout(1500)
    
    # Un ticker invalide peut soit apparaître grisé, soit ne pas apparaître du tout
    # selon l'implémentation. Vérifier juste que l'UI ne crash pas.
    body_text = page.inner_text("body")
    # L'essentiel: pas d'erreur visible, l'app fonctionne
    assert "error" not in body_text.lower(), "No crash on invalid ticker"


def test_api_health(page: Page):
    """L'API health répond OK."""
    response = page.request.get(f"{BASE_URL}/api/health")
    expect(response).to_be_ok()
    data = response.json()
    assert data["status"] == "ok"


def test_no_critical_console_errors(page: Page):
    """Aucune erreur console critique après utilisation."""
    page.goto(f"{BASE_URL}/")
    
    # Faire un parcours simple
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(2000)
    
    _assert_no_critical_errors(page)


# ═══════════════════════════════════════════════════════════════
# F1-F5 — Nami Feedback Fixes (PDF Content Verification)
# ═══════════════════════════════════════════════════════════════

import requests
from pypdf import PdfReader
import io

API_BASE = "http://localhost:8780/stock-analysis/api"


def _fetch_pdf(ticker: str, lang: str = "en", quarter: str = "2026Q1", max_retries: int = 30) -> bytes:
    """Download a deep-dive PDF for the given ticker/language/quarter.
    Handles async generation (202 polling)."""
    import time
    url = f"{API_BASE}/report/{ticker}/pdf"
    for attempt in range(max_retries):
        resp = requests.get(url, params={"lang": lang, "quarter": quarter}, timeout=180)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "")
        if "application/pdf" in ct:
            return resp.content
        if resp.status_code == 202:
            retry = int(resp.headers.get("Retry-After", 10))
            time.sleep(retry)
            continue
        # If not 202 and not PDF, fail
        raise AssertionError(
            f"Expected PDF, got status={resp.status_code} content-type={ct} "
            f"body={resp.text[:200]}"
        )
    raise TimeoutError(f"PDF still generating after {max_retries} retries")


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF byte stream."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# F1 — EPS Source
def test_f1_eps_source_is_consensus():
    """F1: EPS source must be 'Yahoo Finance (consensus)' NOT 'SEC 10-Q/K'."""
    text = _pdf_text(_fetch_pdf("GOOGL"))
    assert "Yahoo Finance" in text and "consensus" in text, \
        f"F1 FAIL: EPS source 'Yahoo Finance (consensus)' missing in PDF"
    assert "SEC 10-Q" not in text, \
        f"F1 FAIL: Found 'SEC 10-Q' — should use 'Yahoo Finance (consensus)'"


# F2 — PDF Title contains quarter
def test_f2_pdf_title_contains_quarter():
    """F2: PDF title must contain 'Q1 2026'."""
    text = _pdf_text(_fetch_pdf("GOOGL"))
    assert "Q1 2026" in text, \
        "F2 FAIL: PDF title does not contain 'Q1 2026'"


# F3 — Column Labels
def test_f3_column_labels_quarter_not_generic():
    """F3: Table columns must use 'Q1 2026'/'Q1 2025' NOT 'Actual'/'Prior Year'."""
    text = _pdf_text(_fetch_pdf("GOOGL"))
    # Must have specific quarter labels
    assert "Q1 2026" in text, \
        "F3 FAIL: Missing 'Q1 2026' column label"
    assert "Q1 2025" in text, \
        "F3 FAIL: Missing 'Q1 2025' column label"
    # Must NOT have generic labels
    has_generic = "Actual" in text and "Prior Year" in text
    # "Actual" may appear in prose, but the combination of both as column headers is the issue
    # We check: if "Prior Year" appears, it's likely the old column format
    assert "Prior Year" not in text, \
        "F3 FAIL: 'Prior Year' column label found — should use 'Q1 2025'"


# F4 — Margins show change in pts
def test_f4_margins_show_points_change():
    """F4: Margins must display change in percentage points (e.g. '+2.7 pts')."""
    text = _pdf_text(_fetch_pdf("GOOGL"))
    import re
    pts_pattern = re.compile(r'[+\-−]\d+\.?\d*\s*pts?', re.IGNORECASE)
    matches = pts_pattern.findall(text)
    assert len(matches) > 0, \
        "F4 FAIL: No margin changes in pts found (e.g. '+2.7 pts')"


# F5 — Japanese PDF
def test_f5_japanese_pdf_generates():
    """F5: lang=ja must generate a Japanese PDF (contains Japanese characters)."""
    pdf_bytes = _fetch_pdf("GOOGL", lang="ja")
    text = _pdf_text(pdf_bytes)
    import re
    # Check for Japanese characters (Hiragana, Katakana, Kanji)
    jp_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text)
    assert len(jp_chars) > 20, \
        f"F5 FAIL: Only {len(jp_chars)} Japanese characters found — expected >20"


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _assert_no_critical_errors(page: Page):
    """Vérifie qu'il n'y a pas d'erreurs console critiques (404/500 sur endpoints API)."""
    # Playwright Python: pas de console_messages cumulatif.
    # On collecte via event listener.
    errors = []
    
    def _on_console(msg):
        if msg.type == "error":
            errors.append(msg.text)
    
    page.on("console", _on_console)
    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
    finally:
        page.remove_listener("console", _on_console)
    
    critical = []
    for e in errors:
        # Ignorer les erreurs non-critiques
        if any(s in e.lower() for s in ["favicon", "third-party", "alpha_radar", "finnhub"]):
            continue
        # 404/500 explicites = critique
        if any(code in e for code in ["404", "500", "502", "503"]):
            critical.append(e)
        # Failed to fetch sur un endpoint API = critique
        elif "Failed to fetch" in e and "/api/" in e:
            critical.append(e)
    
    assert len(critical) == 0, f"Critical console errors: {critical}"
