"""PyMuPDF-based PDF annotation extractor for feedback uploads.

Extracts text annotations, highlight/comment metadata, and page numbers from
user-uploaded PDF files in the feedback pipeline. Returns structured, JSON-serializable
results suitable for API consumption.

No OCR or marker-pdf dependency — this module uses PyMuPDF (fitz) only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class AnnotationInfo(BaseModel):
    """Structured metadata for a single PDF annotation."""

    page_number: int = Field(..., ge=1, description="1-indexed page number")
    type_name: str = Field(
        ..., min_length=1, description="Human-readable annotation type (e.g. Highlight)"
    )
    type_code: int = Field(..., ge=0, description="Numeric PDF annotation type code")
    content: str = Field(
        default="", description="The annotation text content / comment"
    )
    title: str = Field(
        default="", description="Author or title of the annotation"
    )
    rect: dict[str, float] = Field(
        ...,
        description="Bounding box {x0, y0, x1, y1} in PDF point coordinates",
    )

    @field_validator("rect")
    @classmethod
    def _rect_must_be_valid(cls, v: dict[str, float]) -> dict[str, float]:
        if v.get("x1", -1) < v.get("x0", 0):
            raise ValueError("x1 must be >= x0 in rect")
        if v.get("y1", -1) < v.get("y0", 0):
            raise ValueError("y1 must be >= y0 in rect")
        return v


class AnnotationExtractionResult(BaseModel):
    """Complete result of a PDF annotation extraction."""

    annotations: list[AnnotationInfo] = Field(
        default_factory=list, description="Extracted annotations"
    )
    total_count: int = Field(default=0, ge=0, description="Total annotation count")
    error: str | None = Field(
        default=None, description="Error message if extraction failed"
    )


# ── Type name mapping for human-readable labels ─────────────────────────────

PDF_ANNOTATION_TYPES: dict[int, str] = {
    0: "Text",
    1: "Link",
    2: "FreeText",
    3: "Line",
    4: "Square",
    5: "Circle",
    6: "Polygon",
    7: "PolyLine",
    8: "Highlight",
    9: "Underline",
    10: "Squiggly",
    11: "StrikeOut",
    12: "Stamp",
    13: "Caret",
    14: "Ink",
    15: "Popup",
    16: "FileAttachment",
    17: "Sound",
    18: "Movie",
    19: "Widget",
    20: "Screen",
    21: "PrinterMark",
    22: "TrapNet",
    23: "Watermark",
    24: "3D",
}


def _get_annotation_type_name(type_tuple: tuple) -> str:
    """Return a human-readable name from a PyMuPDF annotation type.

    PyMuPDF returns types as ``(code, 'Name')`` tuples. When the built-in name
    is meaningful (Highlight, FreeText, …) we use it directly; otherwise we fall
    back to our mapping dict.
    """
    if isinstance(type_tuple, tuple) and len(type_tuple) == 2:
        code, name = type_tuple
        if name and isinstance(name, str) and len(name) > 0:
            return name
        return PDF_ANNOTATION_TYPES.get(int(code), f"Unknown({code})")
    return "Unknown"


def _rect_to_dict(rect: Any) -> dict[str, float]:
    """Convert a PyMuPDF Rect to a plain dict."""
    return {
        "x0": round(float(rect.x0), 2),
        "y0": round(float(rect.y0), 2),
        "x1": round(float(rect.x1), 2),
        "y1": round(float(rect.y1), 2),
    }


def extract_annotations(pdf_path: str | Path) -> AnnotationExtractionResult:
    """Extract all annotations from a PDF file.

    Parameters
    ----------
    pdf_path : str or Path
        Path to the PDF file to analyse.

    Returns
    -------
    AnnotationExtractionResult
        Structured result with annotations list, total count, and optional error.
    """
    try:
        path = Path(pdf_path)
        if not path.exists():
            return AnnotationExtractionResult(
                annotations=[],
                total_count=0,
                error=f"File not found: {path.name}",
            )

        import fitz  # PyMuPDF — no OCR, no marker-pdf

        doc = fitz.open(str(path))
    except Exception as exc:
        logger.warning("Failed to open PDF for annotation extraction: %s", exc)
        return AnnotationExtractionResult(
            annotations=[],
            total_count=0,
            error=f"Could not open PDF: {exc}",
        )

    annotations: list[AnnotationInfo] = []
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1  # 1-indexed for user-friendliness
            for annot in page.annots():
                type_tuple = annot.type  # e.g. (8, 'Highlight')
                type_code = int(type_tuple[0]) if isinstance(type_tuple, tuple) else 0
                type_name = _get_annotation_type_name(type_tuple)
                info = annot.info or {}
                rect = annot.rect

                annotation = AnnotationInfo(
                    page_number=page_number,
                    type_name=type_name,
                    type_code=type_code,
                    content=info.get("content", ""),
                    title=info.get("title", ""),
                    rect=_rect_to_dict(rect),
                )
                annotations.append(annotation)
    except Exception as exc:
        logger.warning("Error during annotation extraction: %s", exc)
        return AnnotationExtractionResult(
            annotations=annotations,
            total_count=len(annotations),
            error=f"Partial extraction error: {exc}",
        )
    finally:
        try:
            doc.close()
        except Exception:
            pass

    return AnnotationExtractionResult(
        annotations=annotations,
        total_count=len(annotations),
        error=None,
    )


def pdf_has_annotations(pdf_path: str | Path) -> bool:
    """Quick check whether a PDF contains any annotations.

    This is more efficient than ``extract_annotations`` when only a boolean
    answer is needed — it stops iterating at the first annotation found.

    Parameters
    ----------
    pdf_path : str or Path
        Path to the PDF file to check.

    Returns
    -------
    bool
        True if the PDF contains at least one annotation, False otherwise
        (including corrupt or missing files).
    """
    try:
        path = Path(pdf_path)
        if not path.exists():
            return False

        import fitz

        doc = fitz.open(str(path))
        try:
            for page in doc:
                for _annot in page.annots():
                    return True
            return False
        finally:
            doc.close()
    except Exception:
        return False
