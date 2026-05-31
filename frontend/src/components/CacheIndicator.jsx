import { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../api.js';

/**
 * CacheIndicator — shows cache freshness and always exposes
 * a manual clear/refresh action when ticker context is present.
 */
export default function CacheIndicator({ ticker }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [flushing, setFlushing] = useState(false);
  const [actionMessage, setActionMessage] = useState('');

  const fetchInfo = useCallback(() => {
    if (!ticker) return;
    setLoading(true);
    fetch(`${API_BASE}/cache/overview/${ticker}`)
      .then(r => r.json())
      .then(d => {
        setInfo(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [ticker]);

  useEffect(() => {
    fetchInfo();
  }, [fetchInfo]);

  const canFlushCache = typeof window !== 'undefined'
    && ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);

  const handleFlush = async () => {
    if (!ticker || flushing || !canFlushCache) return;
    setFlushing(true);
    setActionMessage('');
    try {
      const res = await fetch(`${API_BASE}/cache/overview/${ticker}/flush`, { method: 'POST' });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(payload?.detail || `HTTP ${res.status}`);
      const deletedCount = Array.isArray(payload?.deleted) ? payload.deleted.length : 0;
      setActionMessage(deletedCount > 0 ? 'cache cleared' : 'already fresh');
      setTimeout(() => {
        fetchInfo();
        setFlushing(false);
      }, 450);
    } catch {
      setActionMessage('refresh failed');
      setFlushing(false);
    }
  };

  if (loading && !info) return null;
  if (!info) return null;

  const ageDays = info.cached ? info.age_days : null;
  const isStale = ageDays !== null && ageDays >= 3;
  const isVeryStale = ageDays !== null && ageDays >= 6;

  const dotColor = !info.cached ? '#8b949e'
    : isVeryStale ? '#da3633'
    : isStale ? '#d29922'
    : '#238636';

  const label = !info.cached
    ? 'Live data'
    : ageDays < 0.01 ? 'Just now'
    : ageDays < 1 ? `${Math.round(ageDays * 24)}h ago`
    : `${ageDays.toFixed(1)}d ago`;

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 11,
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '2px 8px',
      borderRadius: 12,
      background: '#161b22',
      border: '1px solid #21262d',
      flexWrap: 'wrap',
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: dotColor, flexShrink: 0 }} />
      <span style={{ color: '#8b949e' }}>{label}</span>
      {canFlushCache && (
        <button
          onClick={handleFlush}
          disabled={flushing}
          style={{
            background: 'none',
            border: 'none',
            cursor: flushing ? 'default' : 'pointer',
            color: '#58a6ff',
            fontSize: 10,
            padding: '1px 4px',
            textDecoration: 'underline',
            opacity: flushing ? 0.5 : 1,
          }}
          title="Clear cache now and fetch fresh data on next analysis"
        >
          {flushing ? 'refreshing…' : 'clear + refresh'}
        </button>
      )}
      {actionMessage && (
        <span style={{ color: '#8b949e', fontSize: 10 }}>
          · {actionMessage}
        </span>
      )}
    </div>
  );
}
