import { useState, useEffect } from 'react';
import { getReport } from '../api.js';
import ScoringChart from './ScoringChart.jsx';

export default function ReportView({ ticker, scoring, onClose }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (ticker) {
      setLoading(true);
      getReport(ticker).then(r => { setReport(r); setLoading(false); });
    }
  }, [ticker]);

  if (!ticker) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.7)', zIndex: 100,
      display: 'flex', justifyContent: 'center', alignItems: 'flex-start',
      paddingTop: 40,
    }}>
      <div style={{
        background: '#1a1d27', border: '1px solid #30363d',
        borderRadius: 8, width: '90%', maxWidth: 700, maxHeight: '90vh',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '10px 14px', borderBottom: '1px solid #30363d',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#e1e4e8' }}>
            📊 {ticker} — Analysis Report
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: '#8b949e',
              fontSize: 18, cursor: 'pointer', padding: '0 4px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Scoring chart above the report */}
        {scoring && (
          <div style={{ padding: '6px 14px 0', borderBottom: '1px solid #30363d', flexShrink: 0 }}>
            <ScoringChart scoring={scoring} height={100} />
          </div>
        )}

        {/* Content — scrollable */}
        <div style={{
          padding: '10px 14px', flex: 1, overflowY: 'auto',
          fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6,
          color: '#e1e4e8', whiteSpace: 'pre-wrap',
        }}>
          {loading ? '⏳ Loading report...' : (report || 'Report not available')}
        </div>
      </div>
    </div>
  );
}
