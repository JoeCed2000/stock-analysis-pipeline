"""ReportLab renderer for earnings deep-dive PDFs."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import re
from xml.sax.saxutils import escape

from PIL import Image as PILImage, ImageDraw, ImageFont

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    LayoutError,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.earnings_deep_dive.report_model import (
    ClaimSource, CompanyOverview, EarningsDeepDiveReport,
    # V2.7 structured section models
    ExecutiveSnapshot, FinancialMetrics, ValuationSection,
    ValuationContextSection, PeerBenchmarkSection, DataQualitySection,
)
from backend.i18n import translate


_DARK_RED = colors.HexColor("#8B1E1E")
_HEADER_FILL = colors.HexColor("#EFE6E0")
_GRID = colors.HexColor("#B8B8B8")
_TEXT = colors.HexColor("#111111")
_MUTED = colors.HexColor("#5D5D5D")
_POSITIVE = colors.HexColor("#0B6B3A")
_NEGATIVE = colors.HexColor("#A33A2A")
_REGISTERED_FONTS: set[str] = set()

# ── Emoji rendering via PIL + NotoColorEmoji.ttf ──────────────────────────
_NOTO_EMOJI_PATH = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
_EMOJI_FONT: ImageFont.FreeTypeFont | None = None


def _get_emoji_font() -> ImageFont.FreeTypeFont:
    global _EMOJI_FONT
    if _EMOJI_FONT is None:
        _EMOJI_FONT = ImageFont.truetype(_NOTO_EMOJI_PATH, 109)
    return _EMOJI_FONT


def _diamond_image(size: int = 16) -> RLImage:
    """Draw a filled yellow ◆ diamond using PIL shapes (no font dependency)."""
    # Yellow diamond color matching _DIAMOND_YELLOW (#E6A817)
    fill = (230, 168, 23)
    s = size
    # Diamond polygon: top, right, bottom, left
    points = [(s/2, 0), (s, s/2), (s/2, s), (0, s/2)]
    img = PILImage.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon(points, fill=fill)
    # Convert to RGB for PDF
    img_rgb = PILImage.new("RGB", (s, s), (255, 255, 255))
    img_rgb.paste(img, mask=img.split()[3])
    buf = BytesIO()
    img_rgb.save(buf, format="PNG")
    buf.seek(0)
    return RLImage(buf, width=size, height=size)

def _emoji_to_image(char: str, size: int = 16) -> RLImage:
    """Render a single emoji character as a ReportLab Image via PIL + NotoColorEmoji.
    
    Falls back to _diamond_image for ◆ (U+25C6) which is not in NotoColorEmoji."""
    # ◆ is not in NotoColorEmoji — draw as polygon instead
    if char == "◆":
        return _diamond_image(size)
    font = _get_emoji_font()
    # 1. Render on transparent background to get accurate bbox
    img = PILImage.new("RGBA", (136, 136), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((12, 8), char, font=font, embedded_color=True)
    # 2. Crop to emoji content only
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    # 3. Composite onto white RGB background
    img_rgb = PILImage.new("RGB", img.size, (255, 255, 255))
    img_rgb.paste(img, mask=img.split()[3])
    buf = BytesIO()
    img_rgb.save(buf, format="PNG")
    buf.seek(0)
    return RLImage(buf, width=size, height=size)


# ── Section emoji prefixes (model parity — section-specific semantics) ────
_SECTION_PREFIXES: dict[str, str] = {
    "EPS & Revenue":       "📊",
    "Highlights":          "🌟",
    "Operating Metrics":   "🧠",
    "Cash Flow":           "💰",
    "Capital Efficiency":  "🎯",
    "Segments":            "📊",
    "Forward P/E":         "📈",
    "Backlog":             "📦",
    "Guidance":            "🔮",
    "Verdict":             "🏆",
}

# Yellow diamond marker color (model parity)
_DIAMOND_YELLOW = colors.HexColor("#E6A817")


def _section_title_flowables(section, styles: dict[str, ParagraphStyle], *,
                              font_name: str = "Helvetica",
                              emoji_size: int = 16) -> list:
    """Return [Table(emoji_image + title_paragraph)] or [Paragraph] for CJK.
    
    Model parity: each section uses a semantically-appropriate emoji marker
    (📊 data, 🧠 analysis, 💰 cash flow, 🎯 efficiency, 🏆 verdict, etc.)
    rendered via PIL+NotoColorEmoji → PNG to guarantee glyph availability.
    """
    prefix = _SECTION_PREFIXES.get(section.key, "◆")
    if not prefix or font_name in ("MS-PGothic", "HeiseiMin-W3"):
        safe = _glyph_safe(section.title, font_name=font_name)
        paragraph = Paragraph(escape(safe), styles["section"])
        paragraph.keepWithNext = 1
        return [paragraph]

    # Render ◆ as PIL image
    diamond_img = _emoji_to_image(prefix.strip() or "◆", size=emoji_size)
    
    # Replace circled digits ①-⑳ with (1)-(20) — PDF fonts lack these glyphs
    _C_TITLE = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    _P_TITLE = ["(1)","(2)","(3)","(4)","(5)","(6)","(7)","(8)","(9)","(10)","(11)","(12)","(13)","(14)","(15)","(16)","(17)","(18)","(19)","(20)"]
    title_text = section.title
    question_text = section.question or ""
    for ci, ch in enumerate(_C_TITLE):
        title_text = title_text.replace(ch, _P_TITLE[ci])
        question_text = question_text.replace(ch, _P_TITLE[ci])
    safe_title = _glyph_safe(title_text, font_name=font_name)
    title_para = Paragraph(escape(safe_title), styles["section"])

    # Table: diamond image + title
    col_w = emoji_size + 3
    remaining = LETTER[0] - 1.24 * inch - col_w - 6
    table = Table([[diamond_img, title_para]], 
                  colWidths=[col_w, max(remaining, 100)], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
    ]))
    table.keepWithNext = 1
    return [table]


# ── Font discovery ──────────────────────────────────────────────────────
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


@dataclass(frozen=True)
class PdfFontSet:
    regular: str
    bold: str


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
            keepWithNext=1,  # §24 — prevents orphan section titles
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
            fontSize=10,
            leading=14,
            textColor=_TEXT,
            alignment=TA_LEFT,
            spaceBefore=5,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "DeepDiveSmall",
            parent=base["Normal"],
            fontName=fonts.regular,
            fontSize=8.5,
            leading=10.2,
            textColor=_TEXT,
        ),
        "small_bold": ParagraphStyle(
            "DeepDiveSmallBold",
            parent=base["Normal"],
            fontName=fonts.bold,
            fontSize=8.5,
            leading=12,
            textColor=_TEXT,
        ),
    }


# ── Glyph safety (simplified — emojis no longer flow through text) ──────
# ── Circled digit → plain text mapping (DejaVu lacks glyphs for U+2460-U+2473) ─
_CIRCLED_DIGIT_MAP = str.maketrans({
    '\u2460': '(1)', '\u2461': '(2)', '\u2462': '(3)', '\u2463': '(4)',
    '\u2464': '(5)', '\u2465': '(6)', '\u2466': '(7)', '\u2467': '(8)',
    '\u2468': '(9)', '\u2469': '(10)', '\u246a': '(11)', '\u246b': '(12)',
    '\u246c': '(13)', '\u246d': '(14)', '\u246e': '(15)', '\u246f': '(16)',
    '\u2470': '(17)', '\u2471': '(18)', '\u2472': '(19)', '\u2473': '(20)',
})

# ── Inline emoji markers — KEEP as Unicode, render as images ─────────
# No more ASCII replacements. Emojis are structural markers (model parity):
#   👉 = investor implication   🧠 = Nami analysis   🎯 = verdict
#   ⚠️ = warning/lowlight   📊 = data table   💰 = cash flow
#   🏆 = final verdict   🌟 = highlight   🔮 = guidance   📈 = growth
#   ● = bullet   ■ = subsection   ◆ = diamond (fallback only)
# Rendered as inline PIL+NotoColorEmoji images via _paragraph_with_emojis()
_STRUCTURAL_EMOJIS = re.compile(
    '[\U0001F300-\U0001F9FF'   # Misc Symbols, Emoticons, Supplemental, etc.
    '\U00002600-\U000027BF'     # Misc Symbols, Dingbats
    '\U0001F000-\U0001F02F'     # Mahjong, Domino
    '\U000025A0-\U000025FF'     # Geometric Shapes (●■◆▲▼)
    ']'
)

# Only strip truly redundant decorators (not structural markers)
_EMOJI_STRIP_MAP = str.maketrans({
    '\U0001F4A1': '',   # 💡 → redundant (lightbulb — context makes it clear)
})

# ── Emoji → text fallback — KEEP structural emojis for PIL+NotoColorEmoji ──
# ── rendering in _paragraph_with_emojis().  Only downgrade TRUE unknowns  ──
# ── that NotoColorEmoji doesn't cover.  Structural emojis (👉🧠🎯⚠️📊📌✅❌ ──
# ── 💰🏆🔥✔●🟢🔴) pass through for PNG image rendering. ──
_EMOJI_FALLBACK = str.maketrans({
    # Stars / sparkles (NotoColorEmoji covers these, but keep safe fallbacks)
    '\U0001F31F': '\u2605',   # 🌟 → ★
    '\U0001F320': '\u2606',   # 🌠 → ☆
    '\U0001F4AB': '\u2606',   # 💫 → ☆
    # Only downgrade emojis without PIL rendering:
    '\U0001F4CC': '\u25C6',   # 📌 → ◆ (rare, acceptable fallback)
})


# ── Fullwidth → ASCII mapping (LLM leakage) ──────────────────────────────
# LLMs sometimes output fullwidth characters that have no Helvetica glyphs.
_FULLWIDTH_MAP = str.maketrans({
    **{chr(cp): chr(cp - 0xFEE0) for cp in range(0xFF01, 0xFF5F)},  # ！→!, ０→0, Ａ→A, etc.
    '\u3000': ' ',   # ideographic space → regular space
    '\u3001': ',',   # ideographic comma
    '\u3002': '.',   # ideographic full stop
    '\u2018': "'",   # left single quote
    '\u2019': "'",   # right single quote
    '\u201C': '"',   # left double quote
    '\u201D': '"',   # right double quote
    '\uFF0D': '-',   # fullwidth hyphen-minus
})

_PDF_SAFE_PUNCTUATION_MAP = str.maketrans({
    '\u2014': '-',    # — em dash
    '\u2192': '->',   # → rightwards arrow
})


def _glyph_safe(text: str, *, font_name: str = "Helvetica", keep_emojis: bool = False) -> str:
    """Keep characters renderable by standard PDF fonts. Strip the rest silently.
    
    keep_emojis=True: preserve emoji-range characters for PIL image rendering
    (used by _paragraph_with_emojis). When False, emoji-range chars (0x1F300-0x1F9FF)
    are stripped — standard PDF fonts lack these glyphs and will render tofu/null bytes.
    
    Geometric Shapes (●◆▲▼) and Dingbats (⚠️✅❌) are kept as they have partial
    DejaVu/Helvetica coverage and are managed by _EMOJI_FALLBACK/_EMOJI_STRIP_MAP."""
    value = str(text)
    # LLM artifacts: LaTeX-escaped characters (\$35.6B → $35.6B)
    value = value.replace('\\$', '$')
    for ch in ('%', '&', '#', '_'):
        value = value.replace(f'\\{ch}', ch)
    # Replace circled digits with parenthesized numbers — DejaVu has no glyphs
    value = value.translate(_CIRCLED_DIGIT_MAP)
    # Strip redundant emojis (💰📈📦💡📋🔔) but keep structural ones (👉🧠🎯⚠️📊📌✅❌)
    value = value.translate(_EMOJI_STRIP_MAP)
    # Replace emoji-range characters with font-safe text fallbacks.
    if not keep_emojis:
        value = value.translate(_EMOJI_FALLBACK)
    value = value.translate(_PDF_SAFE_PUNCTUATION_MAP)
    # Map fullwidth characters to ASCII (LLM leakage prevention)
    value = value.translate(_FULLWIDTH_MAP)
    # CJK fonts can handle their character ranges natively
    if font_name in ("MS-PGothic", "HeiseiMin-W3"):
        return value

    safe: list[str] = []
    for ch in value:
        cp = ord(ch)
        if (cp < 256                                              # Latin-1
            or (0x2000 <= cp <= 0x206F)                           # General Punctuation (—–•…'')
            or (0x2190 <= cp <= 0x21FF)                           # Arrows (→←↑↓)
            or (0x25A0 <= cp <= 0x26FF)                           # Geometric Shapes + Misc Symbols
            or (0x2700 <= cp <= 0x27BF)                           # Dingbats (✔✘✪★⚠️)
            or (0x2650 <= cp <= 0x265F)                           # Chess symbols
            or (keep_emojis and (0x1F300 <= cp <= 0x1F9FF))):     # Emoji — gated: only when PIL rendering follows
            safe.append(ch)
        else:
            continue  # Strip silently — never inject '?'
    return ''.join(safe)


# ── Paragraph helpers (no more _wrap_emoji / _register_symbola) ──────────
def _paragraph(text: str, style: ParagraphStyle, *, font_name: str) -> Paragraph:
    safe = _glyph_safe(str(text), font_name=font_name)
    return Paragraph(escape(safe), style)


def _format_markdown(text: str) -> str:
    """Convert basic markdown to ReportLab-compatible XML."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    # Strip markdown headings that leak into the PDF
    # Handles "##", "###", ... with optional leading spaces.
    text = re.sub(r'^\s*#{2,6}\s*', '', text, flags=re.MULTILINE)
    # Also strip inline heading markers that can appear after table labels
    # (e.g. "Explanation ### Highlights").
    text = re.sub(r'(?m)(^|\s)#{2,6}\s+', r'\1', text)
    # LLM artifacts: LaTeX-escaped dollar signs (\$35.6B → $35.6B)
    text = text.replace('\\$', '$')
    # LLM artifacts: backslash-escaped percent, ampersand, hash
    for ch in ('%', '&', '#', '_'):
        text = text.replace(f'\\{ch}', ch)
    # ── Strip markdown table syntax that leaks into prose ──
    # Kill separator rows: |---|...| (any combination of hyphens, colons, spaces)
    text = re.sub(r'^\s*\|[\s\-:]+\|\s*$', '', text, flags=re.MULTILINE)
    # Kill pipe-delimited table rows that leak (e.g. "| cell | cell |")
    # Only strip if line starts with | and has at least 2 | separators
    text = re.sub(r'^\s*\|.+\|.+\|\s*$', '', text, flags=re.MULTILINE)
    # Remove double blank lines created by stripping
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _paragraph_md(text: str, style: ParagraphStyle, *, font_name: str) -> Paragraph:
    """Paragraph with markdown formatting support (bold/italic).
    Newlines are converted to <br/> for proper line breaks in ReportLab XML."""
    safe = _glyph_safe(str(text), font_name=font_name)
    formatted = _format_markdown(safe)
    # Convert newlines to <br/> for ReportLab Paragraph (XML-based, \n = whitespace)
    # Double newlines → paragraph break, single newlines → line break
    formatted = formatted.replace('\n\n', '<br/><br/>')
    formatted = formatted.replace('\n', '<br/>')
    formatted = formatted.replace('Investor insight', 'Investor\u00A0insight')
    # Ensure bullet markers and key phrases always start on a new line.
    # Process LONGER phrases first to avoid partial matches (e.g., 'Investor insight'
    # before 'insight'). Only match when preceded by space or at line start.
    import re as _re_markers
    marker_list = sorted([
        '●', '•', '👉', '→', '🎯', '⚠️', '✅', '❌',
        'Investor insight', 'Key takeaway', 'Risk factor',
        '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩',
        'Caution:', 'Essential insight:', 'One-line summary:',
        'Investor takeaway:', 'Verdict takeaway:', 'Operating takeaway:',
        'Cash flow takeaway:', 'Capital efficiency takeaway:',
        'Valuation takeaway:',
    ], key=len, reverse=True)  # longest first
    for marker in marker_list:
        # Match marker preceded by space or at start of text (after <br/>)
        escaped_marker = _re_markers.escape(marker)
        formatted = _re_markers.sub(
            rf'(?<=[ >])({escaped_marker})',
            rf'<br/>\1',
            formatted
        )
    # Normalize numbered bullets and analysis markers often returned by LLMs
    # Example: "(1) ... Data: ... Investor implication: ..."
    formatted = _re_markers.sub(r'(?<!^)(\s*)(\(\d{1,2}\)\s+)', r'<br/>\2', formatted)
    formatted = _re_markers.sub(r'\s+(Data:\s+)', r'<br/>\1', formatted)
    formatted = _re_markers.sub(r'\s+(Investor implication:\s+)', r'<br/>\1', formatted)

    # ── Strip orphaned markers / empty bullets ──
    # Lines like "<br/>●" or "<br/>● " or "<br/>>" with nothing after are clutter
    formatted = _re_markers.sub(r'<br/>\s*(●|•|👉|→|>|🎯|⚠️|✅|❌)\s*<br/>', '<br/>', formatted)
    # Remove leading standalone markers with nothing after
    formatted = _re_markers.sub(r'^(●|•|👉|→|>|🎯|⚠️|✅|❌)\s*<br/>', '', formatted, flags=_re_markers.MULTILINE)
    formatted = _re_markers.sub(r'<br/>(●|•|👉|→|>|🎯|⚠️|✅|❌)\s*$', '', formatted)
    escaped = escape(formatted)
    # Unescape the XML tags we intentionally added
    escaped = escaped.replace('&lt;br/&gt;', '<br/>')
    escaped = escaped.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    escaped = escaped.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
    return Paragraph(escaped, style)


