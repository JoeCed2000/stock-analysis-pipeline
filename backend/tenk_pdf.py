"""10-K HTML → PDF converter using WeasyPrint."""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML
    _WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    logger.warning("weasyprint not installed — 10-K PDF conversion disabled")


def convert_10k_to_pdf(html_path: str, output_dir: str, ticker: str) -> str:
    """Convert a 10-K HTML file to PDF. Returns PDF path or empty string on failure."""
    if not _WEASYPRINT_AVAILABLE:
        return ""

    if not html_path or not os.path.exists(html_path):
        logger.warning(f"10-K HTML not found at {html_path}")
        return ""

    try:
        pdf_dir = os.path.join(output_dir, "02_sec_or_regulatory_filings")
        os.makedirs(pdf_dir, exist_ok=True)

        # Derive filename from HTML filename
        html_name = Path(html_path).stem
        pdf_path = os.path.join(pdf_dir, f"{html_name}.pdf")

        HTML(filename=html_path).write_pdf(pdf_path)
        size_kb = os.path.getsize(pdf_path) / 1024
        logger.info(f"10-K PDF generated: {pdf_path} ({size_kb:.0f} KB)")
        return pdf_path

    except Exception as e:
        logger.warning(f"10-K PDF conversion failed: {e}")
        return ""
