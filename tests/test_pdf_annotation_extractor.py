"""Tests for backend.pdf_annotation_extractor — PyMuPDF-based annotation extraction."""

from __future__ import annotations

import json

import pytest

from backend.pdf_annotation_extractor import (
    AnnotationExtractionResult,
    AnnotationInfo,
    extract_annotations,
    pdf_has_annotations,
)


# ── Fixtures: create test PDFs with known annotations ──────────────────────


@pytest.fixture
def annotated_pdf_path(tmp_path):
    """Create a PDF with 3 annotations across 2 pages."""
    import fitz

    doc = fitz.open()

    # Page 0 — two annotations
    page0 = doc.new_page()
    ft = page0.add_freetext_annot((50, 50, 250, 100), "Comment on revenue figure")
    ft.set_info({"content": "Comment on revenue figure", "title": "Reviewer A"})
    hl = page0.add_highlight_annot((50, 120, 300, 140))
    hl.set_info({"content": "Needs source check", "title": "Analyst"})

    # Page 1 — one annotation
    page1 = doc.new_page()
    ul = page1.add_underline_annot((50, 50, 300, 70))
    ul.set_info({"content": "Verify this", "title": "Manager"})

    path = tmp_path / "annotated.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def clean_pdf_path(tmp_path):
    """Create a PDF with no annotations."""
    import fitz

    doc = fitz.open()
    doc.new_page()
    doc.new_page()

    path = tmp_path / "clean.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def corrupt_pdf_path(tmp_path):
    """Create a file that is not a valid PDF."""
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"not a valid PDF content at all")
    return str(path)


# ── Happy path tests ────────────────────────────────────────────────────────


class TestExtractAnnotations:
    """Happy path: annotated PDF returns structured annotation data."""

    def test_returns_all_annotations_across_pages(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        assert result.total_count == 3
        assert len(result.annotations) == 3

    def test_includes_page_numbers(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        page_numbers = {a.page_number for a in result.annotations}
        assert page_numbers == {1, 2}  # 1-indexed pages

    def test_includes_annotation_type(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        type_names = {a.type_name for a in result.annotations}
        assert "FreeText" in type_names
        assert "Highlight" in type_names
        assert "Underline" in type_names

    def test_includes_annotation_content(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        contents = {a.content for a in result.annotations}
        assert "Comment on revenue figure" in contents
        assert "Needs source check" in contents
        assert "Verify this" in contents

    def test_includes_title_when_present(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        titles = {a.title for a in result.annotations}
        assert "Reviewer A" in titles
        assert "Analyst" in titles
        assert "Manager" in titles

    def test_includes_rectangle_coordinates(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        for a in result.annotations:
            assert isinstance(a.rect, dict)
            assert "x0" in a.rect
            assert "y0" in a.rect
            assert "x1" in a.rect
            assert "y1" in a.rect
            assert a.rect["x0"] < a.rect["x1"]
            assert a.rect["y0"] < a.rect["y1"]

    def test_includes_type_code(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        for a in result.annotations:
            assert isinstance(a.type_code, int)
            assert a.type_code > 0

    def test_serializes_to_json(self, annotated_pdf_path):
        result = extract_annotations(annotated_pdf_path)
        # Must be JSON-serializable for API responses
        dumped = json.dumps(result.model_dump())
        assert "total_count" in dumped
        assert "annotations" in dumped
        assert "error" in dumped


# ── Edge case: no annotations ───────────────────────────────────────────────


class TestNoAnnotations:
    """Empty result for PDFs without annotations."""

    def test_returns_empty_list(self, clean_pdf_path):
        result = extract_annotations(clean_pdf_path)
        assert result.total_count == 0
        assert result.annotations == []

    def test_has_no_error(self, clean_pdf_path):
        result = extract_annotations(clean_pdf_path)
        assert result.error is None

    def test_pdf_has_annotations_false(self, clean_pdf_path):
        assert pdf_has_annotations(clean_pdf_path) is False


# ── Edge case: corrupt PDFs ─────────────────────────────────────────────────


class TestCorruptPdf:
    """Safe structured failure for corrupt PDFs."""

    def test_returns_empty_annotations(self, corrupt_pdf_path):
        result = extract_annotations(corrupt_pdf_path)
        assert result.total_count == 0
        assert result.annotations == []

    def test_has_error_with_message(self, corrupt_pdf_path):
        result = extract_annotations(corrupt_pdf_path)
        assert result.error is not None
        assert isinstance(result.error, str)
        assert len(result.error) > 0

    def test_has_error_does_not_contain_traceback(self, corrupt_pdf_path):
        """Error message should be user-friendly, not a raw traceback."""
        result = extract_annotations(corrupt_pdf_path)
        assert "Traceback" not in result.error
        assert "File" not in result.error

    def test_pdf_has_annotations_returns_false_on_corrupt(self, corrupt_pdf_path):
        assert pdf_has_annotations(corrupt_pdf_path) is False


# ── Edge case: file not found ───────────────────────────────────────────────


class TestFileNotFound:
    def test_returns_error_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.pdf"
        result = extract_annotations(str(missing))
        assert result.total_count == 0
        assert result.annotations == []
        assert result.error is not None

    def test_pdf_has_annotations_returns_false_for_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.pdf"
        assert pdf_has_annotations(str(missing)) is False


# ── pydantic model validation ───────────────────────────────────────────────


class TestAnnotationModel:
    def test_rejects_negative_page_number(self):
        with pytest.raises(ValueError):
            AnnotationInfo(
                page_number=-1,
                type_name="Highlight",
                type_code=8,
                content="test",
                title="",
                rect={"x0": 0, "y0": 0, "x1": 10, "y1": 10},
            )

    def test_rejects_missing_type_name(self):
        with pytest.raises(ValueError):
            AnnotationInfo(
                page_number=1,
                type_name="",
                type_code=8,
                content="test",
                title="",
                rect={"x0": 0, "y0": 0, "x1": 10, "y1": 10},
            )

    def test_rejects_invalid_rect(self):
        with pytest.raises(ValueError):
            AnnotationInfo(
                page_number=1,
                type_name="Highlight",
                type_code=8,
                content="test",
                title="",
                rect={"x0": 100, "y0": 0, "x1": 10, "y1": 10},  # x1 < x0
            )

    def test_valid_annotation_creates_successfully(self):
        info = AnnotationInfo(
            page_number=1,
            type_name="Highlight",
            type_code=8,
            content="test content",
            title="Reviewer",
            rect={"x0": 10, "y0": 10, "x1": 100, "y1": 50},
        )
        assert info.content == "test content"
        assert info.title == "Reviewer"


class TestResultModel:
    def test_result_roundtrip_json(self):
        result = AnnotationExtractionResult(
            annotations=[
                AnnotationInfo(
                    page_number=1,
                    type_name="Highlight",
                    type_code=8,
                    content="test",
                    title="",
                    rect={"x0": 0, "y0": 0, "x1": 10, "y1": 10},
                )
            ],
            total_count=1,
            error=None,
        )
        data = json.loads(result.model_dump_json())
        assert data["total_count"] == 1
        assert len(data["annotations"]) == 1
        assert data["error"] is None

    def test_result_empty(self):
        result = AnnotationExtractionResult(
            annotations=[], total_count=0, error=None
        )
        assert result.model_dump() == {
            "annotations": [],
            "total_count": 0,
            "error": None,
        }