def _paragraph_with_emojis(text: str, style: ParagraphStyle, *, font_name: str, emoji_size: int = 14) -> list:
    """Render text with inline emoji images. Returns list of flowables.

    Structural emojis (👉🧠🎯⚠️📊📌✅❌) are kept as Unicode in the text
    and rendered as PIL+NotoColorEmoji PNG images via line/block flowables.

    Non-emoji text flows through _paragraph_md for standard formatting.
    """
    # Pre-process: strip redundant emojis, keep structural ones
    clean = str(text).translate(_EMOJI_STRIP_MAP)
    clean = _glyph_safe(clean, font_name=font_name, keep_emojis=True)
    if not _STRUCTURAL_EMOJIS.search(clean):
        return [_paragraph_md(text, style, font_name=font_name)]

    # Force structural markers onto their own logical lines before building
    # marker rows. This avoids one very wide inline table for long commentary.
    clean = re.sub(r"(?<!^)(?<!\n)\s*([👉🧠🎯⚠✅❌📊📌])", r"\n\1", clean)

    available_width = LETTER[0] - (1.35 * inch)
    marker_width = emoji_size + 5
    text_width = max(available_width - marker_width, 120)

    def marker_row(emoji_char: str, segment: str) -> Table:
        image = _diamond_image(size=emoji_size) if emoji_char == "◆" else _emoji_to_image(emoji_char, size=emoji_size)
        paragraph = _paragraph_md(segment.strip() or " ", style, font_name=font_name)
        table = Table([[image, paragraph]], colWidths=[marker_width, text_width], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 4),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
            ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
        ]))
        return table

    flowables: list = []
    for raw_line in clean.splitlines():
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 0.04 * inch))
            continue

        cursor = 0
        for match in _STRUCTURAL_EMOJIS.finditer(line):
            prefix = line[cursor:match.start()].strip()
            next_match = _STRUCTURAL_EMOJIS.search(line, match.end())
            end = next_match.start() if next_match else len(line)
            segment = line[match.end():end]

            # ── Keep short labels like "(1)" / "(2)" inline with the marker ──
            # instead of creating a separate Paragraph that forces a line break.
            _SHORT_LABEL = re.compile(r'^\(\d{1,2}\)$')
            if prefix and _SHORT_LABEL.match(prefix):
                segment = f"{prefix} {segment}"
                prefix = ""

            if prefix:
                flowables.append(_paragraph_md(prefix, style, font_name=font_name))
            flowables.append(marker_row(match.group(0), segment))
            cursor = end

        suffix = line[cursor:].strip()
        if suffix:
            flowables.append(_paragraph_md(suffix, style, font_name=font_name))

    return flowables or [_paragraph_md(text, style, font_name=font_name)]


# ── Document structure helpers ──────────────────────────────────────────
def _official_website(report: EarningsDeepDiveReport) -> str | None:
    """Return the official website URL, validated against known-good sources.
    Falls back to yfinance company_website if LLM-generated sources contain hallucinations."""
    
    # Known-fake domains that LLMs hallucinate (add to blocklist as discovered)
    _FAKE_DOMAINS = {
        'eageroryx.dev', 'example.com', 'placeholder.com', 'test.com',
        'fake-url.com', 'not-real.com', 'your-company.com',
    }
    
    # First try: company_overview.company_profile.website (from yfinance, reliable)
    if report.company_overview and report.company_overview.company_profile.website:
        url = report.company_overview.company_profile.website.strip()
        domain = url.split('/')[2] if '://' in url else url.split('/')[0]
        domain = domain.replace('www.', '').lower()
        if domain not in _FAKE_DOMAINS and '.' in domain:
            return url
    
    # Second try: sources with "website"/"official" label (LLM-generated, validate)
    for source in report.sources:
        label = source.label.lower()
        if any(kw in label for kw in ("website", "official", "company site", "homepage")) and source.url:
            url = source.url.strip()
            # Extract domain and validate
            domain = url.split('/')[2] if '://' in url else url.split('/')[0]
            domain = domain.replace('www.', '').lower()
            if domain not in _FAKE_DOMAINS and '.' in domain and len(domain) > 5:
                return url
    
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
            if source.url:
                return source.url
            note = source.note or ""
            if report.language != "jp" and note == "データ未取得":
                return "Unavailable from reviewed sources"
            if note.strip().upper() == "N/A":
                return "Unavailable from reviewed sources"
            return note or "Unavailable from reviewed sources"
    return "Unavailable from reviewed sources"


