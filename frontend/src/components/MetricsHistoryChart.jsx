import { useState, useEffect, useMemo } from 'react';
import {
  METRIC_CATEGORIES, CHART_COLORS, PERIOD_OPTIONS,
  formatValue, formatAxis, formatQuarter, fmtPct,
  calculateStats, enrichData, getMetricUnit, getKpiLabels, getFooterLabels, getModeSubtitle,
  getMetricDefinition, getMetricLabel, getMetricColor, metricIsAvailable,
  getAvailableCategories, getDefaultMetricForCategory, yoyIsAvailable,
} from './chartUtils';
import {
  MetricKpiHeader, MetricModeToggle, PeriodSelector,
  CategorySelector, MetricTabs, ChartTooltip, ChartFooter,
} from './chartComponents';

// ── Main Component ──

export default function MetricsHistoryChart({ ticker, height = 280 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [categoryKey, setCategoryKey] = useState('income_statement');
  const [metric, setMetric] = useState('revenue');
  const [tooltip, setTooltip] = useState(null);
  const [viewMode, setViewMode] = useState('absolute');
  const [period, setPeriod] = useState(12);  // V2: 12Q default
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    fetch(`/stock-analysis/api/metrics-history/${ticker}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) setError(d.error);
        else setData(d.quarters || []);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [ticker]);

  // ── Normalize chronology first, then enrich ──
  // API returns newest-first. Enrichment (TTM windows, rolling metrics) must run
  // on oldest→newest order to avoid null tails on latest rendered points.
  const allSorted = useMemo(() => {
    if (!data || data.length < 2) return [];
    const chronological = [...data].reverse();
    return enrichData(chronological);
  }, [data]);

  const maxAvailable = allSorted.length;

  // Available categories based on data
  const categories = useMemo(() => {
    if (!allSorted.length) return [];
    return getAvailableCategories(allSorted);
  }, [allSorted]);

  // Effective period: prefer requested, fallback to max available
  const effectivePeriod = useMemo(() => {
    const available = PERIOD_OPTIONS.filter(p => p <= maxAvailable);
    return available.includes(period) ? period : Math.max(...available);
  }, [period, maxAvailable]);

  // Validate category is available
  useEffect(() => {
    if (categories.length && !categories.some(c => c.key === categoryKey)) {
      setCategoryKey(categories[0].key);
    }
  }, [categories, categoryKey]);

  // Validate metric is in current category and available
  useEffect(() => {
    const cat = METRIC_CATEGORIES.find(c => c.key === categoryKey);
    if (cat) {
      const inCategory = cat.metrics.some(m => m.key === metric);
      const available = metricIsAvailable(allSorted, metric);
      if (!inCategory || !available) {
        const def = getDefaultMetricForCategory(allSorted, categoryKey);
        setMetric(def);
      }
    }
  }, [categoryKey, allSorted, metric]);

  const sorted = allSorted.slice(Math.max(0, allSorted.length - effectivePeriod));

  const metricInfo = getMetricDefinition(metric) || { label: metric, unit: '' };
  const stats = calculateStats(sorted, metric, viewMode);

  // ── Early returns ──
  if (loading) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>Loading metrics...</div>;
  }
  if (error) {
    return <div style={{ padding: 20, color: '#da3633', fontSize: 14 }}>⚠ {error}</div>;
  }
  if (!data || data.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>Not enough data</div>;
  }
  if (!categories.length) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>No metrics available for {ticker}</div>;
  }
  if (stats.values.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>
      Not enough data for {viewMode !== 'absolute' ? `${viewMode} view` : metricInfo.label}
    </div>;
  }

  // ── Derived values ──
  const color = CHART_COLORS[metric] || '#238636';
  const isPctView = viewMode !== 'absolute';
  const kpiLabels = getKpiLabels(viewMode);
  const footerLabels = getFooterLabels(viewMode);
  const unitStr = metric === 'eps' ? 'USD/share' : (metricInfo.unit || '%');
  const growthLabel = `${effectivePeriod}Q Growth`;
  const periodLabel = `Last ${effectivePeriod} fiscal quarters`;
  const modeSubtitle = getModeSubtitle(viewMode, stats.firstQuarter?.quarter, metricInfo.label);
  const yoyAvail = yoyIsAvailable(sorted);

  // ── Chart geometry ──
  const maxVal = Math.max(...stats.values) * (isPctView ? 1.15 : 1.10);
  const minVal = isPctView ? Math.min(...stats.values) * 1.2 : Math.min(...stats.values) * 0.88;
  const range = maxVal - minVal || 1;
  const pad = { top: 16, right: 36, bottom: 44, left: 66 };
  const w = 620;
  const h = height;
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  const n = sorted.length;
  const transformed = (() => {
    if (viewMode === 'absolute') return sorted.map(d => d[metric]);
    if (viewMode === 'qoq') return sorted.map((d, i) => i === 0 ? null : ((d[metric] - sorted[i - 1][metric]) / Math.abs(sorted[i - 1][metric])) * 100);
    if (viewMode === 'yoy') return sorted.map((d, i) => i < 4 ? null : ((d[metric] - sorted[i - 4][metric]) / Math.abs(sorted[i - 4][metric])) * 100);
    // growth
    const base = sorted[0][metric];
    return sorted.map(d => base ? ((d[metric] - base) / Math.abs(base)) * 100 : null);
  })();

  const points = sorted.map((d, i) => {
    const displayVal = transformed[i];
    if (displayVal == null) return null;
    const x = pad.left + (i / (n - 1)) * chartW;
    const y = pad.top + chartH - ((displayVal - minVal) / range) * chartH;
    return { ...d, x, y, i, displayVal };
  }).filter(Boolean);

  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = minVal + (range * i) / 4;
    return { val, y: pad.top + chartH - ((val - minVal) / range) * chartH };
  });

  const avgY = pad.top + chartH - ((stats.avg - minVal) / range) * chartH;
  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');

  const formatDisplay = (val) => {
    if (val == null) return 'N/A';
    if (isPctView) return fmtPct(val);
    return formatValue(val, metric);
  };

  const formatAxisDisplay = (val) => {
    if (isPctView) return `${val >= 0 ? '+' : ''}${val.toFixed(0)}%`;
    if (metric === 'eps') return `$${val.toFixed(1)}`;
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
    return `${val}`;
  };

  const activeCategory = METRIC_CATEGORIES.find(c => c.key === categoryKey);

  return (
    <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: 12 }}>
      {/* Header */}
      <div style={{ fontSize: 10, color: '#9ba3ae', marginBottom: 4 }}>
        {ticker} · {metricInfo.label} · {activeCategory?.label} · {typeof unitStr === 'string' ? unitStr : unitStr}
      </div>

      {/* Mode context */}
      {modeSubtitle && (
        <div style={{ fontSize: 10, color: '#8b949e', marginBottom: 6, fontStyle: 'italic' }}>
          {modeSubtitle}
        </div>
      )}

      {/* KPIs */}
      <MetricKpiHeader stats={stats} metric={metric} viewMode={viewMode} color={color} effectivePeriod={effectivePeriod} />

      {/* Category selector — first level navigation */}
      {categories.length > 1 && (
        <CategorySelector
          categories={categories}
          activeCategory={categoryKey}
          onChange={(k) => { setCategoryKey(k); setTooltip(null); }}
          color={color}
        />
      )}

      {/* Controls row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
        <MetricModeToggle
          viewMode={viewMode}
          onChange={(v) => { setViewMode(v); setTooltip(null); }}
          color={color}
          effectivePeriod={effectivePeriod}
          yoyAvailable={yoyAvail}
        />
        <PeriodSelector
          period={period}
          effectivePeriod={effectivePeriod}
          maxAvailable={maxAvailable}
          onChange={(p) => { setPeriod(p); setTooltip(null); }}
          color={color}
        />
      </div>

      {/* Metric tabs within current category */}
      <MetricTabs
        category={activeCategory}
        metric={metric}
        onChange={(m) => { setMetric(m); setTooltip(null); }}
        sortedData={allSorted}
      />

      {/* Chart */}
      <div style={{ position: 'relative' }}>
        <svg width={w} height={h} style={{ display: 'block', background: '#0d1117', borderRadius: '6px 6px 0 0' }}>
          {/* Y axis title */}
          <text x={12} y={pad.top + chartH / 2} fill="#9ba3ae" fontSize={10} fontWeight={500}
                textAnchor="middle" transform={`rotate(-90,12,${pad.top + chartH / 2})`}>
            {isPctView ? '% Change' : (metricInfo.axisLabel || metricInfo.label)}
          </text>

          <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1} />

          {/* Grid */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={pad.left} y1={t.y} x2={w - pad.right} y2={t.y} stroke="#21262d" strokeWidth={1} strokeDasharray="3 4" />
              <text x={pad.left - 8} y={t.y + 4} fill="#9ba3ae" textAnchor="end" fontSize={10}>{formatAxisDisplay(t.val)}</text>
            </g>
          ))}

          {/* Average line */}
          {!isPctView && stats.avg != null && (
            <>
              <line x1={pad.left} y1={avgY} x2={w - pad.right} y2={avgY} stroke="#d29922" strokeWidth={1} strokeDasharray="6 3" opacity={0.6} />
              <text x={w - pad.right - 4} y={avgY - 6} fill="#d29922" textAnchor="end" fontSize={9} opacity={0.85}>
                Average {formatValue(stats.avg, metric)}
              </text>
            </>
          )}

          {/* Baseline */}
          <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1.5} />

          {/* X labels */}
          {points.map((p, i) => (
            <text key={i} x={p.x} y={h - pad.bottom + 16} fill="#9ba3ae" textAnchor="middle" fontSize={10}>
              {formatQuarter(p.quarter)}
            </text>
          ))}

          {/* Area + Line */}
          <path d={`${pathD} L ${points[n-1]?.x.toFixed(1)} ${h - pad.bottom} L ${points[0]?.x.toFixed(1)} ${h - pad.bottom} Z`}
                fill={`${color}12`}
                style={{ transition: animating ? 'd 0.3s ease' : 'none' }} />
          <path d={pathD} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round"
                style={{ transition: animating ? 'd 0.3s ease' : 'none' }} />

          {/* Crosshair */}
          {tooltip && (
            <line x1={tooltip.x} y1={pad.top} x2={tooltip.x} y2={h - pad.bottom}
                  stroke="#6e7681" strokeWidth={1} strokeDasharray="2 3" opacity={0.5} />
          )}

          {/* Data points */}
          {points.map((p, i) => {
            const isLatest = i === (points.length - 1);
            const isExtreme = p.displayVal === stats.peak || p.displayVal === stats.low;
            const showLabel = isLatest || (tooltip?.i === i) || (isExtreme && points.length <= 8);
            const isHovered = tooltip?.i === i;
            return (
              <g key={i}>
                <circle cx={p.x} cy={p.y}
                  r={isHovered ? 6 : isLatest ? 5 : 3.5}
                  fill={isHovered ? color : isLatest ? color : '#0d1117'}
                  stroke={color} strokeWidth={isHovered ? 2.5 : 2}
                  style={{ cursor: 'pointer', transition: 'r 0.15s, stroke-width 0.15s' }}
                  onMouseEnter={() => setTooltip(p)}
                  onMouseLeave={() => setTooltip(null)}
                />
                <circle cx={p.x} cy={p.y} r={14} fill="transparent" style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setTooltip(p)} onMouseLeave={() => setTooltip(null)} />
                {showLabel && (
                  <text x={isLatest ? p.x - (metric === 'eps' ? 22 : 28) : p.x}
                        y={p.y - 10} fill={color} textAnchor="middle" fontSize={10} fontWeight={700}>
                    {formatDisplay(p.displayVal)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {/* Tooltip */}
        <ChartTooltip
          tooltip={tooltip}
          metricKey={metric}
          sorted={sorted}
          firstQuarter={stats.firstQuarter || sorted[0]}
          avg={stats.avg}
          avgDisplay={formatValue(stats.avg, metric)}
          growthLabel={growthLabel}
          color={color}
          isPctView={isPctView}
          viewMode={viewMode}
          w={w} h={h} pad={pad}
        />

        {/* Footer */}
        <ChartFooter
          low={stats.low} peak={stats.peak}
          periodLabel={periodLabel}
          footerLabels={footerLabels}
          isPctView={isPctView}
          metric={metric}
        />
      </div>
      {/* Available quarters summary */}
      <div style={{ fontSize: 9, color: '#484f58', marginTop: 4, textAlign: 'right' }}>
        {maxAvailable} quarters available · Default: 12Q · Fallback: 8Q → 5Q
      </div>
    </div>
  );
}
