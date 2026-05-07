"""Earnings call deep-dive generator package."""

from backend.earnings_deep_dive.errors import (
    EarningsDeepDiveError,
    KimiFailureError,
    TranscriptMissingError,
    ValidationError,
)
from backend.earnings_deep_dive.generator import generate_deep_dive
from backend.earnings_deep_dive.markdown import assemble_final_report
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
from backend.earnings_deep_dive.schemas import (
    DeepDiveRequest,
    DeepDiveResponse,
    FinancialMetrics,
    SectionStatus,
)

__all__ = [
    "DeepDiveRequest",
    "DeepDiveResponse",
    "EarningsDeepDiveError",
    "FinancialMetrics",
    "KimiFailureError",
    "SectionStatus",
    "TranscriptMissingError",
    "ValidationError",
    "assemble_final_report",
    "build_earnings_deep_dive_report",
    "generate_deep_dive",
    "render_earnings_deep_dive_pdf",
]