def _earnings_documents_story(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts: PdfFontSet,
) -> list:
    transcript_label = None
    transcript_url = None
    for source in report.sources:
        label_lower = source.label.lower()
        if "transcript" in label_lower:
            transcript_label = source.label
            transcript_url = source.url
            break
    if not transcript_label:
        transcript_label = "Earnings Transcript — Seeking Alpha"
        transcript_url = f"https://seekingalpha.com/symbol/{report.ticker.upper()}/earnings/transcripts"

    ir_value = _source_note(report, "investor relations")
    press_release_value = _source_note(report, "press release")
    presentation_value = _source_note(report, "presentation")
    if report.language == "jp":
        rows = [
            (transcript_label, transcript_url or "Unavailable from reviewed sources", "Earning Call Transcript source"),
            ("Official Investor Relations", ir_value, "Press Release / Earning Call Presentation"),
            ("Press Release", press_release_value, "会社開示データの一次ソース"),
            ("Earning Call Presentation", presentation_value, "補足KPI・セグメント・ガイダンス確認"),
        ]
    else:
        rows = [
            (transcript_label, transcript_url or "Unavailable from reviewed sources", "Earning Call Transcript source"),
            ("Official Investor Relations", ir_value, "Press Release / Earning Call Presentation"),
            ("Press Release", press_release_value, "Primary company-reported earnings source"),
            ("Earning Call Presentation", presentation_value, "Supplemental KPIs, segments, and guidance"),
        ]

    section = type(
        "DocumentsSection",
        (),
        {
            "table": type(
                "DocumentsTable",
                (),
                {
                    "columns": [
                        translate("Document / Source", report.language),
                        translate("Target-company URL or status", report.language),
                        translate("Used for", report.language),
                    ],
                    "rows": [
                        type("DocumentsRow", (), {"label": label, "cells": [value, used_for]})
                        for label, value, used_for in rows
                    ],
                },
            )()
        },
    )()
    story = [Paragraph(translate("Earnings Documents", report.language), styles["section"])] + _table(section, styles, fonts)
    # Page break before sections is handled by the main render loop
    return story


def _section_continuation(section, report: EarningsDeepDiveReport) -> list[str]:
    if report.language == "jp":
        return {
            "Highlights": [
                f"👉 {report.company} ({report.ticker}) の良い点と懸念点は、必ず表の数値・Transcript・Press Releaseに戻して確認します。",
                "● 例示企業の数字は使わず、対象企業の実績・前年比・ガイダンスだけで判断します。",
            ],
            "Operating Metrics": [
                "👉 売上、粗利、営業利益、純利益は同じ会計基準・同じ期間で比較し、成長の質を確認します。",
            ],
            "Cash Flow": [
                "📌 FCF = OCF - CapEx",
                "👉 キャッシュフローは会計上の利益が現金に変わっているかを見るため、決算の信頼度チェックに使います。",
            ],
        }.get(section.key, [])
    return {
        "Highlights": [
            "Key takeaways are derived from sourced metrics, transcript, press release, or company presentation.",
            "All figures are sourced; no data is invented.",
        ],
        "Operating Metrics": [
            "Revenue, gross profit, operating income, and net income are compared on a consistent period and accounting basis to assess earnings quality.",
        ],
        "Cash Flow": [
            "FCF = OCF − CapEx.",
            "Cash flow analysis verifies whether accounting earnings are converting to owner cash.",
        ],
    }.get(section.key, [])


# ── Source label abbreviation ──────────────────────────────────────────────

_SOURCE_ABBREV = {
    "SEC Filing (10-Q/10-K) via EDGAR": "SEC 10-Q/K",
    "SEC Filing (10-K) via EDGAR": "SEC 10-K",
    "SEC Filing (10-Q) via EDGAR": "SEC 10-Q",
    "yfinance (Yahoo Finance)": "Yahoo Finance",
    "finnhub-python (Finnhub)": "Finnhub",
    "Company IR website": "IR website",
    "Press release": "Press Release",
    "Earnings transcript": "Transcript",
    "Calculated / Derived": "Calculated",
    "Analyst consensus (yfinance)": "Consensus",
    "Analyst consensus via yfinance": "Consensus",
    "XBRL via EDGAR": "XBRL/EDGAR",
    "Not disclosed": "—",
    "Data not available in transcript": "—",
}


def _shorten_source(label: str) -> str:
    """Shorten long source labels for compact table rendering."""
    for long, short in _SOURCE_ABBREV.items():
        if long.lower() in label.lower():
            return short
    # Truncate URLs to domain
    if "http" in label:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(label)
            return parsed.netloc or parsed.path[:40]
        except Exception:
            pass
    return label


def _table(section, styles: dict[str, ParagraphStyle], fonts: PdfFontSet) -> list:
    """Build a ReportLab Table with proper word-wrapping via Paragraph cells."""
    BASE_MAX_CELL_CHARS = 160  # keep rich context while still guarding pathological overflows
    
    # Build cell style — compact font, tight leading, force word wrap
    cell_style = ParagraphStyle(
        "DeepDiveTableCell",
        fontName=fonts.regular,
        fontSize=7,
        leading=8.5,
        textColor=_TEXT,
        alignment=TA_LEFT,
        wordSpace=0,
        splitLongWords=True,
        allowWidows=0,
        allowOrphans=0,
    )
    cell_styles = {
        "default": cell_style,
        "positive": ParagraphStyle("DeepDiveTableCellPositive", parent=cell_style, textColor=_POSITIVE),
        "negative": ParagraphStyle("DeepDiveTableCellNegative", parent=cell_style, textColor=_NEGATIVE),
    }

    def _indicator_style(column: str, value: str) -> ParagraphStyle:
        col = column.lower()
        text = value.strip().lower()
        if not text or text in {"not available", "not disclosed", "n/a", "—"}:
            return cell_style
        signal_column = "yoy" in col or "estimate" in col or "change" in col
        if signal_column and re.search(r"(^|[\s(])\+\d", text):
            return cell_styles["positive"]
        if signal_column and re.search(r"(^|[\s(])-\d", text):
            return cell_styles["negative"]
        if any(word in text for word in ("beat", "positive", "favorable", "growth", "improved", "strong")):
            return cell_styles["positive"]
        if any(word in text for word in ("miss", "negative", "decline", "compression", "pressure", "weak")):
            return cell_styles["negative"]
        return cell_style
    
    data = [
        [_paragraph(column, styles["small_bold"], font_name=fonts.bold) for column in section.table.columns]
    ]
    explanation_rows = []  # yanked out: render as prose below table
    for row in section.table.rows:
        label = str(row.label).strip()
        cells_text = [str(c).strip() for c in row.cells]
        all_text = label + " " + " ".join(cells_text)
        # Skip prose rows: label starts with explanation keywords, OR total text is too long
        # (data rows are compact; prose rows like "Explanation and analysis..." bloat cells)
        if (label.lower().startswith(("explanation", "discussion", "analysis", "commentary", "note"))
            or len(all_text) > 200):
            explanation_rows.append(all_text[:300])
            continue
        row_values = [row.label, *row.cells]
        truncated = []
        for cell in row_values:
            column = section.table.columns[len(truncated)] if len(truncated) < len(section.table.columns) else ""
            s = str(cell).strip()
            if s.upper() == "N/A":
                s = "Not disclosed"
            column_lower = column.lower()
            cell_limit = BASE_MAX_CELL_CHARS
            if "source" in column_lower:
                cell_limit = 96
            elif any(token in column_lower for token in ("comparison", "advantage", "analysis", "commentary", "note")):
                cell_limit = 240
            if len(s) > cell_limit:
                s = s[:cell_limit - 1] + "…"
            # Shorten source labels for compact table rendering
            if "source" in column_lower:
                s = _shorten_source(s)
            safe = _glyph_safe(s, font_name=fonts.regular)
            truncated.append(Paragraph(escape(safe), _indicator_style(column, s)))
        data.append(truncated)

    available_width = LETTER[0] - (1.35 * inch)
    col_count = max(1, len(section.table.columns))
    MIN_COL = 1.00 * inch
    if col_count == 7:
        # Wider Driver column (most text-heavy) while keeping the total width below
        # the frame. The older widths exceeded the printable area and pressured
        # ReportLab into overflow-prone layouts.
        # Segment | Revenue | Prior Year | YoY | % of Total | Driver | Source
        col_widths = [0.95 * inch, 0.82 * inch, 0.82 * inch, 0.62 * inch, 0.52 * inch, 1.28 * inch, 1.05 * inch]
    elif col_count == 6:
        # Wider Source column to prevent overflow — shrink label column
        col_widths = [1.15 * inch, 1.05 * inch, 1.00 * inch, 0.95 * inch, 1.30 * inch, 1.65 * inch]
    elif col_count == 5:
        col_widths = [1.20 * inch, 1.15 * inch, 1.15 * inch, 1.25 * inch, 1.60 * inch]
    elif col_count == 4:
        col_widths = [1.50 * inch, 1.50 * inch, 1.50 * inch, 1.50 * inch]
    elif col_count == 3:
        # Earnings Documents table: wide URL column, narrower "Used for"
        if any("URL" in c or "url" in c or "status" in c.lower() for c in section.table.columns):
            col_widths = [1.70 * inch, 2.80 * inch, 1.40 * inch]
        else:
            col_widths = [1.80 * inch, 1.80 * inch, 2.00 * inch]
    elif col_count == 2:
        col_widths = [2.20 * inch, 3.20 * inch]
    else:
        col_widths = [max(MIN_COL, available_width / col_count)] * col_count

    table = Table(data, colWidths=col_widths, splitByRow=1, repeatRows=1, hAlign="LEFT")
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
    # Render extracted prose rows through markdown-aware formatter so raw
    # headings (e.g. ###) and list markers don't leak into the final PDF.
    prose_rows = [_paragraph_md(t[:300], cell_style, font_name=fonts.regular) for t in explanation_rows]
    return [table] + prose_rows


# ── PyMuPDF Page Number Stamping ───────────────────────────────────────

def _stamp_page_numbers(pdf_path: str) -> None:
    """Post-process: stamp 'X / N' page numbers in dark header bar using PyMuPDF.
    
    Called AFTER doc.build() completes, so the total page count is known.
    """
    import fitz
    
    doc = fitz.open(pdf_path)
    total = doc.page_count
    if total <= 1:
        doc.close()
        return
    
    width, height = LETTER
    # Match _draw_header_bar: white text, right-aligned at header bar position
    # Text box: right edge at right margin, positioned in the dark bar area
    text_x0 = 0
    text_y0 = height - 0.38 * inch  # top of text baseline
    text_x1 = width - 0.55 * inch
    text_y1 = height - 0.18 * inch  # bottom of text box
    
    for i in range(total):
        page = doc[i]
        page_num = i + 1
        text = f"{page_num} / {total}"
        # insert_textbox with right-alignment (align=2)
        page.insert_textbox(
            fitz.Rect(text_x0, text_y0, text_x1, text_y1),
            text,
            fontname="helv",
            fontsize=8,
            color=(1, 1, 1),  # white
            align=2,  # right-aligned
        )
    
    doc.saveIncr()
    doc.close()


