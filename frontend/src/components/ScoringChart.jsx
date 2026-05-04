import { useState } from 'react';

const CRITERIA = [
  { key: 'growth', label: 'Growth' },
  { key: 'profitability', label: 'Profit' },
  { key: 'financial_strength', label: 'Finance' },
  { key: 'moat', label: 'Moat' },
  { key: 'management', label: 'Mgmt' },
  { key: 'valuation_risk', label: 'Value' },
  { key: 'geopolitical_risk', label: 'Geo' },
  { key: 'business_momentum', label: 'Mom' },
];

const DESCRIPTIONS = {
  growth: 'Revenue & earnings growth trajectory',
  profitability: 'Margins, ROE, cash flow quality',
  financial_strength: 'Debt levels, liquidity, balance sheet',
  moat: 'Competitive advantage durability',
  management: 'Leadership quality & capital allocation',
  valuation_risk: 'Price vs intrinsic value assessment',
  geopolitical_risk: 'Regulatory, trade, political exposure',
  business_momentum: 'Recent catalysts, product pipeline',
};

function barColor(score) {
  if (score >= 4) return '#238636';
  if (score >= 3) return '#d29922';
  return '#da3633';
}

export default function ScoringChart({ scoring, height = 120 }) {
  const [tooltip, setTooltip] = useState(null);
  if (!scoring) return null;

  const total = scoring.total || 0;
  const barW = 22;
  const gap = 6;
  const chartW = CRITERIA.length * (barW + gap);
  const maxVal = 5;
  const labelH = 18;
  const chartH = height;

  return (
    <div style={{ position: 'relative' }}>
      {/* Title */}
      <div style={{ fontSize: 11, fontWeight: 600, color: '#8b949e', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        Scoring Breakdown
      </div>

      <svg
        viewBox={`0 0 ${chartW} ${chartH + labelH}`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        style={{ display: 'block' }}
      >
        {/* Grid lines */}
        {[1, 2, 3, 4, 5].map(v => (
          <line
            key={v}
            x1={0} y1={chartH - (v / maxVal) * chartH}
            x2={chartW} y2={chartH - (v / maxVal) * chartH}
            stroke="#21262d" strokeWidth={0.5}
          />
        ))}
        {/* Bars */}
        {CRITERIA.map((c, i) => {
          const val = scoring[c.key] || 0;
          const barH = Math.max((val / maxVal) * chartH, val > 0 ? 4 : 0);
          const x = i * (barW + gap);
          const y = chartH - barH;
          const color = barColor(val);
          return (
            <g key={c.key}>
              {/* Bar */}
              <rect
                x={x} y={y} width={barW} height={barH}
                fill={color} rx={3}
                style={{ transition: 'height 0.4s ease' }}
                onMouseEnter={(e) => {
                  const rect = e.target.getBoundingClientRect();
                  setTooltip({
                    key: c.key, label: c.label, val,
                    desc: DESCRIPTIONS[c.key],
                    x: rect.left + rect.width / 2,
                    y: rect.top,
                  });
                  e.target.style.filter = 'brightness(1.3)';
                }}
                onMouseLeave={(e) => {
                  setTooltip(null);
                  e.target.style.filter = '';
                }}
              />
              {/* Score on top of bar */}
              <text
                x={x + barW / 2} y={y - 5}
                textAnchor="middle" fill="#e1e4e8" fontSize={10} fontWeight={600}
              >
                {val}
              </text>
              {/* Label below */}
              <text
                x={x + barW / 2} y={chartH + 14}
                textAnchor="middle" fill="#8b949e" fontSize={9}
              >
                {c.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x,
          top: tooltip.y - 48,
          transform: 'translate(-50%, -100%)',
          background: '#161b22', border: '1px solid #30363d',
          borderRadius: 6, padding: '6px 10px',
          fontSize: 11, color: '#e1e4e8',
          whiteSpace: 'nowrap', zIndex: 1000,
          pointerEvents: 'none',
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
        }}>
          <div style={{ fontWeight: 700, marginBottom: 2 }}>{tooltip.label} — {tooltip.val}/5</div>
          <div style={{ color: '#8b949e', fontSize: 10 }}>{tooltip.desc}</div>
        </div>
      )}
    </div>
  );
}
