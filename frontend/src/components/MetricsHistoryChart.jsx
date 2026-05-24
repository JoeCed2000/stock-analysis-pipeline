import { useState, useEffect } from 'react';
import {
  METRICS, CHART_COLORS, PERIOD_OPTIONS,
  formatValue, formatAxis, formatQuarter, fmtPct,
  calculateStats, getMetricUnit, getKpiLabels, getFooterLabels, getModeSubtitle,
} from './chartUtils';
import {
  MetricKpiHeader, MetricModeToggle, PeriodSelector,
  MetricTabs, ChartTooltip, ChartFooter,
} from './chartComponents';

// ── Main Component ──

export default function MetricsHistoryChart({ ticker, height = 280 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metric, setMetric] = useState('revenue');
  const [tooltip, setTooltip] = useState(null);
  const [viewMode, setViewMode] = useState('absolute');
  const [period, setPeriod] = useState(5);
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

  const changeMetric = (key) => {
    if (key !== metric) {
      setAnimating(true);
      setMetric(key);
      setTimeout(() => setAnimating(false), 350);
    }
  };

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

  // ── Data preparation ──
  const allSorted = [...data].reverse();
  const maxAvailable = allSorted.length;
  const availablePeriods = PERIOD_OPTIONS.filter(p => p <= maxAvailable);
  const effectivePeriod = availablePeriods.includes(period) ? period : Math.max(...availablePeriods);
  const sorted = allSorted.slice(Math.max(0, allSorted.length - effectivePeriod));

  const metricInfo = METRICS.find(m => m.key === metric) || { label: metric, axisLabel: metric, unit: '' };
  const stats = calculateStats(sorted, metric, viewMode);

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
  const unitStr = getMetricUnit(metricInfo.unit);
  const growthLabel = `${effectivePeriod}Q Growth`;
  const periodLabel = `Last ${effectivePeriod} fiscal quarters`;
  const modeSubtitle = getModeSubtitle(viewMode, stats.firstQuarter?.quarter, metricInfo.label);

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

  return (
    <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: 12 }}>
      {/* Header */}
      <div style={{ fontSize: 10, color: '#9ba3ae', marginBottom: 4 }}>
        {ticker} · {metricInfo.label} · Fiscal quarters · {unitStr}
      </div>

      {/* Mode context */}
      {modeSubtitle && (
        <div style={{ fontSize: 10, color: '#8b949e', marginBottom: 6, fontStyle: 'italic' }}>
          {modeSubtitle}
        </div>
      )}

      {/* KPIs */}
      <MetricKpiHeader stats={stats} metric={metric} viewMode={viewMode} color={color} effectivePeriod={effectivePeriod} />

      {/* Controls row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
        <MetricModeToggle viewMode={viewMode} onChange={(v) => { setViewMode(v); setTooltip(null); }} color={color} effectivePeriod={effectivePeriod} />
        <PeriodSelector period={period} effectivePeriod={effectivePeriod} maxAvailable={maxAvailable} onChange={(p) => { setPeriod(p); setTooltip(null); }} color={color} />
      </div>

      {/* Metric tabs */}
      <MetricTabs metric={metric} onChange={changeMetric} />

      {/* Chart */}
      <div style={{ position: 'relative' }}>
        <svg width={w} height={h} style={{ display: 'block', background: '#0d1117', borderRadius: '6px 6px 0 0' }}>
          {/* Y axis title */}
          <text x={12} y={pad.top + chartH / 2} fill="#9ba3ae" fontSize={10} fontWeight={500}
                textAnchor="middle" transform={`rotate(-90,12,${pad.top + chartH / 2})`}>
            {isPctView ? '% Change' : metricInfo.axisLabel}
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
          {!isPctView && (
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
          tooltip={tooltip} metric={metric} metricKey={metric}
          sorted={sorted} firstQuarter={stats.firstQuarter || sorted[0]}
          avg={stats.avg} avgDisplay={formatValue(stats.avg, metric)}
          growthLabel={growthLabel} color={color}
          isPctView={isPctView} viewMode={viewMode}
          w={w} h={h} pad={pad}
        />

        {/* Footer */}
        <ChartFooter
          low={stats.low} peak={stats.peak}
          periodLabel={periodLabel} footerLabels={footerLabels}
          isPctView={isPctView} metric={metric}
        />
      </div>
    </div>
  );
}