# ── Page header/footer (dark bar model parity) ──────────────────────────
_HEADER_BG = colors.HexColor("#2A2A2A")
_HEADER_HEIGHT = 0.45 * inch


def _on_first_page(canvas, doc) -> None:
    """First page: dark header bar with company name + page number."""
    _draw_header_bar(canvas, doc, page_num=1)


def _on_later_pages(canvas, doc) -> None:
    """Later pages: dark header bar with page number."""
    _draw_header_bar(canvas, doc, page_num=canvas.getPageNumber())


def _draw_header_bar(canvas, doc, page_num: int) -> None:
    """Draw a dark gray header bar at the top of the page.
    
    Page numbers are added by _stamp_page_numbers after the PDF is built.
    """
    width = LETTER[0]
    height = LETTER[1]
    
    # Dark gray rectangle across the full page width at the top
    canvas.saveState()
    canvas.setFillColor(_HEADER_BG)
    canvas.rect(0, height - _HEADER_HEIGHT, width, _HEADER_HEIGHT, fill=1, stroke=0)
    
    # Thin dark footer line
    canvas.setStrokeColor(_HEADER_BG)
    canvas.setLineWidth(0.5)
    canvas.line(0.62 * inch, 0.55 * inch, width - 0.62 * inch, 0.55 * inch)
    
    canvas.restoreState()


def _footer(canvas, doc, font_name: str = "Helvetica") -> None:
    """Footer is now handled by _on_first_page / _on_later_pages callbacks."""
    return None


def _section_is_empty(section) -> bool:
    """Return True if the section has no meaningful content (empty/placeholder table)."""
    rows = getattr(section.table, 'rows', [])
    if len(rows) == 0:
        return True
    if len(rows) == 1:
        # Check if the only row is a placeholder
        cells = getattr(rows[0], 'cells', [])
        if all(c.strip() in ('', '-', '—', 'No backlog', 'Not available', 'N/A', 'Not disclosed', 'Unavailable from reviewed sources', 'データ未取得')
               for c in cells):
            return True
    return False


def _section_has_renderable_content(section) -> bool:
    """Return True when a section has table, analysis, or summary content to render."""
    has_table = not _section_is_empty(section)
    has_analysis = any(str(item).strip() for item in getattr(section, "analysis", []) or [])
    summary = str(getattr(section, "summary", "") or "").strip()
    has_summary = bool(summary and summary.lower() not in {"not available.", "not available", "n/a"})
    return has_table or has_analysis or has_summary


# ── Callout box (model parity — blue-bordered insight box) ──────────────
_CALLOUT_BORDER = colors.HexColor("#2563EB")
_CALLOUT_BG = colors.HexColor("#EFF6FF")


def _inline_icon_label(icon: str, text: str, style: ParagraphStyle, *,
                       font_name: str, icon_size: int = 16,
                       available_width: float | None = None) -> Table:
    """Render an emoji icon + text label as a ReportLab Table flowable.
    
    The icon is rendered as a PIL+NotoColorEmoji PNG image to guarantee
    glyph availability regardless of the PDF font. Returns a Table suitable
    for use in section headers, callout headers, and other inline icon
    contexts.
    
    Args:
        icon: Single emoji character (e.g. '👉', '🧠', '🎯')
        text: Label text rendered as a Paragraph
        style: ParagraphStyle for the text
        font_name: Font used for _glyph_safe
        icon_size: Rendered size of the emoji image in points
        available_width: Total available width; if None, uses default LETTER width"""
    if available_width is None:
        available_width = LETTER[0] - 1.24 * inch
    
    emoji_img = _emoji_to_image(icon, size=icon_size)
    text_para = Paragraph(escape(_glyph_safe(text, font_name=font_name)), style)
    
    icon_w = icon_size + 4
    text_w = available_width - icon_w - 6
    
    table = Table([[emoji_img, text_para]], colWidths=[icon_w, max(text_w, 60)], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
    ]))
    return table


def _callout_box(header: str, body: str, styles: dict, font_name: str,
                 *, icon: str | None = None) -> list:
    """Render a blue-bordered callout box matching the model PDF style.
    
    When icon is provided (e.g. '👉'), it is rendered as a PIL+NotoColorEmoji
    image to avoid tofu/null bytes in the PDF output."""
    available_width = LETTER[0] - 1.24 * inch
    padding = 8
    
    if icon:
        header_cell = _inline_icon_label(
            icon, header, styles["small_bold"],
            font_name=font_name, icon_size=16,
            available_width=available_width - 2*padding,
        )
    else:
        header_cell = Paragraph(
            escape(_glyph_safe(header, font_name=font_name)),
            styles["small_bold"]
        )
    
    body_para = Paragraph(escape(_glyph_safe(body, font_name=font_name)), styles["body"])
    
    inner = Table([[header_cell], [body_para]], colWidths=[available_width - 2*padding])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0,0), (-1,-1), padding),
        ("RIGHTPADDING", (0,0), (-1,-1), padding),
        ("TOPPADDING", (0,0), (-1,-1), padding),
        ("BOTTOMPADDING", (0,0), (-1,-1), padding),
        ("BACKGROUND", (0,0), (-1,-1), _CALLOUT_BG),
        ("BOX", (0,0), (-1,-1), 1.5, _CALLOUT_BORDER),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    
    return [Spacer(1, 0.15*inch), inner, Spacer(1, 0.12*inch)]


def _validate_report(report) -> list[str]:
    """Pre-render QA gate. Returns list of issues (empty = pass)."""
    issues = []
    mandatory = {
        "EPS & Revenue", "Highlights", "Operating Metrics", "Cash Flow",
        "Capital Efficiency", "Segments", "Geographic Segments",
        "Forward P/E", "Backlog", "Guidance", "Verdict",
    }
    present = {s.key for s in report.sections}
    missing = mandatory - present
    if missing:
        issues.append(f"Missing mandatory sections: {', '.join(sorted(missing))}")

    for section in report.sections:
        for row in section.table.rows:
            for cell in [row.label, *row.cells]:
                s = str(cell).strip()
                if len(s) > 250:
                    issues.append(f"Cell >250 chars in {section.key}: '{s[:80]}...' ({len(s)} chars)")
                if s.endswith(",") or s.endswith(" and") or (s.endswith(".") and not s.endswith("...") and len(s.split()[-1]) < 3):
                    pass  # not a reliable truncation check

        # Check for "Not disclosed" + unsourced affirmative claim
        analysis_text = " ".join(section.analysis) if section.analysis else ""
        has_not_disclosed = "Not disclosed" in analysis_text or "not disclosed" in analysis_text
        has_affirmative = any(phrase in analysis_text.lower() for phrase in
            ["strongest region", "largest market", "dominant in", "clearly the"])
        if has_not_disclosed and has_affirmative:
            issues.append(f"Geographic: 'Not disclosed' + affirmative claim in {section.key}")

    return issues


def _generate_metrics_chart(chart_data, ticker: str) -> RLImage | None:
    """Generate a bar chart showing EPS/Revenue actual vs estimate as a ReportLab Image.

    Uses matplotlib to render a compact, dark-themed chart (matching the PDF header style)
    showing two comparison panels: EPS and Revenue.

    §25 — returns None if NO data is available (no placeholder charts).
    """
    # §25 — skip chart entirely if no data at all
    eps_ok = (chart_data.eps_actual is not None and chart_data.eps_estimate is not None
              and chart_data.eps_actual != 0 and chart_data.eps_estimate != 0)
    rev_ok = (chart_data.revenue_actual is not None and chart_data.revenue_estimate is not None
              and chart_data.revenue_actual != 0 and chart_data.revenue_estimate != 0)
    if not eps_ok and not rev_ok:
        return None  # no placeholder chart — skip entirely

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        # matplotlib not installed — skip chart generation gracefully
        return None

    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 1.8), facecolor="#FAFAFA")
    except Exception:
        return None

    # Colors matching the PDF aesthetic
    actual_color = "#0B6B3A"   # dark green
    est_color = "#8B8B8B"      # medium gray
    beat_color = "#2563EB"     # blue
    miss_color = "#A33A2A"     # dark red

    # ── Left panel: EPS ──
    eps_actual = chart_data.eps_actual
    eps_estimate = chart_data.eps_estimate
    eps_vs = chart_data.eps_vs_pct

    eps_has_data = eps_actual is not None and eps_estimate is not None
    if eps_has_data:
        bars = ax1.bar(["Estimate", "Actual"], [eps_estimate, eps_actual],
                        color=[est_color, actual_color], width=0.55, edgecolor="white", linewidth=0.5)
        ax1.set_title(f"EPS (${eps_actual:.2f})", fontsize=9, fontweight="bold", color="#111111", pad=8)
        # Annotate bars
        for bar, val in zip(bars, [eps_estimate, eps_actual]):
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                     f"${val:.2f}", ha="center", va="bottom", fontsize=8, color="#111111")
        # Beat/miss annotation
        if eps_vs is not None:
            pct = abs(eps_vs) * 100
            direction = "▲ Beat" if eps_vs > 0 else "▼ Miss"
            color = beat_color if eps_vs > 0 else miss_color
            ax1.text(0.5, 0.90, f"{direction} {pct:.1f}%", transform=ax1.transAxes,
                     ha="center", fontsize=8, fontweight="bold", color=color,
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, alpha=0.9))
    else:
        # §25 — no placeholder: skip panel, don't show "data not available"
        ax1.axis("off")

    # ── Right panel: Revenue ──
    rev_actual = chart_data.revenue_actual
    rev_estimate = chart_data.revenue_estimate
    rev_vs = chart_data.revenue_vs_pct

    rev_has_actual = rev_actual is not None
    rev_has_estimate = rev_estimate is not None
    if rev_has_actual:
        rev_actual_val = float(rev_actual)
        rev_ab = rev_actual_val / 1e9
        if rev_has_estimate:
            rev_estimate_val = float(rev_estimate)
            rev_eb = rev_estimate_val / 1e9
            bars = ax2.bar(["Estimate", "Actual"], [rev_eb, rev_ab],
                            color=[est_color, actual_color], width=0.55, edgecolor="white", linewidth=0.5)
            ax2.set_title(f"Revenue (${rev_ab:.1f}B)", fontsize=9, fontweight="bold", color="#111111", pad=8)
            for bar, val in zip(bars, [rev_eb, rev_ab]):
                ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                         f"${val:.1f}B", ha="center", va="bottom", fontsize=8, color="#111111")
            if rev_vs is not None:
                pct = abs(rev_vs) * 100
                direction = "▲ Beat" if rev_vs > 0 else "▼ Miss"
                color = beat_color if rev_vs > 0 else miss_color
                ax2.text(0.5, 0.90, f"{direction} {pct:.1f}%", transform=ax2.transAxes,
                         ha="center", fontsize=8, fontweight="bold", color=color,
                         bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, alpha=0.9))
        else:
            # Estimate not available — show only the actual revenue bar
            bars = ax2.bar(["Actual"], [rev_ab],
                            color=[actual_color], width=0.55, edgecolor="white", linewidth=0.5)
            ax2.set_title(f"Revenue (${rev_ab:.1f}B)", fontsize=9, fontweight="bold", color="#111111", pad=8)
            for bar, val in zip(bars, [rev_ab]):
                ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                         f"${val:.1f}B", ha="center", va="bottom", fontsize=8, color="#111111")
            ax2.text(0.5, 0.88, "No estimate available", transform=ax2.transAxes,
                     ha="center", fontsize=7, color="#8B8B8B",
                     style="italic")
    else:
        # §25 — no placeholder: skip panel, don't show "data not available"
        ax2.axis("off")

    for ax, has_data in ((ax1, eps_has_data), (ax2, rev_has_actual)):
        if not has_data:
            continue
        ax.set_facecolor("#FAFAFA")
        ax.tick_params(labelsize=7, colors="#666666", length=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#DDDDDD")
        ax.spines["bottom"].set_color("#DDDDDD")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('$%.1f'))

    # Subtitle showing key ratios
    lines = []
    if chart_data.gross_margin is not None:
        lines.append(f"Gross Margin: {chart_data.gross_margin:.1f}%")
    if chart_data.operating_margin is not None:
        lines.append(f"Op Margin: {chart_data.operating_margin:.1f}%")
    if chart_data.pe_forward is not None:
        lines.append(f"Fwd P/E: {chart_data.pe_forward:.1f}x")
    if chart_data.fcf is not None:
        fcf_b = chart_data.fcf / 1e9
        lines.append(f"FCF: ${fcf_b:.1f}B")
    if lines:
        subtitle = " | ".join(lines)
        fig.text(0.5, 0.02, subtitle, ha="center", fontsize=6.5, color="#888888",
                 fontstyle="italic")

    plt.tight_layout(pad=0.8, rect=[0, 0.06, 1, 0.95])

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)

    img = PILImage.open(buf)
    # Scale to fit within margins (~6.1 inches at 150 DPI)
    target_width = 6.1 * inch
    aspect = img.height / img.width
    target_height = target_width * aspect
    return RLImage(buf, width=target_width, height=target_height)


