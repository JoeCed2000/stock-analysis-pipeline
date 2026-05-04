import { getTickerDownloadUrl } from '../api.js';
import ScoringChart from './ScoringChart.jsx';

const SCORE_COLORS = {
  BUY: '#238636',
  'HOLD / BUY ON PULLBACK': '#d29922',
  'HOLD fragile': '#d29922',
  'SELL or AVOID': '#da3633',
};

const CONVICTION_COLORS = {
  High: '#238636',
  Moderate: '#d29922',
  Low: '#da3633',
};

function getConvictionLevel(conviction) {
  if (!conviction) return 'Moderate';
  const c = conviction.toLowerCase();
  if (c.includes('high') || c.includes('strong')) return 'High';
  if (c.includes('low') || c.includes('weak') || c.includes('fragile')) return 'Low';
  return 'Moderate';
}

function getInsight(scoring) {
  if (!scoring) return null;
  const s = scoring;
  if (s.business_momentum >= 4) return '🚀 Strong momentum detected';
  if (s.valuation_risk <= 2 && s.business_momentum >= 3) return '📈 Undervalued vs sector';
  if (s.financial_strength >= 4 && s.profitability >= 4) return '🏛️ Stable fundamentals';
  if (s.moat >= 4) return '🛡️ Strong competitive moat';
  if (s.management >= 4) return '👔 Quality management signals';
  if (s.growth >= 4 && s.business_momentum >= 3) return '📊 Consistent growth pattern';
  if (s.valuation_risk <= 2) return '⚠️ Valuation concerns';
  if (s.geopolitical_risk <= 2) return '🌍 Geopolitical exposure flagged';
  return '🔍 Mixed signals — review full report';
}

export default function AnalysisCard({ result, onViewReport }) {
  const { ticker, company_name, decision, scoring, conviction,
          price_native, currency, price_eur, market_cap, sector } = result || {};

  if (!result) return null;

  const color = SCORE_COLORS[decision] || '#8b949e';
  const total = scoring?.total || 0;
  const level = getConvictionLevel(conviction);
  const convictionColor = CONVICTION_COLORS[level];
  const insight = getInsight(scoring);

  const scorePercent = (total / 40) * 100;
  const scoreBarColor = total >= 32 ? '#238636' : total >= 26 ? '#d29922' : '#da3633';

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #21262d',
      borderRadius: 10, padding: 0, minWidth: 320,
      boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
      transition: 'box-shadow 0.2s, transform 0.15s',
      overflow: 'hidden',
    }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.5)'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.3)'; }}
    >
      {/* ── HEADER ── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '14px 16px 10px', borderBottom: '1px solid #21262d',
      }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#e1e4e8', letterSpacing: 0.5 }}>
            {ticker}
          </div>
          <div style={{ fontSize: 11, color: '#8b949e', marginTop: 1 }}>
            {company_name}
          </div>
        </div>
        <div style={{
          padding: '5px 12px', borderRadius: 5, fontSize: 12, fontWeight: 800,
          background: color, color: '#fff',
          boxShadow: `0 0 10px ${color}40`,
          letterSpacing: 0.5,
        }}>
          {decision}
        </div>
      </div>

      {/* ── SCORE (dominant) ── */}
      <div style={{ padding: '16px 16px 12px', textAlign: 'center' }}>
        <div style={{ fontSize: 36, fontWeight: 800, color: scoreBarColor, lineHeight: 1 }}>
          {total}<span style={{ fontSize: 18, fontWeight: 400, color: '#8b949e' }}>/40</span>
        </div>
        <div style={{ fontSize: 11, color: '#484f58', marginTop: 4, textTransform: 'uppercase', letterSpacing: 1 }}>
          Composite Score
        </div>
        {/* Score bar */}
        <div style={{
          marginTop: 10, background: '#161b22', borderRadius: 4, height: 5, overflow: 'hidden',
        }}>
          <div style={{
            width: `${scorePercent}%`, height: '100%',
            background: scoreBarColor, borderRadius: 4,
            transition: 'width 0.6s ease',
          }} />
        </div>
      </div>

      {/* ── KEY METRICS (compact) ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
        gap: 0, borderTop: '1px solid #21262d', borderBottom: '1px solid #21262d',
      }}>
        <MetricBox label="Price" value={price_native ? `${price_native.toFixed(0)} ${currency}` : '—'} />
        <MetricBox label="Mkt Cap" value={market_cap ? `${(market_cap / 1e12).toFixed(1)}T` : '—'} border />
        <MetricBox label="Sector" value={sector || '—'} />
      </div>

      {/* ── AI INSIGHT ── */}
      {insight && (
        <div style={{
          padding: '8px 16px', fontSize: 12, color: '#8b949e',
          background: '#161b22', borderBottom: '1px solid #21262d',
          fontStyle: 'italic',
        }}>
          {insight}
        </div>
      )}

      {/* ── CHART ── */}
      <div style={{ padding: '12px 16px 4px' }}>
        <ScoringChart scoring={scoring} height={120} />
      </div>

      {/* ── ACTIONS ── */}
      <div style={{ padding: '10px 16px 8px', display: 'flex', gap: 8 }}>
        <button
          onClick={() => onViewReport(ticker, scoring)}
          style={{
            flex: 1, padding: '7px 0', fontSize: 12, fontWeight: 500,
            background: '#21262d', border: '1px solid #30363d',
            borderRadius: 5, color: '#58a6ff', cursor: 'pointer',
            transition: 'background 0.15s',
          }}
          onMouseEnter={e => e.target.style.background = '#30363d'}
          onMouseLeave={e => e.target.style.background = '#21262d'}
        >
          📄 Full report
        </button>
        <a
          href={getTickerDownloadUrl(ticker)}
          download
          style={{
            flex: 1, padding: '7px 0', fontSize: 12, fontWeight: 500,
            background: '#21262d', border: '1px solid #30363d',
            borderRadius: 5, color: '#8b949e', cursor: 'pointer',
            textDecoration: 'none', textAlign: 'center',
            transition: 'background 0.15s',
          }}
          onMouseEnter={e => e.target.style.background = '#30363d'}
          onMouseLeave={e => e.target.style.background = '#21262d'}
        >
          📥 Download
        </a>
      </div>

      {/* ── CONVICTION ── */}
      <div style={{
        padding: '6px 16px 12px', textAlign: 'center',
      }}>
        <span style={{
          display: 'inline-block', padding: '3px 10px', borderRadius: 3,
          fontSize: 10, fontWeight: 700,
          background: `${convictionColor}20`, color: convictionColor,
          border: `1px solid ${convictionColor}40`,
          textTransform: 'uppercase', letterSpacing: 0.5,
        }}>
          {level} conviction
        </span>
      </div>
    </div>
  );
}

function MetricBox({ label, value, border }) {
  return (
    <div style={{
      textAlign: 'center', padding: '8px 4px',
      borderLeft: border ? '1px solid #21262d' : 'none',
      borderRight: border ? '1px solid #21262d' : 'none',
    }}>
      <div style={{ fontSize: 10, color: '#484f58', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#e1e4e8' }}>
        {value}
      </div>
    </div>
  );
}
