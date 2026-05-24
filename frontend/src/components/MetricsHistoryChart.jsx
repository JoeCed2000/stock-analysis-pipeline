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
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>Loading metrics history...</div>;
  }
  if (error) {
    return <div style={{ padding: 20, color: '#da3633', fontSize: 14 }}>⚠ {error}</div>;
  }
  if (!data || data.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>Not enough historical data for chart</div>;
  }

  // Sort oldest → newest for chart rendering
  const sorted = [...data].reverse();
  const values = sorted.map(d => d[metric]).filter(v => v != null);
  if (values.length < 2) {
    return <div style={{ padding: 20, color: '#8b949e', fontSize: 14 }}>
      Not enough data points for {METRICS.find(m => m.key === metric)?.label}
    </div>;
  }

  const maxVal = Math.max(...values) * 1.08;
  const minVal = Math.min(...values) * 0.95;
  const range = maxVal - minVal || 1;
  const color = CHART_COLORS[metric] || '#238636';

  // Chart dimensions
  const pad = { top: 12, right: 20, bottom: 46, left: 66 };
  const w = 600;
  const h = height;
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  // Data → points
  const n = sorted.length;
  const points = sorted.map((d, i) => {
    const x = pad.left + (i / (n - 1)) * chartW;
    const y = pad.top + chartH - ((d[metric] - minVal) / range) * chartH;
    return { ...d, x, y, i };
  });

  // Y axis ticks (5 ticks)
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = minVal + (range * i) / 4;
    return { val, y: pad.top + chartH - ((val - minVal) / range) * chartH };
  });

  // SVG path for line
  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');

  // Format quarter for display: "Q2 FY26"
  function formatQuarter(q) {
    // q = "2026Q2" → "Q2 FY26"
    const m = q.match(/^(\d{4})Q(\d)$/);
    if (!m) return q;
    return `Q${m[2]} FY'${m[1].slice(2)}`;
  }

  // Y axis label
  const yLabel = METRICS.find(m => m.key === metric)?.label || metric;

  return (
    <div style={{ position: 'relative', fontSize: 12, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Metric selector */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        {METRICS.map(m => (
          <button
            key={m.key}
            onClick={() => setMetric(m.key)}
            style={{
              padding: '4px 12px',
              border: `1px solid ${metric === m.key ? color : '#30363d'}`,
              borderRadius: 4,
              background: metric === m.key ? `${color}18` : 'transparent',
              color: metric === m.key ? color : '#8b949e',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: metric === m.key ? 600 : 400,
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Chart */}
      <svg width={w} height={h} style={{ display: 'block', background: '#0d1117', borderRadius: 6 }}>
        {/* Y axis title (rotated) */}
        <text
          x={14}
          y={pad.top + chartH / 2}
          fill="#8b949e"
          fontSize={11}
          fontWeight={500}
          textAnchor="middle"
          transform={`rotate(-90, 14, ${pad.top + chartH / 2})`}
        >
          {yLabel} (USD)
        </text>

        {/* Vertical axis line */}
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1} />

        {/* Grid lines + Y axis labels */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line
              x1={pad.left} y1={t.y} x2={w - pad.right} y2={t.y}
              stroke="#21262d" strokeWidth={1} strokeDasharray="4 3"
            />
            <text x={pad.left - 8} y={t.y + 4} fill="#8b949e" textAnchor="end" fontSize={11}>
              {formatAxis(t.val, metric)}
            </text>
          </g>
        ))}

        {/* Horizontal baseline */}
        <line x1={pad.left} y1={h - pad.bottom} x2={w - pad.right} y2={h - pad.bottom} stroke="#30363d" strokeWidth={1.5} />

        {/* X axis labels — two lines: quarter + year */}
        {points.map((p, i) => {
          const m = p.quarter.match(/^(\d{4})Q(\d)$/);
          const qLabel = m ? `Q${m[2]}` : p.quarter;
          const yrLabel = m ? `'${m[1].slice(2)}` : '';
          return (
            <g key={i}>
              <text
                x={p.x}
                y={h - pad.bottom + 15}
                fill="#8b949e"
                textAnchor="middle"
                fontSize={10}
                fontWeight={600}
              >
                {qLabel}
              </text>
              <text
                x={p.x}
                y={h - pad.bottom + 27}
                fill="#484f58"
                textAnchor="middle"
                fontSize={9}
              >
                {yrLabel}
              </text>
            </g>
          );
        })}

        {/* Filled area under line */}
        <path
          d={`${pathD} L ${points[n-1].x.toFixed(1)} ${h - pad.bottom} L ${points[0].x.toFixed(1)} ${h - pad.bottom} Z`}
          fill={`${color}15`}
        />

        {/* Line */}
        <path d={pathD} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" />

        {/* Data points */}
        {points.map((p, i) => (
          <g key={i}>
            <circle
              cx={p.x}
              cy={p.y}
              r={tooltip?.i === i ? 6 : 4}
              fill={tooltip?.i === i ? color : '#0d1117'}
              stroke={color}
              strokeWidth={2}
              style={{ cursor: 'pointer', transition: 'r 0.15s' }}
              onMouseEnter={() => setTooltip(p)}
              onMouseLeave={() => setTooltip(null)}
            />
            {/* Invisible larger hit area */}
            <circle
              cx={p.x} cy={p.y} r={12}
              fill="transparent"
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setTooltip(p)}
              onMouseLeave={() => setTooltip(null)}
            />
          </g>
        ))}
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: tooltip.x,
            top: tooltip.y - 50,
            transform: 'translateX(-50%)',
            background: '#161b22',
            border: '1px solid #30363d',
            borderRadius: 6,
            padding: '6px 10px',
            color: '#c9d1d9',
            fontSize: 12,
            pointerEvents: 'none',
            zIndex: 10,
            whiteSpace: 'nowrap',
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{tooltip.quarter}</div>
          <div style={{ color }}>{formatValue(tooltip[metric], metric)}</div>
        </div>
      )}
    </div>
  );
}