# ── Company Overview rendering ────────────────────────────────────────────

# ── V2.7 Structured PDF Section Renderers ────────────────────────────────────


def render_executive_snapshot(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts,
) -> list:
    """Render the ExecutiveSnapshot as a prominent header card."""
    es = report.executive_snapshot
    if es is None:
        return []

    lang = report.language
    story: list = []

    story.append(Paragraph(
        f'<font size="16" color="#8B1E1E"><b>{escape(es.company_name or report.company)} ({escape(es.ticker or report.ticker)})</b></font>',
        styles["body"],
    ))
    story.append(Spacer(1, 0.05 * inch))

    meta_parts = []
    if es.quarter:
        meta_parts.append(f'{translate("Quarter", lang)}: {es.quarter}')
    if es.generated_at:
        from datetime import datetime as Dt
        try:
            dt = Dt.fromisoformat(es.generated_at.replace("Z", "+00:00"))
            meta_parts.append(f'{translate("Generated", lang)}: {dt.strftime("%B %d, %Y")}')
        except Exception:
            meta_parts.append(f'{translate("Generated", lang)}: {es.generated_at}')
    if meta_parts:
        story.append(Paragraph(
            f'<font size="9" color="#5D5D5D">{"  ·  ".join(meta_parts)}</font>',
            styles["body"],
        ))
        story.append(Spacer(1, 0.10 * inch))

    # Price & Market Cap row
    stats = []
    if es.price is not None:
        stats.append(f'{translate("Price", lang)}: ${es.price:,.2f}')
    if es.market_cap_display:
        stats.append(f'{translate("Market Cap", lang)}: {es.market_cap_display}')
    elif es.market_cap is not None:
        stats.append(f'{translate("Market Cap", lang)}: ${es.market_cap:,.0f}')
    if es.sector:
        stats.append(f'{translate("Sector", lang)}: {es.sector}')
    if stats:
        story.append(Paragraph(
            f'<font size="10">{"  ·  ".join(stats)}</font>',
            styles["body"],
        ))
        story.append(Spacer(1, 0.08 * inch))

    # Verdict badge
    if es.verdict:
        verdict_color = "#1A6B3C" if es.verdict.upper() == "BUY" else (
            "#D97706" if es.verdict.upper() == "HOLD" else "#A33A2A"
        )
        score_text = ""
        if es.decision_score is not None:
            score_text = f"  ({es.decision_score}/{es.decision_max})"
        story.append(Paragraph(
            f'<font size="12" color="{verdict_color}"><b>{es.verdict.upper()}{score_text}</b></font>',
            styles["body"],
        ))
        story.append(Spacer(1, 0.10 * inch))

    # Next earnings
    if es.next_earnings_date:
        story.append(Paragraph(
            f'<font size="9" color="#5D5D5D">{translate("Next Earnings", lang)}: {es.next_earnings_date}</font>',
            styles["body"],
        ))
        story.append(Spacer(1, 0.08 * inch))

    return story


def render_financial_metrics(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts,
) -> list:
    """Render FinancialMetrics as a structured table."""
    fm = report.financial_metrics
    if fm is None:
        return []

    lang = report.language
    story: list = []

    story.append(Paragraph(translate("Financial Metrics", lang), styles["section"]))
    story.append(Spacer(1, 0.10 * inch))

    rows: list[list] = []
    label_style = styles["small_bold"]
    value_style = styles["small"]

    def _fm_row(label_en: str, value, display_val=None):
        if value is None and display_val is None:
            return
        label = translate(label_en, lang)
        display = display_val or f"{value:,.2f}" if isinstance(value, (int, float)) else str(value)
        rows.append([
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph(escape(_glyph_safe(display, font_name=fonts.regular)), value_style),
        ])

    # EPS block
    _fm_row("EPS (Actual)", fm.eps_actual, fm.eps_actual_display)
    _fm_row("EPS (Estimate)", fm.eps_estimate, fm.eps_estimate_display)
    _fm_row("EPS Beat %", fm.eps_beat_pct, fm.eps_beat_pct_display)

    # Revenue block
    _fm_row("Revenue (Actual)", fm.revenue_actual, fm.revenue_actual_display)
    _fm_row("Revenue (Estimate)", fm.revenue_estimate, fm.revenue_estimate_display)
    _fm_row("Revenue Beat %", fm.revenue_beat_pct, fm.revenue_beat_pct_display)

    # Margins
    _fm_row("Gross Margin", fm.gross_margin, fm.gross_margin_display)
    _fm_row("Operating Margin", fm.operating_margin, fm.operating_margin_display)
    _fm_row("Net Margin", fm.net_margin, fm.net_margin_display)

    # Growth
    _fm_row("Revenue Growth (YoY)", fm.revenue_growth_yoy, fm.revenue_growth_yoy_display)
    _fm_row("EPS Growth (YoY)", fm.eps_growth_yoy, fm.eps_growth_yoy_display)

    # FCF
    _fm_row("Free Cash Flow", fm.fcf, fm.fcf_display)

    if rows:
        available_w = LETTER[0] - 1.24 * inch
        table = Table(rows, colWidths=[1.65 * inch, available_w - 1.75 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRID),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.10 * inch))

    return story


def render_valuation(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts,
) -> list:
    """Render ValuationSection multiples table."""
    v = report.valuation
    if v is None:
        return []

    lang = report.language
    story: list = []

    story.append(Paragraph(translate("Valuation", lang), styles["section"]))
    story.append(Spacer(1, 0.10 * inch))

    rows: list[list] = []
    label_style = styles["small_bold"]
    value_style = styles["small"]

    def _v_row(label_en: str, value, display_val=None):
        if value is None and display_val is None:
            return
        label = translate(label_en, lang)
        display = display_val or f"{value:,.2f}" if isinstance(value, (int, float)) else str(value)
        rows.append([
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph(escape(_glyph_safe(display, font_name=fonts.regular)), value_style),
        ])

    _v_row("P/E (Trailing)", v.pe_trailing, v.pe_trailing_display)
    _v_row("P/E (Forward)", v.pe_forward, v.pe_forward_display)
    _v_row("PEG Ratio", v.peg_ratio, v.peg_ratio_display)
    _v_row("Price / Sales", v.price_to_sales, v.price_to_sales_display)
    _v_row("Price / Book", v.price_to_book, v.price_to_book_display)
    _v_row("EV / EBITDA", v.ev_to_ebitda, v.ev_to_ebitda_display)
    _v_row("FCF Yield", v.fcf_yield, v.fcf_yield_display)
    _v_row("Dividend Yield", v.dividend_yield, v.dividend_yield_display)

    if rows:
        available_w = LETTER[0] - 1.24 * inch
        table = Table(rows, colWidths=[1.65 * inch, available_w - 1.75 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRID),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.10 * inch))

    return story


def render_valuation_context(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts,
) -> list:
    """Render ValuationContextSection — 7 context signals."""
    vc = report.valuation_context
    if vc is None:
        return []

    lang = report.language
    story: list = []

    story.append(Paragraph(translate("Valuation Context", lang), styles["section"]))
    story.append(Spacer(1, 0.10 * inch))

    signals = [
        (translate("PEG Signal", lang), vc.peg_signal, vc.peg_signal_label, vc.peg_signal_detail),
        (translate("P/S vs Growth", lang), vc.ps_vs_growth_signal, vc.ps_vs_growth_label, None),
        (translate("EV/EBITDA vs Growth", lang), vc.ev_ebitda_vs_growth_signal, vc.ev_ebitda_vs_growth_label, None),
        (translate("P/FCF vs Growth", lang), vc.pfcf_vs_growth_signal, vc.pfcf_vs_growth_label, None),
        (translate("FCF Yield", lang), vc.fcf_yield_signal, vc.fcf_yield_label, None),
    ]

    for name, signal_val, label, detail in signals:
        if signal_val is None and label is None:
            continue
        parts = [f'<b>{escape(name)}:</b>']
        if signal_val is not None:
            parts.append(f'{signal_val:,.2f}')
        if label:
            parts.append(f'<font color="#5D5D5D">({escape(label)})</font>')
        if detail:
            parts.append(f'<font size="8" color="#5D5D5D">— {escape(detail)}</font>')
        story.append(Paragraph("  ".join(parts), styles["small"]))
        story.append(Spacer(1, 0.05 * inch))

    # Valuation support summary
    if vc.valuation_support:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(
            f'<b>{translate("Valuation Support", lang)}:</b> {escape(vc.valuation_support)}',
            styles["small"],
        ))
    if vc.context_summary:
        story.append(Paragraph(
            f'<font color="#5D5D5D">{escape(vc.context_summary)}</font>',
            styles["small"],
        ))
        story.append(Spacer(1, 0.08 * inch))

    return story


