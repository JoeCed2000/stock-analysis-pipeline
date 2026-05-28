// chartUtils.js — Pure calculation & formatting functions for MetricsHistoryChart
// Zero React dependency — fully testable in isolation.

/**
 * Format a raw numeric value for display, adapting units per metric.
 * Revenue / Net Income / EBITDA / OCF / FCF / Capex / GP / OI → "$XB" (billions)
 * EPS → "$X.XX" (per share)
 * Margin / growth → "%"
 * Debt/EBITDA → "X.X×"
 * Shares → "XB"
 * Cash/Debt → "$XB"
 * null/undefined → "N/A"
 */
export function formatValue(val, metric) {
  if (val == null) return 'N/A';
  // Ratio-format metrics (Debt/EBITDA → '2.5×')
  if (METRIC_RATIO_KEYS.has(metric)) return `${val.toFixed(1)}×`;
  // Percentage-format metrics (margins, growth)
  if (METRIC_PCT_KEYS.has(metric) || metric.endsWith('_margin') || metric.endsWith('_growth')) {
    return `${val.toFixed(1)}%`;
  }
  if (metric === 'eps' || metric === 'eps_ttm') return `$${val.toFixed(2)}`;
  // Per-share metrics
  if (metric.endsWith('_per_share')) return `$${val.toFixed(2)}`;
  // Shares in billions
  if (metric === 'diluted_shares') {
    if (Math.abs(val) >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
    if (Math.abs(val) >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
    return `${val.toFixed(0)}`;
  }
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toFixed(0)}`;
}

/**
 * Format a value for Y-axis labels.
 */
export function formatAxis(val, metric) {
  if (val == null) return '';
  if (METRIC_PCT_KEYS.has(metric) || metric.endsWith('_margin')) return `${val.toFixed(0)}%`;
  if (metric === 'eps') return `$${val.toFixed(1)}`;
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `${val}`;
}

/**
 * Format a quarter string like "2025Q2" → "Q2 FY'25"
 */
export function formatQuarter(q) {
  const m = q.match(/^(\d{4})Q(\d)$/);
  if (!m) return q;
  return `Q${m[2]} FY'${m[1].slice(2)}`;
}

/**
 * Calculate percentage change: ((curr - prev) / |prev|) * 100
 * Returns null if prev is 0 or missing.
 */
export function pctChange(curr, prev) {
  if (!prev || prev === 0) return null;
  return ((curr - prev) / Math.abs(prev)) * 100;
}

/**
 * Format a percentage value: "+19.8%", "—" if null.
 */
export function fmtPct(v) {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

/**
 * Transform an array of absolute values into the selected view mode.
 * - 'absolute': return as-is
 * - 'qoq': each point is % change from previous (first = null)
 * - 'growth': % change from first quarter
 * - 'yoy': % change from same quarter 1 year ago (first 4 = null if enough data)
 */
export function transformValues(sortedData, metricKey, viewMode) {
  if (viewMode === 'absolute') {
    return sortedData.map(d => d[metricKey]);
  }
  if (viewMode === 'qoq') {
    return sortedData.map((d, i) => {
      if (i === 0) return null;
      return pctChange(d[metricKey], sortedData[i - 1]?.[metricKey]);
    });
  }
  if (viewMode === 'growth') {
    const base = sortedData[0]?.[metricKey];
    return sortedData.map(d => pctChange(d[metricKey], base));
  }
  if (viewMode === 'yoy') {
    return sortedData.map((d, i) => {
      if (i < 4) return null;
      return pctChange(d[metricKey], sortedData[i - 4]?.[metricKey]);
    });
  }
  return sortedData.map(d => d[metricKey]);
}

/**
 * Calculate statistics from an array of values.
 */
export function calculateStats(sortedData, metricKey, viewMode) {
  const transformed = transformValues(sortedData, metricKey, viewMode);
  const isPctView = viewMode !== 'absolute';
  const cleaned = transformed.map(v => (Number.isFinite(v) ? v : null));
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

  return {
    values, latest: latestVal, qoq, yoy, totalChange, peak, low, avg,
    isPctView, latestQuarter: latest, firstQuarter: first,
  };
}

// ── Pure helpers ──

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

function _safeDiv(num, den) {
  if (num == null || den == null || den === 0) return null;
  return num / den;
}

function _average(a, b) {
  if (a == null || b == null) return null;
  return (a + b) / 2;
}

// ── Metric Categories & Definitions ──

/**
 * Enrich raw quarterly data with computed metrics.
 * V2.0: margins, per-share
 * V2.1: TTM rolling sums, balance sheet, share count growth
 */
export function enrichData(sortedData) {
  // Pass 1: compute per-quarter derived fields
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

      // V2.2: Average balance sheet metrics (beginning + ending / 2)
      const bsBegin = sortedData[i - 3]; // 4 quarters ago
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

  // Pass 2: share count growth (relative to first quarter in displayed period)
  const sharesVals = pass1.map(d => d.diluted_shares).filter(v => v != null);
  if (sharesVals.length < 2) return pass1;

  const firstShares = sharesVals[0];
  return pass1.map(d => ({
    ...d,
    share_count_growth: d.diluted_shares != null ? pctChange(d.diluted_shares, firstShares) : null,
  }));
}

/**
 * Metric category definitions.
 */
export const METRIC_CATEGORIES = [
  {
    key: 'income_statement',
    label: 'Income Statement',
    metrics: [
      { key: 'revenue', label: 'Revenue', unit: '$B', source: 'revenue' },
      { key: 'gross_profit', label: 'Gross Profit', unit: '$B', source: 'gross_profit' },
      { key: 'operating_income', label: 'Operating Income', unit: '$B', source: 'operating_income' },
      { key: 'ebitda', label: 'EBITDA', unit: '$B', source: 'ebitda' },
      { key: 'net_income', label: 'Net Income', unit: '$B', source: 'net_income' },
      { key: 'eps', label: 'EPS', unit: '$/share', source: 'eps' },
    ],
  },
  {
    key: 'margins',
    label: 'Margins',
    metrics: [
      { key: 'gross_margin', label: 'Gross Margin', format: 'pct', source: 'gross_margin' },
      { key: 'ebitda_margin', label: 'EBITDA Margin', format: 'pct', source: 'ebitda_margin' },
      { key: 'operating_margin', label: 'Operating Margin', format: 'pct', source: 'operating_margin' },
      { key: 'net_margin', label: 'Net Margin', format: 'pct', source: 'net_margin' },
    ],
  },
  {
    key: 'cash_flow',
    label: 'Cash Flow',
    metrics: [
      { key: 'operating_cash_flow', label: 'Operating CF', unit: '$B', source: 'operating_cash_flow' },
      { key: 'capex', label: 'Capex', unit: '$B', source: 'capex' },
      { key: 'free_cash_flow', label: 'Free Cash Flow', unit: '$B', source: 'free_cash_flow' },
      { key: 'fcf_margin', label: 'FCF Margin', format: 'pct', source: 'fcf_margin' },
    ],
  },
  {
    key: 'balance_sheet',
    label: 'Balance Sheet',
    metrics: [
      { key: 'cash_and_equivalents', label: 'Cash & Equivalents', unit: '$B', source: 'cash_and_equivalents' },
      { key: 'total_debt', label: 'Total Debt', unit: '$B', source: 'total_debt' },
      { key: 'net_cash_debt', label: 'Net Cash / Debt', unit: '$B', source: 'net_cash_debt' },
      { key: 'debt_to_ebitda_ttm', label: 'Debt / EBITDA TTM', format: 'ratio', source: 'debt_to_ebitda_ttm' },
      { key: 'net_debt_to_ebitda_ttm', label: 'Net Debt / EBITDA TTM', format: 'ratio', source: 'net_debt_to_ebitda_ttm' },
    ],
  },
  {
    key: 'per_share',
    label: 'Per Share',
    metrics: [
      { key: 'eps', label: 'EPS', unit: '$/share', source: 'eps' },
      { key: 'diluted_shares', label: 'Diluted Avg Shares', unit: 'B shares', source: 'diluted_shares' },
      { key: 'share_count_growth', label: 'Share Count Growth', format: 'pct', source: 'share_count_growth' },
      { key: 'revenue_per_share', label: 'Revenue / Share', unit: '$/share', source: 'revenue_per_share' },
      { key: 'fcf_per_share', label: 'FCF / Share', unit: '$/share', source: 'fcf_per_share' },
    ],
  },
  {
    key: 'ttm_summary',
    label: 'TTM Summary',
    metrics: [
      { key: 'revenue_ttm', label: 'Revenue TTM', unit: '$B', source: 'revenue_ttm' },
      { key: 'ebitda_ttm', label: 'EBITDA TTM', unit: '$B', source: 'ebitda_ttm' },
      { key: 'net_income_ttm', label: 'Net Income TTM', unit: '$B', source: 'net_income_ttm' },
      { key: 'operating_cash_flow_ttm', label: 'Operating CF TTM', unit: '$B', source: 'operating_cash_flow_ttm' },
      { key: 'free_cash_flow_ttm', label: 'FCF TTM', unit: '$B', source: 'free_cash_flow_ttm' },
      { key: 'fcf_margin_ttm', label: 'FCF Margin TTM', format: 'pct', source: 'fcf_margin_ttm' },
      { key: 'eps_ttm', label: 'EPS TTM', unit: '$/share', source: 'eps_ttm' },
      { key: 'ebitda_margin_ttm', label: 'EBITDA Margin TTM', format: 'pct', source: 'ebitda_margin_ttm' },
    ],
  },
  {
    key: 'quality_returns',
    label: 'Quality / Returns',
    metrics: [
      { key: 'roe', label: 'ROE', format: 'pct', source: 'roe' },
      { key: 'roa', label: 'ROA', format: 'pct', source: 'roa' },
      { key: 'roic', label: 'ROIC', format: 'pct', source: 'roic' },
      { key: 'fcf_conversion_ttm', label: 'FCF Conversion TTM', format: 'pct', source: 'fcf_conversion_ttm' },
      { key: 'fcf_ttm_per_share', label: 'FCF TTM / Share', unit: '$/share', source: 'fcf_ttm_per_share' },
      { key: 'revenue_ttm_per_share', label: 'Revenue TTM / Share', unit: '$/share', source: 'revenue_ttm_per_share' },
      { key: 'ni_ttm_per_share', label: 'Net Income TTM / Share', unit: '$/share', source: 'ni_ttm_per_share' },
    ],
  },
];

// Format type sets
export const METRIC_PCT_KEYS = new Set([
  'gross_margin', 'ebitda_margin', 'operating_margin', 'net_margin', 'fcf_margin',
  'fcf_margin_ttm', 'ebitda_margin_ttm', 'net_margin_ttm',
  'share_count_growth', 'effective_tax_rate',
  'roe', 'roa', 'roic', 'fcf_conversion_ttm',
]);

export const METRIC_RATIO_KEYS = new Set([
  'debt_to_ebitda_ttm', 'net_debt_to_ebitda_ttm',
]);

// Legacy compatibility: flat metrics array
export const METRICS = METRIC_CATEGORIES.flatMap(c => c.metrics);

// All known metric keys (for availability checks)
const ALL_METRIC_KEYS = new Set(METRICS.map(m => m.key));

// Colors — extended for V2.1
export const CHART_COLORS = {
  // Income Statement
  revenue: '#238636', gross_profit: '#2ea043', operating_income: '#3fb950',
  net_income: '#58a6ff', ebitda: '#d29922', eps: '#c44cb0',
  // Margins
  gross_margin: '#7ee787', ebitda_margin: '#e3b341',
  operating_margin: '#56d364', net_margin: '#79c0ff',
  // Cash Flow
  operating_cash_flow: '#a5d6ff', capex: '#f85149',
  free_cash_flow: '#a371f7', fcf_margin: '#d2a8ff',
  // Balance Sheet
  cash_and_equivalents: '#3fb950', total_debt: '#f85149',
  net_cash_debt: '#d29922', debt_to_ebitda_ttm: '#f0883e',
  net_debt_to_ebitda_ttm: '#e5534b',
  // Per Share
  diluted_shares: '#8b949e', share_count_growth: '#58a6ff',
  revenue_per_share: '#7ee787', fcf_per_share: '#a371f7',
  // TTM
  revenue_ttm: '#238636', ebitda_ttm: '#d29922',
  net_income_ttm: '#58a6ff', operating_cash_flow_ttm: '#a5d6ff',
  free_cash_flow_ttm: '#a371f7', fcf_margin_ttm: '#d2a8ff',
  eps_ttm: '#c44cb0', ebitda_margin_ttm: '#e3b341',
  // Quality / Returns
  roe: '#3fb950', roa: '#7ee787', roic: '#56d364',
  fcf_conversion_ttm: '#d2a8ff',
  fcf_ttm_per_share: '#a371f7', revenue_ttm_per_share: '#7ee787',
  ni_ttm_per_share: '#79c0ff',
};

export const PERIOD_OPTIONS = [5, 8, 12];

export const VIEW_MODES = [
  { key: 'absolute', label: 'Absolute' },
  { key: 'qoq', label: 'QoQ %' },
  { key: 'growth', label: 'Growth' },
  { key: 'yoy', label: 'YoY %' },
];

/**
 * Get the unit string for displaying in headers.
 */
export function getMetricUnit(unit) {
  if (!unit) return '%';
  if (unit === '$/share') return 'USD/share';
  if (unit === 'B shares') return 'B shares';
  return 'USD billions';
}

/**
 * Get a metric definition by key.
 */
export function getMetricDefinition(key) {
  return METRICS.find(m => m.key === key);
}

/**
 * Get the metric label from key.
 */
export function getMetricLabel(key) {
  return getMetricDefinition(key)?.label || key;
}

/**
 * Get the metric category for a given key.
 */
export function getMetricCategory(key) {
  for (const cat of METRIC_CATEGORIES) {
    if (cat.metrics.some(m => m.key === key)) return cat;
  }
  return METRIC_CATEGORIES[0];
}

/**
 * Get the metric color from key.
 */
export function getMetricColor(key) {
  return CHART_COLORS[key] || '#238636';
}

/**
 * Check if a metric has enough data to display.
 */
export function metricIsAvailable(sortedData, metricKey) {
  if (!ALL_METRIC_KEYS.has(metricKey)) return false;
  if (sortedData.length < 2) return false;
  const values = sortedData.map(d => d[metricKey]).filter(v => v != null);
  return values.length >= 2;
}

/**
 * Get the default metric for a category (first metric with available data).
 */
export function getDefaultMetricForCategory(sortedData, categoryKey) {
  const cat = METRIC_CATEGORIES.find(c => c.key === categoryKey);
  if (!cat) return 'revenue';
  for (const m of cat.metrics) {
    if (metricIsAvailable(sortedData, m.key)) return m.key;
  }
  return cat.metrics[0].key;
}

/**
 * Get available categories (those with at least one available metric).
 */
export function getAvailableCategories(sortedData) {
  return METRIC_CATEGORIES.filter(cat =>
    cat.metrics.some(m => metricIsAvailable(sortedData, m.key))
  );
}

/**
 * Get contextual KPI labels based on view mode.
 */
export function getKpiLabels(viewMode) {
  if (viewMode === 'qoq') {
    return { latest: 'Latest QoQ', peak: 'Highest QoQ', low: 'Lowest QoQ', avg: 'Average' };
  }
  if (viewMode === 'growth') {
    return { latest: 'Current growth', peak: 'Peak growth', low: 'Lowest growth', avg: 'Average' };
  }
  if (viewMode === 'yoy') {
    return { latest: 'Latest YoY', peak: 'Highest YoY', low: 'Lowest YoY', avg: 'Average' };
  }
  return { latest: 'Latest', peak: 'Peak', low: 'Low', avg: 'Average' };
}

/**
 * Get contextual footer labels based on view mode.
 */
export function getFooterLabels(viewMode) {
  if (viewMode === 'qoq') return { low: 'Lowest QoQ', high: 'Highest QoQ' };
  if (viewMode === 'growth') return { low: 'Lowest growth', high: 'Peak growth' };
  if (viewMode === 'yoy') return { low: 'Lowest YoY', high: 'Highest YoY' };
  return { low: 'Low', high: 'High' };
}

/**
 * Get the mode context subtitle for QoQ / Growth / YoY views.
 */
export function getModeSubtitle(viewMode, firstQuarter, metricLabel) {
  if (viewMode === 'qoq') return `Quarter-over-quarter · ${metricLabel}`;
  if (viewMode === 'growth') return `Growth since ${formatQuarter(firstQuarter)} · ${metricLabel}`;
  if (viewMode === 'yoy') return `Year-over-year · ${metricLabel}`;
  return null;
}

/**
 * Check if YoY view mode is available (need >= 8 quarters of data).
 */
export function yoyIsAvailable(sortedData) {
  return sortedData.length >= 8;
}

// ── V2.1: Net Cash / Debt label ──
/**
 * Get the dynamic label for net_cash_debt based on its value.
 */
export function getNetCashDebtLabel(val) {
  if (val == null) return 'Net Cash / Debt';
  return val >= 0 ? 'Net Cash' : 'Net Debt';
}

// ═══════════════════════════════════════════
// V3: Valuation Group — Calculation functions
// ═══════════════════════════════════════════

/**
 * Enterprise Value = Market Cap + Total Debt - Cash & Equivalents
 */
export function calculateEnterpriseValue(marketCap, totalDebt, cashAndEquivalents) {
  if (marketCap == null) return null;
  const debt = totalDebt ?? 0;
  const cash = cashAndEquivalents ?? 0;
  return marketCap + debt - cash;
}

/**
 * P/E TTM = Price / EPS TTM
 */
export function calculatePeTtm(price, epsTtm) {
  if (price == null || epsTtm == null || epsTtm <= 0) return null;
  return price / epsTtm;
}

/**
 * P/S TTM = Market Cap / Revenue TTM
 */
export function calculatePsTtm(marketCap, revenueTtm) {
  if (marketCap == null || revenueTtm == null || revenueTtm <= 0) return null;
  return marketCap / revenueTtm;
}

/**
 * EV/Sales = Enterprise Value / Revenue TTM
 */
export function calculateEvSalesTtm(enterpriseValue, revenueTtm) {
  if (enterpriseValue == null || revenueTtm == null || revenueTtm <= 0) return null;
  return enterpriseValue / revenueTtm;
}

/**
 * EV/EBITDA = Enterprise Value / EBITDA TTM
 */
export function calculateEvEbitdaTtm(enterpriseValue, ebitdaTtm) {
  if (enterpriseValue == null || ebitdaTtm == null || ebitdaTtm <= 0) return null;
  return enterpriseValue / ebitdaTtm;
}

/**
 * P/FCF = Market Cap / Free Cash Flow TTM
 */
export function calculatePriceToFcfTtm(marketCap, fcfTtm) {
  if (marketCap == null || fcfTtm == null || fcfTtm <= 0) return null;
  return marketCap / fcfTtm;
}

/**
 * FCF Yield = FCF TTM / Market Cap × 100
 */
export function calculateFcfYield(fcfTtm, marketCap) {
  if (fcfTtm == null || marketCap == null || marketCap <= 0) return null;
  return (fcfTtm / marketCap) * 100;
}

// ═══════════════════════════════════════════
// V3: Valuation Group — Format functions
// ═══════════════════════════════════════════

/**
 * Format market cap to human-readable: $3.2T, €850B, $450M
 */
export function formatMarketCap(val, currency = 'USD') {
  if (val == null) return 'N/A';
  const sym = currency === 'EUR' ? '€' : '$';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `${sym}${(val / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `${sym}${(val / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sym}${(val / 1e6).toFixed(0)}M`;
  return `${sym}${val.toFixed(0)}`;
}

/**
 * Format enterprise value (same pattern as market cap)
 */
export function formatEnterpriseValue(val, currency = 'USD') {
  return formatMarketCap(val, currency);
}

/**
 * Format valuation multiple: 35.2x
 */
export function formatValuationMultiple(val) {
  if (val == null) return 'N/A';
  return `${val.toFixed(1)}×`;
}

/**
 * Format yield: 2.8%
 */
export function formatYield(val) {
  if (val == null) return 'N/A';
  return `${val.toFixed(1)}%`;
}

// ═══════════════════════════════════════════
// V3: Valuation Group — Status / Availability
// ═══════════════════════════════════════════

/**
 * Get valuation metric availability with freshness status.
 * Fresh: computed from data present in the latest quarter
 * Cached: computed from older data (>15 min since retrieval)
 * Stale: null/missing inputs
 */
export function getValuationAvailability(val, retrievedAt) {
  if (val == null) return { available: false, status: 'stale', label: 'N/A' };
  if (!retrievedAt) return { available: true, status: 'cached', label: '—' };
  const ageMin = (Date.now() - new Date(retrievedAt).getTime()) / 60000;
  if (isNaN(ageMin)) return { available: true, status: 'cached', label: '—' };
  if (ageMin < 15) return { available: true, status: 'fresh', label: '' };
  if (ageMin < 120) return { available: true, status: 'cached', label: '' };
  return { available: true, status: 'stale', label: '' };
}

/**
 * Get market data status label from retrieval timestamp.
 */
export function getMarketDataStatusLabel(retrievedAt) {
  if (!retrievedAt) return 'stale';
  const ageMin = (Date.now() - new Date(retrievedAt).getTime()) / 60000;
  if (isNaN(ageMin)) return 'stale';
  if (ageMin < 15) return 'fresh';
  if (ageMin < 120) return 'cached';
  return 'stale';
}

// ═══════════════════════════════════════════
// V3: Valuation Group — Metric definitions
// ═══════════════════════════════════════════

export const VALUATION_METRICS = [
  { key: 'market_cap',      label: 'Market Cap',    format: 'cap',         id: 'market_cap' },
  { key: 'enterprise_value', label: 'Enterprise Val', format: 'cap',       id: 'enterprise_value' },
  { key: 'pe_ttm',          label: 'P/E TTM',       format: 'multiple',   id: 'pe_ttm' },
  { key: 'ps_ttm',          label: 'P/S TTM',       format: 'multiple',   id: 'ps_ttm' },
  { key: 'ev_sales',        label: 'EV/Sales',      format: 'multiple',   id: 'ev_sales' },
  { key: 'ev_ebitda',       label: 'EV/EBITDA',     format: 'multiple',   id: 'ev_ebitda' },
  { key: 'p_fcf',           label: 'P/FCF',         format: 'multiple',   id: 'p_fcf' },
  { key: 'fcf_yield',       label: 'FCF Yield',     format: 'yield',      id: 'fcf_yield' },
];

/**
 * Compute all valuation metrics from the latest enriched quarterly data + market data.
 */
export function computeValuationMetrics(enrichedData, marketData) {
  if (!enrichedData || enrichedData.length === 0) return {};
  const latest = enrichedData[enrichedData.length - 1]; // oldest-first, latest at end

  const marketCap = marketData?.market_cap;
  const price = marketData?.price_native;
  const currency = marketData?.currency || 'USD';

  const revenueTtm = latest.revenue_ttm;
  const ebitdaTtm = latest.ebitda_ttm;
  const fcfTtm = latest.free_cash_flow_ttm;
  const epsTtm = latest.eps_ttm;
  const totalDebt = latest.total_debt;
  const cashAndEquivalents = latest.cash_and_equivalents;

  const ev = calculateEnterpriseValue(marketCap, totalDebt, cashAndEquivalents);

  return {
    market_cap: marketCap,
    enterprise_value: ev,
    pe_ttm: calculatePeTtm(price, epsTtm),
    ps_ttm: calculatePsTtm(marketCap, revenueTtm),
    ev_sales: calculateEvSalesTtm(ev, revenueTtm),
    ev_ebitda: calculateEvEbitdaTtm(ev, ebitdaTtm),
    p_fcf: calculatePriceToFcfTtm(marketCap, fcfTtm),
    fcf_yield: calculateFcfYield(fcfTtm, marketCap),
    currency,
    _latest: latest,
  };
}
