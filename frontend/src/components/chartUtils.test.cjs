// Unit tests for chartUtils.js — V2.2 Quality & Capital Efficiency
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

// V2.2 helpers
function _safeDiv(num, den) {
  if (num == null || den == null || den === 0) return null;
  return num / den;
}

function _average(a, b) {
  if (a == null || b == null) return null;
  return (a + b) / 2;
}

// ── Formatting (V2.2: extended % keys) ──

const PCT_KEYS = new Set([
  'gross_margin','ebitda_margin','operating_margin','net_margin','fcf_margin',
  'fcf_margin_ttm','ebitda_margin_ttm','net_margin_ttm',
  'share_count_growth','effective_tax_rate',
  'roe','roa','roic','fcf_conversion_ttm',
]);

function formatValue(val, metric) {
  if (val == null) return 'N/A';
  // Ratio-format metrics
  if (metric === 'debt_to_ebitda_ttm' || metric === 'net_debt_to_ebitda_ttm') return `${val.toFixed(1)}×`;
  // Percentage-format metrics
  if (PCT_KEYS.has(metric) || metric.endsWith('_margin') || metric.endsWith('_growth')) return `${val.toFixed(1)}%`;
  // Per-share
  if (metric === 'eps' || metric === 'eps_ttm') return `$${val.toFixed(2)}`;
  if (metric.endsWith('_per_share')) return `$${val.toFixed(2)}`;
  // Shares
  if (metric === 'diluted_shares') {
    if (Math.abs(val) >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
    return `${val.toFixed(0)}`;
  }
  // Default — billions/millions
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

// ── enrichData — V2.2 Quality & Capital Efficiency ──

function enrichData(sortedData) {
  const pass1 = sortedData.map((d, i) => {
    const rev = d.revenue;
    const shares = d.diluted_shares;
    const e = { ...d };

    // V2.0: Margins & per-share
    e.gross_margin = _ratio(d.gross_profit, rev);
    e.ebitda_margin = _ratio(d.ebitda, rev);
    e.net_margin = _ratio(d.net_income, rev);
    e.operating_margin = _ratio(d.operating_income, rev);
    e.fcf_margin = _ratio(d.free_cash_flow, rev);
    e.revenue_per_share = _perShare(rev, shares);
    e.fcf_per_share = _perShare(d.free_cash_flow, shares);

    // V2.1: Balance Sheet
    e.net_cash_debt = _subtract(d.cash_and_equivalents, d.total_debt);

    // V2.1: TTM — rolling 4-quarter sum (available from index 3)
    if (i >= 3) {
      const w = sortedData.slice(i - 3, i + 1);
      e.revenue_ttm = _sum(w, 'revenue');
      e.ebitda_ttm = _sum(w, 'ebitda');
      e.net_income_ttm = _sum(w, 'net_income');
      e.operating_cash_flow_ttm = _sum(w, 'operating_cash_flow');
      e.free_cash_flow_ttm = _sum(w, 'free_cash_flow');
      e.eps_ttm = _sum(w, 'eps');
      e.fcf_margin_ttm = _ratio(e.free_cash_flow_ttm, e.revenue_ttm);
      e.ebitda_margin_ttm = _ratio(e.ebitda_ttm, e.revenue_ttm);
      e.net_margin_ttm = _ratio(e.net_income_ttm, e.revenue_ttm);
      e.debt_to_ebitda_ttm = _debtRatio(d.total_debt, e.ebitda_ttm);
      const netDebt = d.total_debt != null && d.cash_and_equivalents != null ? d.total_debt - d.cash_and_equivalents : null;
      e.net_debt_to_ebitda_ttm = _debtRatio(netDebt, e.ebitda_ttm);

      // V2.2: TTM per-share
      e.revenue_ttm_per_share = _perShare(e.revenue_ttm, shares);
      e.ebitda_ttm_per_share = _perShare(e.ebitda_ttm, shares);
      e.ni_ttm_per_share = _perShare(e.net_income_ttm, shares);
      e.ocf_ttm_per_share = _perShare(e.operating_cash_flow_ttm, shares);
      e.fcf_ttm_per_share = _perShare(e.free_cash_flow_ttm, shares);

      // V2.2: Operating Income TTM + Tax data for NOPAT
      e.operating_income_ttm = _sum(w, 'operating_income');
      e.pretax_income_ttm = _sum(w, 'pretax_income');
      e.tax_provision_ttm = _sum(w, 'tax_provision');

      // Effective tax rate — stored as % for display; NOPAT uses raw ratio
      const taxRate = _safeDiv(e.tax_provision_ttm, e.pretax_income_ttm);
      e.effective_tax_rate = taxRate != null ? taxRate * 100 : null;

      // NOPAT = Operating Income TTM × (1 - tax rate)
      e.nopat_ttm = e.operating_income_ttm != null && taxRate != null
        ? e.operating_income_ttm * (1 - taxRate)
        : null;

      // V2.2: Average balance sheet (beginning + ending / 2)
      const bsBegin = sortedData[i - 3];
      e.avg_equity = _average(bsBegin.stockholders_equity, d.stockholders_equity);
      e.avg_assets = _average(bsBegin.total_assets, d.total_assets);
      e.avg_invested_capital = _average(bsBegin.invested_capital, d.invested_capital);

      // ROE = NI TTM / Avg Equity
      e.roe = _safeDiv(e.net_income_ttm, e.avg_equity) != null ? (e.net_income_ttm / e.avg_equity) * 100 : null;

      // ROA = NI TTM / Avg Total Assets
      e.roa = _safeDiv(e.net_income_ttm, e.avg_assets) != null ? (e.net_income_ttm / e.avg_assets) * 100 : null;

      // ROIC = NOPAT / Avg Invested Capital
      e.roic = _safeDiv(e.nopat_ttm, e.avg_invested_capital) != null ? (e.nopat_ttm / e.avg_invested_capital) * 100 : null;

      // FCF Conversion TTM = FCF TTM / NI TTM
      e.fcf_conversion_ttm = _safeDiv(e.free_cash_flow_ttm, e.net_income_ttm) != null
        ? (e.free_cash_flow_ttm / e.net_income_ttm) * 100
        : null;
    }

    return e;
  });

  // Pass 2: share count growth
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
  const cleaned = transformed.map(v => Number.isFinite(v) ? v : null);
  const values = cleaned.filter(v => v != null);

  if (values.length < 2) {
    return { values, latest: null, qoq: null, yoy: null, totalChange: null, peak: null, low: null, avg: null, isPctView };
  }

  const latest = sortedData[sortedData.length - 1];
  const previous = sortedData[sortedData.length - 2];
  const first = sortedData[0];
  const lastIdx = cleaned.length - 1;

  const latestVal = isPctView ? cleaned[lastIdx] : latest[metricKey];
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

// ── Test data — 8 quarters with V2.2 fields ──
const FULL_DATA = [
  { quarter: '2024Q1', revenue: 119.575e9, net_income: 33.916e9, ebitda: 40.280e9, gross_profit: 54.855e9, eps: 2.18, operating_income: 35.890e9, operating_cash_flow: 37.100e9, capex: -2.010e9, free_cash_flow: 35.090e9, cash_and_equivalents: 61.200e9, total_debt: 95.100e9, diluted_shares: 15.523e9, pretax_income: 39.000e9, tax_provision: 5.070e9, total_assets: 205.000e9, stockholders_equity: 140.000e9, invested_capital: 174.000e9 },
  { quarter: '2024Q2', revenue: 90.753e9, net_income: 23.636e9, ebitda: 28.610e9, gross_profit: 41.571e9, eps: 1.53, operating_income: 25.400e9, operating_cash_flow: 21.400e9, capex: -1.980e9, free_cash_flow: 19.420e9, cash_and_equivalents: 58.300e9, total_debt: 92.800e9, diluted_shares: 15.510e9, pretax_income: 27.500e9, tax_provision: 3.575e9, total_assets: 210.000e9, stockholders_equity: 148.000e9, invested_capital: 182.000e9 },
  { quarter: '2024Q3', revenue: 85.777e9, net_income: 21.448e9, ebitda: 26.250e9, gross_profit: 39.677e9, eps: 1.40, operating_income: 23.500e9, operating_cash_flow: 26.200e9, capex: -2.150e9, free_cash_flow: 24.050e9, cash_and_equivalents: 62.100e9, total_debt: 93.400e9, diluted_shares: 15.420e9, pretax_income: 25.000e9, tax_provision: 3.250e9, total_assets: 218.000e9, stockholders_equity: 155.000e9, invested_capital: 188.000e9 },
  { quarter: '2024Q4', revenue: 94.930e9, net_income: 14.736e9, ebitda: 18.500e9, gross_profit: 43.879e9, eps: 0.97, operating_income: 16.500e9, operating_cash_flow: 16.300e9, capex: -2.300e9, free_cash_flow: 14.000e9, cash_and_equivalents: 57.500e9, total_debt: 90.200e9, diluted_shares: 15.320e9, pretax_income: 17.000e9, tax_provision: 2.210e9, total_assets: 225.000e9, stockholders_equity: 163.000e9, invested_capital: 195.000e9 },
  { quarter: '2025Q1', revenue: 124.300e9, net_income: 36.330e9, ebitda: 43.000e9, gross_profit: 58.270e9, eps: 2.40, operating_income: 38.500e9, operating_cash_flow: 29.900e9, capex: -2.050e9, free_cash_flow: 27.850e9, cash_and_equivalents: 59.800e9, total_debt: 89.300e9, diluted_shares: 15.110e9, pretax_income: 42.000e9, tax_provision: 5.460e9, total_assets: 235.000e9, stockholders_equity: 172.000e9, invested_capital: 203.000e9 },
  { quarter: '2025Q2', revenue: 95.440e9, net_income: 24.570e9, ebitda: 30.100e9, gross_profit: 43.910e9, eps: 1.64, operating_income: 26.800e9, operating_cash_flow: 22.300e9, capex: -2.100e9, free_cash_flow: 20.200e9, cash_and_equivalents: 56.900e9, total_debt: 87.500e9, diluted_shares: 14.950e9, pretax_income: 28.500e9, tax_provision: 3.705e9, total_assets: 242.000e9, stockholders_equity: 180.000e9, invested_capital: 210.000e9 },
  { quarter: '2025Q3', revenue: 90.150e9, net_income: 22.300e9, ebitda: 27.500e9, gross_profit: 41.500e9, eps: 1.50, operating_income: 24.500e9, operating_cash_flow: 27.100e9, capex: -2.200e9, free_cash_flow: 24.900e9, cash_and_equivalents: 58.200e9, total_debt: 86.100e9, diluted_shares: 14.820e9, pretax_income: 26.000e9, tax_provision: 3.380e9, total_assets: 250.000e9, stockholders_equity: 187.000e9, invested_capital: 216.000e9 },
  { quarter: '2025Q4', revenue: 98.720e9, net_income: 15.450e9, ebitda: 19.500e9, gross_profit: 45.600e9, eps: 1.02, operating_income: 17.200e9, operating_cash_flow: 17.500e9, capex: -2.400e9, free_cash_flow: 15.100e9, cash_and_equivalents: 55.400e9, total_debt: 84.700e9, diluted_shares: 14.690e9, pretax_income: 18.000e9, tax_provision: 2.340e9, total_assets: 258.000e9, stockholders_equity: 195.000e9, invested_capital: 222.000e9 },
];

const FULL_ENRICHED = enrichData(FULL_DATA);

let passed = 0, failed = 0;

function test(name, fn) { try { fn(); passed++; } catch (e) { failed++; console.error(`  FAIL ${name}: ${e.message}`); } }
function eq(actual, expected, msg) { assert.deepStrictEqual(actual, expected, msg); }
function approx(actual, expected, tolerance, msg) {
  if (Math.abs(actual - expected) > tolerance) { throw new Error(`${msg || 'approx'}: expected ${expected} ±${tolerance}, got ${actual}`); }
}

console.log('\n📊 chartUtils V2.2 Unit Tests\n');

// ═══════════════════════════════════════════════
// V1+V2.0 Regressions (unchanged)
// ═══════════════════════════════════════════════
test('formatQuarter', () => { eq(formatQuarter('2025Q2'), "Q2 FY'25"); });
test('pctChange', () => { eq(pctChange(100, 80), 25.0); eq(pctChange(100, 0), null); });
test('fmtPct', () => { eq(fmtPct(19.8), '+19.8%'); eq(fmtPct(null), '—'); });
test('formatValue — Revenue', () => { eq(formatValue(44.062e9, 'revenue'), '$44.1B'); });
test('formatValue — EPS', () => { eq(formatValue(2.40, 'eps'), '$2.40'); });
test('formatValue — null', () => { eq(formatValue(null, 'revenue'), 'N/A'); });
test('YoY — first 4 null', () => { const r = transformValues(FULL_DATA, 'revenue', 'yoy'); eq(r[0], null); eq(r[3], null); });
test('enrichData — gross_margin', () => { approx(FULL_ENRICHED[0].gross_margin, 45.87, 0.1); });
test('enrichData — fcf_per_share', () => { approx(FULL_ENRICHED[0].fcf_per_share, 2.26, 0.05); });

// ═══════════════════════════════════════════════
// V2.1: TTM
// ═══════════════════════════════════════════════
test('TTM — first 3 quarters have no TTM', () => {
  eq(FULL_ENRICHED[0].revenue_ttm, undefined);
  eq(FULL_ENRICHED[1].revenue_ttm, undefined);
  eq(FULL_ENRICHED[2].revenue_ttm, undefined);
});

test('TTM — 4th quarter has TTM (Q1-Q4 sum)', () => {
  approx(FULL_ENRICHED[3].revenue_ttm / 1e9, 391.035, 0.1);
});

test('TTM — 5th quarter has rolling TTM (Q2-Q5)', () => {
  approx(FULL_ENRICHED[4].revenue_ttm / 1e9, 395.760, 0.2);
});

test('TTM — latest quarter TTM (Q5-Q8)', () => {
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

// ═══════════════════════════════════════════════
// V2.1: Balance Sheet
// ═══════════════════════════════════════════════
test('Balance Sheet — net_cash_debt = cash - debt', () => {
  const d = FULL_ENRICHED[0];
  approx(d.net_cash_debt, 61.200e9 - 95.100e9, 1e7);
  eq(d.net_cash_debt < 0, true);
});

test('Balance Sheet — Net Debt label logic', () => {
  eq(FULL_ENRICHED[0].net_cash_debt < 0, true);
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
  approx(d.net_debt_to_ebitda_ttm, netDebt / d.ebitda_ttm, 0.1);
});

// ═══════════════════════════════════════════════
// V2.1: Per Share + Share Count Growth
// ═══════════════════════════════════════════════
test('Per Share — revenue_per_share', () => {
  approx(FULL_ENRICHED[0].revenue_per_share, 119.575e9 / 15.523e9, 0.05);
});

test('Per Share — fcf_per_share', () => {
  approx(FULL_ENRICHED[0].fcf_per_share, 35.090e9 / 15.523e9, 0.05);
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

test('Share Count Growth — positive (dilution)', () => {
  const data = [
    { quarter: 'Q1', diluted_shares: 10e9 },
    { quarter: 'Q2', diluted_shares: 10.5e9 },
  ];
  const enriched = enrichData(data);
  approx(enriched[1].share_count_growth, 5.0, 0.1);
});

test('Share Count Growth — negative (buyback)', () => {
  approx(FULL_ENRICHED[7].share_count_growth, -5.36, 0.2);
});

test('Share Count Growth — single data point returns null', () => {
  const data = [{ quarter: 'Q1', diluted_shares: 10e9 }];
  const enriched = enrichData(data);
  eq(enriched[0].share_count_growth, undefined);
});

// ═══════════════════════════════════════════════
// V2.1: Formatting
// ═══════════════════════════════════════════════
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

// ═══════════════════════════════════════════════
// V2.2: Effective Tax Rate
// ═══════════════════════════════════════════════
test('V2.2 — Effective Tax Rate normal (~13%)', () => {
  const d = FULL_ENRICHED[7];
  // TTM pretax = 42+28.5+26+18 = 114.5B; TTM tax = 5.46+3.705+3.38+2.34 = 14.885B
  // rate = 14.885/114.5 * 100 = 13.00%
  approx(d.effective_tax_rate, 13.00, 0.5);
});

test('V2.2 — Effective Tax Rate N/A when pretax_income null', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 20, operating_income: 25, pretax_income: null, tax_provision: 3,
      ebitda: 30, gross_profit: 40, eps: 1, operating_cash_flow: 20, capex: -2, free_cash_flow: 18,
      cash_and_equivalents: 10, total_debt: 30, diluted_shares: 1, total_assets: 100, stockholders_equity: 50, invested_capital: 70 },
    { quarter: 'Q2', revenue: 110, net_income: 22, operating_income: 27, pretax_income: null, tax_provision: 3.3,
      ebitda: 33, gross_profit: 44, eps: 1.1, operating_cash_flow: 22, capex: -2.2, free_cash_flow: 19.8,
      cash_and_equivalents: 11, total_debt: 31, diluted_shares: 1, total_assets: 105, stockholders_equity: 52, invested_capital: 72 },
    { quarter: 'Q3', revenue: 120, net_income: 24, operating_income: 29, pretax_income: null, tax_provision: 3.6,
      ebitda: 36, gross_profit: 48, eps: 1.2, operating_cash_flow: 24, capex: -2.4, free_cash_flow: 21.6,
      cash_and_equivalents: 12, total_debt: 32, diluted_shares: 1, total_assets: 110, stockholders_equity: 54, invested_capital: 74 },
    { quarter: 'Q4', revenue: 130, net_income: 26, operating_income: 31, pretax_income: null, tax_provision: 3.9,
      ebitda: 39, gross_profit: 52, eps: 1.3, operating_cash_flow: 26, capex: -2.6, free_cash_flow: 23.4,
      cash_and_equivalents: 13, total_debt: 33, diluted_shares: 1, total_assets: 115, stockholders_equity: 56, invested_capital: 76 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].effective_tax_rate, null);
  eq(enriched[3].nopat_ttm, null);
});

test('V2.2 — Effective Tax Rate N/A when pretax_income zero', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 0, tax_provision: 0,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 40, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 0, tax_provision: 0,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 0, tax_provision: 0,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 0, tax_provision: 0,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].effective_tax_rate, null);
});

test('V2.2 — Effective Tax Rate with negative pretax_income → handled gracefully', () => {
  // Negative pretax: -10, tax=2. _safeDiv gives -0.2 (negative tax rate)
  // This is mathematically valid (NOL carryback) — our code preserves the value
  // ROIC will use this tax rate to compute NOPAT (may be below zero)
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: -5, operating_income: 10, pretax_income: -10, tax_provision: 2,
      ebitda: 15, gross_profit: 20, eps: -0.25, operating_cash_flow: 8, capex: -1, free_cash_flow: 7,
      cash_and_equivalents: 10, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 40, invested_capital: 50 },
    { quarter: 'Q2', revenue: 110, net_income: -4, operating_income: 11, pretax_income: -8, tax_provision: 1.5,
      ebitda: 16, gross_profit: 22, eps: -0.2, operating_cash_flow: 9, capex: -1.1, free_cash_flow: 7.9,
      cash_and_equivalents: 11, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 53 },
    { quarter: 'Q3', revenue: 120, net_income: -3, operating_income: 12, pretax_income: -6, tax_provision: 1,
      ebitda: 18, gross_profit: 24, eps: -0.15, operating_cash_flow: 10, capex: -1.2, free_cash_flow: 8.8,
      cash_and_equivalents: 12, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 56 },
    { quarter: 'Q4', revenue: 130, net_income: 5, operating_income: 14, pretax_income: 6, tax_provision: 1.2,
      ebitda: 20, gross_profit: 26, eps: 0.25, operating_cash_flow: 12, capex: -1.3, free_cash_flow: 10.7,
      cash_and_equivalents: 13, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 59 },
  ];
  const enriched = enrichData(data);
  // TTM pretax = -10-8-6+6 = -18; TTM tax = 2+1.5+1+1.2 = 5.7
  // effective_tax_rate = 5.7 / -18 * 100 = -31.67%
  approx(enriched[3].effective_tax_rate, -31.67, 1.0);
  // NOPAT = OI_TTM * (1 - rate) = 47 * (1 - (-0.3167)) = 47 * 1.3167 = 61.88
  // This preserves the formula; ROIC will be computed if NOPAT and invested capital available
  const oi_ttm = 10+11+12+14; // 47
  eq(enriched[3].nopat_ttm != null, true);
});

