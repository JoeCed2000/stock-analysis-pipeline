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
        fetch(`${API}/admin/recent-searches?limit=100`).then(r => r.ok ? r.json() : null),
      ]);
      if (statsRes) setStats(statsRes);
      if (searchRes) setSearches(searchRes.searches || []);
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
    try { return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
    catch { return iso?.slice(11, 19) || '--:--:--'; }
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

      {/* Stats Cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 24 }}>
          <StatCard label="Total Searches" value={stats.total} color="#58a6ff" />
          <StatCard label="Success Rate" value={`${stats.success_rate}%`} color={stats.success_rate > 90 ? '#3fb950' : '#d29922'} />
          <StatCard label="Avg Duration" value={formatMs(stats.avg_duration_ms)} color="#8b949e" />
          <StatCard label="Last 24h" value={stats.last_24h} color="#58a6ff" />
        </div>
      )}

      {/* Top Tickers + Recent Errors — side by side */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 24 }}>
          {/* Top Tickers */}
          <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e1e4e8', marginBottom: 12 }}>🔥 Top Tickers</h3>
            {stats.top_tickers?.map((tt, i) => (
              <div key={tt.ticker} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: i < stats.top_tickers.length - 1 ? '1px solid #21262d' : 'none', fontSize: 13 }}>
                <span style={{ color: '#e1e4e8', fontWeight: 500 }}>{tt.ticker}</span>
                <span style={{ color: '#58a6ff' }}>{tt.count}×</span>
              </div>
            )) || <span style={{ color: '#8b949e', fontSize: 13 }}>No data</span>}
          </div>

          {/* Recent Errors */}
          <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e1e4e8', marginBottom: 12 }}>⚠️ Recent Errors</h3>
            {stats.recent_errors?.length > 0 ? stats.recent_errors.map((e, i) => (
              <div key={i} style={{ fontSize: 12, padding: '4px 0', borderBottom: i < stats.recent_errors.length - 1 ? '1px solid #21262d' : 'none' }}>
                <span style={{ color: '#8b949e' }}>{formatTime(e.timestamp)} </span>
                <span style={{ color: '#f85149', fontWeight: 500 }}>{e.ticker}</span>
                <span style={{ color: '#8b949e' }}> — {e.error}</span>
              </div>
            )) : <span style={{ color: '#3fb950', fontSize: 13 }}>No errors 🎉</span>}
          </div>
        </div>
      )}

      {/* Recent Searches Table */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #30363d' }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#e1e4e8' }}>📋 Recent Searches</span>
          <span style={{ fontSize: 11, color: '#484f58', marginLeft: 8 }}>(auto-refresh 5s)</span>
        </div>
        <div style={{ maxHeight: 500, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#0d1117', position: 'sticky', top: 0, zIndex: 1 }}>
                <th style={thStyle}>Time</th>
                <th style={thStyle}>Ticker</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Duration</th>
                <th style={thStyle}>IP</th>
                <th style={thStyle}>User Agent</th>
                <th style={thStyle}>Error</th>
              </tr>
            </thead>
            <tbody>
              {searches.map((s, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
                  <td style={tdStyle}>{formatTime(s.timestamp)}</td>
                  <td style={{ ...tdStyle, fontWeight: 600, color: '#e1e4e8' }}>{s.ticker}</td>
                  <td style={tdStyle}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 11,
                      background: s.status === 'completed' ? '#23863620' : s.status === 'failed' ? '#da363320' : '#d2992220',
                      color: s.status === 'completed' ? '#3fb950' : s.status === 'failed' ? '#f85149' : '#d29922',
                    }}>
                      {s.status}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, color: '#8b949e' }}>{formatMs(s.duration_ms)}</td>
                  <td style={{ ...tdStyle, color: '#8b949e', fontFamily: 'monospace', fontSize: 11 }}>
                    {s.client_ip || '-'}
                  </td>
                  <td style={{ ...tdStyle, color: '#8b949e', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.user_agent?.slice(0, 40) || '-'}
                  </td>
                  <td style={{ ...tdStyle, color: '#f85149', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.error || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </div>

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