def render_peer_benchmark(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts,
) -> list:
    """Render PeerBenchmarkSection — peer-relative comparison."""
    pb = report.peer_benchmark
    if pb is None:
        return []

    lang = report.language
    story: list = []

    story.append(Paragraph(translate("Peer Benchmark", lang), styles["section"]))
    story.append(Spacer(1, 0.10 * inch))

    # Peer group line
    if pb.peer_group:
        ticker_list = ", ".join(pb.peer_tickers) if pb.peer_tickers else ""
        story.append(Paragraph(
            f'<b>{translate("Peer Group", lang)}:</b> {escape(pb.peer_group)}'
            + (f" ({escape(ticker_list)})" if ticker_list else ""),
            styles["small"],
        ))
        story.append(Spacer(1, 0.10 * inch))

    # Relative labels table
    pb_rows = []
    label_style = styles["small_bold"]
    value_style = styles["small"]

    for dim_label, rel_label, rel_detail in [
        (translate("Valuation", lang), pb.relative_valuation_label, pb.relative_valuation_detail),
        (translate("Growth", lang), pb.relative_growth_label, pb.relative_growth_detail),
        (translate("Quality", lang), pb.relative_quality_label, pb.relative_quality_detail),
    ]:
        if rel_label is None:
            continue
        detail_text = f'<font size="8" color="#5D5D5D"> {escape(rel_detail)}</font>' if rel_detail else ""
        pb_rows.append([
            Paragraph(f"<b>{escape(dim_label)}</b>", label_style),
            Paragraph(f"{escape(rel_label)}{detail_text}", value_style),
        ])

    if pb_rows:
        available_w = LETTER[0] - 1.24 * inch
        table = Table(pb_rows, colWidths=[1.65 * inch, available_w - 1.75 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRID),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.10 * inch))

    # Benchmark summary
    if pb.benchmark_summary:
        story.append(Paragraph(
            f'<font size="9" color="#5D5D5D"><i>{escape(pb.benchmark_summary)}</i></font>',
            styles["small"],
        ))
        story.append(Spacer(1, 0.08 * inch))

    return story


def render_data_quality(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts,
) -> list:
    """Render DataQualitySection — source freshness + completeness."""
    dq = report.data_quality
    if dq is None:
        return []

    lang = report.language
    story: list = []

    story.append(Paragraph(translate("Data Quality", lang), styles["section"]))
    story.append(Spacer(1, 0.10 * inch))

    # Source freshness table
    dq_rows = []
    label_style = styles["small_bold"]
    value_style = styles["small"]

    for src_name, freshness, label in [
        ("YFinance", dq.yfinance_freshness, dq.yfinance_source_label),
        ("Finnhub", dq.finnhub_freshness, dq.finnhub_source_label),
        ("SEC EDGAR", dq.sec_edgar_freshness, dq.sec_edgar_source_label),
        ("Transcript", dq.transcript_freshness, dq.transcript_source_label),
    ]:
        if freshness is None and label is None:
            continue
        display = f"{escape(label)}" if label else ""
        if freshness:
            display += f"  <font size=\"7\" color=\"#999\">({escape(freshness)})</font>"
        if display:
            dq_rows.append([
                Paragraph(f"<b>{escape(src_name)}</b>", label_style),
                Paragraph(display, value_style),
            ])

    if dq_rows:
        available_w = LETTER[0] - 1.24 * inch
        table = Table(dq_rows, colWidths=[1.65 * inch, available_w - 1.75 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRID),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.10 * inch))

    # Confidence + completeness
    if dq.overall_confidence:
        conf_map = {"high": "#1A6B3C", "medium": "#D97706", "low": "#A33A2A"}
        color = conf_map.get(dq.overall_confidence.lower(), "#5D5D5D")
        story.append(Paragraph(
            f'<b>{translate("Confidence", lang)}:</b> '
            f'<font color="{color}">{dq.overall_confidence.upper()}</font>',
            styles["small"],
        ))
    if dq.completeness_score is not None:
        pct = dq.completeness_score
        score_color = "#1A6B3C" if pct >= 80 else "#D97706" if pct >= 50 else "#A33A2A"
        story.append(Paragraph(
            f'<b>{translate("Completeness", lang)}:</b> '
            f'<font color="{score_color}">{pct}/{dq.completeness_max} ({pct}%)</font>',
            styles["small"],
        ))
    if dq.missing_fields:
        story.append(Paragraph(
            f'<font size="8" color="#A33A2A"><b>{translate("Missing", lang)}:</b> '
            f'{", ".join(dq.missing_fields)}</font>',
            styles["small"],
        ))
        story.append(Spacer(1, 0.06 * inch))

    return story


