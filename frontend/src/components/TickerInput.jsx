import { useState } from 'react';
import { uploadTickerFile } from '../api.js';

export default function TickerInput({ onAnalyze, loading }) {
  const [value, setValue] = useState('');
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());

  const validItems = items.filter(it => it.status === 'valid');
  const invalidItems = items.filter(it => it.status === 'invalid');

  const handleParse = async () => {
    if (!value.trim()) return;
    const blob = new Blob([value], { type: 'text/plain' });
    blob.name = 'input.txt';
    try {
      const data = await uploadTickerFile(blob);
      setItems(data.items || []);
      setSelected(new Set((data.items || []).filter(it => it.status === 'valid').map(it => it.normalized)));
    } catch (e) {
      // silently ignore parse errors
    }
  };

  const toggle = (t) => setSelected(prev => {
    const next = new Set(prev);
    next.has(t) ? next.delete(t) : next.add(t);
    return next;
  });

  const selectAll = () => setSelected(new Set(validItems.map(it => it.normalized)));
  const deselect = () => setSelected(new Set());

  const handleSubmit = (e) => {
    e.preventDefault();
    const tickers = [...selected];
    if (tickers.length > 0) onAnalyze(tickers);
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <form onSubmit={handleSubmit}>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Enter tickers or ISINs, one per line or comma-separated...&#10;NVDA&#10;MSFT&#10;AAPL&#10;US0378331005"
          rows={4}
          disabled={loading}
          style={{
            width: '100%', padding: '10px 14px', fontSize: 14,
            background: '#1a1d27', border: '1px solid #30363d',
            borderRadius: 6, color: '#e1e4e8', resize: 'vertical',
            outline: 'none', fontFamily: 'monospace', marginBottom: 8,
          }}
        />

        <div style={{ display: 'flex', gap: 8, marginBottom: items.length > 0 ? 12 : 0 }}>
          <button
            type="button"
            onClick={handleParse}
            disabled={loading || !value.trim()}
            style={{
              padding: '6px 14px', fontSize: 12,
              background: '#21262d', border: '1px solid #30363d',
              borderRadius: 4, color: '#8b949e',
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            📋 Parse
          </button>

          {items.length > 0 && (
            <button
              type="submit"
              disabled={loading || selected.size === 0}
              style={{
                padding: '8px 20px', fontSize: 14, fontWeight: 600,
                background: loading ? '#30363d' : '#238636',
                color: '#fff', border: 'none', borderRadius: 4,
                cursor: loading || selected.size === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? '⏳ Running...' : `🔍 Analyze ${selected.size} ticker(s)`}
            </button>
          )}
        </div>
      </form>

      {/* Parsed list */}
      {items.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 12, color: '#8b949e' }}>
              {validItems.length} valid — {invalidItems.length} invalid — {selected.size} selected
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button type="button" onClick={selectAll} disabled={loading}
                style={{ fontSize: 11, padding: '2px 8px', background: '#21262d', border: '1px solid #30363d', borderRadius: 3, color: '#8b949e', cursor: 'pointer' }}>
                All
              </button>
              <button type="button" onClick={deselect} disabled={loading}
                style={{ fontSize: 11, padding: '2px 8px', background: '#21262d', border: '1px solid #30363d', borderRadius: 3, color: '#8b949e', cursor: 'pointer' }}>
                None
              </button>
            </div>
          </div>

          {/* Valid tickers */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 6,
            padding: 6, background: '#1a1d27', border: '1px solid #30363d',
            borderRadius: 4, marginBottom: invalidItems.length > 0 ? 6 : 0,
          }}>
            {validItems.map(it => (
              <label key={it.value} style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '4px 8px', borderRadius: 3,
                background: selected.has(it.normalized) ? '#1a3528' : '#21262d',
                border: `1px solid ${selected.has(it.normalized) ? '#238636' : '#30363d'}`,
                cursor: loading ? 'not-allowed' : 'pointer',
                fontSize: 12, color: '#e1e4e8',
              }}>
                <input type="checkbox" checked={selected.has(it.normalized)}
                  onChange={() => toggle(it.normalized)} disabled={loading}
                  style={{ accentColor: '#238636' }} />
                <strong>{it.normalized}</strong>
                <span style={{ fontSize: 9, color: '#484f58' }}>{it.type}</span>
              </label>
            ))}
            {validItems.length === 0 && <span style={{ fontSize: 11, color: '#484f58', padding: 2 }}>No valid tickers</span>}
          </div>

          {/* Invalid */}
          {invalidItems.length > 0 && (
            <div style={{ padding: 6, background: '#1a1d27', border: '1px solid #da3633', borderRadius: 4 }}>
              <span style={{ fontSize: 11, color: '#f85149', fontWeight: 600 }}>⚠️ {invalidItems.length} invalid:</span>
              {' '}
              {invalidItems.map(it => (
                <span key={it.value} title={it.error} style={{
                  fontSize: 11, color: '#f85149', textDecoration: 'line-through', marginLeft: 4,
                }}>{it.value}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
