# PDF Print Color Verification

## The Pitfall

Dark-mode UI color palettes (GitHub dark, Dracula, Nord, etc.) use light text on dark backgrounds. When these colors are carried directly into PDF generation (ReportLab, WeasyPrint, wkhtmltopdf), the text becomes **unreadable on white paper**.

## Example (stock-analysis-pipeline, 2026-05-04)

### Before (dark-mode, illegible on white)
```python
# Colors
GREEN = HexColor('#238636')
MUTED = HexColor('#8b949e')    # Light gray — barely visible
LIGHT = HexColor('#e1e4e8')    # Almost white — invisible

body_style = ParagraphStyle('Body', textColor='#c9d1d9')  # Light gray
small_style = ParagraphStyle('Small', textColor='#8b949e')  # Very light gray
title_style = ParagraphStyle('Title', textColor='#e1e4e8')  # White
```

### After (dark-on-white, readable)
```python
# Colors — dark-on-white palette for print
DARK = HexColor('#0d1117')      # Near black → titles
LIGHT = HexColor('#1f2328')      # Dark gray → body text
MUTED = HexColor('#57606a')      # Medium gray → secondary text

body_style = ParagraphStyle('Body', textColor='#1f2328')
small_style = ParagraphStyle('Small', textColor='#57606a')
title_style = ParagraphStyle('Title', textColor='#0d1117')
```

## Conversion Rules of Thumb

| Dark-mode color | Print equivalent | Contrast on white |
|-----------------|------------------|-------------------|
| `#e1e4e8` (almost white) | `#0d1117` (near black) | 18:1 |
| `#c9d1d9` (light gray) | `#1f2328` (dark gray) | 12:1 |
| `#8b949e` (medium-light gray) | `#57606a` (medium-dark gray) | 6:1 |
| `#58a6ff` (light blue) | `#0969da` (dark blue) | 7:1 |
| `#238636` (light green) | `#1a7f37` (dark green) | 5:1 |

## Verification Checklist

When generating PDFs from a codebase with dark-mode colors:

- [ ] Grep for `#e1e4e8`, `#c9d1d9`, `#8b949e`, `#f0f6fc` — any light color on white paper = illegible
- [ ] Check ALL `ParagraphStyle` definitions for `textColor` values
- [ ] Check ALL `setFillColor()` calls
- [ ] Check ALL inline `<font color="...">` HTML in Paragraph content
- [ ] Generate a test PDF and visually inspect in a PDF viewer (not just grep)
- [ ] Minimum contrast ratio 4.5:1 for body text, 3:1 for large text (WCAG AA)

## Related Anti-Patterns

- **Inheriting web CSS directly**: `getSampleStyleSheet()` from ReportLab already provides print-safe defaults — don't override with web colors
- **Table style leakage**: `TableStyle([('TEXTCOLOR', ...)])` often mirrors the UI palette
- **Footer/page number colors**: often overlooked, same dark-mode values
