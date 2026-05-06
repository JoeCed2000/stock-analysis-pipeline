from pathlib import Path

import fastapi.dependencies.utils

fastapi.dependencies.utils.ensure_multipart_is_installed = lambda: None

from backend import main


def test_pdf_conversion_does_not_overwrite_structured_earnings_deep_dive(tmp_path):
    report_dir = tmp_path / "07_final_report"
    report_dir.mkdir(parents=True)
    markdown_path = report_dir / "earnings_deep_dive.md"
    pdf_path = report_dir / "earnings_deep_dive.pdf"
    markdown_path.write_text("# translated markdown", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF structured")

    assert main._should_convert_dossier_text_to_pdf(markdown_path, refresh_pdf=True) is False


def test_pdf_conversion_refreshes_regular_translated_markdown(tmp_path):
    markdown_path = tmp_path / "05_market_and_context" / "market_context_MSFT.md"
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text("# translated market context", encoding="utf-8")

    assert main._should_convert_dossier_text_to_pdf(markdown_path, refresh_pdf=True) is True