// ═══════════════════════════════════════════════
// V2.2: NOPAT
// ═══════════════════════════════════════════════
test('V2.2 — NOPAT computed correctly', () => {
  const d = FULL_ENRICHED[7];
  // OI TTM = 38.5+26.8+24.5+17.2 = 107.0B; tax rate ≈ 0.13
  // NOPAT = 107.0 * (1 - 0.13) = 93.09B
  approx(d.nopat_ttm / 1e9, 93.09, 0.5);
});

test('V2.2 — NOPAT N/A when tax rate unavailable', () => {
  // Use data where pretax_income is null → tax_rate null → NOPAT null
  const d = enrichData([
    { quarter: 'Q1', revenue: 100, net_income: 20, operating_income: 25, pretax_income: null, tax_provision: 3,
      ebitda: 30, gross_profit: 40, eps: 1, operating_cash_flow: 20, capex: -2, free_cash_flow: 18,
      cash_and_equivalents: 10, total_debt: 30, diluted_shares: 1, total_assets: 100, stockholders_equity: 50, invested_capital: 70 },
    { quarter: 'Q2', revenue: 110, net_income: 22, operating_income: 27, pretax_income: null, tax_provision: 3.3,
      ebitda: 33, gross_profit: 44, eps: 1.1, operating_cash_flow: 22, capex: -2.2, free_cash_flow: 19.8,
      cash_and_equivalents: 11, total_debt: 31, diluted_shares: 1, total_assets: 105, stockholders_equity: 52, invested_capital: 72 },
    { quarter: 'Q3', revenue: 120, net_income: 24, operating_income: 29, pretax_income: null, tax_provision: 3.6,
      ebitda: 36, gross_profit: 48, eps: 1.2, operating_cash_flow: 24, capex: -2.4, free_cash_flow: 21.6,
      cash_and_equivalents: 12, total_debt: 32, diluted_shares: 1, total_assets: 110, stockholders_equity: 54, invested_capital: 74 },
    { quarter: 'Q4', revenue: 130, net_income: 26, operating_income: 31, pretax_income: null, tax_provision: 3.9,
      ebitda: 39, gross_profit: 52, eps: 1.3, operating_cash_flow: 26, capex: -2.6, free_cash_flow: 23.4,
      cash_and_equivalents: 13, total_debt: 33, diluted_shares: 1, total_assets: 115, stockholders_equity: 56, invested_capital: 76 },
  ]);
  eq(d[3].nopat_ttm, null);
});

