# CSS Grid + Card Shrink-to-Fit + SVG Fixed Dimensions

## Pattern (two bugs, one symptom)

When result cards are rendered in a CSS Grid with `minmax(Npx, 1fr)` but the cards lack `width: 100%`, they shrink to content width instead of filling their column. If the card also contains an SVG chart with fixed pixel dimensions (no `viewBox`), the chart doesn't adapt to the available space — bars appear cramped while empty space fills the rest of the column.

## Observed

Stock Analysis Pipeline V3 — 4 result cards in grid, user reports "les cartes ne rentrent pas, les barres sont coupées":

### Bug 1: Card shrink-to-fit
```jsx
// ❌ Shrink-to-fit — card matches content width, not column width
<div style={{ minWidth: 320, maxWidth: '100%', ... }}>

// ✅ Fill the column
<div style={{ width: '100%', ... }}>
```

Without `width: 100%`, a block-level element in a CSS Grid column doesn't automatically expand — it sizes to its content (`shrink-to-fit`). `maxWidth: 100%` only caps the maximum, it doesn't stretch.

### Bug 2: SVG without viewBox is fixed-size
```jsx
// ❌ Fixed 224×138 — never adapts to container width
<svg width={224} height={138} style={{ display: 'block' }}>

// ✅ Responsive — scales to fill available width while preserving aspect ratio
<svg
  viewBox={`0 0 ${chartW} ${chartH + labelH}`}
  preserveAspectRatio="xMidYMid meet"
  width="100%"
  style={{ display: 'block' }}
>
```

## Diagnostic flow

1. **Check card width** — `browser_console`: `[...document.querySelectorAll('[style*="0d1117"]')].map(el => el.getBoundingClientRect().width)` — if cards are narrower than the grid column, it's Bug 1
2. **Check SVG dimensions** — `[...document.querySelectorAll('svg')].map(el => ({w: el.width.baseVal.value, viewBox: el.getAttribute('viewBox')}))` — if `viewBox` is `null` and `w` is a fixed pixel value, it's Bug 2
3. **Check CSS chain** — `getComputedStyle(el).width` walking up from SVG to card to grid container — look for `width: auto` where `width: 100%` expected

## Why both bugs must be fixed together

Fixing only Bug 1 gives a wider card but the SVG chart stays at 224px — it looks lost in the middle of a big card. Fixing only Bug 2 makes the SVG scale up inside a narrow card — bars get taller but not wider, aspect ratio distorts. Both must be fixed for the chart to fill the card correctly.

## Detection

- User: "les barres sont coupées", "tout ne rentre pas", "largeur des cards"
- `browser_vision`: ask "Are chart bars fully visible? Do cards fill their column?"
- Cards have visible empty space on their right side, chart bars cramped on the left
