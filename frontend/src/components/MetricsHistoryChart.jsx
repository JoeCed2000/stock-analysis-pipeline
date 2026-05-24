import { useState, useEffect } from 'react';

const METRICS = [
  { key: 'revenue', label: 'Revenue', unit: '$B', axisLabel: 'Revenue ($B)' },
  { key: 'net_income', label: 'Net Income', unit: '$B', axisLabel: 'Net income ($B)' },
  { key: 'ebitda', label: 'EBITDA', unit: '$B', axisLabel: 'EBITDA ($B)' },
  { key: 'eps', label: 'EPS', unit: '$/share', axisLabel: 'EPS ($/share)' },
];

const CHART_COLORS = {
  revenue: '#238636',
  net_income: '#58a6ff',
  ebitda: '#d29922',
  eps: '#c44cb0',
};

const PERIOD_OPTIONS = [5, 8, 12];
const VIEW_MODES = [
  { key: 'absolute', label: 'Absolute' },
  { key: 'qoq', label: 'QoQ %' },
  { key: 'growth', label: '5Q Growth' },
];

function formatValue(val, metric) {
  if (val == null) return 'N/A';
  if (metric === 'eps') return `$${val.toFixed(2)}`;
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toFixed(0)}`;
}

function formatAxis(val, metric) {
  if (val == null) return '';
  if (metric === 'eps') return `$${val.toFixed(1)}`;
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `${val}`;
}

function formatQuarter(q) {
  const m = q.match(/^(\d{4})Q(\d)$/);
  if (!m) return q;
  return `Q${m[2]} FY${m[1].slice(2)}`;
}

function pctChange(curr, prev) {
  if (!prev || prev === 0) return null;
  return ((curr - prev) / Math.abs(prev)) * 100;
}

function fmtPct(v) {
  if (v == null) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

// Transform absolute values to view mode
function transformValues(sortedData, metricKey, viewMode) {
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

// ── Component ──

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

  // Trigger animation on metric change
  const changeMetric = (key) => {
    if (key !== metric) {
      setAnimating(true);
      setMetric(key);
      setTimeout(() => setAnimating(false), 350);
    }
  };

  if (loading) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>Loading metrics...</div>;
  }
  if (error) {
    return <div style={{ padding: 20, color: '#da3633', fontSize: 14 }}>⚠ {error}</div>;
  }
  if (!data || data.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>Not enough data</div>;
  }

  // Sort oldest → newest (API returns newest first)
  const allSorted = [...data].reverse();
  const maxAvailable = allSorted.length;
  const availablePeriods = PERIOD_OPTIONS.filter(p => p <= maxAvailable);
  const effectivePeriod = availablePeriods.includes(period) ? period : Math.max(...availablePeriods);

  // Slice to selected period
  const sorted = allSorted.slice(Math.max(0, allSorted.length - effectivePeriod));

  const metricInfo = METRICS.find(m => m.key === metric) || { label: metric, axisLabel: metric, unit: '' };

  // Transform values based on view mode
  const transformed = transformValues(sorted, metric, viewMode);
  const isPctView = viewMode !== 'absolute';

  // For percentage views, filter nulls
  const values = isPctView ? transformed.filter(v => v != null) : transformed;
  if (values.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>
      Not enough data for {viewMode !== 'absolute' ? `${VIEW_MODES.find(v => v.key === viewMode)?.label} view` : metricInfo.label}
    </div>;
  }

  const latest = sorted[sorted.length - 1];
  const previous = sorted[sorted.length - 2];
  const first = sorted[0];
  const lastIdx = transformed.length - 1;
  const latestVal = isPctView ? transformed[lastIdx] : latest[metric];
  const firstVal = isPctView ? null : first[metric];
  const qoq = isPctView ? null : pctChange(latest[metric], previous?.[metric]);
  const totalChange = !isPctView ? pctChange(latest[metric], firstVal) : null;
  const peak = Math.max(...values);
  const low = Math.min(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;

  const color = CHART_COLORS[metric] || '#238636';
  const trendColor = qoq != null && qoq >= 0 ? '#238636' : '#da3633';

  // ── Chart geometry ──
  const maxVal = Math.max(...values) * (isPctView ? 1.15 : 1.10);
  const minVal = isPctView ? Math.min(...values) * 1.2 : Math.min(...values) * 0.88;
  const range = maxVal - minVal || 1;
  const pad = { top: 16, right: 36, bottom: 44, left: 66 };
  const w = 620;
  const h = height;
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  const n = sorted.length;
  const points = sorted.map((d, i) => {
    const displayVal = transformed[i];
    if (displayVal == null) return null;
    const x = pad.left + (i / (n - 1)) * chartW;
    const y = pad.top + chartH - ((displayVal - minVal) / range) * chartH;
    return { ...d, x, y, i, displayVal };
  }).filter(Boolean);

  // Y ticks
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = minVal + (range * i) / 4;
    return { val, y: pad.top + chartH - ((val - minVal) / range) * chartH };
  });

  const avgY = pad.top + chartH - ((avg - minVal) / range) * chartH;
  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');

  // Format display value based on view mode
  const formatDisplay = (val) => {
    if (val == null) return 'N/A';
    if (isPctView) return fmtPct(val);
    return formatValue(val, metric);
  };

  const formatAxisDisplay = (val) => {
    if (isPctView) return `${val >= 0 ? '+' : ''}${val.toFixed(0)}%`;
    return formatAxis(val, metric);
  };

  // ── Labels ──
  const unitStr = metricInfo.unit === '$/share' ? 'USD/share' : 'USD billions';
  const growthLabel = `${effectivePeriod}Q Growth`;
  const periodLabel = `Last ${effectivePeriod} fiscal quarters`;

  // Mode context subtitle
  let modeSubtitle;
  if (isPctView && viewMode === 'qoq') {
    modeSubtitle = `Quarter-over-quarter · ${metricInfo.label}`;
  } else if (isPctView && viewMode === 'growth') {
    modeSubtitle = `Growth since ${formatQuarter(first.quarter)} · ${metricInfo.label}`;
  }

  // KPI labels based on view mode
  const kpiLabels = isPctView
    ? {
        latest: viewMode === 'qoq' ? 'Latest QoQ' : 'Current growth',
        peak: viewMode === 'qoq' ? 'Highest QoQ' : 'Peak growth',
        low: viewMode === 'qoq' ? 'Lowest QoQ' : 'Lowest growth',
        avg: 'Average',
      }
    : {
        latest: 'Latest',
        peak: 'Peak',
        low: 'Low',
        avg: 'Average',
      };

  // Footer labels
  const footerLowLabel = isPctView
    ? (viewMode === 'qoq' ? 'Lowest QoQ' : 'Lowest growth')
    : 'Low';
  const footerHighLabel = isPctView
    ? (viewMode === 'qoq' ? 'Highest QoQ' : 'Peak growth')
    : 'High';

  // Tooltip placement: if point is in top half of chart, place tooltip below it
  const tooltipPlacement = tooltip
    ? (tooltip.y < pad.top + chartH * 0.55 ? 'below' : 'above')
    : 'above';

  return (
    <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: 12 }}>
      {/* ── Header ── */}
      <div style={{ fontSize: 10, color: '#9ba3ae', marginBottom: 4 }}>
        {ticker} · {metricInfo.label} · Fiscal quarters · {unitStr}
      </div>

      {/* ── Mode context (QoQ / Growth) ── */}
      {modeSubtitle && (
        <div style={{ fontSize: 10, color: '#8b949e', marginBottom: 6, fontStyle: 'italic' }}>
          {modeSubtitle}
        </div>
      )}

      {/* ── KPI Summary Bar (always visible, adapted) ── */}
      <div style={{
        display: 'flex', gap: 20, flexWrap: 'wrap',
        padding: '10px 14px', marginBottom: 8,
        background: '#0d1117', borderRadius: 6,
        border: '1px solid #21262d',
      }}>
        {isPctView ? (
          <>
            <KpiBox label={kpiLabels.latest} value={fmtPct(latestVal)} color={color} bold />
            <KpiBox label={kpiLabels.peak} value={fmtPct(peak)} color={peak >= 0 ? '#238636' : '#da3633'} />
            <KpiBox label={kpiLabels.low} value={fmtPct(low)} color={low >= 0 ? '#238636' : '#da3633'} />
            <KpiBox label={kpiLabels.avg} value={fmtPct(avg)} color="#e1e4e8" />
          </>
        ) : (
          <>
            <KpiBox label={kpiLabels.latest} value={formatValue(latestVal, metric)} color={color} bold />
            <KpiBox label="QoQ" value={fmtPct(qoq)} color={trendColor} />
            <KpiBox label={growthLabel} value={fmtPct(totalChange)} color={totalChange >= 0 ? '#238636' : '#da3633'} />
            <KpiBox label={kpiLabels.peak} value={formatValue(peak, metric)} color="#e1e4e8" />
            <KpiBox label={kpiLabels.avg} value={formatValue(avg, metric)} color="#e1e4e8" />
          </>
        )}
      </div>

      {/* ── View Mode Toggle ── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 1, background: '#1c2128', borderRadius: 4, padding: 2, border: '1px solid #30363d' }}>
          {VIEW_MODES.map(v => (
            <button
              key={v.key}
              onClick={() => { setViewMode(v.key); setTooltip(null); }}
              style={{
                padding: '4px 10px', fontSize: 10, fontWeight: viewMode === v.key ? 600 : 400,
                border: 'none', borderRadius: 3,
                background: viewMode === v.key ? `${color}22` : 'transparent',
                color: viewMode === v.key ? color : '#8b949e',
                cursor: 'pointer', transition: 'all 0.2s',
              }}
            >
              {v.label}
            </button>
          ))}
        </div>

        {/* ── Period Selector ── */}
        <div style={{ display: 'flex', gap: 1, marginLeft: 'auto', background: '#1c2128', borderRadius: 4, padding: 2, border: '1px solid #30363d' }}>
          {PERIOD_OPTIONS.map(p => {
            const available = p <= maxAvailable;
            return (
              <button
                key={p}
                onClick={() => { if (available) { setPeriod(p); setTooltip(null); } }}
                disabled={!available}
                title={!available ? 'Not enough historical data' : `Show last ${p} quarters`}
                style={{
                  padding: '4px 8px', fontSize: 10, fontWeight: effectivePeriod === p ? 600 : 400,
                  border: 'none', borderRadius: 3,
                  background: effectivePeriod === p ? `${color}22` : 'transparent',
                  color: effectivePeriod === p ? color : available ? '#8b949e' : '#484f58',
                  cursor: available ? 'pointer' : 'not-allowed', transition: 'all 0.2s',
                  opacity: available ? 1 : 0.4,
                }}
              >
                {p}Q
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Metric Tabs ── */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 8 }}>
        {METRICS.map(m => (
          <button
            key={m.key}
            onClick={() => changeMetric(m.key)}
            style={{
              flex: 1, padding: '5px 0', fontSize: 11, fontWeight: metric === m.key ? 600 : 400,
              border: `1px solid ${metric === m.key ? CHART_COLORS[m.key] : '#3a4050'}`,
              borderRadius: 4,
              background: metric === m.key ? `${CHART_COLORS[m.key]}18` : '#161b22',
              color: metric === m.key ? CHART_COLORS[m.key] : '#c0c8d0',
              cursor: 'pointer', transition: 'all 0.25s',
            }}
            onMouseEnter={e => {
              if (metric !== m.key) {
                e.target.style.background = '#1c2128';
                e.target.style.color = '#d2d9e0';
              }
            }}
            onMouseLeave={e => {
              if (metric !== m.key) {
                e.target.style.background = '#161b22';
                e.target.style.color = '#c0c8d0';
              }
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* ── Chart ── */}
      <div style={{ position: 'relative' }}>
        <svg width={w} height={h} style={{ display: 'block', background: '#0d1117', borderRadius: '6px 6px 0 0' }}>
          {/* Y axis title */}
          <text x={12} y={pad.top + chartH / 2} fill="#9ba3ae" fontSize={10} fontWeight={500}
                textAnchor="middle" transform={`rotate(-90,12,${pad.top + chartH / 2})`}>
            {isPctView ? '% Change' : metricInfo.axisLabel}
          </text>

          {/* Vertical axis */}
          <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1} />

          {/* Grid + Y labels */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={pad.left} y1={t.y} x2={w - pad.right} y2={t.y} stroke="#21262d" strokeWidth={1} strokeDasharray="3 4" />
              <text x={pad.left - 8} y={t.y + 4} fill="#9ba3ae" textAnchor="end" fontSize={10}>{formatAxisDisplay(t.val)}</text>
            </g>
          ))}

          {/* Average reference line (absolute mode only) */}
          {!isPctView && (
            <>
              <line x1={pad.left} y1={avgY} x2={w - pad.right} y2={avgY} stroke="#d29922" strokeWidth={1} strokeDasharray="6 3" opacity={0.6} />
              <text x={w - pad.right - 4} y={avgY - 6} fill="#d29922" textAnchor="end" fontSize={9} opacity={0.85}>
                Average {formatValue(avg, metric)}
              </text>
            </>
          )}

          {/* Baseline */}
          <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1.5} />

          {/* X axis labels */}
          {points.map((p, i) => (
            <text key={i} x={p.x} y={h - pad.bottom + 16} fill="#9ba3ae" textAnchor="middle" fontSize={10}>
              {formatQuarter(p.quarter)}
            </text>
          ))}

          {/* Area fill — with animation */}
          <path d={`${pathD} L ${points[n-1]?.x.toFixed(1)} ${h - pad.bottom} L ${points[0]?.x.toFixed(1)} ${h - pad.bottom} Z`}
                fill={`${color}12`}
                style={{ transition: animating ? 'd 0.3s ease' : 'none' }} />

          {/* Line — with animation */}
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
            const isExtreme = p.displayVal === peak || p.displayVal === low;
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

        {/* ── Rich Tooltip (smart placement) ── */}
        {tooltip && (
          <div style={{
            position: 'absolute',
            left: Math.min(Math.max(tooltip.x, 130), w - 130),
            ...(tooltipPlacement === 'above'
              ? { bottom: h - tooltip.y + 12 }
              : { top: tooltip.y + 16 }),
            transform: 'translateX(-50%)',
            background: '#161b22', border: `1px solid ${color}44`,
            borderRadius: 8, padding: '8px 12px', color: '#c9d1d9',
            fontSize: 11, pointerEvents: 'none', zIndex: 10,
            whiteSpace: 'nowrap', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4, color }}>{formatQuarter(tooltip.quarter)}</div>
            <div style={{ color, fontWeight: 600, marginBottom: 3 }}>
              {isPctView ? fmtPct(tooltip.displayVal) : formatValue(tooltip.displayVal, metric)}
            </div>
            {!isPctView && tooltip.i > 0 && (
              <div style={{ color: '#9ba3ae', marginTop: 1 }}>
                QoQ: <span style={{ color: pctChange(tooltip[metric], sorted[tooltip.i - 1]?.[metric]) >= 0 ? '#238636' : '#da3633' }}>
                  {fmtPct(pctChange(tooltip[metric], sorted[tooltip.i - 1]?.[metric]))}
                </span>
              </div>
            )}
            {!isPctView && (
              <div style={{ color: '#9ba3ae', marginTop: 1 }}>
                {growthLabel}: <span style={{ color: pctChange(tooltip[metric], first[metric]) >= 0 ? '#238636' : '#da3633' }}>
                  {fmtPct(pctChange(tooltip[metric], first[metric]))}
                </span>
              </div>
            )}
            {!isPctView && (
              <div style={{ color: '#9ba3ae', marginTop: 1 }}>
                vs avg: <span style={{ color: tooltip[metric] >= avg ? '#238636' : '#da3633' }}>
                  {fmtPct(pctChange(tooltip[metric], avg))}
                </span>
              </div>
            )}
            {isPctView && tooltip.i > 0 && (
              <div style={{ color: '#9ba3ae', marginTop: 1 }}>
                Abs: <span style={{ color: '#e1e4e8' }}>{formatValue(tooltip[metric], metric)}</span>
              </div>
            )}
          </div>
        )}

        {/* ── Chart footer (2 levels) ── */}
        <div style={{
          background: '#0d1117', borderRadius: '0 0 6px 6px',
          borderTop: '1px solid #21262d', padding: '8px 14px 6px',
        }}>
          <div style={{
            display: 'flex', gap: 16, fontSize: 10, color: '#9ba3ae', marginBottom: 3,
          }}>
            <span>{footerLowLabel}: <b style={{ color: '#e1e4e8' }}>{formatDisplay(low)}</b></span>
            <span>{footerHighLabel}: <b style={{ color: '#e1e4e8' }}>{formatDisplay(peak)}</b></span>
            <span style={{ marginLeft: 'auto' }}>{periodLabel}</span>
          </div>
          <div style={{ fontSize: 9, color: '#6e7681', textAlign: 'right' }}>
            Source: SEC filings · Yahoo Finance · Updated May 2026
          </div>
        </div>
      </div>
    </div>
  );
}

// ── KPI Box ──
function KpiBox({ label, value, color, bold }) {
  return (
    <div style={{ minWidth: 80 }}>
      <div style={{ fontSize: 9, color: '#6e7681', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{
        fontSize: bold ? 15 : 13, fontWeight: bold ? 700 : 500,
        color, lineHeight: 1.2,
      }}>
        {value}
      </div>
    </div>
  );
}
