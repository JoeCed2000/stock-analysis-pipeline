// chartUtils.js — Pure calculation & formatting functions for MetricsHistoryChart
// Zero React dependency — fully testable in isolation.

/**
 * Format a raw numeric value for display, adapting units per metric.
 * Revenue / Net Income / EBITDA → "$XB" (billions)
 * EPS → "$X.XX" (per share)
 * null/undefined → "N/A"
 */
export function formatValue(val, metric) {
  if (val == null) return 'N/A';
  if (metric === 'eps') return `$${val.toFixed(2)}`;
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toFixed(0)}`;
}

/**
 * Format a value for Y-axis labels.
 */
export function formatAxis(val, metric) {
  if (val == null) return '';
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
 * - 'qoq': each point is % change from previous (first point = null)
 * - 'growth': each point is % change from first quarter
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
  return sortedData.map(d => d[metricKey]);
}

/**
 * Calculate statistics from an array of values.
 * Returns { latest, qoq, totalChange, peak, low, avg, values }
 */
export function calculateStats(sortedData, metricKey, viewMode) {
  const transformed = transformValues(sortedData, metricKey, viewMode);
  const isPctView = viewMode !== 'absolute';
  const values = isPctView ? transformed.filter(v => v != null) : transformed;

  if (values.length < 2) {
    return { values, latest: null, qoq: null, totalChange: null, peak: null, low: null, avg: null, isPctView };
  }

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

/**
 * Metric definitions with labels, units, axis labels, and colors.
 */
export const METRICS = [
  { key: 'revenue', label: 'Revenue', unit: '$B', axisLabel: 'Revenue ($B)' },
  { key: 'net_income', label: 'Net Income', unit: '$B', axisLabel: 'Net income ($B)' },
  { key: 'ebitda', label: 'EBITDA', unit: '$B', axisLabel: 'EBITDA ($B)' },
  { key: 'eps', label: 'EPS', unit: '$/share', axisLabel: 'EPS ($/share)' },
];

export const CHART_COLORS = {
  revenue: '#238636',
  net_income: '#58a6ff',
  ebitda: '#d29922',
  eps: '#c44cb0',
};

export const PERIOD_OPTIONS = [5, 8, 12];

export const VIEW_MODES = [
  { key: 'absolute', label: 'Absolute' },
  { key: 'qoq', label: 'QoQ %' },
  { key: 'growth', label: '5Q Growth' },
];

/**
 * Get the unit string for displaying in headers.
 */
export function getMetricUnit(unit) {
  return unit === '$/share' ? 'USD/share' : 'USD billions';
}

/**
 * Get the metric label from key.
 */
export function getMetricLabel(key) {
  return METRICS.find(m => m.key === key)?.label || key;
}

/**
 * Get the metric color from key.
 */
export function getMetricColor(key) {
  return CHART_COLORS[key] || '#238636';
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
  return { latest: 'Latest', peak: 'Peak', low: 'Low', avg: 'Average' };
}

/**
 * Get contextual footer labels based on view mode.
 */
export function getFooterLabels(viewMode) {
  if (viewMode === 'qoq') return { low: 'Lowest QoQ', high: 'Highest QoQ' };
  if (viewMode === 'growth') return { low: 'Lowest growth', high: 'Peak growth' };
  return { low: 'Low', high: 'High' };
}

/**
 * Get the mode context subtitle for QoQ / Growth views.
 */
export function getModeSubtitle(viewMode, firstQuarter, metricLabel) {
  if (viewMode === 'qoq') return `Quarter-over-quarter · ${metricLabel}`;
  if (viewMode === 'growth') return `Growth since ${formatQuarter(firstQuarter)} · ${metricLabel}`;
  return null;
}
