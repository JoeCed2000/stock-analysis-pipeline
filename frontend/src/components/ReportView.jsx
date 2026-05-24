import { useState, useEffect } from 'react';
import { getReport } from '../api.js';
import ScoringChart from './ScoringChart.jsx';
import MetricsHistoryChart from './MetricsHistoryChart.jsx';

const DECISION_COLORS = {
  BUY: '#238636',
  'HOLD / BUY ON PULLBACK': '#d29922',
  'HOLD fragile': '#d29922',
  'SELL or AVOID': '#da3633',
};

export default function ReportView({ ticker, result, onClose }) {
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | success | empty | error

  const { scoring, decision, conviction, price_native, currency, company_name } = result || {};

  useEffect(() => {
    if (ticker) {
      setStatus('loading');
      setReport(null);
      getReport(ticker)
        .then(r => {
          if (r) { setReport(r); setStatus('success'); }
          else { setStatus('empty'); }
        })
        .catch(() => setStatus('error'));
    }
  }, [ticker]);

  if (!ticker) return null;

  const totalScore = scoring?.total || 0;
  const scorePercent = (totalScore / 40) * 100;
  const scoreColor = totalScore >= 32 ? '#238636' : totalScore >= 26 ? '#d29922' : '#da3633';

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.7)', zIndex: 100, backdropFilter: 'blur(2px)',
      display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
      paddingTop: 24,
    }} onClick={onClose}>
      <div style={{
        background: '#1a1d27', border: '1px solid #30363d',
        borderRadius: 10, width: '92%', maxWidth: 720, maxHeight: '92vh',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        animation: 'modalIn 0.2s ease',
      }} onClick={e => e.stopPropagation()}>

        {/* ── HEADER ── */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 18px', borderBottom: '1px solid #30363d', flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#e1e4e8' }}>
              {ticker}
              {company_name && <span style={{ fontSize: 12, fontWeight: 400, color: '#8b949e', marginLeft: 8 }}>{company_name}</span>}
            </div>
            {price_native && (
              <div style={{ fontSize: 12, color: '#8b949e', marginTop: 2 }}>
                {price_native.toFixed(2)} {currency}{' · '}
                <span style={{
                  color: DECISION_COLORS[decision] || '#8b949e', fontWeight: 600,
                }}>
                  {decision}
                </span>
              </div>
            )}
          </div>

          {/* Score + close */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {totalScore > 0 && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 22, fontWeight: 800, color: scoreColor, lineHeight: 1 }}>
                  {totalScore}<span style={{ fontSize: 11, fontWeight: 400, color: '#484f58' }}>/40</span>
                </div>
                <div style={{ fontSize: 8, color: '#484f58', textTransform: 'uppercase', letterSpacing: 1 }}>
                  Score
                </div>
              </div>
            )}
            <button
              onClick={onClose}
              style={{
                background: '#21262d', border: '1px solid #30363d',
                color: '#8b949e', borderRadius: 6, padding: '6px 12px',
                fontSize: 12, cursor: 'pointer', fontWeight: 500,
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { e.target.style.background = '#30363d'; e.target.style.color = '#e1e4e8'; }}
              onMouseLeave={e => { e.target.style.background = '#21262d'; e.target.style.color = '#8b949e'; }}
            >
              ✕ Close
            </button>
          </div>
        </div>

        {/* ── SCORING CHART ── */}
        {scoring && (
          <div style={{ padding: '10px 18px 2px', borderBottom: '1px solid #30363d', flexShrink: 0 }}>
            <ScoringChart scoring={scoring} height={100} />
          </div>
        )}

        {/* ── METRICS HISTORY CHART ── */}
        <div style={{ padding: '10px 18px 8px', borderBottom: '1px solid #30363d', flexShrink: 0 }}>
          <MetricsHistoryChart ticker={ticker} height={220} />
        </div>

        {/* ── STATUS BANNER ── */}
        {status !== 'success' && (
          <div style={{
            margin: '10px 18px', padding: '10px 14px', borderRadius: 6,
            fontSize: 12, fontWeight: 500, flexShrink: 0,
            ...(status === 'loading' ? {
              background: '#1a2e1a', border: '1px solid #23863640', color: '#3fb950',
            } : status === 'error' ? {
              background: '#3a1a1a', border: '1px solid #da363340', color: '#f85149',
            } : {
              background: '#1a2a3a', border: '1px solid #1f6feb40', color: '#58a6ff',
            }),
          }}>
            {status === 'loading' && '⏳ Generating full analysis report…'}
            {status === 'error' && '⚠️ Report generation failed. The scoring chart above reflects the live analysis.'}
            {status === 'empty' && (
              <>
                📊 <strong>Scoring complete</strong> — full markdown report not yet generated.
                {' '}Run a new analysis to generate the complete report with detailed reasoning.
              </>
            )}
          </div>
        )}

        {/* ── REPORT CONTENT ── */}
        {status === 'success' && report && (
          <div style={{
            padding: '12px 18px', flex: 1, overflowY: 'auto',
            fontFamily: 'monospace', fontSize: 12, lineHeight: 1.7,
            color: '#e1e4e8', whiteSpace: 'pre-wrap',
          }}>
            {report}
          </div>
        )}

        {/* ── FOOTER ── */}
        <div style={{
          padding: '10px 18px', borderTop: '1px solid #30363d',
          display: 'flex', justifyContent: 'flex-end', gap: 8, flexShrink: 0,
          background: '#161b22',
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '6px 16px', fontSize: 12, fontWeight: 500,
              background: '#21262d', border: '1px solid #30363d',
              borderRadius: 6, color: '#8b949e', cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </div>

      <style>{`
        @keyframes modalIn {
          from { opacity: 0; transform: scale(0.96); }
          to   { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
