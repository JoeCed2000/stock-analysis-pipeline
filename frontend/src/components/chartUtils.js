// chartUtils.js — Pure calculation & formatting functions for MetricsHistoryChart
// Zero React dependency — fully testable in isolation.

/**
 * Format a raw numeric value for display, adapting units per metric.
 * Revenue / Net Income / EBITDA / OCF / FCF / Capex / GP / OI → "$XB" (billions)
 * EPS → "$X.XX" (per share)
 * Margin / ratio → "%"
 * Shares → "XB"
 * Cash/Debt → "$XB"
 * null/undefined → "N/A"
 */
export function formatValue(val, metric) {
  if (val == null) return 'N/A';
  // Percentage-format metrics (margins, ratios)
  if (METRIC_PCT_KEYS.has(metric) || metric.endsWith('_margin') || metric.endsWith('_ratio')) {
    return `${val >= 0 ? '' : ''}${val.toFixed(1)}%`;
  }
  if (metric === 'eps') return `$${val.toFixed(2)}`;
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
      if (i < 4) return null;  // no prior year data
      return pctChange(d[metricKey], sortedData[i - 4]?.[metricKey]);
    });
  }
  return sortedData.map(d => d[metricKey]);
}

/**
 * Calculate statistics from an array of values.
 * Returns { latest, qoq, yoy, totalChange, peak, low, avg, values, isPctView }
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

  // YoY: last vs 4 quarters back
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

// ── Metric Categories & Definitions ──

/**
 * Enrich raw quarterly data with computed metrics.
 * Adds: gross_margin, ebitda_margin, net_margin, operating_margin,
 *       fcf_margin, revenue_per_share, fcf_per_share
 */
export function enrichData(sortedData) {
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

function _ratio(num, den) {
  if (num == null || den == null || den === 0) return null;
  return (num / den) * 100;
}

function _perShare(val, shares) {
  if (val == null || shares == null || shares === 0) return null;
  return val / shares;
}

/**
 * Metric category definitions.
 * Each category has: key, label, metrics[]
 * Each metric has: key, label, unit? (for $B/$M etc), format? ('pct'), source? (raw field)
 * Computed metrics have: compute:true, num+den (already in enriched data, so source also works)
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
];

// Set of metric keys that are displayed as percentages
export const METRIC_PCT_KEYS = new Set([
  'gross_margin', 'ebitda_margin', 'operating_margin', 'net_margin', 'fcf_margin',
]);

// Legacy compatibility: flat metrics array
export const METRICS = METRIC_CATEGORIES.flatMap(c => c.metrics);

// All known metric keys (for availability checks)
const ALL_METRIC_KEYS = new Set(METRICS.map(m => m.key));

// V1 compatibility colors
export const CHART_COLORS = {
  revenue: '#238636',
  gross_profit: '#2ea043',
  operating_income: '#3fb950',
  net_income: '#58a6ff',
  ebitda: '#d29922',
  eps: '#c44cb0',
  gross_margin: '#7ee787',
  ebitda_margin: '#e3b341',
  operating_margin: '#56d364',
  net_margin: '#79c0ff',
  operating_cash_flow: '#a5d6ff',
  capex: '#f85149',
  free_cash_flow: '#a371f7',
  fcf_margin: '#d2a8ff',
};

export const PERIOD_OPTIONS = [5, 8, 12];

export const VIEW_MODES = [
  { key: 'absolute', label: 'Absolute' },
  { key: 'qoq', label: 'QoQ %' },
  { key: 'growth', label: '5Q Growth' },
  { key: 'yoy', label: 'YoY %' },
];

/**
 * Get the unit string for displaying in headers.
 */
export function getMetricUnit(unit) {
  if (!unit) return '%';
  return unit === '$/share' ? 'USD/share' : 'USD billions';
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
 * For source metrics: at least 2 non-null values in the data.
 * For computed metrics: both source fields are available.
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