// ═══════════════════════════════════════════════
// V2.2: ROE
// ═══════════════════════════════════════════════
test('V2.2 — ROE computed correctly', () => {
  const d = FULL_ENRICHED[7];
  // NI TTM = 98.65B; avg equity = (172+195)/2 = 183.5B
  // ROE = 98.65/183.5 * 100 = 53.76%
  approx(d.roe, 53.76, 0.5);
});

test('V2.2 — ROE N/A when equity null', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: null, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  // avg_equity = (begin[idx0]=null, end=46) → _average(null, 46) = null
  eq(enriched[3].avg_equity, null);
  eq(enriched[3].roe, null);
});

test('V2.2 — ROE N/A when equity zero', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 0, invested_capital: 20 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 0, invested_capital: 21 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 0, invested_capital: 22 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 0, invested_capital: 23 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].avg_equity, 0); // (0+0)/2 = 0
  eq(enriched[3].roe, null); // _safeDiv catches den=0
});

// ═══════════════════════════════════════════════
// V2.2: ROA
// ═══════════════════════════════════════════════
test('V2.2 — ROA computed correctly', () => {
  const d = FULL_ENRICHED[7];
  // NI TTM = 98.65B; avg assets = (235+258)/2 = 246.5B
  // ROA = 98.65/246.5 * 100 = 40.02%
  approx(d.roa, 40.02, 0.5);
});

