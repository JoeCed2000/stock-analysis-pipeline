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
  const values = isPctView ? transformed.filter(v => v != null) : transformed;

  if (values.length < 2) {
    return { values, latest: null, qoq: null, yoy: null, totalChange: null, peak: null, low: null, avg: null, isPctView };
  }

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
];

// Format type sets
export const METRIC_PCT_KEYS = new Set([
  'gross_margin', 'ebitda_margin', 'operating_margin', 'net_margin', 'fcf_margin',
  'fcf_margin_ttm', 'ebitda_margin_ttm', 'net_margin_ttm',
  'share_count_growth',
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
