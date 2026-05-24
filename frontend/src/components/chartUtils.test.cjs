// Unit tests for chartUtils.js — V2.1 Financial Depth
// Run with: node chartUtils.test.cjs

const assert = require('assert');

// ── Pure functions (inline for CJS testing) ──

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

function _ratio(num, den) {
  if (num == null || den == null || den === 0) return null;
  return (num / den) * 100;
}

function _perShare(val, shares) {
  if (val == null || shares == null || shares === 0) return null;
  return val / shares;
}

function _subtract(a, b) {
  if (a == null || b == null) return null;
  return a - b;
}

function _sum(arr, key) {
  const vals = arr.map(d => d[key]).filter(v => v != null);
  if (vals.length < 4) return null;
  return vals.reduce((a, b) => a + b, 0);
}

function _debtRatio(debt, ebitda) {
  if (debt == null || ebitda == null || ebitda <= 0) return null;
  return debt / ebitda;
}

function formatValue(val, metric) {
  if (val == null) return 'N/A';
  if (metric === 'debt_to_ebitda_ttm' || metric === 'net_debt_to_ebitda_ttm') return `${val.toFixed(1)}×`;
  if (metric.endsWith('_margin') || metric.endsWith('_growth') || metric === 'share_count_growth') return `${val.toFixed(1)}%`;
  if (metric === 'eps' || metric === 'eps_ttm') return `$${val.toFixed(2)}`;
  if (metric.endsWith('_per_share')) return `$${val.toFixed(2)}`;
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

function enrichData(sortedData) {
  const pass1 = sortedData.map((d, i) => {
    const rev = d.revenue;
    const shares = d.diluted_shares;
    const e = { ...d };
    e.gross_margin = _ratio(d.gross_profit, rev);
    e.ebitda_margin = _ratio(d.ebitda, rev);
    e.net_margin = _ratio(d.net_income, rev);
    e.operating_margin = _ratio(d.operating_income, rev);
    e.fcf_margin = _ratio(d.free_cash_flow, rev);
    e.revenue_per_share = _perShare(rev, shares);
    e.fcf_per_share = _perShare(d.free_cash_flow, shares);
    e.net_cash_debt = _subtract(d.cash_and_equivalents, d.total_debt);
    if (i >= 3) {
      const w = sortedData.slice(i - 3, i + 1);
      e.revenue_ttm = _sum(w, 'revenue');
      e.ebitda_ttm = _sum(w, 'ebitda');
      e.net_income_ttm = _sum(w, 'net_income');
      e.operating_cash_flow_ttm = _sum(w, 'operating_cash_flow');
      e.free_cash_flow_ttm = _sum(w, 'free_cash_flow');
      e.eps_ttm = _sum(w, 'eps');
      e.fcf_margin_ttm = _ratio(e.free_cash_flow_ttm, e.revenue_ttm);
      e.debt_to_ebitda_ttm = _debtRatio(d.total_debt, e.ebitda_ttm);
      const netDebt = d.total_debt != null && d.cash_and_equivalents != null ? d.total_debt - d.cash_and_equivalents : null;
      e.net_debt_to_ebitda_ttm = _debtRatio(netDebt, e.ebitda_ttm);
    }
    return e;
  });
  const sharesVals = pass1.map(d => d.diluted_shares).filter(v => v != null);
  if (sharesVals.length < 2) return pass1;
  const firstShares = sharesVals[0];
  return pass1.map(d => ({
    ...d,
    share_count_growth: d.diluted_shares != null ? pctChange(d.diluted_shares, firstShares) : null,
  }));
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

// ── Test data — 8 quarters with full V2.1 fields ──
const FULL_DATA = [
  { quarter: '2024Q1', revenue: 119.575e9, net_income: 33.916e9, ebitda: 40.280e9, gross_profit: 54.855e9, eps: 2.18, operating_income: 35.890e9, operating_cash_flow: 37.100e9, capex: -2.010e9, free_cash_flow: 35.090e9, cash_and_equivalents: 61.200e9, total_debt: 95.100e9, diluted_shares: 15.523e9 },
  { quarter: '2024Q2', revenue: 90.753e9, net_income: 23.636e9, ebitda: 28.610e9, gross_profit: 41.571e9, eps: 1.53, operating_income: 25.400e9, operating_cash_flow: 21.400e9, capex: -1.980e9, free_cash_flow: 19.420e9, cash_and_equivalents: 58.300e9, total_debt: 92.800e9, diluted_shares: 15.510e9 },
  { quarter: '2024Q3', revenue: 85.777e9, net_income: 21.448e9, ebitda: 26.250e9, gross_profit: 39.677e9, eps: 1.40, operating_income: 23.500e9, operating_cash_flow: 26.200e9, capex: -2.150e9, free_cash_flow: 24.050e9, cash_and_equivalents: 62.100e9, total_debt: 93.400e9, diluted_shares: 15.420e9 },
  { quarter: '2024Q4', revenue: 94.930e9, net_income: 14.736e9, ebitda: 18.500e9, gross_profit: 43.879e9, eps: 0.97, operating_income: 16.500e9, operating_cash_flow: 16.300e9, capex: -2.300e9, free_cash_flow: 14.000e9, cash_and_equivalents: 57.500e9, total_debt: 90.200e9, diluted_shares: 15.320e9 },
  { quarter: '2025Q1', revenue: 124.300e9, net_income: 36.330e9, ebitda: 43.000e9, gross_profit: 58.270e9, eps: 2.40, operating_income: 38.500e9, operating_cash_flow: 29.900e9, capex: -2.050e9, free_cash_flow: 27.850e9, cash_and_equivalents: 59.800e9, total_debt: 89.300e9, diluted_shares: 15.110e9 },
  { quarter: '2025Q2', revenue: 95.440e9, net_income: 24.570e9, ebitda: 30.100e9, gross_profit: 43.910e9, eps: 1.64, operating_income: 26.800e9, operating_cash_flow: 22.300e9, capex: -2.100e9, free_cash_flow: 20.200e9, cash_and_equivalents: 56.900e9, total_debt: 87.500e9, diluted_shares: 14.950e9 },
  { quarter: '2025Q3', revenue: 90.150e9, net_income: 22.300e9, ebitda: 27.500e9, gross_profit: 41.500e9, eps: 1.50, operating_income: 24.500e9, operating_cash_flow: 27.100e9, capex: -2.200e9, free_cash_flow: 24.900e9, cash_and_equivalents: 58.200e9, total_debt: 86.100e9, diluted_shares: 14.820e9 },
  { quarter: '2025Q4', revenue: 98.720e9, net_income: 15.450e9, ebitda: 19.500e9, gross_profit: 45.600e9, eps: 1.02, operating_income: 17.200e9, operating_cash_flow: 17.500e9, capex: -2.400e9, free_cash_flow: 15.100e9, cash_and_equivalents: 55.400e9, total_debt: 84.700e9, diluted_shares: 14.690e9 },
];

const FULL_ENRICHED = enrichData(FULL_DATA);

let passed = 0, failed = 0;

function test(name, fn) { try { fn(); passed++; } catch (e) { failed++; console.error(`  FAIL ${name}: ${e.message}`); } }
function eq(actual, expected, msg) { assert.deepStrictEqual(actual, expected, msg); }
function approx(actual, expected, tolerance, msg) {
  if (Math.abs(actual - expected) > tolerance) { throw new Error(`${msg || 'approx'}: expected ${expected} ±${tolerance}, got ${actual}`); }
}

console.log('\n📊 chartUtils V2.1 Unit Tests\n');

// ── V1+V2.0 Regressions ──
test('formatQuarter', () => { eq(formatQuarter('2025Q2'), "Q2 FY'25"); });
test('pctChange', () => { eq(pctChange(100, 80), 25.0); eq(pctChange(100, 0), null); });
test('fmtPct', () => { eq(fmtPct(19.8), '+19.8%'); eq(fmtPct(null), '—'); });
test('formatValue — Revenue', () => { eq(formatValue(44.062e9, 'revenue'), '$44.1B'); });
test('formatValue — EPS', () => { eq(formatValue(2.40, 'eps'), '$2.40'); });
test('formatValue — null', () => { eq(formatValue(null, 'revenue'), 'N/A'); });
test('YoY — first 4 null', () => { const r = transformValues(FULL_DATA, 'revenue', 'yoy'); eq(r[0], null); eq(r[3], null); });
test('enrichData — gross_margin', () => { approx(FULL_ENRICHED[0].gross_margin, 45.87, 0.1); });
test('enrichData — fcf_per_share', () => { approx(FULL_ENRICHED[0].fcf_per_share, 2.26, 0.05); });

// ── V2.1: TTM ──
test('TTM — first 3 quarters have no TTM', () => {
  eq(FULL_ENRICHED[0].revenue_ttm, undefined);
  eq(FULL_ENRICHED[1].revenue_ttm, undefined);
  eq(FULL_ENRICHED[2].revenue_ttm, undefined);
});

test('TTM — 4th quarter has TTM (Q1-Q4 sum)', () => {
  // Q1-Q4 revenue: 119.575 + 90.753 + 85.777 + 94.930 = 391.035B
  approx(FULL_ENRICHED[3].revenue_ttm / 1e9, 391.035, 0.1);
});

test('TTM — 5th quarter has rolling TTM (Q2-Q5)', () => {
  // Q2-Q5: 90.753 + 85.777 + 94.930 + 124.300 = 395.760B
  approx(FULL_ENRICHED[4].revenue_ttm / 1e9, 395.760, 0.2);
});

test('TTM — latest quarter TTM (Q5-Q8)', () => {
  // Q5-Q8: 124.300 + 95.440 + 90.150 + 98.720 = 408.610B
  approx(FULL_ENRICHED[7].revenue_ttm / 1e9, 408.610, 0.2);
});

test('TTM — EBITDA TTM computed', () => {
  approx(FULL_ENRICHED[7].ebitda_ttm / 1e9, 120.1, 0.2);
});

test('TTM — EPS TTM computed', () => {
  approx(FULL_ENRICHED[7].eps_ttm, 6.56, 0.05);
});

test('TTM — FCF Margin TTM', () => {
  approx(FULL_ENRICHED[7].fcf_margin_ttm, 21.54, 0.2);
});

test('TTM — less than 4 quarters returns null', () => {
  const short = FULL_DATA.slice(0, 3);
  const enriched = enrichData(short);
  eq(enriched[2].revenue_ttm, undefined);
});

// ── V2.1: Balance Sheet ──
test('Balance Sheet — net_cash_debt = cash - debt', () => {
  const d = FULL_ENRICHED[0];
  // cash=61.2B, debt=95.1B → net_cash_debt = -33.9B (Net Debt)
  approx(d.net_cash_debt, 61.200e9 - 95.100e9, 1e7);
  eq(d.net_cash_debt < 0, true); // Net Debt position
});

test('Balance Sheet — Net Debt label logic', () => {
  const val = FULL_ENRICHED[0].net_cash_debt;
  eq(val < 0, true); // Net Debt
});

test('Balance Sheet — Debt/EBITDA TTM', () => {
  const d = FULL_ENRICHED[7];
  approx(d.debt_to_ebitda_ttm, 84.700e9 / (19.500e9 + 27.500e9 + 30.100e9 + 43.000e9), 0.1);
});

test('Balance Sheet — Debt/EBITDA with zero EBITDA returns null', () => {
  eq(_debtRatio(100, 0), null);
  eq(_debtRatio(100, -10), null);
  eq(_debtRatio(null, 100), null);
});

test('Balance Sheet — Net Debt/EBITDA TTM', () => {
  const d = FULL_ENRICHED[7];
  const netDebt = d.total_debt - d.cash_and_equivalents;
  const netDebtRatio = netDebt / d.ebitda_ttm;
  approx(d.net_debt_to_ebitda_ttm, netDebtRatio, 0.1);
});

// ── V2.1: Per Share ──
test('Per Share — revenue_per_share', () => {
  const d = FULL_ENRICHED[0];
  approx(d.revenue_per_share, 119.575e9 / 15.523e9, 0.05);
});

test('Per Share — fcf_per_share', () => {
  const d = FULL_ENRICHED[0];
  approx(d.fcf_per_share, 35.090e9 / 15.523e9, 0.05);
});

test('Per Share — diluted_shares null → N/A', () => {
  const bad = [{ quarter: 'Q1', revenue: 100, diluted_shares: null }];
  const enriched = enrichData(bad);
  eq(enriched[0].revenue_per_share, null);
  eq(enriched[0].fcf_per_share, null);
});

test('Per Share — diluted_shares zero → N/A', () => {
  const bad = [{ quarter: 'Q1', revenue: 100, diluted_shares: 0 }];
  const enriched = enrichData(bad);
  eq(enriched[0].revenue_per_share, null);
});

// ── V2.1: Share Count Growth ──
test('Share Count Growth — positive (dilution)', () => {
  const data = [
    { quarter: 'Q1', diluted_shares: 10e9 },
    { quarter: 'Q2', diluted_shares: 10.5e9 },
  ];
  const enriched = enrichData(data);
  approx(enriched[1].share_count_growth, 5.0, 0.1);
});

test('Share Count Growth — negative (buyback)', () => {
  const data = [
    { quarter: 'Q1', diluted_shares: 15.523e9 },
    { quarter: 'Q8', diluted_shares: 14.690e9 },
  ];
  // In FULL_DATA: first=15.523B, last=14.690B → -5.4%
  approx(FULL_ENRICHED[7].share_count_growth, -5.36, 0.2);
});

test('Share Count Growth — single data point returns null', () => {
  const data = [{ quarter: 'Q1', diluted_shares: 10e9 }];
  const enriched = enrichData(data);
  eq(enriched[0].share_count_growth, undefined);
});

// ── V2.1: Formatting ──
test('formatValue — ratio (Debt/EBITDA)', () => {
  eq(formatValue(2.45, 'debt_to_ebitda_ttm'), '2.5×');
  eq(formatValue(0.53, 'net_debt_to_ebitda_ttm'), '0.5×');
});

test('formatValue — per share', () => {
  eq(formatValue(7.70, 'revenue_per_share'), '$7.70');
  eq(formatValue(2.26, 'fcf_per_share'), '$2.26');
});

test('formatValue — diluted_shares in billions', () => {
  eq(formatValue(15.523e9, 'diluted_shares'), '15.52B');
});

test('formatValue — share_count_growth', () => {
  eq(formatValue(-5.4, 'share_count_growth'), '-5.4%');
  eq(formatValue(3.2, 'share_count_growth'), '3.2%');
});

test('formatValue — EPS TTM', () => {
  eq(formatValue(6.56, 'eps_ttm'), '$6.56');
});

// ── Results ──
console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
if (failed > 0) process.exit(1);