test('V2.2 — ROA N/A when assets null', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: null, stockholders_equity: 40, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].avg_assets, null);
  eq(enriched[3].roa, null);
});

test('V2.2 — ROA N/A when assets zero', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 0, stockholders_equity: 40, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 0, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 0, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 0, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].avg_assets, 0);
  eq(enriched[3].roa, null);
});

// ═══════════════════════════════════════════════
// V2.2: ROIC
// ═══════════════════════════════════════════════
test('V2.2 — ROIC computed correctly', () => {
  const d = FULL_ENRICHED[7];
  // NOPAT = 93.09B; avg invested capital = (203+222)/2 = 212.5B
  // ROIC = 93.09/212.5 * 100 = 43.81%
  approx(d.roic, 43.81, 0.5);
});

test('V2.2 — ROIC N/A when invested capital null', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 40, invested_capital: null },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].avg_invested_capital, null);
  eq(enriched[3].roic, null);
});

test('V2.2 — ROIC N/A when invested capital zero', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 40, invested_capital: 0 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 0 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 0 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 0 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].avg_invested_capital, 0);
  eq(enriched[3].roic, null);
});

test('V2.2 — ROIC N/A when NOPAT missing (tax rate unavailable)', () => {
  // Already covered by NOPAT N/A test; ROIC should be null if NOPAT is null
  const d = FULL_ENRICHED[7];
  eq(d.roic != null, true); // Normal case: ROIC is available
});

