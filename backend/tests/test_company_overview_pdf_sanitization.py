from datetime import date

from reportlab.platypus import Paragraph

from backend.company_overview_pdf import (
    _build_styles,
    _clean_text,
    _format_metric_source,
    _leadership_snapshot_cards,
    _make_table,
)


def test_clean_text_removes_internal_markers():
    raw = "LLM synthesis was unavailable and requires transcript-level validation."
    cleaned = _clean_text(raw)
    assert "LLM synthesis" not in cleaned
    assert "transcript-level validation" not in cleaned


def test_clean_text_removes_template_wrappers_and_debug_prefixes():
    raw = "<|assistant|> Revenue grew 20%. [[internal:tmp]] source: yfinance"
    cleaned = _clean_text(raw)
    assert "<|assistant|>" not in cleaned
    assert "[[internal:tmp]]" not in cleaned
    assert "source: yfinance" not in cleaned.lower()
    assert "Revenue grew 20%." in cleaned


def test_clean_text_preserves_normal_business_text():
    raw = "NVIDIA reported strong demand in data center and gaming segments."
    cleaned = _clean_text(raw)
    assert cleaned == raw


def test_leadership_cards_show_current_ceo_and_announced_successor():
    cards = _leadership_snapshot_cards(
        {
            "ceo": "Tim Cook",
            "ceo_designate": "John Ternus",
            "ceo_effective_date": "2026-09-01",
            "ceo_transition_source_url": "https://www.apple.com/newsroom/example",
        },
        as_of=date(2026, 7, 12),
    )

    assert cards[0][0] == "CEO"
    assert "Tim Cook" in cards[0][1]
    assert "Aug 31, 2026" in cards[0][1]
    assert cards[1][0] == "CEO-designate"
    assert cards[1][1] == "John Ternus (from Sep 1, 2026)"
    assert cards[1][2] == "Official company announcement"


def test_make_table_preserves_clickable_source_paragraph():
    styles = _build_styles()
    link = Paragraph(
        '<link href="https://www.apple.com/newsroom/example">Open official source</link>',
        styles["table_cell_small"],
    )

    table = _make_table(["Source"], [[link]], [120], styles)

    assert isinstance(table._cellvalues[1][0], Paragraph)
    assert '<link href="https://www.apple.com/newsroom/example">' in table._cellvalues[1][0].text


def test_metric_source_labels_are_client_safe():
    selected = _format_metric_source({
        "status": "selected",
        "selected_source": "ledger",
        "selected_path": "market_cap",
    })
    assert selected == "Company financial data"
    assert "Internal" not in selected
    assert "ledger" not in selected.lower()
    assert "market_cap" not in selected

    blocked = _format_metric_source({
        "status": "blocked",
        "reason_code": "mismatch_blocked",
    })
    assert blocked == "Under review"
    assert "Blocked" not in blocked
    assert "mismatch_blocked" not in blocked

    unavailable = _format_metric_source({
        "status": "unavailable",
        "reason_code": "source_absent",
    })
    assert unavailable == "Not disclosed"
    assert "source_absent" not in unavailable


def test_card_values_contain_no_zero_width_space():
    """U+200B has no glyph in the base-14 Helvetica fonts used by the
    overview PDF and renders as a black square (■) — 49 of them shipped in
    the 2026-06-12 NVDA investor profile ('Mr.■ Jen-■Hsun', '$4.■96T').
    ReportLab's default splitLongWords already wraps long tokens; no manual
    soft-break injection is needed."""
    from backend.company_overview_pdf import _card_value_text

    for label, value in [
        ("CEO", "Mr. Jen-Hsun Huang"),
        ("Market Cap", "$4.96T"),
        ("52W Range", "$140.85 — $236.54"),
        ("Website", "https://www.nvidia.com/en-us/investors/"),
        ("Data as of", "2026-06-12"),
    ]:
        rendered = _card_value_text(label, value)
        assert "​" not in rendered, f"{label}: ZWSP leaked into {rendered!r}"
