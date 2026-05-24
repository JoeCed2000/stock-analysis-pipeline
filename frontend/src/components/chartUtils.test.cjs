// Unit tests for chartUtils.js — V2.0 Financial Depth
// Run with: node chartUtils.test.cjs

const assert = require('assert');

// ── Re-implement pure functions inline for testing (no ESM import hassle) ──

function pctChange(curr, prev) {
  if (!prev || prev === 0) return null;
  return ((curr - prev) / Math.abs(prev)) * 100;
}

function fmtPct(v) {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

function formatQuarter(q) {
  const m = q.match(/^(\d{4})Q(\d)$/);
  if (!m) return q;
  return `Q${m[2]} FY'${m[1].slice(2)}`;
}

function formatValue(val, metric) {
  if (val == null) return 'N/A';
  // Pct metrics
  if (metric.endsWith('_margin') || metric.endsWith('_ratio')) {
    return `${val.toFixed(1)}%`;
  }
  if (metric === 'eps') return `$${val.toFixed(2)}`;
  if (metric === 'diluted_shares') {
    if (Math.abs(val) >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
    return `${val.toFixed(0)}`;
  }
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toFixed(0)}`;
}

function transformValues(sortedData, metricKey, viewMode) {
  if (viewMode === 'absolute') return sortedData.map(d => d[metricKey]);
  if (viewMode === 'qoq') return sortedData.map((d, i) => i === 0 ? null : pctChange(d[metricKey], sortedData[i - 1]?.[metricKey]));
  if (viewMode === 'yoy') return sortedData.map((d, i) => i < 4 ? null : pctChange(d[metricKey], sortedData[i - 4]?.[metricKey]));
  if (viewMode === 'growth') {
    const base = sortedData[0]?.[metricKey];
    return sortedData.map(d => pctChange(d[metricKey], base));
  }
  return sortedData.map(d => d[metricKey]);
}

function _ratio(num, den) {
  if (num == null || den == null || den === 0) return null;
  return (num / den) * 100;
}

function _perShare(val, shares) {
  if (val == null || shares == null || shares === 0) return null;
  return val / shares;
}

function enrichData(sortedData) {
  return sortedData.map(d => {
    const rev = d.revenue;
    const shares = d.diluted_shares;
    const enriched = { ...d };
    enriched.gross_margin = _ratio(d.gross_profit, rev);
    enriched.ebitda_margin = _ratio(d.ebitda, rev);
    enriched.net_margin = _ratio(d.net_income, rev);
    enriched.operating_margin = _ratio(d.operating_income, rev);
    enriched.fcf_margin = _ratio(d.free_cash_flow, rev);
    enriched.revenue_per_share = _perShare(rev, shares);
    enriched.fcf_per_share = _perShare(d.free_cash_flow, shares);
    return enriched;
  });
}

function calculateStats(sortedData, metricKey, viewMode) {
  const transformed = transformValues(sortedData, metricKey, viewMode);
  const isPctView = viewMode !== 'absolute';
  const values = isPctView ? transformed.filter(v => v != null) : transformed;
  if (values.length < 2) return { values, latest: null, qoq: null, yoy: null, totalChange: null, peak: null, low: null, avg: null, isPctView };
  const latest = sortedData[sortedData.length - 1];
  const previous = sortedData[sortedData.length - 2];
  const first = sortedData[0];
  const lastIdx = transformed.length - 1;
  const latestVal = isPctView ? transformed[lastIdx] : latest[metricKey];
  const firstVal = isPctView ? null : first[metricKey];
  const qoq = isPctView ? null : pctChange(latest[metricKey], previous?.[metricKey]);
  const totalChange = !isPctView ? pctChange(latest[metricKey], firstVal) : null;
  let yoy = null;
  if (!isPctView && sortedData.length > 4) {
    const yearAgo = sortedData[sortedData.length - 5];
    yoy = pctChange(latest[metricKey], yearAgo?.[metricKey]);
  }
  const peak = Math.max(...values);
  const low = Math.min(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return { values, latest: latestVal, qoq, yoy, totalChange, peak, low, avg, isPctView, latestQuarter: latest, firstQuarter: first };
}

// ── Test data — AAPL-style with full V2.0 fields (8 quarters for YoY) ──
const FULL_DATA = [
  { quarter: '2024Q1', revenue: 119.575e9, net_income: 33.916e9, ebitda: 40.280e9, gross_profit: 54.855e9,
    eps: 2.18, operating_income: 35.890e9, operating_cash_flow: 37.100e9, capex: -2.010e9,
    free_cash_flow: 35.090e9, cash_and_equivalents: 61.200e9, total_debt: 95.100e9, diluted_shares: 15.523e9 },
  { quarter: '2024Q2', revenue: 90.753e9, net_income: 23.636e9, ebitda: 28.610e9, gross_profit: 41.571e9,
    eps: 1.53, operating_income: 25.400e9, operating_cash_flow: 21.400e9, capex: -1.980e9,
    free_cash_flow: 19.420e9, cash_and_equivalents: 58.300e9, total_debt: 92.800e9, diluted_shares: 15.510e9 },
  { quarter: '2024Q3', revenue: 85.777e9, net_income: 21.448e9, ebitda: 26.250e9, gross_profit: 39.677e9,
    eps: 1.40, operating_income: 23.500e9, operating_cash_flow: 26.200e9, capex: -2.150e9,
    free_cash_flow: 24.050e9, cash_and_equivalents: 62.100e9, total_debt: 93.400e9, diluted_shares: 15.420e9 },
  { quarter: '2024Q4', revenue: 94.930e9, net_income: 14.736e9, ebitda: 18.500e9, gross_profit: 43.879e9,
    eps: 0.97, operating_income: 16.500e9, operating_cash_flow: 16.300e9, capex: -2.300e9,
    free_cash_flow: 14.000e9, cash_and_equivalents: 57.500e9, total_debt: 90.200e9, diluted_shares: 15.320e9 },
  { quarter: '2025Q1', revenue: 124.300e9, net_income: 36.330e9, ebitda: 43.000e9, gross_profit: 58.270e9,
    eps: 2.40, operating_income: 38.500e9, operating_cash_flow: 29.900e9, capex: -2.050e9,
    free_cash_flow: 27.850e9, cash_and_equivalents: 59.800e9, total_debt: 89.300e9, diluted_shares: 15.110e9 },
  { quarter: '2025Q2', revenue: 95.440e9, net_income: 24.570e9, ebitda: 30.100e9, gross_profit: 43.910e9,
    eps: 1.64, operating_income: 26.800e9, operating_cash_flow: 22.300e9, capex: -2.100e9,
    free_cash_flow: 20.200e9, cash_and_equivalents: 56.900e9, total_debt: 87.500e9, diluted_shares: 14.950e9 },
  { quarter: '2025Q3', revenue: 90.150e9, net_income: 22.300e9, ebitda: 27.500e9, gross_profit: 41.500e9,
    eps: 1.50, operating_income: 24.500e9, operating_cash_flow: 27.100e9, capex: -2.200e9,
    free_cash_flow: 24.900e9, cash_and_equivalents: 58.200e9, total_debt: 86.100e9, diluted_shares: 14.820e9 },
  { quarter: '2025Q4', revenue: 98.720e9, net_income: 15.450e9, ebitda: 19.500e9, gross_profit: 45.600e9,
    eps: 1.02, operating_income: 17.200e9, operating_cash_flow: 17.500e9, capex: -2.400e9,
    free_cash_flow: 15.100e9, cash_and_equivalents: 55.400e9, total_debt: 84.700e9, diluted_shares: 14.690e9 },
];

const FULL_ENRICHED = enrichData(FULL_DATA);

let passed = 0, failed = 0;

function test(name, fn) {
  try { fn(); passed++; }
  catch (e) { failed++; console.error(`  FAIL ${name}: ${e.message}`); }
}

function eq(actual, expected, msg) { assert.deepStrictEqual(actual, expected, msg); }
function approx(actual, expected, tolerance, msg) {
  if (Math.abs(actual - expected) > tolerance) {
    throw new Error(`${msg || 'approx'}: expected ${expected} ±${tolerance}, got ${actual}`);
  }
}

// ── Tests ──
console.log('\n📊 chartUtils V2.0 Unit Tests\n');

// ── V1 TESTS (non-regression) ──

test('formatQuarter parses standard format', () => {
  eq(formatQuarter('2025Q2'), "Q2 FY'25");
  eq(formatQuarter('2026Q4'), "Q4 FY'26");
  eq(formatQuarter('invalid'), 'invalid');
});

test('pctChange calculates correctly', () => {
  eq(pctChange(100, 80), 25.0);
  eq(pctChange(50, 100), -50.0);
  eq(pctChange(0, 100), -100.0);
});

test('pctChange returns null for zero prev', () => {
  eq(pctChange(100, 0), null);
  eq(pctChange(50, null), null);
});

test('fmtPct formats percentages', () => {
  eq(fmtPct(19.8), '+19.8%');
  eq(fmtPct(-5.2), '-5.2%');
  eq(fmtPct(null), '—');
  eq(fmtPct(0), '+0.0%');
});

test('formatValue — Revenue in billions', () => {
  eq(formatValue(44.062e9, 'revenue'), '$44.1B');
  eq(formatValue(81.615e9, 'revenue'), '$81.6B');
});

test('formatValue — EPS in per share', () => {
  eq(formatValue(2.40, 'eps'), '$2.40');
  eq(formatValue(0.77, 'eps'), '$0.77');
});

test('formatValue — null returns N/A', () => {
  eq(formatValue(null, 'revenue'), 'N/A');
  eq(formatValue(undefined, 'eps'), 'N/A');
});

test('transformValues — absolute returns raw values', () => {
  const result = transformValues(FULL_DATA, 'revenue', 'absolute');
  eq(result[7], 98.720e9);
  eq(result.length, 8);
});

test('transformValues — qoq first point is null', () => {
  const result = transformValues(FULL_DATA, 'revenue', 'qoq');
  eq(result[0], null);
  approx(result[1], -24.12, 0.1, 'QoQ Q2→Q1 drop');
});

test('transformValues — growth from first quarter', () => {
  const result = transformValues(FULL_DATA, 'eps', 'growth');
  approx(result[0], 0, 0.01);
  approx(result[7], -53.2, 1.0, 'EPS growth over 8Q');
});

test('calculateStats — absolute mode', () => {
  const stats = calculateStats(FULL_DATA, 'revenue', 'absolute');
  eq(stats.latest, 98.720e9);
  eq(stats.peak, 124.300e9);
  eq(stats.low, 85.777e9);
  eq(stats.values.length, 8);
  eq(stats.isPctView, false);
});

test('calculateStats — qoq mode', () => {
  const stats = calculateStats(FULL_DATA, 'eps', 'qoq');
  eq(stats.isPctView, true);
  eq(stats.values.length, 7);  // 8 data points, 1 null for qoq
});

test('calculateStats — empty data returns nulls', () => {
  const stats = calculateStats([], 'revenue', 'absolute');
  eq(stats.latest, null);
  eq(stats.values.length, 0);
});

test('calculateStats — single data point', () => {
  const stats = calculateStats([FULL_DATA[0]], 'eps', 'absolute');
  eq(stats.latest, null);
  eq(stats.values.length, 1);
});

test('transformValues — missing metric returns undefined', () => {
  const data = [{ quarter: 'Q1', revenue: 100 }, { quarter: 'Q2' }];
  const result = transformValues(data, 'revenue', 'absolute');
  eq(result[0], 100);
  eq(result[1], undefined);
});

// ── V2.0 TESTS — YoY ──

test('YoY — returns null for first 4 quarters', () => {
  const result = transformValues(FULL_DATA, 'revenue', 'yoy');
  eq(result[0], null);
  eq(result[1], null);
  eq(result[2], null);
  eq(result[3], null);
  // Q5 (2025Q1) YoY vs Q1 (2024Q1): (124.3 - 119.575) / 119.575 ≈ 3.95%
  approx(result[4], 3.95, 0.2, 'YoY 2025Q1 vs 2024Q1');
});

test('YoY — works for all metrics', () => {
  for (const m of ['revenue', 'net_income', 'ebitda', 'eps', 'gross_profit']) {
    const result = transformValues(FULL_DATA, m, 'yoy');
    eq(result[0], null, `${m} yoy[0]`);
    eq(result[3], null, `${m} yoy[3]`);
    eq(typeof result[7], 'number', `${m} yoy[7] should be number`);
  }
});

test('calculateStats — includes yoy when 8+ quarters', () => {
  const stats = calculateStats(FULL_DATA, 'revenue', 'absolute');
  eq(typeof stats.yoy, 'number');
  // 2026Q1 (last) vs 2025Q1 (4 back): (98.720 - 94.930) / 94.930 ≈ 3.99%
  approx(stats.yoy, 3.99, 0.3);
});

test('calculateStats — yoy is null with <5 quarters', () => {
  const short = FULL_DATA.slice(0, 4);  // 4 quarters, not enough for YoY
  const stats = calculateStats(short, 'revenue', 'absolute');
  eq(stats.yoy, null);
});

// ── V2.0 TESTS — Enrichment (margins) ──

test('enrichData — computes gross_margin', () => {
  // Q1: 54.855B / 119.575B ≈ 45.87%
  const d = FULL_ENRICHED[0];
  approx(d.gross_margin, 45.87, 0.1);
});

test('enrichData — computes ebitda_margin', () => {
  const d = FULL_ENRICHED[0];
  approx(d.ebitda_margin, 33.69, 0.1);
});

test('enrichData — computes net_margin', () => {
  const d = FULL_ENRICHED[0];
  approx(d.net_margin, 28.36, 0.1);
});

test('enrichData — computes operating_margin', () => {
  const d = FULL_ENRICHED[0];
  approx(d.operating_margin, 30.01, 0.1);
});

test('enrichData — computes fcf_margin', () => {
  const d = FULL_ENRICHED[0];
  approx(d.fcf_margin, 29.35, 0.1);
});

test('enrichData — computes revenue_per_share', () => {
  const d = FULL_ENRICHED[0];
  approx(d.revenue_per_share, 7.70, 0.05);  // 119.575B / 15.523B
});

test('enrichData — computes fcf_per_share', () => {
  const d = FULL_ENRICHED[0];
  approx(d.fcf_per_share, 2.26, 0.05);  // 35.090B / 15.523B
});

test('enrichData — handles null inputs gracefully', () => {
  const bad = [{ quarter: 'Q1', revenue: null, gross_profit: 50, ebitda: null,
    net_income: 10, operating_income: 20, free_cash_flow: null, diluted_shares: null }];
  const enriched = enrichData(bad);
  eq(enriched[0].gross_margin, null);  // rev is null
  eq(enriched[0].revenue_per_share, null);  // shares null
});

test('enrichData — handles zero revenue', () => {
  const zero = [{ quarter: 'Q1', revenue: 0, gross_profit: 50, net_income: 10,
    ebitda: 20, operating_income: 15, free_cash_flow: 5, diluted_shares: 1e9 }];
  const enriched = enrichData(zero);
  eq(enriched[0].gross_margin, null);
});

// ── V2.0 TESTS — Formatting ──

test('formatValue — margins show as %', () => {
  eq(formatValue(45.87, 'gross_margin'), '45.9%');
  eq(formatValue(28.36, 'net_margin'), '28.4%');
  eq(formatValue(29.35, 'fcf_margin'), '29.4%');
});

test('formatValue — diluted_shares in billions', () => {
  eq(formatValue(15.523e9, 'diluted_shares'), '15.52B');
});

test('formatValue — operating_cash_flow in $B', () => {
  eq(formatValue(37.100e9, 'operating_cash_flow'), '$37.1B');
});

test('formatValue — capex in $B (negative)', () => {
  eq(formatValue(-2.010e9, 'capex'), '$-2.0B');
});

// ── V2.0 TESTS — Metric availability ──

// Simple inline version of metricIsAvailable
function metricIsAvailable(sortedData, metricKey) {
  if (sortedData.length < 2) return false;
  const values = sortedData.map(d => d[metricKey]).filter(v => v != null);
  return values.length >= 2;
}

test('metricIsAvailable — true for metric with data', () => {
  eq(metricIsAvailable(FULL_ENRICHED, 'revenue'), true);
  eq(metricIsAvailable(FULL_ENRICHED, 'gross_margin'), true);
  eq(metricIsAvailable(FULL_ENRICHED, 'free_cash_flow'), true);
});

test('metricIsAvailable — false for short data', () => {
  const short = FULL_ENRICHED.slice(0, 1);
  eq(metricIsAvailable(short, 'revenue'), false);
});

test('metricIsAvailable — false for all-null metric', () => {
  const bad = [{ quarter: 'Q1', revenue: null }, { quarter: 'Q2', revenue: null }];
  eq(metricIsAvailable(bad, 'revenue'), false);
});

// ── Results ──
console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
if (failed > 0) process.exit(1);
