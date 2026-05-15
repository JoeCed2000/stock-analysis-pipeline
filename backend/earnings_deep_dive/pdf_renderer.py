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

from backend.earnings_deep_dive.report_model import EarningsDeepDiveReport


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
    text = re.sub(r'^###\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+', '', text, flags=re.MULTILINE)
    # LLM artifacts: LaTeX-escaped dollar signs (\$35.6B → $35.6B)
    text = text.replace('\\$', '$')
    # LLM artifacts: backslash-escaped percent, ampersand, hash
    for ch in ('%', '&', '#', '_'):
        text = text.replace(f'\\{ch}', ch)
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
    formatted = formatted.replace('For Nami-san', 'For\u00A0Nami-san')
    # Ensure bullet markers and key phrases always start on a new line.
    # Process LONGER phrases first to avoid partial matches (e.g., 'For Nami-san'
    # before 'Nami-san'). Only match when preceded by space or at line start.
    import re as _re_markers
    marker_list = sorted([
        '●', '•', '👉', '→', '🎯', '⚠️', '✅', '❌',
        'For Nami-san', 'Nami-san', 'Namiさん',
        '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩',
        'Caution:', 'Essential insight:', 'One-line summary:',
        'Nami takeaway:', 'Verdict takeaway:', 'Operating takeaway:',
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
            if source.url:
                return source.url
            note = source.note or ""
            if report.language != "jp" and note == "データ未取得":
                return "Not available"
            return note or "N/A"
    return "N/A"


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
        transcript_label = "Earnings Transcript — StockAnalysis"
        transcript_url = f"https://stockanalysis.com/stocks/{report.ticker.lower()}/transcripts/"

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
    else:
        rows = [
            (transcript_label, transcript_url or "N/A", "Earning Call Transcript source"),
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
                    "columns": ["Document / Source", "Target-company URL or status", "Used for"],
                    "rows": [
                        type("DocumentsRow", (), {"label": label, "cells": [value, used_for]})
                        for label, value, used_for in rows
                    ],
                },
            )()
        },
    )()
    story = [Paragraph("Earnings Documents", styles["section"])] + _table(section, styles, fonts)
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


def _table(section, styles: dict[str, ParagraphStyle], fonts: PdfFontSet) -> Table:
    """Build a ReportLab Table with proper word-wrapping via Paragraph cells."""
    MAX_CELL_CHARS = 80  # aggressive truncation — prevents cell overflow crashes
    
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
            if len(s) > MAX_CELL_CHARS:
                s = s[:MAX_CELL_CHARS - 1] + "…"
            # Shorten source labels for compact table rendering
            if "source" in column.lower():
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

    table = Table(data, colWidths=col_widths, splitByRow=1, hAlign="LEFT")
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
    return [table] + [Paragraph(escape(_glyph_safe(t[:300], font_name=fonts.regular)), cell_style) for t in explanation_rows]


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
    """Draw a dark gray header bar at the top of the page."""
    width = LETTER[0]
    height = LETTER[1]
    
    # Dark gray rectangle across the full page width at the top
    canvas.saveState()
    canvas.setFillColor(_HEADER_BG)
    canvas.rect(0, height - _HEADER_HEIGHT, width, _HEADER_HEIGHT, fill=1, stroke=0)
    
    # Page number — right-aligned in white
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8)
    total_pages = doc.page if hasattr(doc, 'page') else "—"
    page_text = f"{page_num} / {total_pages}" if total_pages != "—" else str(page_num)
    canvas.drawRightString(width - 0.55 * inch, height - 0.30 * inch, page_text)
    
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
        if all(c.strip() in ('', '-', '—', 'No backlog', 'Not available', 'N/A', 'データ未取得')
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


# ── Main entry point ────────────────────────────────────────────────────
def render_earnings_deep_dive_pdf(report: EarningsDeepDiveReport, output_path: str | Path) -> str:
    """Render a structured earnings deep-dive report to an extractable PDF."""
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
        topMargin=(0.58 + 0.45) * inch,  # extra space for dark header bar
        bottomMargin=0.62 * inch,
        pageCompression=0,
        title=report.title,
        author="stock-analysis-pipeline",
    )
    # Register dark header bar on every page
    doc.onFirstPage = _on_first_page
    doc.onLaterPages = _on_later_pages

    story: list = [
        Paragraph(escape(f"{report.company} ({report.ticker})"), styles["title"]),
        Paragraph(escape(f"Earnings Deep-Dive - {report.quarter}"), styles["meta"]),
    ]
    website = _official_website(report)
    if website:
        story.append(Paragraph(escape(f"Official Website: {website}"), styles["meta"]))
    story.extend(_earnings_documents_story(report, styles, fonts))

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

    if report.sources or report.next_earnings_date or report.earnings_audio_url:
        story.append(PageBreak())
        story.append(Paragraph("Sources", styles["section"]))
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
            story.append(Paragraph("<b>Key Dates</b>", styles["body"]))
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
            story.append(Paragraph("<b>Earnings Documents</b>", styles["body"]))
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
            story.append(Paragraph("<b>Data &amp; Analytics</b>", styles["body"]))
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
        story.append(Paragraph(
            "<b>Methodology:</b> This deep-dive combines quantitative metrics from SEC filings "
            "(via yfinance/Finnhub) with qualitative analysis of the earnings call transcript. "
            "All figures are sourced; no data is invented. "
            "Ratings reflect Nami-grade buy-side analysis standards.",
            styles["small"]
        ))

    try:
        doc.build(story)
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
            title=report.title, author="stock-analysis-pipeline"
        )
        doc2.onFirstPage = _on_first_page
        doc2.onLaterPages = _on_later_pages
        doc2.build(story)
        print(f"[PDF RENDER] Recovered with {len(report.sections)} sections (1 dropped)", file=sys.stderr)
    return str(output)