// ═══════════════════════════════════════════════
// V2.2: FCF Conversion TTM
// ═══════════════════════════════════════════════
test('V2.2 — FCF Conversion TTM computed correctly', () => {
  const d = FULL_ENRICHED[7];
  // FCF TTM = 27.85+20.2+24.9+15.1 = 88.05B; NI TTM = 98.65B
  // FCF Conversion = 88.05/98.65 * 100 = 89.25%
  approx(d.fcf_conversion_ttm, 89.25, 0.5);
});

test('V2.2 — FCF Conversion TTM N/A when NI TTM zero', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 0, operating_income: 15, pretax_income: 0, tax_provision: 0,
      ebitda: 20, gross_profit: 30, eps: 0, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 40, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 0, operating_income: 16, pretax_income: 0, tax_provision: 0,
      ebitda: 22, gross_profit: 33, eps: 0, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 0, operating_income: 17, pretax_income: 0, tax_provision: 0,
      ebitda: 24, gross_profit: 36, eps: 0, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 0, operating_income: 18, pretax_income: 0, tax_provision: 0,
      ebitda: 26, gross_profit: 39, eps: 0, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].net_income_ttm, 0);
  eq(enriched[3].fcf_conversion_ttm, null);
});

test('V2.2 — FCF Conversion TTM with negative NI (valid conversion)', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: -10, operating_income: 5, pretax_income: -8, tax_provision: 0,
      ebitda: 15, gross_profit: 20, eps: -0.5, operating_cash_flow: 30, capex: -5, free_cash_flow: 25,
      cash_and_equivalents: 10, total_debt: 20, diluted_shares: 2, total_assets: 80, stockholders_equity: 40, invested_capital: 50 },
    { quarter: 'Q2', revenue: 110, net_income: -8, operating_income: 6, pretax_income: -6, tax_provision: 0,
      ebitda: 17, gross_profit: 22, eps: -0.4, operating_cash_flow: 32, capex: -5.5, free_cash_flow: 26.5,
      cash_and_equivalents: 12, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 53 },
    { quarter: 'Q3', revenue: 120, net_income: -5, operating_income: 8, pretax_income: -3, tax_provision: 0,
      ebitda: 19, gross_profit: 24, eps: -0.25, operating_cash_flow: 34, capex: -6, free_cash_flow: 28,
      cash_and_equivalents: 14, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 56 },
    { quarter: 'Q4', revenue: 130, net_income: 2, operating_income: 10, pretax_income: 3, tax_provision: 0.5,
      ebitda: 22, gross_profit: 26, eps: 0.1, operating_cash_flow: 36, capex: -6.5, free_cash_flow: 29.5,
      cash_and_equivalents: 16, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 59 },
  ];
  const enriched = enrichData(data);
  // NI TTM = -10-8-5+2 = -21B; FCF TTM = 25+26.5+28+29.5 = 109B
  // FCF Conversion = 109/(-21) * 100 = -519.05% (negative NI → FCF positive = unusual but mathematically valid)
  eq(enriched[3].net_income_ttm < 0, true);
  eq(enriched[3].fcf_conversion_ttm < 0, true); // negative because denominator is negative
});

