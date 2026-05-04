import { getReport } from '../api.js';
import { Fragment } from 'react';
import ScoringChart from './ScoringChart.jsx';

const SCORE_COLORS = {
  BUY: '#238636',
  'HOLD / BUY ON PULLBACK': '#d29922',
  'HOLD fragile': '#d29922',
  'SELL or AVOID': '#da3633',
};

export default function AnalysisCard({ result, onViewReport }) {
  const { ticker, company_name, decision, scoring, conviction,
          price_native, currency, price_eur, market_cap, sector } = result || {};

  if (!result) return null;

  const color = SCORE_COLORS[decision] || '#8b949e';
  const total = scoring?.total || 0;

  return (
    <div style={{
      background: '#1a1d27', border: '1px solid #30363d',
      borderRadius: 8, padding: 16, minWidth: 280, flex: 1,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#e1e4e8' }}>{ticker}</div>
          <div style={{ fontSize: 12, color: '#8b949e', marginTop: 2 }}>{company_name}</div>
        </div>
        <div style={{
          background: color, color: '#fff', padding: '4px 10px',
          borderRadius: 4, fontSize: 13, fontWeight: 700,
        }}>
          {decision}
        </div>
      </div>

      {/* Score bar */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
          <span>Score</span>
          <span style={{ fontWeight: 700, color: '#e1e4e8' }}>{total}/40</span>
        </div>
        <div style={{ background: '#30363d', borderRadius: 4, height: 6, overflow: 'hidden' }}>
          <div style={{
            width: `${(total / 40) * 100}%`, height: '100%',
            background: total >= 32 ? '#238636' : total >= 26 ? '#d29922' : total >= 18 ? '#d29922' : '#da3633',
            borderRadius: 4, transition: 'width 0.5s',
          }} />
        </div>
      </div>

      {/* Key metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: 13 }}>
        {price_native && (
          <>
            <span style={{ color: '#8b949e' }}>Price</span>
            <span style={{ color: '#e1e4e8', textAlign: 'right' }}>{price_native.toFixed(2)} {currency}</span>
          </>
        )}
        {price_eur && (
          <>
            <span style={{ color: '#8b949e' }}>EUR</span>
            <span style={{ color: '#e1e4e8', textAlign: 'right' }}>{price_eur.toFixed(2)} €</span>
          </>
        )}
        {market_cap && (
          <>
            <span style={{ color: '#8b949e' }}>Mkt Cap</span>
            <span style={{ color: '#e1e4e8', textAlign: 'right' }}>{(market_cap / 1e12).toFixed(2)}T</span>
          </>
        )}
        {sector && (
          <>
            <span style={{ color: '#8b949e' }}>Sector</span>
            <span style={{ color: '#e1e4e8', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sector}</span>
          </>
        )}
      </div>

      {/* Scoring chart */}
      <div style={{ marginTop: 12, borderTop: '1px solid #30363d', paddingTop: 10 }}>
        <ScoringChart scoring={scoring} height={140} />
      </div>

      {/* View report button */}
      <button
        onClick={() => onViewReport(ticker, scoring)}
        style={{
          marginTop: 12, width: '100%', padding: '6px 0',
          background: '#21262d', border: '1px solid #30363d',
          borderRadius: 4, color: '#58a6ff', fontSize: 12,
          cursor: 'pointer',
        }}
      >
        📄 View full report
      </button>

      <div style={{ marginTop: 4, fontSize: 11, color: '#484f58', textAlign: 'center' }}>
        Conviction: {conviction}
      </div>
    </div>
  );
}
