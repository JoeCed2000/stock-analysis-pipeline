import { useState, useEffect, useCallback } from 'react';
import SearchMonitor from './SearchMonitor.jsx';

const POLL_MS = 5000;
const API = '/api';

export default function AdminPage({ t, onClose }) {
  const [stats, setStats] = useState(null);
  const [searches, setSearches] = useState([]);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, searchRes] = await Promise.all([
        fetch(`${API}/admin/search-stats`).then(r => r.ok ? r.json() : null),
        fetch(`${API}/admin/recent-searches?limit=2000`).then(r => r.ok ? r.json() : null),
      ]);
      console.log('[AdminPage] statsRes:', statsRes);
      console.log('[AdminPage] searchRes:', searchRes);
      if (statsRes) setStats(statsRes);
      if (searchRes) {
        console.log('[AdminPage] searches count:', searchRes.searches?.length);
        setSearches(searchRes.searches || []);
      }
    } catch (e) {
      console.error('[AdminPage] fetch failed:', e);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  const formatTime = (iso) => {
    try { return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
    catch { return iso?.slice(0, 19)?.replace('T', ' ') || '--'; }
  };

  const formatMs = (ms) => {
    if (!ms) return '-';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div style={{ padding: '24px 16px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: '#e1e4e8', margin: 0 }}>
          📊 Admin — Search Traceability
        </h2>
        <button
          onClick={onClose}
          style={{
            padding: '6px 16px', fontSize: 13, background: '#21262d',
            color: '#8b949e', border: '1px solid #30363d', borderRadius: 6, cursor: 'pointer',
          }}
        >
          ← Back
        </button>
      </div>

      {/* Stats Cards — compact, one row */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, marginBottom: 16 }}>
          <StatCard label="Searches" value={stats.total} color="#58a6ff" />
          <StatCard label="Success" value={`${stats.success_rate}%`} color={stats.success_rate > 90 ? '#3fb950' : '#d29922'} />
          <StatCard label="Avg" value={formatMs(stats.avg_duration_ms)} color="#8b949e" />
          <StatCard label="24h" value={stats.last_24h} color="#58a6ff" />
        </div>
      )}

      {/* Recent Searches Table — FIRST, the main content */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #30363d' }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#e1e4e8' }}>📋 All Searches</span>
          <span style={{ fontSize: 11, color: '#484f58', marginLeft: 8 }}>(auto-refresh 5s)</span>
        </div>
        <div style={{ maxHeight: 500, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#0d1117', position: 'sticky', top: 0, zIndex: 1 }}>
                <th style={thStyle}>Time</th>
                <th style={{ ...thStyle, width: 70 }}>Ticker</th>
                <th style={{ ...thStyle, width: 70 }}>Status</th>
                <th style={{ ...thStyle, width: 60 }}>Dur</th>
                <th style={{ ...thStyle, width: 90 }}>IP</th>
                <th style={thStyle}>User Agent</th>
                <th style={thStyle}>Error</th>
              </tr>
            </thead>
            <tbody>
              {searches.map((s, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
                  <td style={tdStyle}>{formatTime(s.timestamp)}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: '#e1e4e8', fontFamily: 'monospace', fontSize: 11, maxWidth: 70, overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.ticker}</td>
                  <td style={tdStyle}>
                    <span style={{
                      padding: '1px 6px', borderRadius: 3, fontSize: 10,
                      background: s.status === 'completed' ? '#23863620' : s.status === 'failed' ? '#da363320' : '#d2992220',
                      color: s.status === 'completed' ? '#3fb950' : s.status === 'failed' ? '#f85149' : '#d29922',
                    }}>
                      {s.status === 'completed' ? 'OK' : s.status === 'failed' ? 'FAIL' : s.status}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, color: '#8b949e', fontFamily: 'monospace', fontSize: 11, width: 60 }}>{formatMs(s.duration_ms)}</td>
                  <td style={{ ...tdStyle, color: '#484f58', fontFamily: 'monospace', fontSize: 10, maxWidth: 90, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {s.client_ip || '—'}
                  </td>
                  <td style={{ ...tdStyle, color: '#8b949e', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.user_agent?.slice(0, 30) || '—'}
                  </td>
                  <td style={{ ...tdStyle, color: '#f85149', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.error || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Top Tickers + Recent Errors — compact, BELOW table */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 12 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: '#e1e4e8', marginBottom: 8 }}>🔥 Top Tickers</h3>
            {stats.top_tickers?.filter(tt => tt.ticker.length < 20).slice(0, 6).map((tt, i) => (
              <div key={tt.ticker} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', borderBottom: i < Math.min(stats.top_tickers.length, 6) - 1 ? '1px solid #21262d' : 'none', fontSize: 12 }}>
                <span style={{ color: '#e1e4e8', fontWeight: 500, fontFamily: 'monospace' }}>{tt.ticker}</span>
                <span style={{ color: '#58a6ff', fontSize: 11 }}>{tt.count}×</span>
              </div>
            )) || <span style={{ color: '#8b949e', fontSize: 12 }}>No data</span>}
          </div>

          <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 12 }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: '#e1e4e8', marginBottom: 8 }}>⚠️ Recent Errors</h3>
            {stats.recent_errors?.length > 0 ? stats.recent_errors.slice(0, 4).map((e, i) => (
              <div key={i} style={{ fontSize: 11, padding: '2px 0', borderBottom: i < Math.min(stats.recent_errors.length, 4) - 1 ? '1px solid #21262d' : 'none' }}>
                <span style={{ color: '#8b949e' }}>{formatTime(e.timestamp)} </span>
                <span style={{ color: '#f85149', fontWeight: 500 }}>{e.ticker?.slice(0, 30)}</span>
                <span style={{ color: '#8b949e' }}> — {e.error?.slice(0, 60)}</span>
              </div>
            )) : <span style={{ color: '#3fb950', fontSize: 12 }}>No errors 🎉</span>}
          </div>
        </div>
      )}

      {/* Live search monitor — fixed bottom-right */}
      <SearchMonitor t={t} />
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
      padding: '16px', textAlign: 'center',
    }}>
      <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </div>
    </div>
  );
}

const thStyle = {
  textAlign: 'left', padding: '8px 12px', fontSize: 11, fontWeight: 600,
  color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.3px',
};

const tdStyle = {
  padding: '6px 12px', fontSize: 12, color: '#c9d1d9',
};
