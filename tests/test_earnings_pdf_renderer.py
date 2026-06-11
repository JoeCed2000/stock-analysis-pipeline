import pytest

from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf, resolve_pdf_fonts
from backend.earnings_deep_dive.schemas import FinancialMetrics


fitz = pytest.importorskip("fitz")


def _sample_report():
    return build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(
            eps_estimate=3.10,
            eps_actual=3.46,
            eps_vs_estimate=0.116,
            eps_yoy=0.22,
            revenue_estimate=80_000_000_000,
            revenue_actual=82_900_000_000,
            revenue_yoy=0.183,
            gross_profit=56_000_000_000,
            gross_margin=0.676,
            opex=18_000_000_000,
            operating_income=38_400_000_000,
            operating_margin=0.463,
            net_income=101_800_000_000,
            operating_cash_flow=95_000_000_000,
            capex=23_400_000_000,
            free_cash_flow=71_600_000_000,
            roe=0.35,
            roic=0.28,
            pe_forward=21.19,
            guidance="Revenue growth expected to remain double-digit.",
            segments={"Cloud": {"revenue": 45_000_000_000, "yoy": 0.26}},
        ),
        transcript_url="https://example.com/msft-transcript",
    )


def test_pdf_renderer_uses_letter_page_size(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive.pdf"

    render_earnings_deep_dive_pdf(_sample_report(), pdf_path)

    doc = fitz.open(pdf_path)
    page = doc[0]
    assert round(page.rect.width, 2) == 612.00
    assert round(page.rect.height, 2) == 792.00


def test_pdf_renderer_generates_extractable_text_and_tables(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive.pdf"

    render_earnings_deep_dive_pdf(_sample_report(), pdf_path)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 10_000

    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)

    for expected in (
        "Microsoft Corporation (MSFT)",
        "EPS & Revenue",
        "Highlights",
        "Operating Metrics",
        "Cash Flow",
        "Capital Efficiency",
        "Segments",
        "Forward P/E",
        "Backlog",
        "Guidance",
        "Verdict / Overall Assessment",
        "Metric",
        "Estimate",
        "Actual",
        "Source",
    ):
        assert expected in text

    assert "GE Vernova" not in text
    assert "SanDisk" not in text


def test_pdf_renderer_generates_language_specific_japanese_report(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive_jp.pdf"
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="jp",
        metrics=FinancialMetrics(revenue_actual=82_900_000_000),
        transcript_url="https://example.com/msft-transcript",
    )

    render_earnings_deep_dive_pdf(report, pdf_path)

    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    normalized_text = " ".join(text.split())

    assert pdf_path.exists()
    assert "Microsoft Corporation (MSFT)" in text
    assert "総合評価" in text
    assert "DONNÉE NON DISPONIBLE" not in normalized_text

    # F5: Japanese labels must appear in the JP PDF
    jp_labels = [
        "決算詳細分析",       # "Earnings Deep-Dive"
        "ソース",            # "Sources"
        "決算資料",          # "Earnings Documents"
        "ソース凡例",        # "Source Legend" (client-facing legend)
        "データ & アナリティクス",  # "Data & Analytics"
        "手法",              # "Methodology"
    ]
    # Note: "主要日程" (Key Dates) is conditional — only appears when
    # next_earnings_date is present. The translation is applied when rendered.
    for label in jp_labels:
        assert label in text, f"JP PDF missing label: {label}"

    # Claim Traceability appendix is INTERNAL ONLY — verify on an internal render
    if report.claim_sources:
        internal_path = tmp_path / "earnings_deep_dive_jp_internal.pdf"
        render_earnings_deep_dive_pdf(report, internal_path, include_traceability=True)
        internal_text = "\n".join(page.get_text() for page in fitz.open(internal_path))
        for label in ("セクション別主張", "主張の追跡可能性"):
            assert label in internal_text, f"JP internal PDF missing label: {label}"


def test_pdf_renderer_resolves_model_fonts_when_available():
    english_fonts = resolve_pdf_fonts("en")
    japanese_fonts = resolve_pdf_fonts("jp")

    assert english_fonts.regular in {"Arial", "Helvetica"}
    assert english_fonts.bold in {"Arial-Bold", "Helvetica-Bold"}
    assert japanese_fonts.regular in {"MS-PGothic", "HeiseiMin-W3", "Helvetica"}


def test_pdf_renderer_has_no_tofu_or_null_bytes(tmp_path):
    """Regression test: emoji must be rendered as PIL images, not as
    raw Unicode in the PDF text stream.  Raw emoji codepoints that escape
    _paragraph_with_emojis() will produce tofu (empty squares) or null
    bytes because standard PDF fonts lack those glyphs.

    This test asserts:
      - Zero null bytes (\\x00) — the symptom of the 👉 callout bug
      - Zero Unicode replacement chars (U+FFFD) — general tofu flag
      - Zero raw emoji-range codepoints in extracted text
    """
    pdf_path = tmp_path / "earnings_deep_dive.pdf"
    render_earnings_deep_dive_pdf(_sample_report(), pdf_path)

    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        text = page.get_text()

        # ── Null bytes: primary symptom of emoji-in-Paragraph bug ──
        null_count = text.count('\x00')
        assert null_count == 0, (
            f"Page {i+1}: found {null_count} null byte(s) — "
            f"emoji character leaked into Paragraph without PIL image rendering"
        )

        # ── Unicode replacement char: generic tofu indicator ──
        replacement_count = text.count('\ufffd')
        assert replacement_count == 0, (
            f"Page {i+1}: found {replacement_count} U+FFFD replacement char(s) — "
            f"font cannot render one or more glyphs"
        )

        # ── Raw emoji-range codepoints: must be rendered as images ──
        emoji_codepoints = [
            ch for ch in text if 0x1F300 <= ord(ch) <= 0x1F9FF
        ]
        assert not emoji_codepoints, (
            f"Page {i+1}: found raw emoji codepoint(s) {emoji_codepoints!r} in extracted text — "
            f"emoji must be rendered as PIL+NotoColorEmoji images, not as text glyphs"
        )

    doc.close()
