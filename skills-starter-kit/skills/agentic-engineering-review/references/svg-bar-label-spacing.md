# SVG Bar Chart Label Spacing Formula

## Problem
Non-rotated labels under bars in an SVG bar chart overlap when the `viewBox` is too narrow.
The rendered font size = `fontSize * containerWidth / viewBoxWidth` — MUCH larger than the viewBox value.
Labels appear concatenated ("GrowthProfitFinanceMoat"). Descenders (g, p, y) are clipped if `labelH`
doesn't account for text height below the baseline.

## Root cause chain
1. `viewBox="0 0 160 138"` with 8 bars at 20px spacing (barW=16, gap=4)
2. Container is 300-400px wide → SVG scales up by 1.8-2.5x
3. `fontSize=7` in viewBox → renders at 13-17px actual
4. "Growth" at 13px ≈ 45px wide, but label centers are only 38px apart → overlap
5. Descenders at `y = chartH + 12` with `labelH = 18` → text extends to `chartH + 21` → clipped at `chartH + 18`

## Solution

### Step 1: Calculate minimum spacing
```
For each label, estimate width: labelWidth ≈ labelChars * fontSize * 0.55
Required spacing per bar: spacing > max(labelWidth)
viewBox total width: N * spacing
```

### Step 2: Adjust dimensions
Increase `barW`, `gap`, `labelH`; decrease `fontSize`:
```
barW:  16 → 18  (wider bars = more spacing between centers)
gap:   4  → 8   (more gap = less label overlap)
labelH: 18 → 26 (enough height for descenders below baseline)
fontSize: 7 → 6 (smaller text = less overlap, fits in viewBox)
```

### Step 3: Verify at all container widths
Check the tightest container (narrowest card in grid) and the widest (modal on desktop).
At 300px container with 8 bars:
- viewBox = 208, scale = 300/208 = 1.44x
- fontSize 6 → renders at 8.6px
- "Growth" = 6 * 0.55 * 8.6 = 28px
- Spacing = 26 * 1.44 = 37px
- 28 < 37 → OK

### Concrete fix (stock-analysis-pipeline, 2026-05-04)
```jsx
// Before (broken)
const barW = 16, gap = 4, labelH = 18;
// labels fontSize={7}, y={chartH + 12}

// After (fixed)
const barW = 18, gap = 8, labelH = 26;
// labels fontSize={6}, y={chartH + 14}
```

## Anti-patterns
- **`overflow: 'visible'` on SVG** — prevents clipping but lets SVG content overflow
  onto HTML elements below. Never use as a label overflow fix.
- **Reducing font too much** — below 5px in viewBox becomes illegible at small containers.
- **Abbreviating labels excessively** — "Mgmt" is fine, "Grw" is not.

## Related
- `systematic-debugging` §1j — CSS Grid card shrink + SVG viewBox
- `agentic-engineering-review` §14b — SVG rotated labels
