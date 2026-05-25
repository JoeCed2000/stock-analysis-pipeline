---
version: alpha
name: SA Pipeline Dark
description: Dark financial dashboard with GitHub-inspired palette. Valuation Group extends the metric card pattern.
colors:
  primary: "#e1e4e8"
  secondary: "#c9d1d9"
  tertiary: "#8b949e"
  neutral: "#0d1117"
  bgCard: "#161b22"
  bgBorder: "#21262d"
  accentPositive: "#238636"
  accentNeutral: "#d29922"
  accentNegative: "#da3633"
  accentLink: "#58a6ff"
  fresh: "#3fb950"
  cached: "#d29922"
  stale: "#f85149"
typography:
  body-md:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: 13px
    fontWeight: 400
  label-sm:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: 9px
    fontWeight: 500
    letterSpacing: "0.05em"
  metric-value:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: 11px
    fontWeight: 600
  metric-label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: 8px
    fontWeight: 500
    letterSpacing: "0.05em"
  footer-sm:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: 8px
    fontWeight: 400
rounded:
  sm: 4px
  md: 8px
  lg: 10px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 14px
components:
  valuation-group:
    backgroundColor: "#161b22"
    borderColor: "#21262d"
    rounded: 10px
    padding: "12px 14px"
  valuation-row:
    display: grid
    gridTemplateColumns: "1fr 1fr 1fr 1fr"
    gap: 0
  valuation-cell:
    textAlign: center
    padding: "6px 4px"
    borderLeft: "1px solid #21262d"
  valuation-footer:
    fontSize: 8px
    color: "#484f58"
    textAlign: center
    padding: "4px 0 0"
    borderTop: "1px solid #21262d"
  status-fresh:
    backgroundColor: "#3fb950"
  status-cached:
    backgroundColor: "#d29922"
  status-stale:
    backgroundColor: "#f85149"
---

## Overview

Valuation Group extends the SA Pipeline dark dashboard pattern. It presents 8 valuation metrics in a compact 4×2 grid with status indicators, consistent with the existing MetricBox pattern in AnalysisCard. All values use the same GitHub-inspired dark palette (#0d1117 surface, #e1e4e8 text, #8b949e secondary).

## Colors

- **Primary (#e1e4e8):** Main text for metric values and headers
- **Secondary (#c9d1d9):** Section headers, emphasis
- **Tertiary (#8b949e):** Labels, muted text, footers
- **Neutral (#0d1117):** Page background
- **bgCard (#161b22):** Card/section surface
- **bgBorder (#21262d):** Borders, dividers
- **accentPositive (#238636):** BUY, positive values, download buttons
- **accentLink (#58a6ff):** Interactive links, view buttons, select dropdowns
- **Status colors:** fresh=#3fb950, cached=#d29922, stale=#f85149

## Typography

Metric values at 11px/600, labels at 8px/500 uppercase, values at 13px/600 for large numbers. All Segoe UI stack (system fonts, no external dependencies).

## Components

- **valuation-group:** Card container with bg #161b22, border #21262d, 10px radius
- **valuation-row:** 4-column grid (expanded from existing 3-col MetricBox)
- **valuation-cell:** Centered metric with label/value/status bar
- **valuation-footer:** 8px muted footer with data freshness status

## Do's and Don'ts

- ✅ Use "N/A" for unavailable metrics (null/undefined values)
- ✅ Show status dot (green/yellow/red) for data freshness
- ✅ Format multiples as "35.2x", yields as "2.8%", large caps as "$3.2T"
- ✅ Show currency symbol where applicable
- ❌ Don't show "0.0x" for zero values — use "N/A"
- ❌ Don't use emoji for status — use colored dots/squares
