from backend.company_overview_pdf import _clean_text


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
