"""Earnings call deep-dive generator package.

Heavy modules (generator, mapper, pdf_renderer, markdown) are loaded lazily
via __getattr__ to avoid loading ReportLab, LLM providers, and other heavy
dependencies on cold import. This reduces cold import of backend.main from
~13s to ~5-6s.
"""

from backend.earnings_deep_dive.errors import (
    EarningsDeepDiveError,
    KimiFailureError,
    TranscriptMissingError,
    ValidationError,
)
from backend.earnings_deep_dive.schemas import (
    DeepDiveRequest,
    DeepDiveResponse,
    FinancialMetrics,
    SectionStatus,
)

# ── Lazy imports for heavy modules ──
# These are loaded on first access to avoid loading ReportLab, LLM providers,
# and other heavy dependencies at import time.
_LAZY_IMPORTS = {
    "generate_deep_dive": ("backend.earnings_deep_dive.generator", "generate_deep_dive"),
    "assemble_final_report": ("backend.earnings_deep_dive.markdown", "assemble_final_report"),
    "post_process_markdown": ("backend.earnings_deep_dive.markdown", "post_process_markdown"),
    "build_earnings_deep_dive_report": ("backend.earnings_deep_dive.mapper", "build_earnings_deep_dive_report"),
    "render_earnings_deep_dive_pdf": ("backend.earnings_deep_dive.pdf_renderer", "render_earnings_deep_dive_pdf"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib
        module_name, attr_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_name)
        attr = getattr(module, attr_name)
        # Cache in module globals so subsequent accesses are direct
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    "post_process_markdown",
    "render_earnings_deep_dive_pdf",
]
