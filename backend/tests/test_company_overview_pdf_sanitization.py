from backend.company_overview_pdf import _clean_text, _format_metric_source


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
