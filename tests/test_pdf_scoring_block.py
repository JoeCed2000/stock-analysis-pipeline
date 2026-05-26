"""Tests for generate_pdf() scoring block rendering.

Covers: 6 canonical scoring categories with bars, decision badge visible.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from backend.models import AnalysisResult, FinancialData, Scoring
from backend.pdf_generator import generate_pdf, _bar


# ── Fixtures ──────────────────────────────────────────────────────────────

def _sample_result(decision: str = "BUY", conviction: str = "High") -> AnalysisResult:
    """Build a minimal AnalysisResult with all 6 scoring categories populated."""
    return AnalysisResult(
        ticker="AAPL",
        company_name="Apple Inc.",
        retrieved_at="2026-05-25",
        price_native=210.50,
        currency="USD",
        market_cap=3_200_000_000_000,
        sector="Technology",
        financials=FinancialData(),
        scoring=Scoring(
            financial_health=8,
            growth=7,
            valuation=6,
            management=4,
            moat=3,
            sentiment=2,
        ),
        decision=decision,
        conviction=conviction,
        key_phrase="Strong ecosystem moat with growing services revenue.",
    )


# ── _bar() unit tests ────────────────────────────────────────────────────

def test_bar_zero():
    """Zero score = all empty blocks."""
    assert _bar(0, 5) == "░░░░░"


def test_bar_full():
    """Max score = all filled blocks."""
    assert _bar(5, 5) == "█████"


def test_bar_partial():
    """Partial score renders proportional fill."""
    result = _bar(3, 5)
    assert result == "███░░"


def test_bar_clamped_negative():
    """Negative score clamps to 0."""
    assert _bar(-2, 5) == "░░░░░"


def test_bar_clamped_exceed():
    """Score > max clamps to max."""
    assert _bar(7, 5) == "█████"


def test_bar_custom_max():
    """Custom max value works for all 6 categories."""
    assert len(_bar(3, 10)) == 10
    assert len(_bar(6, 8)) == 8
    assert len(_bar(2, 4)) == 4
    assert len(_bar(1, 3)) == 3


# ── PDF scoring block tests ──────────────────────────────────────────────


def test_pdf_scoring_block_has_6_categories():
    """Generated PDF contains all 6 weighted category names."""
    result = _sample_result()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    try:
        generate_pdf(result, "", pdf_path)
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0

        # Extract PDF text via pymupdf (fitz)
        import fitz
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() or ""

        # All 6 categories must appear
        categories = ["Growth", "Financial Health", "Valuation", "Management", "Moat", "Sentiment"]
        for cat in categories:
            assert cat in full_text, f"Missing scoring category: {cat}"

        # Total line must show /40
        assert "/40" in full_text

    finally:
        os.unlink(pdf_path)


def test_pdf_decision_badge_visible():
    """Generated PDF shows decision badge (BUY/HOLD/SELL) at top."""
    result = _sample_result(decision="BUY", conviction="High")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    try:
        generate_pdf(result, "", pdf_path)
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0

        import fitz
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() or ""

        # Decision badge visible
        assert "BUY" in full_text
        assert "Score:" in full_text
        assert "Conviction: High" in full_text

        # Verify decision appears early (first page)
        page1_text = doc[0].get_text() or ""
        assert "BUY" in page1_text, "Decision badge should be on first page"

    finally:
        os.unlink(pdf_path)


def test_pdf_scoring_total_matches_model():
    """Scoring.total (30) appears in PDF as 30/40."""
    result = _sample_result()
    assert result.scoring.total == 30  # 8+7+6+4+3+2 = 30

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    try:
        generate_pdf(result, "", pdf_path)
        import fitz
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() or ""

        assert "30/40" in full_text
    finally:
        os.unlink(pdf_path)


def test_pdf_hold_decision_badge():
    """HOLD decision appears in PDF."""
    result = _sample_result(decision="HOLD", conviction="Medium")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        generate_pdf(result, "", pdf_path)
        import fitz
        doc = fitz.open(pdf_path)
        full_text = doc[0].get_text() or ""
        assert "HOLD" in full_text
    finally:
        os.unlink(pdf_path)


def test_pdf_sell_decision_badge():
    """SELL decision appears in PDF."""
    result = _sample_result(decision="SELL", conviction="Weak")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        generate_pdf(result, "", pdf_path)
        import fitz
        doc = fitz.open(pdf_path)
        full_text = doc[0].get_text() or ""
        assert "SELL" in full_text
    finally:
        os.unlink(pdf_path)
