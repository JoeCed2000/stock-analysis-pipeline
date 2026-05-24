import { useState, useEffect } from 'react';

const METRICS = [
  { key: 'revenue', label: 'Revenue' },
  { key: 'net_income', label: 'Net Income' },
  { key: 'ebitda', label: 'EBITDA' },
  { key: 'eps', label: 'EPS' },
];

const CHART_COLORS = {
  revenue: '#238636',
  net_income: '#58a6ff',
  ebitda: '#d29922',
  eps: '#c44cb0',
};

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

// ── Component ──

export default function MetricsHistoryChart({ ticker, height = 280 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metric, setMetric] = useState('revenue');
  const [tooltip, setTooltip] = useState(null);

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
  const sorted = [...data].reverse();
  const values = sorted.map(d => d[metric]).filter(v => v != null);
  if (values.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>
      Not enough data for {METRICS.find(m => m.key === metric)?.label}
    </div>;
  }

  const latest = sorted[sorted.length - 1];
  const previous = sorted[sorted.length - 2];
  const first = sorted[0];
  const latestVal = latest[metric];
  const prevVal = previous?.[metric];
  const firstVal = first[metric];
  const qoq = pctChange(latestVal, prevVal);
  const totalChange = pctChange(latestVal, firstVal);
  const peak = Math.max(...values);
  const low = Math.min(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;

  const color = CHART_COLORS[metric] || '#238636';
  const trendColor = qoq != null && qoq >= 0 ? '#238636' : '#da3633';

  // ── Chart geometry ──
  const maxVal = Math.max(...values) * 1.10;
  const minVal = Math.min(...values) * 0.88;
  const range = maxVal - minVal || 1;
  const pad = { top: 16, right: 24, bottom: 44, left: 66 };
  const w = 620;
  const h = height;
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  const n = sorted.length;
  const points = sorted.map((d, i) => {
    const x = pad.left + (i / (n - 1)) * chartW;
    const y = pad.top + chartH - ((d[metric] - minVal) / range) * chartH;
    return { ...d, x, y, i };
  });

  // Y ticks
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = minVal + (range * i) / 4;
    return { val, y: pad.top + chartH - ((val - minVal) / range) * chartH };
  });

  const avgY = pad.top + chartH - ((avg - minVal) / range) * chartH;
  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');

  return (
    <div style={{ fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: 12 }}>
      {/* ── KPI Summary Bar ── */}
      <div style={{
        display: 'flex', gap: 20, flexWrap: 'wrap',
        padding: '10px 14px', marginBottom: 8,
        background: '#0d1117', borderRadius: 6,
        border: '1px solid #21262d',
      }}>
        <KpiBox label="Latest" value={formatValue(latestVal, metric)} color={color} bold />
        <KpiBox label="QoQ" value={fmtPct(qoq)} color={trendColor} />
        <KpiBox label="5Q Change" value={fmtPct(totalChange)} color={totalChange >= 0 ? '#238636' : '#da3633'} />
        <KpiBox label="Peak" value={formatValue(peak, metric)} color="#8b949e" />
        <KpiBox label="Avg" value={formatValue(avg, metric)} color="#8b949e" />
      </div>

      {/* ── Metric Tabs ── */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 8 }}>
        {METRICS.map(m => (
          <button
            key={m.key}
            onClick={() => setMetric(m.key)}
            style={{
              flex: 1, padding: '5px 0', fontSize: 11, fontWeight: metric === m.key ? 600 : 400,
              border: `1px solid ${metric === m.key ? CHART_COLORS[m.key] : 'transparent'}`,
              borderRadius: 4,
              background: metric === m.key ? `${CHART_COLORS[m.key]}18` : '#161b22',
              color: metric === m.key ? CHART_COLORS[m.key] : '#8b949e',
              cursor: 'pointer', transition: 'all 0.2s',
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
          <text x={12} y={pad.top + chartH / 2} fill="#8b949e" fontSize={10} fontWeight={500}
                textAnchor="middle" transform={`rotate(-90,12,${pad.top + chartH / 2})`}>
            {METRICS.find(m => m.key === metric)?.label} {metric === 'eps' ? '(USD)' : '(USD B)'}
          </text>

          {/* Vertical axis */}
          <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1} />

          {/* Grid + Y labels */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line x1={pad.left} y1={t.y} x2={w - pad.right} y2={t.y} stroke="#21262d" strokeWidth={1} strokeDasharray="3 4" />
              <text x={pad.left - 8} y={t.y + 4} fill="#8b949e" textAnchor="end" fontSize={10}>{formatAxis(t.val, metric)}</text>
            </g>
          ))}

          {/* Average reference line */}
          <line x1={pad.left} y1={avgY} x2={w - pad.right} y2={avgY} stroke="#d29922" strokeWidth={1} strokeDasharray="6 3" opacity={0.6} />
          <text x={w - pad.right - 4} y={avgY - 6} fill="#d29922" textAnchor="end" fontSize={9} opacity={0.8}>
            avg {formatValue(avg, metric)}
          </text>

          {/* Baseline */}
          <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1.5} />

          {/* X axis labels — single line Q1 FY26 */}
          {points.map((p, i) => (
            <text key={i} x={p.x} y={h - pad.bottom + 16} fill="#8b949e" textAnchor="middle" fontSize={10}>
              {formatQuarter(p.quarter)}
            </text>
          ))}

          {/* Area fill */}
          <path d={`${pathD} L ${points[n-1].x.toFixed(1)} ${h - pad.bottom} L ${points[0].x.toFixed(1)} ${h - pad.bottom} Z`}
                fill={`${color}12`} />

          {/* Line */}
          <path d={pathD} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" />

          {/* Data points + value labels for latest & peak/low */}
          {points.map((p, i) => {
            const isLatest = i === n - 1;
            const isExtreme = p[metric] === peak || p[metric] === low;
            const showLabel = isLatest || (isExtreme && n <= 8);
            return (
              <g key={i}>
                <circle cx={p.x} cy={p.y}
                  r={tooltip?.i === i ? 6 : isLatest ? 5 : 3.5}
                  fill={tooltip?.i === i ? color : isLatest ? color : '#0d1117'}
                  stroke={color} strokeWidth={2}
                  style={{ cursor: 'pointer', transition: 'r 0.15s' }}
                  onMouseEnter={() => setTooltip(p)}
                  onMouseLeave={() => setTooltip(null)}
                />
                <circle cx={p.x} cy={p.y} r={12} fill="transparent" style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setTooltip(p)} onMouseLeave={() => setTooltip(null)} />
                {showLabel && (
                  <text x={p.x} y={p.y - 10} fill={color} textAnchor="middle" fontSize={10} fontWeight={700}>
                    {formatValue(p[metric], metric)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {/* ── Rich Tooltip ── */}
        {tooltip && (
          <div style={{
            position: 'absolute',
            left: Math.min(Math.max(tooltip.x, 120), w - 120),
            top: Math.max(tooltip.y - 90, 4),
            transform: 'translateX(-50%)',
            background: '#161b22', border: '1px solid #30363d',
            borderRadius: 8, padding: '8px 12px', color: '#c9d1d9',
            fontSize: 11, pointerEvents: 'none', zIndex: 10,
            whiteSpace: 'nowrap', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          }}>
            <div style={{ fontWeight: 600, marginBottom: 4, color }}>{formatQuarter(tooltip.quarter)}</div>
            <div style={{ color }}>{formatValue(tooltip[metric], metric)}</div>
            {tooltip.i > 0 && (
              <div style={{ color: '#8b949e', marginTop: 2 }}>
                QoQ: <span style={{ color: pctChange(tooltip[metric], sorted[tooltip.i - 1]?.[metric]) >= 0 ? '#238636' : '#da3633' }}>
                  {fmtPct(pctChange(tooltip[metric], sorted[tooltip.i - 1]?.[metric]))}
                </span>
              </div>
            )}
            <div style={{ color: '#8b949e', marginTop: 1 }}>
              vs avg: <span style={{ color: tooltip[metric] >= avg ? '#238636' : '#da3633' }}>
                {fmtPct(pctChange(tooltip[metric], avg))}
              </span>
            </div>
          </div>
        )}

        {/* ── Chart footer ── */}
        <div style={{
          background: '#0d1117', borderRadius: '0 0 6px 6px',
          borderTop: '1px solid #21262d', padding: '6px 14px',
          display: 'flex', gap: 16, fontSize: 10, color: '#8b949e',
        }}>
          <span>Peak: <b style={{ color: '#e1e4e8' }}>{formatValue(peak, metric)}</b></span>
          <span>Low: <b style={{ color: '#e1e4e8' }}>{formatValue(low, metric)}</b></span>
          <span>Avg: <b style={{ color: '#d29922' }}>{formatValue(avg, metric)}</b></span>
          <span style={{ marginLeft: 'auto' }}>5Q range</span>
        </div>
      </div>
    </div>
  );
}

// ── KPI Box ──
function KpiBox({ label, value, color, bold }) {
  return (
    <div style={{ minWidth: 80 }}>
      <div style={{ fontSize: 9, color: '#484f58', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>
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
