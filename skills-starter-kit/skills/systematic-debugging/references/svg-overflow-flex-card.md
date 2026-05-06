# SVG Overflow in Flex Cards — Labels Overlapping Buttons

## Pattern

When an SVG chart with `overflow: 'visible'` is placed inside a flex `column` card layout, rotated text labels extend beyond the SVG viewport and visually overlap elements below (buttons, text).

## Observed

Stock Analysis Pipeline — AnalysisCard with ScoringChart SVG:
- SVG has `height={height + 65}` with `overflow: 'visible'`
- Rotated labels at `y={height + 14}`, rotated `-25°`, font-size `9px`
- Labels like "Geopolitical" (~70px wide) extend `70 * sin(25°) ≈ 30px` below their y position
- The "View full report" / "Download documents" button was partially hidden by descending labels
- Flex layout only accounts for SVG's declared height, not overflow content

## Fix (two-part)

### 1. Remove `overflow: 'visible'` from SVG
```jsx
// ❌ Before — overflow bleeds into buttons
<svg height={height + 65} style={{ overflow: 'visible' }}>

// ✅ After — contained within SVG bounds
<svg height={height + 80} style={{ display: 'block' }}>
```

### 2. Add `marginBottom` to chart container
```jsx
// ❌ Before
<div style={{ marginTop: 12, borderTop: '1px solid #30363d', paddingTop: 10 }}>
  <ScoringChart scoring={scoring} height={140} />
</div>

// ✅ After — extra bottom margin prevents overlap
<div style={{ marginTop: 12, borderTop: '1px solid #30363d', paddingTop: 10, marginBottom: 40 }}>
  <ScoringChart scoring={scoring} height={140} />
</div>
```

## Why `overflow: 'hidden'` alone isn't enough

The overflow content may be the very labels the user needs to read. Clipping them is worse than the overlap. The correct fix is:
1. Give the SVG enough height to contain rotated labels (`height + 80` instead of `height + 65`)
2. Add margin to the **container** (not the SVG) so flex layout accounts for the space
3. Remove `overflow: 'visible'` so the browser respects the declared height

## Detection

- `browser_vision`: ask "Is the button below the chart fully visible or cut off?"
- Symptom: user sends screenshot showing a button partially hidden by chart elements
- Root cause: `overflow: 'visible'` + rotated text + insufficient SVG height + no bottom margin on container
