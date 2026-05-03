import { useState, useEffect } from 'react';
import { getReport } from '../api.js';

export default function ReportView({ ticker, onClose }) {
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
        borderRadius: 8, width: '90%', maxWidth: 800, maxHeight: '85vh',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 16px', borderBottom: '1px solid #30363d',
        }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: '#e1e4e8' }}>
            📊 {ticker} — Rapport d'analyse
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', color: '#8b949e',
              fontSize: 20, cursor: 'pointer', padding: '0 4px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div style={{
          padding: 16, overflow: 'auto', flex: 1,
          fontFamily: 'monospace', fontSize: 13, lineHeight: 1.6,
          color: '#e1e4e8', whiteSpace: 'pre-wrap',
        }}>
          {loading ? '⏳ Chargement du rapport...' : (report || 'Rapport non disponible')}
        </div>
      </div>
    </div>
  );
}