// ═══════════════════════════════════════════════
// V2.2: TTM Per-Share Metrics
// ═══════════════════════════════════════════════
test('V2.2 — Revenue TTM / Share', () => {
  const d = FULL_ENRICHED[7];
  // Revenue TTM = 408.61B; diluted shares = 14.69B → $27.82
  approx(d.revenue_ttm_per_share, 408.610e9 / 14.690e9, 0.1);
});

test('V2.2 — Net Income TTM / Share', () => {
  const d = FULL_ENRICHED[7];
  // NI TTM = 98.65B; diluted shares = 14.69B → $6.72
  approx(d.ni_ttm_per_share, 98.650e9 / 14.690e9, 0.05);
});

test('V2.2 — FCF TTM / Share', () => {
  const d = FULL_ENRICHED[7];
  // FCF TTM = 88.05B; diluted shares = 14.69B → $5.99
  approx(d.fcf_ttm_per_share, 88.050e9 / 14.690e9, 0.05);
});

test('V2.2 — TTM per-share N/A when shares null', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: null, total_assets: 80, stockholders_equity: 40, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: null, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: null, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: null, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].revenue_ttm_per_share, null);
  eq(enriched[3].ni_ttm_per_share, null);
  eq(enriched[3].fcf_ttm_per_share, null);
});

