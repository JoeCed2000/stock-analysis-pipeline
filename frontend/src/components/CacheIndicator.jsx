import { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../api.js';

/**
 * CacheIndicator — shows cache freshness and flush button for the
 * company overview cache (7-day TTL). Displays "X days ago" with
 * amber/red styling when stale, green when fresh.
 */
export default function CacheIndicator({ ticker }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [flushing, setFlushing] = useState(false);

  const fetchInfo = useCallback(() => {
    if (!ticker) return;
    setLoading(true);
    fetch(`${API_BASE}/cache/overview/${ticker}`)
      .then(r => r.json())
      .then(d => { setInfo(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [ticker]);

  useEffect(() => { fetchInfo(); }, [fetchInfo]);

  const handleFlush = async () => {
    setFlushing(true);
    try {
      await fetch(`${API_BASE}/cache/overview/${ticker}/flush`, { method: 'POST' });
      // Re-check cache state after flush
      setTimeout(() => { fetchInfo(); setFlushing(false); }, 500);
    } catch {
      setFlushing(false);
    }
  };

  if (loading && !info) return null;  // don't flash during initial load
  if (!info) return null;

  const ageDays = info.cached ? info.age_days : null;
  const isStale = ageDays !== null && ageDays >= 3;
  const isVeryStale = ageDays !== null && ageDays >= 6;

  const dotColor = !info.cached ? '#8b949e'      // gray: no cache
    : isVeryStale ? '#da3633'                     // red: 6+ days
    : isStale ? '#d29922'                         // amber: 3+ days
    : '#238636';                                   // green: fresh

  const label = !info.cached
    ? 'Live data'
    : ageDays < 0.01 ? 'Just now'
    : ageDays < 1 ? `${Math.round(ageDays * 24)}h ago`
    : `${ageDays.toFixed(1)}d ago`;

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      fontSize: 11, fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '2px 8px', borderRadius: 12,
      background: '#161b22', border: '1px solid #21262d',
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        backgroundColor: dotColor, flexShrink: 0,
      }} />
      <span style={{ color: '#8b949e' }}>{label}</span>
      {info.cached && isStale && (
        <button
          onClick={handleFlush}
          disabled={flushing}
          style={{
            background: 'none', border: 'none', cursor: flushing ? 'default' : 'pointer',
            color: '#58a6ff', fontSize: 10, padding: '1px 4px',
            textDecoration: 'underline', opacity: flushing ? 0.5 : 1,
          }}
          title="Clear cache and fetch fresh data on next analysis"
        >
          {flushing ? '...' : 'flush'}
        </button>
      )}
    </div>
  );
}
