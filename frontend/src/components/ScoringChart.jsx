import { useState } from 'react';

const CRITERIA = [
  { key: 'financial_health', label: 'Financial', max: 10 },
  { key: 'growth', label: 'Growth', max: 10 },
  { key: 'valuation', label: 'Value', max: 8 },
  { key: 'management', label: 'Mgmt', max: 5 },
  { key: 'moat', label: 'Moat', max: 4 },
  { key: 'sentiment', label: 'Sentiment', max: 3 },
];

const DESCRIPTIONS = {
  financial_health: 'Profitability, margins & balance sheet strength',
  growth: 'Revenue growth, business momentum & catalysts',
  valuation: 'Price vs intrinsic value assessment',
  management: 'Leadership quality & capital allocation',
  moat: 'Competitive advantage durability',
  sentiment: 'Geopolitical, regulatory & macro exposure',
};

function barColor(score, max) {
  const pct = score / max;
  if (pct >= 0.8) return '#34d399';
  if (pct >= 0.5) return '#d29922';
  return '#f85149';
}

export default function ScoringChart({ scoring, height = 120 }) {
  const [tooltip, setTooltip] = useState(null);
  if (!scoring) return null;

  const total = scoring.total || 0;
  const barW = 22;
  const gap = 10;
  const chartW = CRITERIA.length * (barW + gap);
  const labelH = 28;
  const chartH = height;
  const topPad = 12;   // room for the value label above a full-height bar
  const sidePad = 10;  // room for the first/last category labels

  return (
    <div style={{ position: 'relative' }}>
      {/* Title */}
      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        Scoring Breakdown
      </div>

      <svg
        viewBox={`0 0 ${chartW + sidePad * 2} ${chartH + labelH + topPad}`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        style={{ display: 'block' }}
      >
        <g transform={`translate(${sidePad}, ${topPad})`}>
        {/* Grid lines: percentage-based (25%, 50%, 75%) */}
        {[0.25, 0.5, 0.75].map(pct => (
          <line
            key={pct}
            x1={0} y1={chartH - pct * chartH}
            x2={chartW} y2={chartH - pct * chartH}
            stroke="rgba(125,155,195,0.12)" strokeWidth={0.5}
          />
        ))}
        {/* Bars */}
        {CRITERIA.map((c, i) => {
          const val = scoring[c.key] || 0;
          const pct = val / c.max;
          const barH = Math.max(pct * chartH, val > 0 ? 4 : 0);
          const x = i * (barW + gap);
          const y = chartH - barH;
          const color = barColor(val, c.max);
          return (
            <g key={c.key}>
              {/* Bar */}
              <rect
                x={x} y={y} width={barW} height={barH}
                fill={color} fillOpacity={0.9} rx={3}
                style={{
                  transition: 'height 0.4s ease',
                  filter: `drop-shadow(0 0 5px ${color}55)`,
                  animation: `barGrow 0.7s cubic-bezier(0.3, 0.7, 0.3, 1) ${i * 0.07}s both`,
                  transformOrigin: `${x + barW / 2 + sidePad}px ${chartH + topPad}px`,
                }}
                onMouseEnter={(e) => {
                  const rect = e.target.getBoundingClientRect();
                  setTooltip({
                    key: c.key, label: c.label, val, max: c.max,
                    desc: DESCRIPTIONS[c.key],
                    x: rect.left + rect.width / 2,
                    y: rect.top,
                  });
                  e.target.style.filter = `brightness(1.3) drop-shadow(0 0 8px ${color}88)`;
                }}
                onMouseLeave={(e) => {
                  setTooltip(null);
                  e.target.style.filter = `drop-shadow(0 0 5px ${color}55)`;
                }}
              />
              {/* Score on top of bar */}
              <text
                x={x + barW / 2} y={y - 4}
                textAnchor="middle" fill="var(--ink)" fontSize={8} fontWeight={600}
              >
                {val}
              </text>
              {/* Label below */}
              <text
                x={x + barW / 2} y={chartH + 14}
                textAnchor="middle" fill="var(--muted)" fontSize={7}
              >
                {c.label}
              </text>
            </g>
          );
        })}
        </g>
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x,
          top: tooltip.y - 48,
          transform: 'translate(-50%, -100%)',
          background: 'rgba(11,18,33,0.92)', border: '1px solid rgba(125,155,195,0.3)',
          borderRadius: 6, padding: '6px 10px',
          fontSize: 11, color: 'var(--ink)',
          whiteSpace: 'nowrap', zIndex: 1000,
          pointerEvents: 'none',
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        }}>
          <div style={{ fontWeight: 700, marginBottom: 2 }}>{tooltip.label} — {tooltip.val}/{tooltip.max}</div>
          <div style={{ color: 'var(--muted)', fontSize: 10 }}>{tooltip.desc}</div>
        </div>
      )}
    </div>
  );
}