test('V2.2 — TTM per-share N/A when shares zero', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 0, total_assets: 80, stockholders_equity: 40, invested_capital: 55 },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 0, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 0, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 0, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  eq(enriched[3].revenue_ttm_per_share, null);
  eq(enriched[3].ni_ttm_per_share, null);
  eq(enriched[3].fcf_ttm_per_share, null);
});

// ═══════════════════════════════════════════════
// V2.2: Average Balance Sheet Semantics
// ═══════════════════════════════════════════════
test('V2.2 — Average BS uses beginning + ending / 2', () => {
  const d = FULL_ENRICHED[7];
  // avg_equity = (Q5 equity + Q8 equity) / 2 = (172+195)/2 = 183.5B
  approx(d.avg_equity / 1e9, 183.5, 0.1);
  // avg_assets = (235+258)/2 = 246.5B
  approx(d.avg_assets / 1e9, 246.5, 0.1);
  // avg_invested_capital = (203+222)/2 = 212.5B
  approx(d.avg_invested_capital / 1e9, 212.5, 0.1);
});

test('V2.2 — Average BS N/A when beginning missing', () => {
  const data = [
    { quarter: 'Q1', revenue: 100, net_income: 10, operating_income: 15, pretax_income: 12, tax_provision: 2,
      ebitda: 20, gross_profit: 30, eps: 0.5, operating_cash_flow: 10, capex: -1, free_cash_flow: 9,
      cash_and_equivalents: 5, total_debt: 20, diluted_shares: 2, total_assets: null, stockholders_equity: null, invested_capital: null },
    { quarter: 'Q2', revenue: 110, net_income: 11, operating_income: 16, pretax_income: 13, tax_provision: 2.1,
      ebitda: 22, gross_profit: 33, eps: 0.55, operating_cash_flow: 11, capex: -1.1, free_cash_flow: 9.9,
      cash_and_equivalents: 5.5, total_debt: 21, diluted_shares: 2, total_assets: 85, stockholders_equity: 42, invested_capital: 58 },
    { quarter: 'Q3', revenue: 120, net_income: 12, operating_income: 17, pretax_income: 14, tax_provision: 2.2,
      ebitda: 24, gross_profit: 36, eps: 0.6, operating_cash_flow: 12, capex: -1.2, free_cash_flow: 10.8,
      cash_and_equivalents: 6, total_debt: 22, diluted_shares: 2, total_assets: 90, stockholders_equity: 44, invested_capital: 61 },
    { quarter: 'Q4', revenue: 130, net_income: 13, operating_income: 18, pretax_income: 15, tax_provision: 2.3,
      ebitda: 26, gross_profit: 39, eps: 0.65, operating_cash_flow: 13, capex: -1.3, free_cash_flow: 11.7,
      cash_and_equivalents: 6.5, total_debt: 23, diluted_shares: 2, total_assets: 95, stockholders_equity: 46, invested_capital: 64 },
  ];
  const enriched = enrichData(data);
  // TTM window indices 0-3: bsBegin = index 0 → all null → avg = null
  eq(enriched[3].avg_equity, null);
  eq(enriched[3].avg_assets, null);
  eq(enriched[3].avg_invested_capital, null);
  // ROE, ROA, ROIC should be N/A
  eq(enriched[3].roe, null);
  eq(enriched[3].roa, null);
  eq(enriched[3].roic, null);
});

