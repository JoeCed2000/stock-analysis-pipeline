"""ReportLab renderer for earnings deep-dive PDFs."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
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
_GLYPH_FALLBACKS = {
    "🌟": "*",
    "⚠️": "!!",
    "🧠": ">>",
    "🎯": ">>",
    "📊": "::",
    "💵": "$",
    "💰": "$",
    "🏦": "::",
    "🧩": "::",
    "📈": "^^",
    "📦": "[]",
    "🔭": ">>",
    "🔮": "**",
    "🏆": "**",
    "👉": "->",
}
_SECTION_PREFIXES = {
    "EPS & Revenue": "📊",
    "Highlights": "🌟 ⚠️",
    "Operating Metrics": "🧠",
    "Cash Flow": "💵",
    "Capital Efficiency": "🏦",
    "Segments": "🧩",
    "Forward P/E": "📈",
    "Backlog": "📦",
    "Guidance": "🔭",
    "Verdict": "🎯",
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


@lru_cache(maxsize=4)
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


def _glyph_safe(text: str, *, font_name: str = "Helvetica") -> str:
    """Replace emoji with ASCII fallbacks. Only strip to Latin-1 for non-CJK fonts."""
    value = str(text)
    for source, replacement in _GLYPH_FALLBACKS.items():
        value = value.replace(source, replacement)
    # Only strip to Latin-1 for fonts that don't support CJK
    if font_name not in ("MS-PGothic", "HeiseiMin-W3"):
        return value.encode("latin-1", errors="replace").decode("latin-1")
    return value


def _paragraph(text: str, style: ParagraphStyle, *, font_name: str) -> Paragraph:
    escaped = escape(_glyph_safe(str(text), font_name=font_name))
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
    formatted = _format_markdown(_glyph_safe(str(text), font_name=font_name))
    escaped = escape(formatted)
    # Unescape the XML tags we intentionally added
    escaped = escaped.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    escaped = escaped.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
    return Paragraph(escaped, style)


def _section_title(section, *, font_name: str = "Helvetica") -> str:
    prefix = _SECTION_PREFIXES.get(section.key)
    if not prefix:
        return _glyph_safe(section.title, font_name=font_name)
    return _glyph_safe(f"{prefix} {section.title}", font_name=font_name)


def _official_website(report: EarningsDeepDiveReport) -> str | None:
    for source in report.sources:
        label = source.label.lower()
        if any(kw in label for kw in ("website", "official", "company site", "homepage")) and source.url:
            return source.url
    return None


def _source_url(report: EarningsDeepDiveReport, *labels: str) -> str | None:
    lowered = tuple(label.lower() for label in labels)
    for source in report.sources:
        label = source.label.lower()
        if source.url and any(expected in label for expected in lowered):
            return source.url
    return None


def _source_note(report: EarningsDeepDiveReport, *labels: str) -> str:
    lowered = tuple(label.lower() for label in labels)
    for source in report.sources:
        label = source.label.lower()
        if any(expected in label for expected in lowered):
            return source.url or source.note or "N/A"
    return "N/A"


def _earnings_documents_story(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts: PdfFontSet,
) -> list:
    # Look for the actual transcript source in the report's sources list
    transcript_label = None
    transcript_url = None
    for source in report.sources:
        label_lower = source.label.lower()
        if "transcript" in label_lower:
            transcript_label = source.label
            transcript_url = source.url
            break
    # Fallback: if no transcript source found, use generic Seeking Alpha link
    if not transcript_label:
        transcript_label = "Earnings Transcript — Seeking Alpha"
        transcript_url = f"https://seekingalpha.com/symbol/{report.ticker}/earnings/transcripts"

    ir_value = _source_note(report, "investor relations")
    press_release_value = _source_note(report, "press release")
    presentation_value = _source_note(report, "presentation")
    if report.language == "jp":
        rows = [
            (transcript_label, transcript_url or "N/A", "Earning Call Transcript source"),
            ("Official Investor Relations", ir_value, "Press Release / Earning Call Presentation"),
            ("Press Release", press_release_value, "会社開示データの一次ソース"),
            ("Earning Call Presentation", presentation_value, "補足KPI・セグメント・ガイダンス確認"),
        ]
        analysis = [
            "General Questions for Earnings",
            "赤字プロンプト相当の質問は、PDFへ直接コピーせず、Transcript・Press Release・Presentationから構造化データを抽出するために使います。",
            f"👉 会社名やリンクはモデル例ではなく、対象企業 {report.company} ({report.ticker}) のソースに置き換えます。",
        ]
    else:
        rows = [
            (transcript_label, transcript_url or "N/A", "Earning Call Transcript source"),
            ("Official Investor Relations", ir_value, "Press Release / Earning Call Presentation"),
            ("Press Release", press_release_value, "Primary company-reported earnings source"),
            ("Earning Call Presentation", presentation_value, "Supplemental KPIs, segments, and guidance"),
        ]
        analysis = [
            "General Questions for Earnings",
            "The red prompt blocks in the model are treated as structured extraction prompts, not as final prose.",
            f"👉 Company names and links are replaced with target-company sources for {report.company} ({report.ticker}).",
        ]

    section = type(
        "DocumentsSection",
        (),
        {
            "table": type(
                "DocumentsTable",
                (),
                {
                    "columns": ["Document / Source", "Target-company URL or status", "Used for"],
                    "rows": [
                        type("DocumentsRow", (), {"label": label, "cells": [value, used_for]})
                        for label, value, used_for in rows
                    ],
                },
            )()
        },
    )()
    story = [Paragraph("Earnings Documents", styles["section"]), _table(section, styles, fonts)]
    story.extend(_paragraph_md(line, styles["body"], font_name=fonts.regular) for line in analysis)
    story.append(PageBreak())
    return story


def _section_continuation(section, report: EarningsDeepDiveReport) -> list[str]:
    if report.language == "jp":
        return {
            "Highlights": [
                f"👉 {report.company} ({report.ticker}) の良い点と懸念点は、必ず表の数値・Transcript・Press Releaseに戻して確認します。",
                "● 例示企業の数字は使わず、対象企業の実績・前年比・ガイダンスだけで判断します。",
            ],
            "Operating Metrics": [
                "🧠 Namiさん向け補足",
                "👉 売上、粗利、営業利益、純利益は同じ会計基準・同じ期間で比較し、成長の質を確認します。",
            ],
            "Cash Flow": [
                "📌 FCF = OCF - CapEx",
                "👉 キャッシュフローは会計上の利益が現金に変わっているかを見るため、決算の信頼度チェックに使います。",
            ],
        }.get(section.key, [])
    return {
        "Highlights": [
            f"For Nami-san: {report.company} ({report.ticker}) positives and risks must tie back to this company's sourced metrics, transcript, press release, or presentation.",
            "Model example company figures are never reused for another ticker.",
        ],
        "Operating Metrics": [
            "For Nami-san: revenue, gross profit, operating income, and net income must be compared on a consistent period and accounting basis.",
        ],
        "Cash Flow": [
            "FCF = OCF - CapEx.",
            "Cash flow is used to verify whether accounting earnings are turning into owner cash.",
        ],
    }.get(section.key, [])


def _table(section, styles: dict[str, ParagraphStyle], fonts: PdfFontSet) -> Table:
    data = [
        [_paragraph(column, styles["small_bold"], font_name=fonts.bold) for column in section.table.columns]
    ]
    for row in section.table.rows:
        row_values = [row.label, *row.cells]
        data.append([_paragraph(cell, styles["small"], font_name=fonts.regular) for cell in row_values])

    available_width = LETTER[0] - (1.35 * inch)
    col_count = max(1, len(section.table.columns))
    if col_count == 6:
        col_widths = [1.2 * inch, 1.1 * inch, 1.1 * inch, 1.0 * inch, 1.1 * inch, 1.65 * inch]
    elif col_count == 5:
        col_widths = [1.3 * inch, 1.3 * inch, 1.3 * inch, 1.45 * inch, 1.4 * inch]
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
    story.extend(_earnings_documents_story(report, styles, fonts))

    for index, section in enumerate(report.sections):
        story.append(Paragraph(escape(_section_title(section)), styles["section"]))
        if section.question:
            story.append(_paragraph(section.question, styles["question"], font_name=fonts.regular))
        story.append(_table(section, styles, fonts))
        if section.analysis:
            for paragraph in section.analysis:
                story.append(_paragraph_md(paragraph, styles["body"], font_name=fonts.regular))
        continuation = _section_continuation(section, report)
        if continuation:
            # Use spacer instead of unconditional PageBreak — ReportLab
            # handles page flow naturally. Only break if needed.
            story.append(Spacer(1, 0.18 * inch))
            story.append(Paragraph(escape(f"{_section_title(section)} - continued"), styles["section"]))
            for paragraph in continuation:
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
            story.append(Spacer(1, 0.25 * inch))
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
