import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchRecentSearches } from '../api.js';

const POLL_INTERVAL_MS = 5000;

export default function SearchMonitor({ t }) {
  const [searches, setSearches] = useState([]);
  const [expanded, setExpanded] = useState(false);
  const emptySince = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      const data = await fetchRecentSearches(15);
      const items = data?.searches || [];
      setSearches(items);

      if (items.length === 0) {
        if (!emptySince.current) emptySince.current = Date.now();
      } else {
        emptySince.current = null;
      }
    } catch {
      // silent — network errors are normal during dev
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Auto-hide after 60s of empty results
  const now = Date.now();
  if (emptySince.current && now - emptySince.current > 60000 && !expanded) {
    return null;
  }

  if (searches.length === 0 && !expanded) return null;

  const statusIcon = (s) => (s === 'completed' ? '✅' : s === 'failed' ? '❌' : '⏳');
  const statusColor = (s) => (s === 'completed' ? '#3fb950' : s === 'failed' ? '#f85149' : '#d29922');

  const formatTime = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso?.slice(11, 19) || '--:--:--';
    }
  };

  const formatDuration = (ms) => {
    if (!ms || ms <= 0) return '';
    if (ms < 1000) return `${ms}ms`;
    const s = (ms / 1000).toFixed(1);
    return `${s}s`;
  };

  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 1000,
      maxWidth: 320, minWidth: 260,
      background: '#161b22', border: '1px solid #30363d',
      borderRadius: 8, boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
      fontSize: 12, color: '#e1e4e8',
      transition: 'all 0.2s ease',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '8px 12px', cursor: 'pointer',
          background: 'linear-gradient(135deg, #1a2332 0%, #161b22 100%)',
          borderBottom: expanded ? '1px solid #30363d' : 'none',
          userSelect: 'none',
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 12 }}>
          {t('searchMonitorTitle') || '🔍 Live Searches'} ({searches.length})
        </span>
        <span style={{ color: '#8b949e', fontSize: 10 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Body */}
      {expanded && (
        <div style={{ maxHeight: 300, overflowY: 'auto', padding: '4px 0' }}>
          {searches.map((s, i) => (
            <div
              key={`${s.timestamp}-${s.ticker}-${i}`}
              style={{
                display: 'flex', flexDirection: 'column',
                padding: '4px 12px',
                borderBottom: i < searches.length - 1 ? '1px solid #21262d' : 'none',
                animation: 'slideIn 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: '#484f58', fontSize: 10, minWidth: 56, fontVariantNumeric: 'tabular-nums' }}>
                  {formatTime(s.timestamp)}
                </span>
                <span style={{ fontWeight: 600, fontSize: 12, minWidth: 48 }}>
                  {s.ticker}
                </span>
                <span style={{ color: statusColor(s.status), fontSize: 13 }}>
                  {statusIcon(s.status)}
                </span>
                {s.duration_ms > 0 && (
                  <span style={{ color: '#8b949e', fontSize: 10, marginLeft: 'auto' }}>
                    {formatDuration(s.duration_ms)}
                  </span>
                )}
                {s.error && (
                  <span style={{ color: '#f85149', fontSize: 9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 60 }}>
                    {s.error}
                  </span>
                )}
              </div>
              {/* Trace row: IP + UA */}
              {(s.client_ip || s.user_agent) && (
                <div style={{ display: 'flex', gap: 8, marginTop: 2, fontSize: 9, color: '#484f58' }}>
                  {s.client_ip && (
                    <span title={s.client_ip}>🌐 {s.client_ip}</span>
                  )}
                  {s.user_agent && (
                    <span title={s.user_agent} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 160 }}>
                      🖥 {s.user_agent.length > 40 ? s.user_agent.slice(0, 40) + '…' : s.user_agent}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(8px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