def render_company_overview(
    report: EarningsDeepDiveReport,
    styles: dict[str, ParagraphStyle],
    fonts: PdfFontSet,
) -> list:
    """Render the Company Overview section as PDF flowables.

    Six subsections:
    1. Company Profile (header block)
    2. Business Description (text block)
    3. Key Financials (bullet list)
    4. Competitive Position (text block)
    5. Recent Developments (bullet list with sentiment)
    6. Competitors Table

    Returns empty list if report.company_overview is None.
    Uses report.language to select text_en/text_jp on bilingual fields.
    """
    co = report.company_overview
    if co is None:
        return []

    lang = report.language
    story: list = []

    # ── Section header ──
    story.append(Paragraph(
        translate("Company Overview", lang),
        styles["section"],
    ))
    story.append(Spacer(1, 0.08 * inch))

    cp = co.company_profile

    # ── 1. Company Profile block (compact 2-column) ──
    profile_rows: list[list] = []
    label_style = styles["small_bold"]
    value_style = styles["small"]

    def _add_row(label_en: str, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        label = translate(label_en, lang)
        safe_val = escape(_glyph_safe(str(value), font_name=fonts.regular))
        profile_rows.append([
            Paragraph(f"<b>{label}:</b>", label_style),
            Paragraph(safe_val, value_style),
        ])

    _add_row("Ticker", cp.ticker)
    _add_row("Sector", cp.sector)
    _add_row("Industry", cp.industry)
    _add_row("Country", cp.country)
    _add_row("Headquarters", cp.headquarters)
    _add_row("Employees", f"{cp.employees:,}" if cp.employees else None)
    if cp.founded:
        _add_row("Founded", str(cp.founded))
    if cp.website:
        url = escape(cp.website)
        profile_rows.append([
            Paragraph(f"<b>{translate('Website', lang)}:</b>", label_style),
            Paragraph(f'<font size="7"><a href="{url}" color="blue">{url}</a></font>', value_style),
        ])

    if profile_rows:
        available_w = LETTER[0] - 1.24 * inch
        profile_table = Table(profile_rows, colWidths=[1.65 * inch, available_w - 1.75 * inch], hAlign="LEFT")
        profile_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRID),
            ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ]))
        story.append(profile_table)
        story.append(Spacer(1, 0.10 * inch))

    # ── 2. Business Description ──
    if co.business_description and co.business_description.strip():
        story.append(Paragraph(
            f"<b>{translate('Business Description', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_desc = escape(_glyph_safe(co.business_description.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_desc, styles["body"]))
        story.append(Spacer(1, 0.08 * inch))

    def _render_small_bullet_section(title_key: str, items: list[str] | None):
        cleaned = [str(x).strip() for x in (items or []) if str(x).strip()]
        if not cleaned:
            return
        story.append(Paragraph(
            f"<b>{translate(title_key, lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        for item in cleaned[:8]:
            safe_item = escape(_glyph_safe(item, font_name=fonts.regular))
            story.append(Paragraph(f'<font size="9">● {safe_item}</font>', styles["small"]))
            story.append(Spacer(1, 0.03 * inch))
        story.append(Spacer(1, 0.05 * inch))

    # ── 3. Investor perspective subsections ──
    if co.revenue_model and co.revenue_model.strip():
        story.append(Paragraph(
            f"<b>{translate('Revenue Model', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_rev = escape(_glyph_safe(co.revenue_model.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_rev, styles["body"]))
        story.append(Spacer(1, 0.08 * inch))

    _render_small_bullet_section("Business Segments", co.business_segments)
    _render_small_bullet_section("Growth Drivers", co.growth_drivers)
    _render_small_bullet_section("Competitive Advantages (Moats)", co.moats)
    _render_small_bullet_section("Key Metrics / KPIs", co.key_kpis)
    _render_small_bullet_section("Biggest Business Risks", co.business_risks)

    # ── 4. Key Financials ──
    kf = co.key_financials
    has_kf = kf is not None and any([
        kf.market_cap_display, kf.revenue_display, kf.pe_ratio,
        kf.pe_forward, kf.dividend_yield, kf.beta,
        kf.window_52w_high, kf.window_52w_low,
    ])
    if has_kf:
        story.append(Paragraph(
            f"<b>{translate('Key Financials', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        kf_items = []
        if kf.market_cap_display:
            kf_items.append(f"<b>{translate('Market Cap', lang)}:</b> {escape(kf.market_cap_display)}")
        if kf.revenue_display:
            kf_items.append(f"<b>{translate('Revenue', lang)}:</b> {escape(kf.revenue_display)}")
        if kf.pe_ratio is not None:
            kf_items.append(f"<b>{translate('P/E Ratio', lang)}:</b> {kf.pe_ratio:.1f}x")
        if kf.pe_forward is not None:
            kf_items.append(f"<b>{translate('Forward P/E', lang)}:</b> {kf.pe_forward:.1f}x")
        if kf.dividend_yield is not None and kf.dividend_yield > 0:
            # Normalize: if > 0.5 (50%+ dividend impossible), treat as already-percentage form
            dy = kf.dividend_yield
            if dy > 0.5:
                dy = dy / 100  # LLM stored percentage (0.23) instead of decimal (0.0023)
            kf_items.append(f"<b>{translate('Dividend Yield', lang)}:</b> {dy * 100:.2f}%")
        if kf.beta is not None:
            kf_items.append(f"<b>{translate('Beta', lang)}:</b> {kf.beta:.2f}")
        if kf.window_52w_high is not None and kf.window_52w_low is not None:
            kf_items.append(
                f"<b>{translate('52-Week Range', lang)}:</b> "
                f"${kf.window_52w_low:.2f} – ${kf.window_52w_high:.2f}"
            )
        for item in kf_items:
            story.append(Paragraph(
                f'<font size="9">{_glyph_safe(item, font_name=fonts.regular)}</font>',
                styles["small"],
            ))
            story.append(Spacer(1, 0.03 * inch))
        story.append(Spacer(1, 0.05 * inch))

    # ── 5. Competitive Position ──
    if co.competitive_position and co.competitive_position.strip():
        story.append(Paragraph(
            f"<b>{translate('Competitive Position', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_cp = escape(_glyph_safe(co.competitive_position.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_cp, styles["body"]))
        story.append(Spacer(1, 0.08 * inch))

    if co.strengths_vs_competitors and co.strengths_vs_competitors.strip():
        story.append(Paragraph(
            f"<b>{translate('Strengths vs Competitors', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_strengths = escape(_glyph_safe(co.strengths_vs_competitors.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_strengths, styles["body"]))
        story.append(Spacer(1, 0.06 * inch))

    if co.weaker_areas_vs_competitors and co.weaker_areas_vs_competitors.strip():
        story.append(Paragraph(
            f"<b>{translate('Weaker Areas vs Competitors', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_weak = escape(_glyph_safe(co.weaker_areas_vs_competitors.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_weak, styles["body"]))
        story.append(Spacer(1, 0.06 * inch))

    if co.ceo_leadership_style and co.ceo_leadership_style.strip():
        story.append(Paragraph(
            f"<b>{translate('CEO Leadership Style', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_ceo = escape(_glyph_safe(co.ceo_leadership_style.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_ceo, styles["body"]))
        story.append(Spacer(1, 0.06 * inch))

    if co.long_term_vision and co.long_term_vision.strip():
        story.append(Paragraph(
            f"<b>{translate('Long-Term Vision', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        safe_vision = escape(_glyph_safe(co.long_term_vision.strip(), font_name=fonts.regular))
        story.append(Paragraph(safe_vision, styles["body"]))
        story.append(Spacer(1, 0.08 * inch))

    # ── 6. Recent Developments ──
    devs = co.recent_developments
    if devs:
        story.append(Paragraph(
            f"<b>{translate('Recent Developments', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.04 * inch))
        for dev in devs[:5]:  # max 5
            sentiment_color = "#0B6B3A" if dev.sentiment == "positive" else (
                "#A33A2A" if dev.sentiment == "negative" else "#5D5D5D"
            )
            date_str = f" ({dev.date})" if dev.date else ""
            dev_line = (
                f'<font size="9">● <b>{escape(_glyph_safe(dev.title, font_name=fonts.regular))}</b>'
                f'{date_str} — '
                f'{escape(_glyph_safe(dev.summary, font_name=fonts.regular))}'
            )
            if dev.sentiment:
                dev_line += (
                    f' <font color="{sentiment_color}"><i>[{dev.sentiment}]</i></font>'
                )
            dev_line += '</font>'
            story.append(Paragraph(dev_line, styles["small"]))
            story.append(Spacer(1, 0.04 * inch))
        story.append(Spacer(1, 0.05 * inch))

    # ── 6. Competitors Table ──
    competitors = co.competitors
    if competitors:
        story.append(Paragraph(
            f"<b>{translate('Competitors', lang)}</b>",
            styles["body"],
        ))
        story.append(Spacer(1, 0.06 * inch))

        # Table header
        header_style = styles["small_bold"]
        cell_style_small = ParagraphStyle(
            "CoTableCell",
            fontName=fonts.regular,
            fontSize=7.5,
            leading=9.5,
            textColor=_TEXT,
            alignment=TA_LEFT,
        )
        available_w = LETTER[0] - 1.24 * inch
        col_widths = [
            1.25 * inch,                 # Competitor name
            available_w - 4.00 * inch,   # Comparison text
            2.20 * inch,                 # Advantage (wider to avoid clipped rationale)
            0.55 * inch,                 # Source
        ]

        comp_data = [[
            Paragraph(f"<b>{translate('Competitor', lang)}</b>", header_style),
            Paragraph(f"<b>{translate('Comparison', lang)}</b>", header_style),
            Paragraph(f"<b>{translate('Advantage', lang)}</b>", header_style),
            Paragraph("<b>Src</b>", header_style),
        ]]

        for comp in competitors[:6]:
            text = comp.text_en if lang == "en" else (comp.text_jp or comp.text_en)
            adv = comp.competitive_advantage or "—"
            comp_data.append([
                Paragraph(escape(_glyph_safe(comp.competitor_name, font_name=fonts.regular)), cell_style_small),
                Paragraph(escape(_glyph_safe(text[:260], font_name=fonts.regular)), cell_style_small),
                Paragraph(escape(_glyph_safe(adv[:220], font_name=fonts.regular)), cell_style_small),
                Paragraph(
                    f'<font size="7" color="#2563EB"><b>{escape(comp.source_id)}</b></font>',
                    cell_style_small,
                ),
            ])

        comp_table = Table(comp_data, colWidths=col_widths, hAlign="LEFT", splitByRow=1)
        comp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_FILL),
            ("TEXTCOLOR", (0, 0), (-1, 0), _TEXT),
            ("FONTNAME", (0, 0), (-1, 0), fonts.bold),
            ("FONTNAME", (0, 1), (-1, -1), fonts.regular),
            ("GRID", (0, 0), (-1, -1), 0.45, _GRID),
            ("BOX", (0, 0), (-1, -1), 0.8, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(comp_table)

    return story


# ── Main entry point ────────────────────────────────────────────────────
def render_earnings_deep_dive_pdf(report: EarningsDeepDiveReport, output_path: str | Path, include_traceability: bool = False) -> str:
    """Render a structured earnings deep-dive report to an extractable PDF.
    
    Args:
        report: The deep-dive report model
        output_path: Where to write the PDF
        include_traceability: If True, include the Claim Traceability appendix (for internal audit).
                             If False (default), omit it from the client-facing PDF.
    """
    # ── QA gate ──
    validation_issues = _validate_report(report)
    if validation_issues:
        for issue in validation_issues:
            print(f"[QA WARNING] {issue}", file=__import__('sys').stderr)
        # Non-blocking for now — log warnings but don't abort

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fonts = resolve_pdf_fonts(report.language)
    styles = _styles(fonts)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=LETTER,
        rightMargin=0.62 * inch,
        leftMargin=0.62 * inch,
        topMargin=(0.58 + 0.45) * inch,
        bottomMargin=0.62 * inch,
        pageCompression=0,
        title=report.title,
        author="Stock Analysis Pipeline — AI-assisted buy-side research",
        subject=f"Earnings Deep-Dive: {report.company} ({report.ticker}) — {report.quarter}",
        creator="stock-analysis-pipeline v2",
    )
    # Register dark header bar on every page
    doc.onFirstPage = _on_first_page
    doc.onLaterPages = _on_later_pages

    story: list = [
        Paragraph(escape(f"{report.company} ({report.ticker})"), styles["title"]),
        Paragraph(escape(f"{translate('Earnings Deep-Dive', report.language)} - {report.quarter}"), styles["meta"]),
    ]
    website = _official_website(report)
    if website:
        story.append(Paragraph(escape(f"{translate('Official Website', report.language)}: {website}"), styles["meta"]))
    story.extend(_earnings_documents_story(report, styles, fonts))

    # ── Charts: key metrics at a glance ──
    if report.charts and (report.charts.eps_actual or report.charts.revenue_actual):
        story.append(Spacer(1, 0.20 * inch))
        chart_image = _generate_metrics_chart(report.charts, report.ticker)
        if chart_image:
            story.append(chart_image)
        story.append(Spacer(1, 0.15 * inch))

    # ── V2.7 Executive Snapshot (header card, after charts) ──
    es_story = render_executive_snapshot(report, styles, fonts)
    if es_story:
        story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.08 * inch))
        story.extend(es_story)
        story.append(Spacer(1, 0.10 * inch))

    # ── Company Overview (after charts, before deep-dive sections) ──
    co_story = render_company_overview(report, styles, fonts)
    if co_story:
        story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.08 * inch))
        story.extend(co_story)
        story.append(Spacer(1, 0.10 * inch))

    rendered_sections = [section for section in report.sections if _section_has_renderable_content(section)]

    for index, section in enumerate(rendered_sections):
        if index > 0:
            story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.12 * inch))

        # Emoji image + title as flowables
        story.extend(_section_title_flowables(
            section, styles,
            font_name=fonts.regular,
            emoji_size=20,
        ))
        # Spacing between title and table (model parity — prevents title touching table)
        story.append(Spacer(1, 0.10 * inch))

        # Section question is used by the LLM as context — not displayed in PDF (model parity)
        # The section title already identifies the topic

        # Prose-only sections (Highlights, Backlog when not applicable) skip the table
        if section.key == "Highlights":
            # Render Highlights as structured prose — no table
            pass
        else:
            story.extend(_table(section, styles, fonts))
            # Spacing between table and analysis text (prevents text sticking to table)
            story.append(Spacer(1, 0.15 * inch))
        if section.analysis:
            for paragraph in section.analysis:
                story.extend(_paragraph_with_emojis(paragraph, styles["body"], font_name=fonts.regular))

        # ── Nami-san continuation (analysis guidance) ──
        continuation_lines = _section_continuation(section, report)
        if continuation_lines:
            story.append(Spacer(1, 0.10 * inch))
            for line in continuation_lines:
                story.extend(_paragraph_with_emojis(line, styles["body"], font_name=fonts.regular))

        # ── Nami takeaway (callout box — model parity) ──
        if section.summary and section.summary.strip() and section.summary.strip().lower() not in {"not available.", "not available", "n/a"}:
            story.extend(_callout_box(section.summary_label, section.summary, styles, fonts.regular, icon='👉'))

    # ── V2.7 Structured Sections: Financial Metrics, Valuation, Context, Peers ──
    fm_story = render_financial_metrics(report, styles, fonts)
    if fm_story:
        story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.12 * inch))
        story.extend(fm_story)

    v_story = render_valuation(report, styles, fonts)
    if v_story:
        story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.12 * inch))
        story.extend(v_story)

    vc_story = render_valuation_context(report, styles, fonts)
    if vc_story:
        story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.12 * inch))
        story.extend(vc_story)

    pb_story = render_peer_benchmark(report, styles, fonts)
    if pb_story:
        story.append(CondPageBreak(2.25 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
        story.append(Spacer(1, 0.12 * inch))
        story.extend(pb_story)

    if report.sources or report.next_earnings_date or report.earnings_audio_url or report.scoring or report.data_quality:
        story.append(PageBreak())

        # ── 6-Category Scoring Summary (when available) ──
        if report.scoring:
            story.append(Paragraph(translate("Scoring Breakdown", report.language), styles["section"]))
            story.append(Spacer(1, 0.12 * inch))

            # Verdict banner
            verdict_color = "#1A6B3C" if report.scoring.verdict == "BUY" else "#D97706" if report.scoring.verdict == "HOLD" else "#DC2626"
            story.append(Paragraph(
                f'<font size="14" color="{verdict_color}"><b>{report.scoring.verdict}</b></font> '
                f'<font size="11">{translate("Composite Score", report.language)}: {report.scoring.total_score}/{report.scoring.max_total}</font>',
                styles["body"]
            ))
            story.append(Spacer(1, 0.15 * inch))

            # Category bars
            for cat in report.scoring.categories:
                label = cat.label_jp if report.language == "jp" and cat.label_jp else cat.label
                pct = min(100, int(cat.score / cat.max_score * 100))
                bar_width = max(2, int(pct * 1.5))  # scale to points

                bar_color = "#1A6B3C" if pct >= 70 else "#D97706" if pct >= 40 else "#DC2626"

                # Build a simple bar: ████████░░░░  score/max
                filled = int(pct / 5)  # each block = 5%
                empty = 20 - filled
                bar = "█" * filled + "░" * empty

                story.append(Paragraph(
                    f'<font size="9"><b>{label}</b></font> '
                    f'<font size="8" color="{bar_color}">{bar}</font> '
                    f'<font size="9"><b>{cat.score}/{cat.max_score}</b></font>',
                    styles["body"]
                ))
                story.append(Spacer(1, 0.08 * inch))

            story.append(Spacer(1, 0.12 * inch))

        # ── V2.7 Data Quality (source freshness + completeness) ──
        dq_story = render_data_quality(report, styles, fonts)
        if dq_story:
            story.append(HRFlowable(width="100%", thickness=0.5, color=_GRID))
            story.append(Spacer(1, 0.12 * inch))
            story.extend(dq_story)
            story.append(Spacer(1, 0.08 * inch))

        # ── Sources ──
        story.append(Paragraph(translate("Sources", report.language), styles["section"]))
        story.append(Spacer(1, 0.15 * inch))

        # --- Key Dates (prominent, before document sources) ---
        key_items = []
        if report.next_earnings_date:
            try:
                from datetime import datetime
                dt = datetime.strptime(report.next_earnings_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%B %d, %Y")
                days_left = (dt.date() - datetime.now().date()).days
                urgency = "URGENT — " if days_left <= 7 else ("SOON — " if days_left <= 30 else "")
                key_items.append(
                    f"<b>{urgency}Next Earnings:</b> {formatted_date} "
                    f'<font size="8" color="#666666">({days_left} days)</font>'
                )
            except Exception:
                key_items.append(f"<b>Next Earnings:</b> {report.next_earnings_date}")
        if report.earnings_audio_url:
            key_items.append(
                f'<b>Earnings Call Audio:</b> '
                f'<font size="8"><a href="{escape(report.earnings_audio_url)}" color="blue">{escape(report.earnings_audio_url)}</a></font>'
            )
        if key_items:
            story.append(Paragraph(f"<b>{translate('Key Dates', report.language)}</b>", styles["body"]))
            for item in key_items:
                story.append(Paragraph(item, styles["small"]))
                story.append(Spacer(1, 0.08 * inch))
            story.append(Spacer(1, 0.15 * inch))

        # Separate document sources from data sources
        doc_sources = []
        data_sources = []
        doc_labels = {
            "Earnings Transcript", "Official Investor Relations", "Official Website",
            "Press Release", "Earnings Call Presentation", "Seeking Alpha Transcripts",
        }
        for source in report.sources:
            if source.label in doc_labels or "Transcript" in source.label or "Investor" in source.label or "Website" in source.label or "Press Release" in source.label or "Presentation" in source.label:
                doc_sources.append(source)
            else:
                data_sources.append(source)

        # --- Document Sources ---
        if doc_sources:
            story.append(Paragraph(f"<b>{translate('Earnings Documents', report.language)}</b>", styles["body"]))
            for source in doc_sources:
                if source.url:
                    url_text = f'<font size="8"><a href="{escape(source.url)}" color="blue">{escape(source.url)}</a></font>'
                    story.append(Paragraph(url_text, styles["body"]))
                label_text = f'<b>{escape(_glyph_safe(source.label, font_name=fonts.regular))}</b>'
                if source.note:
                    label_text += f'  <font size="8" color="#555555">{escape(_glyph_safe(source.note, font_name=fonts.regular))}</font>'
                story.append(Paragraph(label_text, styles["small"]))
                story.append(Spacer(1, 0.08 * inch))
            story.append(Spacer(1, 0.12 * inch))

        # --- Data Sources ---
        if data_sources:
            story.append(Paragraph(f"<b>{translate('Data & Analytics', report.language)}</b>", styles["body"]))
            for source in data_sources:
                if source.url:
                    url_text = f'<font size="8"><a href="{escape(source.url)}" color="blue">{escape(source.url)}</a></font>'
                    story.append(Paragraph(url_text, styles["body"]))
                label_text = f'<b>{escape(_glyph_safe(source.label, font_name=fonts.regular))}</b>'
                if source.note:
                    label_text += f'  <font size="8" color="#555555">{escape(_glyph_safe(source.note, font_name=fonts.regular))}</font>'
                story.append(Paragraph(label_text, styles["small"]))
                story.append(Spacer(1, 0.08 * inch))

        # Methodology note
        story.append(Spacer(1, 0.2 * inch))
        methodology_label = translate("Methodology", report.language)
        methodology_text = translate(
            "This deep-dive combines quantitative metrics from SEC filings "
            "(via yfinance/Finnhub) with qualitative analysis of the earnings call transcript. "
            "All figures are sourced; no data is invented. "
            "Ratings reflect institutional buy-side analysis standards.",
            report.language,
        )
        story.append(Paragraph(
            f"<b>{methodology_label}:</b> {methodology_text}",
            styles["small"]
        ))

        # ── Claim Traceability Appendix (INTERNAL ONLY — excluded from client PDF) ──
        if include_traceability and report.claim_sources:
            story.append(PageBreak())
            story.append(Paragraph(translate("Claim Traceability", report.language), styles["section"]))
            story.append(Spacer(1, 0.08 * inch))
            story.append(Paragraph(
                f"<i>{translate('Every analytical claim in this report is traceable to a specific data source. This appendix provides the audit trail.', report.language)}</i>",
                styles["small"]
            ))
            story.append(Spacer(1, 0.12 * inch))

            # Group claims by section for readability
            from collections import defaultdict
            by_section: dict[str, list] = defaultdict(list)
            for cs in report.claim_sources[:80]:
                by_section[cs.section].append(cs)

            # ── Source legend (compact) ──
            story.append(Paragraph(f"<b>{translate('Source Legend', report.language)}</b>", styles["body"]))
            legend_items = []
            seen_ids = set()
            for cs in report.claim_sources:
                if cs.source_id not in seen_ids:
                    seen_ids.add(cs.source_id)
                    src_name = cs.source_name or cs.source_id
                    src_url = cs.source_url or ""
                    grounding_info = f" [{cs.grounding}]" if cs.grounding != "direct_metric" else ""
                    if src_url:
                        legend_items.append(
                            f'<font size="8"><b>{cs.source_id}</b> = {_glyph_safe(src_name, font_name=fonts.regular)}'
                            f'{grounding_info} — <a href="{escape(src_url)}" color="blue">link</a></font>'
                        )
                    else:
                        legend_items.append(
                            f'<font size="8"><b>{cs.source_id}</b> = {_glyph_safe(src_name, font_name=fonts.regular)}{grounding_info}</font>'
                        )
            for item in legend_items:
                story.append(Paragraph(item, styles["small"]))
                story.append(Spacer(1, 0.04 * inch))

            story.append(Spacer(1, 0.12 * inch))

            # ── Per-section claim summaries ──
            story.append(Paragraph(f"<b>{translate('Claims by Section', report.language)}</b>", styles["body"]))
            story.append(Spacer(1, 0.08 * inch))

            grounding_colors = {
                "direct_metric": "#1A6B3C",   # green — high confidence
                "calculated": "#2563EB",       # blue — formula
                "direct_quote": "#7C3AED",     # purple — quote
                "document_fact": "#0891B2",    # teal — filing fact
                "inference": "#D97706",        # amber — interpretation
                "unsupported": "#DC2626",      # red — blocked
            }

            for section_name in sorted(by_section.keys()):
                claims = by_section[section_name]
                story.append(Paragraph(
                    f'<font size="9"><b>{_glyph_safe(section_name, font_name=fonts.regular)}</b> '
                    f'({len(claims)} claims)</font>',
                    styles["body"]
                ))
                for cs in claims[:8]:  # Max 8 per section
                    gcolor = grounding_colors.get(cs.grounding, "#666666")
                    claim_text = cs.claim_text or f"{cs.source_field}: {cs.source_value}"
                    story.append(Paragraph(
                        f'<font size="7" color="{gcolor}">[{cs.grounding}]</font> '
                        f'<font size="8"><b>{cs.source_id}</b> → {_glyph_safe(str(claim_text)[:120], font_name=fonts.regular)}'
                        f'{(" <i>(" + cs.confidence + ")</i>") if cs.confidence else ""}</font>',
                        styles["small"]
                    ))
                    story.append(Spacer(1, 0.03 * inch))
                if len(claims) > 8:
                    story.append(Paragraph(
                        f'<font size="7" color="#888888">'
                        + translate("… and {n} more claims (see machine-readable export)", report.language).replace(
                            "{n}", str(len(claims) - 8)
                        )
                        + '</font>',
                        styles["small"]
                    ))
                story.append(Spacer(1, 0.08 * inch))

            story.append(Spacer(1, 0.1 * inch))
            story.append(Paragraph(
                f"<font size='7' color='#888888'>"
                f"<b>{translate('Grounding levels:', report.language)}</b> "
                f"{translate('direct_metric = exact source value | calculated = formula from source data | direct_quote = transcript | document_fact = filing fact | inference = analyst interpretation | unsupported = blocked', report.language)}"
                f"</font>",
                styles["small"]
            ))

    try:
        doc.build(story)
        _stamp_page_numbers(str(output))
    except LayoutError as layout_err:
        # ReportLab LayoutError — likely a table cell overflow.
        # Recover by dropping the last section and retrying.
        import sys
        print(f"[PDF RENDER ERROR] {layout_err}", file=sys.stderr)
        if len(report.sections) > 0:
            problem_section = report.sections[-1]
            print(f"[PDF RENDER] Dropping section '{problem_section.key}' due to layout overflow", file=sys.stderr)
            report.sections = report.sections[:-1]
        # Rebuild with truncated sections, adding a visible warning
        warning_para = Paragraph(
            "<font color='red'><b>⚠ WARNING: This report is incomplete — a layout error prevented full rendering.</b></font>",
            styles["body"]
        )
        story.insert(0, warning_para)
        story.insert(1, Spacer(1, 0.15 * inch))
        doc2 = SimpleDocTemplate(
            str(output), pagesize=LETTER,
            rightMargin=0.62*inch, leftMargin=0.62*inch,
            topMargin=(0.58 + 0.45)*inch, bottomMargin=0.62*inch, pageCompression=0,
            title=report.title,
            author="Stock Analysis Pipeline — AI-assisted buy-side research",
            subject=f"Earnings Deep-Dive: {report.company} ({report.ticker}) — {report.quarter}",
        )
        doc2.onFirstPage = _on_first_page
        doc2.onLaterPages = _on_later_pages
        doc2.build(story)
        _stamp_page_numbers(str(output))
        print(f"[PDF RENDER] Recovered with {len(report.sections)} sections (1 dropped)", file=sys.stderr)

    # ── URL validation (BL-SA-003) — non-blocking, advisory only ──
    # Validate the final rendered PDF artifact, not only the source model. This
    # catches hallucinated/escaped/injected links that are visible or clickable
    # in the delivered file.
    try:
        from backend.url_validator import validate_pdf_urls_sync
        vr = validate_pdf_urls_sync(output, ticker=getattr(report, 'ticker', ''))
        if vr.dead > 0:
            print(f"[URL VALIDATOR] 🔴 {vr.dead}/{vr.total_urls} DEAD links in {vr.ticker}", file=__import__('sys').stderr)
            for c in vr.dead_urls:
                print(f"  DEAD: [{c.label}] {c.url} — {c.error or c.status_code}", file=__import__('sys').stderr)
        else:
            print(f"[URL VALIDATOR] ✅ {vr.total_urls}/{vr.total_urls} URLs OK in {vr.ticker}", file=__import__('sys').stderr)
    except Exception as val_err:
        print(f"[URL VALIDATOR] ⚠️ Validation skipped: {val_err}", file=__import__('sys').stderr)

    return str(output)
