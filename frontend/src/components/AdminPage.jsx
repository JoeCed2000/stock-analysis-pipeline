import { useState, useEffect, useCallback } from 'react';
import { getFeedbackAttachmentUrl } from '../api.js';
import SearchMonitor from './SearchMonitor.jsx';
import SeekingAlphaAccessPanel from './SeekingAlphaAccessPanel.jsx';

const POLL_MS = 5000;
const API = '/api';
const PAGE_SIZE = 50;

export default function AdminPage({ t, onClose }) {
  const [stats, setStats] = useState(null);
  const [searches, setSearches] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(0);
  const [feedbacks, setFeedbacks] = useState([]);
  const [feedbackError, setFeedbackError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const offset = page * PAGE_SIZE;
      const [statsRes, searchRes, fbRes] = await Promise.all([
        fetch(`${API}/search-stats`).then(r => r.ok ? r.json() : null),
        fetch(`${API}/recent-searches?limit=${PAGE_SIZE}&offset=${offset}`).then(r => r.ok ? r.json() : null),
        fetch(`${API}/feedback`).then(r => r.ok ? r.json() : { error: `HTTP ${r.status}` }),
      ]);
      if (statsRes) setStats(statsRes);
      if (searchRes) {
        setSearches(searchRes.searches || []);
        setTotalCount(searchRes.total || 0);
      }
      if (fbRes?.error) {
        setFeedbackError(fbRes.error);
      } else {
        setFeedbackError('');
        setFeedbacks((fbRes?.entries || []));
      }
    } catch (e) {
      console.error('[AdminPage] fetch failed:', e);
    }
  }, [page]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

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
    <div style={{ padding: '24px 16px', maxWidth: 1440, margin: '0 auto' }}>
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

      <SeekingAlphaAccessPanel />

      {/* Stats Cards — compact, one row */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, marginBottom: 16 }}>
          <StatCard label="Searches" value={stats.total} color="#58a6ff" />
          <StatCard label="Success" value={`${stats.success_rate}%`} color={stats.success_rate > 90 ? '#3fb950' : '#d29922'} />
          <StatCard label="Avg" value={formatMs(stats.avg_duration_ms)} color="#8b949e" />
          <StatCard label="24h" value={stats.last_24h} color="#58a6ff" />
        </div>
      )}

      {/* Recent Searches Table */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #30363d', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#e1e4e8' }}>📋 All Searches</span>
            <span style={{ fontSize: 11, color: '#484f58', marginLeft: 8 }}>(auto-refresh 5s)</span>
          </span>
          <span style={{ fontSize: 11, color: '#8b949e' }}>
            Page {page + 1} of {totalPages} — {totalCount} total
          </span>
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
                <tr key={`${s.timestamp}-${i}`} style={{ borderBottom: '1px solid #21262d' }}>
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

        {/* Pagination controls */}
        <div style={{
          padding: '8px 16px', borderTop: '1px solid #30363d',
          display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8,
        }}>
          <PageBtn onClick={() => setPage(0)} disabled={page === 0} label="⏮" />
          <PageBtn onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} label="◀" />
          <span style={{ fontSize: 12, color: '#8b949e', minWidth: 80, textAlign: 'center' }}>
            {page + 1} / {totalPages}
          </span>
          <PageBtn onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} label="▶" />
          <PageBtn onClick={() => setPage(totalPages - 1)} disabled={page >= totalPages - 1} label="⏭" />
        </div>
      </div>

      {/* Feedback Viewer */}
      <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
        <div style={{ padding: '10px 16px', borderBottom: '1px solid #30363d', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#e1e4e8' }}>💬 Feedback</span>
            <span style={{ fontSize: 11, color: '#484f58', marginLeft: 8 }}>(auto-refresh 5s)</span>
          </span>
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 10,
            background: feedbacks.filter(f => !f.processed).length > 0 ? '#da363320' : '#23863620',
            color: feedbacks.filter(f => !f.processed).length > 0 ? '#f85149' : '#3fb950',
          }}>
            {feedbacks.filter(f => !f.processed).length} unprocessed / {feedbacks.length} total
          </span>
        </div>
        {feedbackError ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#f85149', fontSize: 13 }}>
            Feedback history failed to load: {feedbackError}
          </div>
        ) : feedbacks.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#484f58', fontSize: 13 }}>
            Submitted notes will appear here
          </div>
        ) : (
          <div style={{ maxHeight: 400, overflowY: 'auto' }}>
            {feedbacks.map((fb, i) => (
              <div key={fb.id || i} style={{
                padding: '12px 16px',
                borderBottom: i < feedbacks.length - 1 ? '1px solid #21262d' : 'none',
                background: !fb.processed ? '#1a1d27' : 'transparent',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                      fontFamily: 'monospace', fontSize: 12, fontWeight: 600, color: '#58a6ff',
                      background: '#0d1117', padding: '2px 8px', borderRadius: 4,
                    }}>
                      {fb._ticker || fb.ticker}
                    </span>
                    <span style={{ fontSize: 11, color: '#8b949e' }}>
                      {formatTime(fb.submitted_at)}
                    </span>
                    {!fb.processed && (
                      <span style={{
                        fontSize: 10, padding: '1px 6px', borderRadius: 3,
                        background: '#da363320', color: '#f85149',
                      }}>
                        NEW
                      </span>
                    )}
                    {fb.processed && (
                      <span style={{
                        fontSize: 10, padding: '1px 6px', borderRadius: 3,
                        background: '#23863620', color: '#3fb950',
                      }}>
                        processed
                      </span>
                    )}
                  </div>
                  {fb.files?.length > 0 && (
                    <span style={{ fontSize: 11, color: '#8b949e' }}>
                      📎 {fb.files.length} file{fb.files.length > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
                <div style={{
                  fontSize: 13, color: '#c9d1d9', lineHeight: 1.5,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}>
                  {fb.text || '(no text)'}
                </div>
                {fb.files?.length > 0 && (
                  <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {fb.files.map((f, j) => (
                      <a
                        key={j}
                        href={getFeedbackAttachmentUrl(fb._ticker || fb.ticker, f)}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          fontSize: 11,
                          color: '#58a6ff',
                          background: '#21262d',
                          padding: '2px 8px',
                          borderRadius: 4,
                          textDecoration: 'none',
                        }}
                      >
                        📄 {f}
                      </a>
                    ))}
                  </div>
                )}
                {fb.notes && (
                  <div style={{ marginTop: 6, fontSize: 11, color: '#d29922', fontStyle: 'italic' }}>
                    📝 {fb.notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Top Tickers + Recent Errors */}
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

function PageBtn({ onClick, disabled, label }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '4px 10px', fontSize: 12,
        background: disabled ? '#0d1117' : '#21262d',
        color: disabled ? '#484f58' : '#c9d1d9',
        border: '1px solid #30363d', borderRadius: 4,
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.4 : 1,
      }}
    >
      {label}
    </button>
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
