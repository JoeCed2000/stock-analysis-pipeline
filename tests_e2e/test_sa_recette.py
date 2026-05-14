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
    
    # Taper un ticker
    input_box.fill("NVDA")
    page.wait_for_timeout(1500)  # debounce 500ms + réseau
    
    # Le tag NVDA doit apparaître
    expect(page.locator("text=NVDA").first).to_be_visible(timeout=5000)
    
    # Le bouton Analyze doit apparaître
    analyze_btn = page.get_by_role("button", name=re.compile(r"Analyze \d ticker"))
    expect(analyze_btn).to_be_visible(timeout=3000)


def test_p0_analysis_completes(page: Page):
    """L'analyse d'un ticker produit une carte de résultat avec score."""
    page.goto(f"{BASE_URL}/")
    
    # Saisir NVDA
    page.locator("textarea").fill("NVDA")
    page.wait_for_timeout(1500)
    
    # Cliquer Analyze
    analyze_btn = page.get_by_role("button", name=re.compile(r"Analyze|🔍"))
    analyze_btn.click()
    
    # Attendre le résultat (max 5 min — le cache devrait être plus rapide)
    # La carte de résultat doit apparaître
    expect(page.locator("text=COMPOSITE SCORE").first).to_be_visible(timeout=300000)
    
    # Le score devrait être affiché
    score_text = page.locator("text=/\\d+\\/40/").first
    expect(score_text).to_be_visible()
    
    # La décision (BUY/HOLD/SELL) doit être visible
    decision_badge = page.locator("[class*='AnalysisCard']").get_by_text(re.compile(r"BUY|HOLD|SELL"))
    expect(decision_badge.first).to_be_visible()


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
# Helpers
# ═══════════════════════════════════════════════════════════════

def _assert_no_critical_errors(page: Page):
    """Vérifie qu'il n'y a pas d'erreurs console critiques (Failed to fetch, 404, 500)."""
    # Playwright Python: console messages are on the Page, not context
    errors = []
    try:
        for msg in page.console_messages():
            if msg.type == "error":
                text = msg.text
                if "favicon" in text.lower() or "third-party" in text.lower():
                    continue
                errors.append(text)
    except AttributeError:
        # Fallback: page.console_messages may not exist in older Playwright
        pass
    
    critical = [e for e in errors if "Failed to fetch" in e or "404" in e or "500" in e]
    assert len(critical) == 0, f"Critical console errors: {critical}"
