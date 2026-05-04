// Pure SVG scoring bar chart — zero dependencies
const CRITERIA = [
  { key: 'growth', label: 'Growth' },
  { key: 'profitability', label: 'Profitability' },
  { key: 'financial_strength', label: 'Financials' },
  { key: 'moat', label: 'Moat' },
  { key: 'management', label: 'Management' },
  { key: 'valuation_risk', label: 'Valuation' },
  { key: 'geopolitical_risk', label: 'Geopolitical' },
  { key: 'business_momentum', label: 'Momentum' },
];

function barColor(score) {
  if (score >= 4) return '#238636';
  if (score >= 3) return '#d29922';
  return '#da3633';
}

export default function ScoringChart({ scoring, height = 200 }) {
  if (!scoring) return null;
  const total = scoring.total || 0;
  const barW = 28;
  const gap = 12;
  const chartW = CRITERIA.length * (barW + gap);
  const maxVal = 5;

  return (
    <div style={{ margin: '12px 0' }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#e1e4e8', marginBottom: 8 }}>
        Detailed Scoring ({total}/40)
      </div>
      <svg width={chartW} height={height + 30} style={{ display: 'block' }}>
        {/* Grid lines */}
        {[1, 2, 3, 4, 5].map(v => (
          <line
            key={v}
            x1={0} y1={height - (v / maxVal) * height}
            x2={chartW} y2={height - (v / maxVal) * height}
            stroke="#30363d" strokeWidth={0.5} strokeDasharray="3,3"
          />
        ))}
        {/* Bars */}
        {CRITERIA.map((c, i) => {
          const val = scoring[c.key] || 0;
          const barH = (val / maxVal) * height;
          const x = i * (barW + gap);
          const y = height - barH;
          return (
            <g key={c.key}>
              <rect
                x={x} y={y} width={barW} height={barH}
                fill={barColor(val)} rx={3}
              />
              <text
                x={x + barW / 2} y={y - 6}
                textAnchor="middle" fill="#e1e4e8" fontSize={11}
              >
                {val}
              </text>
              <text
                x={x + barW / 2} y={height + 16}
                textAnchor="middle" fill="#8b949e" fontSize={10}
                transform={`rotate(-30, ${x + barW / 2}, ${height + 16})`}
              >
                {c.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
