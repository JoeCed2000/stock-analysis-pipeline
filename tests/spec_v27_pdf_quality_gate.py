"""Post-render PDFQA gate tests.

These tests cover defects found in the 2026-06-01 PDF audit: non-PDF JP
artifacts, visible NaN/internal source labels, insufficient links, missing
sections, and key-financial mismatches.
"""

from backend.earnings_deep_dive.pdf_quality_gate import validate_pdf_audit


def _base_artifact(**overrides):
    artifact = {
        "exists": True,
        "is_pdf": True,
        "size": 400_000,
        "pages": 25,
        "links": 8,
        "lang": {"jp_ratio": 0.0},
        "forbidden_counts": {},
        "placeholder_counts": {},
        "sections_present": {
            "Financial Metrics": True,
            "Valuation": True,
            "Operating Metrics": True,
            "Cash Flow": True,
            "Capital Efficiency": True,
            "Management": True,
            "Risks": True,
            "Sources": True,
        },
        "rendered_pages": ["/tmp/page1.png"],
        "errors": [],
    }
    artifact.update(overrides)
    return artifact


def _audit(**artifact_overrides):
    deep_en_overrides = artifact_overrides.pop("deep_en", {})
    deep_jp_overrides = {"lang": {"jp_ratio": 0.55}, **artifact_overrides.pop("deep_jp", {})}
    company_overrides = {"size": 18_000, "pages": 5, "links": 1, "lang": {"jp_ratio": 0.0}, **artifact_overrides.pop("company", {})}
    deep_en = _base_artifact(**deep_en_overrides)
    deep_jp = _base_artifact(**deep_jp_overrides)
    company = _base_artifact(**company_overrides)
    return {
        "tickers": {
            "NVDA": {
                "analysis_dir": "/tmp/NVDA_analysis",
                "artifacts": {"deep_en": deep_en, "deep_jp": deep_jp, "company": company},
                "raw_compare": artifact_overrides.pop("raw_compare", {}),
            }
        }
    }


def _defects(result, rule_id=None):
    defects = result.defects
    if rule_id:
        defects = [f for f in defects if f.rule_id == rule_id]
    return defects


def test_clean_audit_passes():
    result = validate_pdf_audit(_audit())
    assert result.passed, result.findings


def test_japanese_artifact_must_be_real_pdf_with_japanese_text():
    result = validate_pdf_audit(_audit(deep_jp={"is_pdf": False, "pages": 0, "size": 142, "lang": {"jp_ratio": 0.0}, "errors": ["FileDataError"]}))
    assert not result.passed
    assert _defects(result, "PDFQA-003")
    assert _defects(result, "PDFQA-004")
    assert _defects(result, "PDFQA-005")


def test_visible_nan_blocks_client_pdf():
    result = validate_pdf_audit(_audit(company={"forbidden_counts": {"NaN": 24}}))
    defects = _defects(result, "PDFQA-007")
    assert len(defects) == 1
    assert defects[0].observed == {"NaN": 24}


def test_internal_source_labels_block_generic_pdf():
    result = validate_pdf_audit(_audit(deep_en={"forbidden_counts": {"source: yfinance": 9, "S1": 6}}))
    defects = _defects(result, "PDFQA-008")
    assert len(defects) == 2


def test_raw_metric_keys_block_generic_pdf():
    """Real PDF defect: raw snake_case provider metric keys are internal labels."""
    result = validate_pdf_audit(
        _audit(
            deep_en={"forbidden_counts": {"eps_actual": 15, "eps_estimate": 10}},
            deep_jp={"forbidden_counts": {"revenue_yoy": 7}},
        )
    )
    defects = _defects(result, "PDFQA-008")
    observed = {marker for defect in defects for marker in (defect.observed or {})}
    assert {"eps_actual", "eps_estimate", "revenue_yoy"} <= observed


def test_nami_personalization_blocks_generic_but_allowed_in_personalized_mode():
    generic = validate_pdf_audit(_audit(deep_en={"forbidden_counts": {"Nami-san": 12}}), audience_mode="generic")
    personalized = validate_pdf_audit(_audit(deep_en={"forbidden_counts": {"Nami-san": 12}}), audience_mode="nami_personalized")
    internal = validate_pdf_audit(_audit(deep_en={"forbidden_counts": {"Nami-san": 12}}), audience_mode="internal_debug")
    assert _defects(generic, "PDFQA-006")
    assert personalized.passed
    assert personalized.allowed
    assert internal.passed
    assert [w for w in internal.warnings if w.rule_id == "PDFQA-006"]


def test_missing_sections_block_deep_dive_pdf():
    sections = {
        "Financial Metrics": True,
        "Valuation": True,
        "Operating Metrics": False,
        "Cash Flow": True,
        "Capital Efficiency": True,
        "Management": True,
        "Risks": False,
        "Sources": True,
    }
    result = validate_pdf_audit(_audit(deep_en={"sections_present": sections}))
    defects = _defects(result, "PDFQA-010")
    assert len(defects) == 1
    assert "Operating Metrics" in defects[0].observed
    assert "Risks" in defects[0].observed


def test_insufficient_source_links_blocks_pdf():
    result = validate_pdf_audit(_audit(deep_en={"links": 2}, company={"links": 0}))
    defects = _defects(result, "PDFQA-011")
    assert len(defects) == 2


def test_company_overview_yahoo_mismatch_over_10_percent_blocks():
    result = validate_pdf_audit(
        _audit(
            raw_compare={
                "market_cap": {
                    "company_overview": 3_100_000_000_000,
                    "yahoo_snapshot": 5_114_022_068_224,
                    "delta_pct": -39.4,
                }
            }
        )
    )
    defects = _defects(result, "PDFQA-013")
    assert len(defects) == 1
    assert defects[0].ticker == "NVDA"


def test_requested_ticker_missing_blocks():
    result = validate_pdf_audit({"tickers": {}}, requested_tickers=["NVDA"])
    assert _defects(result, "PDFQA-001")


def test_real_20260601_audit_blocks_known_pdf_defects():
    """Regression: the saved real-world audit must not pass silently."""
    import json
    from pathlib import Path

    path = Path("docs/pdf-audits/2026-06-01-sa-pdf-pro-qa-raw.json")
    audit = json.loads(path.read_text(encoding="utf-8"))
    result = validate_pdf_audit(audit, audience_mode="generic")
    defect_rules = {f.rule_id for f in result.defects}
    assert not result.passed
    assert "PDFQA-003" in defect_rules  # non-PDF / extraction errors
    assert "PDFQA-007" in defect_rules  # NaN/null markers
    assert "PDFQA-008" in defect_rules  # raw provider/internal labels
    assert "PDFQA-013" in defect_rules  # financial mismatch vs Yahoo snapshot
    print(f"REAL_AUDIT_DEFECTS={len(result.defects)} WARNINGS={len(result.warnings)}")
