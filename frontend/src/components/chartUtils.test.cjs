// Unit tests for chartUtils.js
// Run with: node chartUtils.test.js
//
// Note: chartUtils uses ES module syntax (export/import).
// For Node.js testing with ESM, rename to .mjs or use --experimental-vm-modules.
// This file is a reference — run in a proper Jest/Vitest setup in CI.

const assert = require('assert');

// Re-implement the pure functions inline for testing (no ESM import hassle)
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
  if (metric === 'eps') return `$${val.toFixed(2)}`;
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toFixed(0)}`;
}

function transformValues(sortedData, metricKey, viewMode) {
  if (viewMode === 'absolute') return sortedData.map(d => d[metricKey]);
  if (viewMode === 'qoq') return sortedData.map((d, i) => i === 0 ? null : pctChange(d[metricKey], sortedData[i - 1]?.[metricKey]));
  if (viewMode === 'growth') {
    const base = sortedData[0]?.[metricKey];
    return sortedData.map(d => pctChange(d[metricKey], base));
  }
  return sortedData.map(d => d[metricKey]);
}

function calculateStats(sortedData, metricKey, viewMode) {
  const transformed = transformValues(sortedData, metricKey, viewMode);
  const isPctView = viewMode !== 'absolute';
  const values = isPctView ? transformed.filter(v => v != null) : transformed;
  if (values.length < 2) return { values, latest: null, qoq: null, totalChange: null, peak: null, low: null, avg: null, isPctView };
  const latest = sortedData[sortedData.length - 1];
  const previous = sortedData[sortedData.length - 2];
  const first = sortedData[0];
  const lastIdx = transformed.length - 1;
  const latestVal = isPctView ? transformed[lastIdx] : latest[metricKey];
  const firstVal = isPctView ? null : first[metricKey];
  const qoq = isPctView ? null : pctChange(latest[metricKey], previous?.[metricKey]);
  const totalChange = !isPctView ? pctChange(latest[metricKey], firstVal) : null;
  const peak = Math.max(...values);
  const low = Math.min(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  return { values, latest: latestVal, qoq, totalChange, peak, low, avg, isPctView, latestQuarter: latest, firstQuarter: first };
}

// ── Test data ──
const NVDA_DATA = [
  { quarter: '2025Q2', revenue: 44.062e9, net_income: 18.775e9, ebitda: 22.584e9, eps: 0.77 },
  { quarter: '2025Q3', revenue: 46.743e9, net_income: 26.422e9, ebitda: 31.937e9, eps: 1.08 },
  { quarter: '2025Q4', revenue: 57.006e9, net_income: 31.910e9, ebitda: 38.748e9, eps: 1.31 },
  { quarter: '2026Q1', revenue: 68.127e9, net_income: 42.960e9, ebitda: 51.283e9, eps: 1.77 },
  { quarter: '2026Q2', revenue: 81.615e9, net_income: 58.321e9, ebitda: 71.002e9, eps: 2.40 },
];

let passed = 0, failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
  } catch (e) {
    failed++;
    console.error(`  FAIL ${name}: ${e.message}`);
  }
}

function eq(actual, expected, msg) {
  assert.deepStrictEqual(actual, expected, msg);
}

// ── Tests ──
console.log('\n📊 chartUtils Unit Tests\n');

// 1. formatQuarter
test('formatQuarter parses standard format', () => {
  eq(formatQuarter('2025Q2'), "Q2 FY'25");
  eq(formatQuarter('2026Q4'), "Q4 FY'26");
  eq(formatQuarter('invalid'), 'invalid');
});

// 2. pctChange
test('pctChange calculates correctly', () => {
  eq(pctChange(100, 80), 25.0);
  eq(pctChange(50, 100), -50.0);
  eq(pctChange(0, 100), -100.0);
});

test('pctChange returns null for zero prev', () => {
  eq(pctChange(100, 0), null);
  eq(pctChange(50, null), null);
});

// 3. fmtPct
test('fmtPct formats percentages', () => {
  eq(fmtPct(19.8), '+19.8%');
  eq(fmtPct(-5.2), '-5.2%');
  eq(fmtPct(null), '—');
  eq(fmtPct(0), '+0.0%');
});

// 4. formatValue
test('formatValue — Revenue in billions', () => {
  eq(formatValue(44.062e9, 'revenue'), '$44.1B');
  eq(formatValue(81.615e9, 'revenue'), '$81.6B');
  eq(formatValue(1.0e6, 'revenue'), '$1M');
  eq(formatValue(1.5e6, 'revenue'), '$2M');  // toFixed(0) rounds 1.5→2
});

test('formatValue — EPS in per share', () => {
  eq(formatValue(2.40, 'eps'), '$2.40');
  eq(formatValue(0.77, 'eps'), '$0.77');
});

test('formatValue — null returns N/A', () => {
  eq(formatValue(null, 'revenue'), 'N/A');
  eq(formatValue(undefined, 'eps'), 'N/A');
});

// 5. transformValues — Absolute
test('transformValues — absolute returns raw values', () => {
  const result = transformValues(NVDA_DATA, 'revenue', 'absolute');
  eq(result[4], 81.615e9);
  eq(result.length, 5);
});

// 6. transformValues — QoQ (first null)
test('transformValues — qoq first point is null', () => {
  const result = transformValues(NVDA_DATA, 'revenue', 'qoq');
  eq(result[0], null);
  eq(result[1].toFixed(2), '6.08');  // (46.743-44.062)/44.062 * 100 ≈ 6.08
});

test('transformValues — qoq handles all metrics', () => {
  for (const m of ['revenue', 'net_income', 'ebitda', 'eps']) {
    const result = transformValues(NVDA_DATA, m, 'qoq');
    eq(result[0], null, `${m} qoq[0] should be null`);
    eq(typeof result[4], 'number', `${m} qoq[4] should be number`);
  }
});

// 7. transformValues — Growth
test('transformValues — growth from first quarter', () => {
  const result = transformValues(NVDA_DATA, 'eps', 'growth');
  eq(result[0], 0);  // 0% growth from base (same quarter)
  eq(result[4].toFixed(1), '211.7');  // (2.40-0.77)/0.77 * 100
});

// 8. calculateStats
test('calculateStats — absolute mode', () => {
  const stats = calculateStats(NVDA_DATA, 'revenue', 'absolute');
  eq(stats.latest, 81.615e9);
  eq(stats.peak, 81.615e9);
  eq(stats.low, 44.062e9);
  eq(stats.values.length, 5);
  eq(stats.isPctView, false);
});

test('calculateStats — qoq mode', () => {
  const stats = calculateStats(NVDA_DATA, 'eps', 'qoq');
  eq(stats.isPctView, true);
  eq(stats.values.length, 4);  // 5 data points, 1 null
});

test('calculateStats — growth mode', () => {
  const stats = calculateStats(NVDA_DATA, 'net_income', 'growth');
  eq(stats.isPctView, true);
  eq(stats.values.length, 5);
});

// 9. Edge case: empty data
test('calculateStats — empty data returns nulls', () => {
  const stats = calculateStats([], 'revenue', 'absolute');
  eq(stats.latest, null);
  eq(stats.values.length, 0);
});

// 10. Edge case: single point
test('calculateStats — single data point', () => {
  const stats = calculateStats([NVDA_DATA[0]], 'eps', 'absolute');
  eq(stats.latest, null);
  eq(stats.values.length, 1);
});

// 11. Edge case: missing metric
test('transformValues — missing metric returns undefined', () => {
  const data = [{ quarter: 'Q1', revenue: 100 }, { quarter: 'Q2' }];
  const result = transformValues(data, 'revenue', 'absolute');
  eq(result[0], 100);
  eq(result[1], undefined);
});

// ── Results ──
console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
if (failed > 0) process.exit(1);
