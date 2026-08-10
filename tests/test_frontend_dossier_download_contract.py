from pathlib import Path


ANALYSIS_CARD = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "components"
    / "AnalysisCard.jsx"
)

APP = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "App.jsx"
)

API = Path(__file__).resolve().parents[1] / "frontend" / "src" / "api.js"


def test_dossier_download_requests_latest_verified_artifact():
    source = ANALYSIS_CARD.read_text(encoding="utf-8")
    assert "getTickerDownloadUrl(ticker, lang, selectedQuarter)" not in source
    assert "getTickerDownloadUrl(ticker, lang)" in source


def test_pdf_tab_is_claimed_during_the_user_gesture_before_any_await():
    """Popup blockers swallow a window.open that runs after an await.

    The invariant is *when* the tab is claimed, not how it is filled. Asserting
    the literal `window.open(pdfUrl, '_blank', 'noopener')` over-specified the
    implementation and forced two regressions: `noopener` makes window.open
    return null, so the `if (!reportWindow)` branch fired a bogus "allow
    pop-ups" warning on every successful open; and navigating straight to
    pdfUrl dropped the 422/pdf_blocked handling and the MAX_PDF_POLL_ATTEMPTS
    cap that WIKI.md 2026-05-31 records as delivered (frontend/src/
    App.pdfBlocked.test.cjs guards the other half of that contract).
    """
    source = APP.read_text(encoding="utf-8")
    report_handler = source[source.index("const handleViewReport"):source.index("const handleAnalyze")]

    assert "window.open(" in report_handler, "the report tab must be opened by this handler"
    # "await fetch(" rather than bare "await ", which also matches prose in comments.
    assert report_handler.index("window.open(") < report_handler.index("await fetch("), (
        "window.open must run before the first await, inside the user gesture"
    )
    # noopener nulls the return value, which would break the popup-blocked
    # branch below; the opener is severed by hand instead.
    assert ", 'noopener')" not in report_handler  # the call-site form, not prose about it
    assert "reportWindow.opener = null" in report_handler
    assert "if (!reportWindow)" in report_handler, "a blocked popup must still be reported"


def test_result_card_does_not_offer_calendar_quarters_for_a_fiscal_pdf():
    source = ANALYSIS_CARD.read_text(encoding="utf-8")
    assert "fetchQuarters" not in source
    assert "selectedQuarter" not in source
    assert "onViewReport(result)" in source
    assert "onViewReport(result, selectedQuarter)" not in source


def test_static_client_chip_is_not_rendered_as_a_fake_control():
    source = APP.read_text(encoding="utf-8")
    assert "📋 Client" not in source
    assert "audienceMode" in source


def test_quick_analysis_copy_distinguishes_score_latency_from_background_pdf():
    source = (
        Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n.js"
    ).read_text(encoding="utf-8")

    assert "This takes 3-5 minutes" not in source
    assert "Results usually appear in 1-2 minutes" in source
    assert "verified PDF continues building in the background" in source


def test_about_modal_decision_rules_match_backend_scoring_contract():
    source = (
        Path(__file__).resolve().parents[1] / "frontend" / "src" / "i18n.js"
    ).read_text(encoding="utf-8")

    assert 'Score ≥ 28/40' in source
    assert 'Score 18-27' in source
    assert 'Score ≥ 32/40' not in source
    assert 'Score 26-31' not in source
    assert 'Score 18-25' not in source


def test_company_overview_url_is_versioned_by_analysis_timestamp():
    api_source = API.read_text(encoding="utf-8")
    card_source = ANALYSIS_CARD.read_text(encoding="utf-8")

    assert "params.set('v', version)" in api_source
    assert "getCompanyOverviewDownloadUrl(ticker, 'auto', retrieved_at)" in card_source
