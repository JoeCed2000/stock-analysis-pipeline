# PDF Dark-Mode Colors on White Paper

## Symptom
PDF text appears light gray, washed out, or barely readable. User says "le texte est en gris et c'est pas très lisible."

## Root Cause
Color palette was designed for **dark backgrounds** (GitHub dark mode, terminal themes) but the PDF renders on **white paper**. Light gray text (#8b949e, #c9d1d9) that's readable on `#0d1117` background becomes nearly invisible on white.

## Common Offenders (ReportLab / WeasyPrint)

| Usage | Dark-mode color | Print replacement |
|-------|----------------|-------------------|
| Body text | `#c9d1d9` (light gray) | `#1f2328` (dark gray, near black) |
| Secondary/muted text | `#8b949e` (very light gray) | `#57606a` (medium gray) |
| Titles | `#e1e4e8` (white-gray) | `#0d1117` (black) |
| Accent/links | `#58a6ff` (light blue) | `#0969da` (darker blue) |
| Green (BUY) | `#238636` | `#1a7f37` |
| Yellow (HOLD) | `#d29922` | `#9a6700` |
| Red (SELL) | `#da3633` | `#cf222e` |

## Fix Pattern

In `pdf_generator.py` or equivalent:
1. Replace all color constants at the top of the file
2. Check ParagraphStyle `textColor` parameters
3. Check TableStyle `TEXTCOLOR` directives
4. Check footer/canvas `setFillColor()` calls
5. Verify no remaining dark-mode hex codes with `grep`

```python
# Before — dark-mode palette (GitHub)
BODY_COLOR = '#c9d1d9'    # invisible on white
MUTED_COLOR = '#8b949e'   # invisible on white

# After — print palette
BODY_COLOR = '#1f2328'    # dark gray, readable
MUTED_COLOR = '#57606a'   # medium gray, readable
```

## Verification

After fixing, grep for remaining dark-mode colors:
```bash
grep -n '#e1e4e8\|#c9d1d9\|#8b949e\|#f0f6fc' pdf_generator.py
# Should return nothing
```

## Prevention

- When designing PDF templates, start with a print palette (dark-on-white), not a screen palette
- Test PDF output with a real ticker before declaring done
- Dark-mode web colors and print colors are NOT interchangeable