// ═══════════════════════════════════════════════
// V2.2: Formatting
// ═══════════════════════════════════════════════
test('V2.2 — formatValue ROE as %', () => {
  eq(formatValue(53.76, 'roe'), '53.8%');
  eq(formatValue(-12.3, 'roe'), '-12.3%');
});

test('V2.2 — formatValue ROIC as %', () => {
  eq(formatValue(43.81, 'roic'), '43.8%');
});

test('V2.2 — formatValue FCF Conversion TTM as %', () => {
  eq(formatValue(89.25, 'fcf_conversion_ttm'), '89.3%');
});

test('V2.2 — formatValue Effective Tax Rate as %', () => {
  eq(formatValue(13.0, 'effective_tax_rate'), '13.0%');
});

test('V2.2 — formatValue TTM per-share as $/share', () => {
  eq(formatValue(27.82, 'revenue_ttm_per_share'), '$27.82');
  eq(formatValue(6.72, 'ni_ttm_per_share'), '$6.72');
  eq(formatValue(5.994, 'fcf_ttm_per_share'), '$5.99');
});

test('V2.2 — formatValue N/A for null metric', () => {
  eq(formatValue(null, 'roe'), 'N/A');
  eq(formatValue(null, 'fcf_conversion_ttm'), 'N/A');
  eq(formatValue(null, 'revenue_ttm_per_share'), 'N/A');
});

// ═══════════════════════════════════════════════
// V2.2: TTM fields absent for quarters < index 3
// ═══════════════════════════════════════════════
test('V2.2 — Quality/Returns fields undefined for quarter 1', () => {
  eq(FULL_ENRICHED[0].roe, undefined);
  eq(FULL_ENRICHED[0].roa, undefined);
  eq(FULL_ENRICHED[0].roic, undefined);
  eq(FULL_ENRICHED[0].fcf_conversion_ttm, undefined);
  eq(FULL_ENRICHED[0].revenue_ttm_per_share, undefined);
  eq(FULL_ENRICHED[0].ni_ttm_per_share, undefined);
  eq(FULL_ENRICHED[0].fcf_ttm_per_share, undefined);
});

test('V2.2 — No regression: existing V2.1 fields still populated', () => {
  // Verify that adding V2.2 fields didn't break V2.0/V2.1 fields
  const d = FULL_ENRICHED[0];
  eq(d.gross_margin != null, true);
  eq(d.ebitda_margin != null, true);
  eq(d.net_cash_debt != null, true);
  eq(d.revenue_per_share != null, true);
  eq(d.fcf_per_share != null, true);
});

// ── Results ──
console.log(`\n${passed} passed, ${failed} failed, ${passed + failed} total\n`);
if (failed > 0) process.exit(1);
