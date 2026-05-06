"""ReportLab renderer for earnings deep-dive PDFs."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.earnings_deep_dive.mapper import MISSING
from backend.earnings_deep_dive.report_model import EarningsDeepDiveReport


_DARK_RED = colors.HexColor("#8B1E1E")
_HEADER_FILL = colors.HexColor("#EFE6E0")
_GRID = colors.HexColor("#B8B8B8")
_TEXT = colors.HexColor("#111111")
_MUTED = colors.HexColor("#5D5D5D")
_REGISTERED_FONTS: set[str] = set()
_SECTION_PREFIXES = {
    "EPS & Revenue": "[EPS]",
    "Highlights": "[Highlights] [Lowlights]",
    "Operating Metrics": "[Operating]",
    "Cash Flow": "[Cash]",
    "Capital Efficiency": "[Capital]",
    "Segments": "[Segments]",
    "Forward P/E": "[Valuation]",
    "Backlog": "[Backlog]",
    "Guidance": "[Guidance]",
    "Verdict": "[Verdict]",
}


@dataclass(frozen=True)
class PdfFontSet:
    regular: str
    bold: str


def _font_candidates(filename: str) -> list[Path]:
    configured = os.getenv("PDF_FONT_DIR")
    roots = [
        Path(configured) if configured else None,
        Path("assets/fonts"),
        Path("backend/assets/fonts"),
        Path("C:/Windows/Fonts"),
        Path("/mnt/c/Windows/Fonts"),
    ]
    return [root / filename for root in roots if root is not None]


def _first_existing_font(filename: str) -> Path | None:
    for candidate in _font_candidates(filename):
        if candidate.exists():
            return candidate
    return None


def _register_ttf(font_name: str, path: Path, *, subfont_index: int | None = None) -> bool:
    if font_name in _REGISTERED_FONTS or font_name in pdfmetrics.getRegisteredFontNames():
        _REGISTERED_FONTS.add(font_name)
        return True
    try:
        if subfont_index is None:
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
        else:
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(path), subfontIndex=subfont_index))
            except TypeError:
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
        _REGISTERED_FONTS.add(font_name)
        return True
    except Exception:
        return False


def _register_cid(font_name: str) -> bool:
    if font_name in _REGISTERED_FONTS or font_name in pdfmetrics.getRegisteredFontNames():
        _REGISTERED_FONTS.add(font_name)
        return True
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
        _REGISTERED_FONTS.add(font_name)
        return True
    except Exception:
        return False


def resolve_pdf_fonts(language: str) -> PdfFontSet:
    arial = _first_existing_font("arial.ttf")
    arial_bold = _first_existing_font("arialbd.ttf")
    regular = "Arial" if arial and _register_ttf("Arial", arial) else "Helvetica"
    bold = "Arial-Bold" if arial_bold and _register_ttf("Arial-Bold", arial_bold) else "Helvetica-Bold"

    if language == "jp":
        msgothic = _first_existing_font("msgothic.ttc")
        if msgothic and _register_ttf("MS-PGothic", msgothic, subfont_index=0):
            return PdfFontSet(regular="MS-PGothic", bold="MS-PGothic")
        if _register_cid("HeiseiMin-W3"):
            return PdfFontSet(regular="HeiseiMin-W3", bold="HeiseiMin-W3")
    return PdfFontSet(regular=regular, bold=bold)


def _styles(fonts: PdfFontSet) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DeepDiveTitle",
            parent=base["Title"],
            fontName=fonts.bold,
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            textColor=_TEXT,
            spaceAfter=10,
        ),
        "meta": ParagraphStyle(
            "DeepDiveMeta",
            parent=base["Normal"],
            fontName=fonts.regular,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=_MUTED,
            spaceAfter=18,
        ),
        "section": ParagraphStyle(
            "DeepDiveSection",
            parent=base["Heading2"],
            fontName=fonts.bold,
            fontSize=15,
            leading=18,
            textColor=_TEXT,
            spaceBefore=3,
            spaceAfter=7,
        ),
        "question": ParagraphStyle(
            "DeepDiveQuestion",
            parent=base["Normal"],
            fontName=fonts.regular,
            fontSize=10.5,
            leading=14,
            textColor=_DARK_RED,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "DeepDiveBody",
            parent=base["Normal"],
            fontName=fonts.regular,
            fontSize=9.5,
            leading=13,
            textColor=_TEXT,
            alignment=TA_LEFT,
            spaceBefore=5,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "DeepDiveSmall",
            parent=base["Normal"],
            fontName=fonts.regular,
            fontSize=7.6,
            leading=9.2,
            textColor=_TEXT,
        ),
        "small_bold": ParagraphStyle(
            "DeepDiveSmallBold",
            parent=base["Normal"],
            fontName=fonts.bold,
            fontSize=7.6,
            leading=9.2,
            textColor=_TEXT,
        ),
    }


def _paragraph(text: str, style: ParagraphStyle, *, font_name: str) -> Paragraph:
    escaped = escape(str(text))
    return Paragraph(escaped, style)


def _format_markdown(text: str) -> str:
    """Convert basic markdown to ReportLab-compatible XML."""
    import re
    # Convert **bold** to <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Convert *italic* to <i>italic</i> (but not **already bold**)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    return text


def _paragraph_md(text: str, style: ParagraphStyle, *, font_name: str) -> Paragraph:
    """Paragraph with markdown formatting support (bold/italic)."""
    formatted = _format_markdown(str(text))
    escaped = escape(formatted)
    # Unescape the XML tags we intentionally added
    escaped = escaped.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    escaped = escaped.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
    return Paragraph(escaped, style)


def _section_title(section) -> str:
    prefix = _SECTION_PREFIXES.get(section.key)
    if not prefix:
        return section.title
    return f"{prefix} {section.title}"


def _official_website(report: EarningsDeepDiveReport) -> str | None:
    for source in report.sources:
        label = source.label.lower()
        if any(kw in label for kw in ("website", "official", "company site", "homepage")) and source.url:
            return source.url
    return None


def _table(section, styles: dict[str, ParagraphStyle], fonts: PdfFontSet) -> Table:
    data = [
        [_paragraph(column, styles["small_bold"], font_name=fonts.bold) for column in section.table.columns]
    ]
    for row in section.table.rows:
        data.append([_paragraph(cell, styles["small"], font_name=fonts.regular) for cell in row.cells])

    available_width = LETTER[0] - (1.35 * inch)
    col_count = max(1, len(section.table.columns))
    if col_count == 6:
        col_widths = [0.95 * inch, 0.85 * inch, 0.85 * inch, 0.8 * inch, 0.85 * inch, 1.3 * inch]
    elif col_count == 5:
        col_widths = [1.05 * inch, 1.05 * inch, 1.05 * inch, 1.25 * inch, 1.2 * inch]
    else:
        col_widths = [available_width / col_count] * col_count

    table = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_FILL),
                ("TEXTCOLOR", (0, 0), (-1, 0), _TEXT),
                ("FONTNAME", (0, 0), (-1, 0), fonts.bold),
                ("FONTNAME", (0, 1), (-1, -1), fonts.regular),
                ("GRID", (0, 0), (-1, -1), 0.45, _GRID),
                ("BOX", (0, 0), (-1, -1), 0.8, _GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _footer(canvas, doc, font_name: str = "Helvetica") -> None:
    canvas.saveState()
    canvas.setFont(font_name, 8)
    canvas.setFillColor(_MUTED)
    canvas.drawCentredString(LETTER[0] / 2, 0.42 * inch, f"{doc.page}")
    canvas.restoreState()


def render_earnings_deep_dive_pdf(report: EarningsDeepDiveReport, output_path: str | Path) -> str:
    """Render a structured earnings deep-dive report to an extractable PDF."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fonts = resolve_pdf_fonts(report.language)
    styles = _styles(fonts)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=LETTER,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        pageCompression=0,
        title=report.title,
        author="stock-analysis-pipeline",
    )

    story = [
        Paragraph(escape(f"{report.company} ({report.ticker})"), styles["title"]),
        Paragraph(escape(f"Earnings Deep-Dive - {report.quarter}"), styles["meta"]),
    ]
    website = _official_website(report)
    if website:
        story.append(Paragraph(escape(f"Official Website: {website}"), styles["meta"]))

    for index, section in enumerate(report.sections):
        story.append(Paragraph(escape(_section_title(section)), styles["section"]))
        story.append(_table(section, styles, fonts))
        if section.analysis:
            for paragraph in section.analysis:
                story.append(_paragraph_md(paragraph, styles["body"], font_name=fonts.regular))
        # Summary as a styled sub-heading + body text on separate lines
        story.append(Spacer(1, 0.12 * inch))
        story.append(Paragraph(
            f"<b>{escape(section.summary_label)}</b>",
            styles["question"],
        ))
        story.append(_paragraph_md(
            section.summary.strip() if section.summary.strip() else "Not available.",
            styles["body"],
            font_name=fonts.regular,
        ))
        if index < len(report.sections) - 1:
            story.append(PageBreak())
        else:
            story.append(Spacer(1, 0.18 * inch))

    if report.sources:
        story.append(Paragraph("Sources", styles["section"]))
        for source in report.sources:
            text = escape(source.label)
            if source.url:
                text += f": {escape(source.url)}"
            elif source.note:
                text += f": {escape(source.note)}"
            story.append(Paragraph(text, styles["body"]))

    def draw_footer(canvas, doc) -> None:
        _footer(canvas, doc, fonts.regular)

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return str(output)
