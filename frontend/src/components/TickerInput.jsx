import { useState, useEffect, useRef } from 'react';
import { uploadTickerFile } from '../api.js';

const DEBOUNCE_MS = 500;

export default function TickerInput({ onAnalyze, loading }) {
  const [value, setValue] = useState('');
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [parsing, setParsing] = useState(false);
  const timerRef = useRef(null);

  const validItems = items.filter(it => it.status === 'valid');
  const invalidItems = items.filter(it => it.status === 'invalid');

  // Auto-parse with debounce
  useEffect(() => {
    if (!value.trim()) {
      setItems([]);
      setSelected(new Set());
      return;
    }

    setParsing(true);
    if (timerRef.current) clearTimeout(timerRef.current);

    timerRef.current = setTimeout(async () => {
      const file = new File([value], 'input.txt', { type: 'text/plain' });
      try {
        const data = await uploadTickerFile(file);
        setItems(data.items || []);
        setSelected(new Set(
          (data.items || [])
            .filter(it => it.status === 'valid')
            .map(it => it.normalized)
        ));
      } catch (e) {
        console.error('Parse error:', e);
      } finally {
        setParsing(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timerRef.current);
  }, [value]);

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
        {/* Input area */}
        <div style={{
          background: '#1a1d27', border: '1px solid #30363d',
          borderRadius: 8, padding: 12,
          transition: 'border-color 0.2s',
        }}>
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Type tickers or ISINs (comma, space, or line separated)…"
            rows={2}
            disabled={loading}
            style={{
              width: '100%', padding: '8px 0', fontSize: 15,
              background: 'transparent', border: 'none',
              color: '#e1e4e8', resize: 'none', outline: 'none',
              fontFamily: 'monospace', marginBottom: items.length > 0 ? 10 : 0,
            }}
          />

          {/* Parsed tags */}
          {items.length > 0 && (
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center',
              borderTop: '1px solid #21262d', paddingTop: 10,
            }}>
              <span style={{ fontSize: 11, color: '#484f58', marginRight: 2 }}>
                {parsing ? '…' : `${validItems.length} valid · ${invalidItems.length} invalid`}
              </span>

              {[...validItems, ...invalidItems].map((it, idx) => {
                const isValid = it.status === 'valid';
                const isSelected = selected.has(it.normalized);
                return (
                  <span
                    key={it.value}
                    onClick={() => isValid && !loading && toggle(it.normalized)}
                    title={it.error || it.value}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      padding: '3px 8px', borderRadius: 4, fontSize: 12,
                      fontWeight: 600,
                      background: isValid
                        ? (isSelected ? '#1a3528' : '#21262d')
                        : '#3d1414',
                      border: `1px solid ${
                        isValid
                          ? (isSelected ? '#238636' : '#30363d')
                          : '#da3633'
                      }`,
                      color: isValid ? '#e1e4e8' : '#f85149',
                      cursor: isValid && !loading ? 'pointer' : 'default',
                      opacity: isValid && !isSelected ? 0.7 : 1,
                      transition: 'all 0.15s ease',
                      animation: 'tagIn 0.2s ease',
                    }}
                  >
                    {isValid && (
                      <span style={{
                        fontSize: 10, color: isSelected ? '#238636' : '#484f58',
                        transition: 'color 0.15s',
                      }}>
                        {isSelected ? '✓' : '○'}
                      </span>
                    )}
                    <span>{it.normalized}</span>
                    {!isValid && (
                      <span style={{ fontSize: 10, opacity: 0.7, marginLeft: 2 }}>
                        ✕
                      </span>
                    )}
                    <span style={{ fontSize: 9, opacity: 0.4 }}>{it.type}</span>
                  </span>
                );
              })}

              {validItems.length > 0 && (
                <span style={{ display: 'flex', gap: 4, marginLeft: 6 }}>
                  <button type="button" onClick={selectAll} disabled={loading}
                    style={{
                      fontSize: 10, padding: '2px 6px', background: 'transparent',
                      border: '1px solid #30363d', borderRadius: 3, color: '#8b949e',
                      cursor: 'pointer',
                    }}>
                    All
                  </button>
                  <button type="button" onClick={deselect} disabled={loading}
                    style={{
                      fontSize: 10, padding: '2px 6px', background: 'transparent',
                      border: '1px solid #30363d', borderRadius: 3, color: '#8b949e',
                      cursor: 'pointer',
                    }}>
                    None
                  </button>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Analyze button */}
        {validItems.length > 0 && selected.size > 0 && (
          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: 10, width: '100%', padding: '10px 0',
              fontSize: 15, fontWeight: 600,
              background: loading ? '#30363d' : '#238636',
              color: '#fff', border: 'none', borderRadius: 6,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s, transform 0.1s',
              transform: loading ? 'none' : undefined,
            }}
            onMouseEnter={e => { if (!loading) e.target.style.background = '#2ea043'; }}
            onMouseLeave={e => { if (!loading) e.target.style.background = '#238636'; }}
            onMouseDown={e => { if (!loading) e.target.style.transform = 'scale(0.98)'; }}
            onMouseUp={e => { if (!loading) e.target.style.transform = 'scale(1)'; }}
          >
            {loading ? 'Analyzing…' : `🔍 Analyze ${selected.size} ticker${selected.size > 1 ? 's' : ''}`}
          </button>
        )}

        {/* Hint when no valid tickers */}
        {value.trim() && validItems.length === 0 && !parsing && (
          <div style={{
            marginTop: 10, fontSize: 12, color: '#8b949e',
            textAlign: 'center', padding: '8px 0',
          }}>
            Type a ticker like <span style={{ color: '#58a6ff', fontWeight: 600 }}>NVDA</span> or an ISIN like <span style={{ color: '#58a6ff', fontWeight: 600 }}>US0378331005</span>
          </div>
        )}
      </form>

      {/* Inline CSS for tag animation */}
      <style>{`
        @keyframes tagIn {
          0%   { opacity: 0; transform: scale(0.85); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>

    </div>
  );
}
