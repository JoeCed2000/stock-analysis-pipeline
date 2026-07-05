// v2 — all tickers pass format check, no valid/invalid display
// Build SHA: fc050e6 — force cache bust
import { useState, useEffect, useRef } from 'react';
import { uploadTickerFile } from '../api.js';

const DEBOUNCE_MS = 500;
const TICKER_PATTERN = /^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$/;
const ISIN_PATTERN = /^[A-Z]{2}[A-Z0-9]{10}$/;

function parseFallbackTickers(text) {
  const seen = new Set();
  return text
    .split(/[\n,;\s]+/)
    .map(token => token.trim().toUpperCase())
    .filter(Boolean)
    .filter(token => {
      if (seen.has(token)) return false;
      seen.add(token);
      return TICKER_PATTERN.test(token) || ISIN_PATTERN.test(token);
    })
    .map(token => ({
      value: token,
      type: ISIN_PATTERN.test(token) ? 'ISIN' : 'TICKER',
      normalized: token,
      status: 'valid',
      fallback: true,
    }));
}

export default function TickerInput({ onAnalyze, loading, t }) {
  const [value, setValue] = useState('');
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState(null);
  const timerRef = useRef(null);

  const validItems = items.filter(it => it.status !== 'invalid');

  // Auto-parse with debounce
  useEffect(() => {
    // Clear stale items on every keystroke to prevent race condition:
    // user corrects ticker → submits before new debounce fires → old data persists
    setItems([]);
    setSelected(new Set());
    setParseError(null);

    if (!value.trim()) {
      return;
    }

    setParsing(true);
    if (timerRef.current) clearTimeout(timerRef.current);

    timerRef.current = setTimeout(async () => {
      const file = new File([value], 'input.txt', { type: 'text/plain' });
      try {
        const data = await uploadTickerFile(file);
        const selectable = (data.items || []).filter(it => it.status !== 'invalid');
        setItems(data.items || []);
        setSelected(new Set(
          selectable.map(it => it.normalized)
        ));
      } catch (e) {
        console.error('Parse error:', e);
        const fallbackItems = parseFallbackTickers(value);
        if (fallbackItems.length > 0) {
          setItems(fallbackItems);
          setSelected(new Set(fallbackItems.map(it => it.normalized)));
          setParseError('Live parser temporarily unavailable — using local ticker parsing.');
        } else {
          setParseError(`Could not parse tickers (${e.message}). Please retry shortly.`);
        }
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
        {/* Input area — command bar */}
        <div className="cmdbar" style={{ padding: '16px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <span aria-hidden="true" style={{
              fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700,
              color: 'var(--accent)', lineHeight: '30px', userSelect: 'none',
              textShadow: '0 0 12px rgba(52, 211, 153, 0.5)',
            }}>❯</span>
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t('tickerPlaceholder')}
            rows={2}
            disabled={loading}
            style={{
              width: '100%', padding: '4px 0', fontSize: 16,
              background: 'transparent', border: 'none',
              color: '#e7edf6', resize: 'none', outline: 'none',
              marginBottom: items.length > 0 ? 10 : 0,
            }}
          />
          </div>

          {/* Parsed tags */}
          {items.length > 0 && (
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: 7, alignItems: 'center',
              borderTop: '1px solid var(--line)', paddingTop: 12,
            }}>
              <span className="mono" style={{ fontSize: 11, color: 'var(--faint)', marginRight: 2, letterSpacing: '0.06em' }}>
                {parsing ? '…' : `${items.length} ticker${items.length !== 1 ? 's' : ''}`}
              </span>

              {items.map((it, idx) => {
                const isSelected = selected.has(it.normalized);
                const isInvalid = it.status === 'invalid';
                return (
                  <span
                    key={it.value}
                    className={`ticker-tag${isSelected ? ' selected' : ''}`}
                    onClick={() => !loading && !isInvalid && toggle(it.normalized)}
                    title={it.error || it.value}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5,
                      padding: '4px 10px', borderRadius: 8, fontSize: 12,
                      fontWeight: 600, letterSpacing: '0.03em',
                      background: isInvalid ? 'rgba(218, 54, 51, 0.12)' : isSelected ? 'rgba(52, 211, 153, 0.13)' : 'rgba(125, 155, 195, 0.08)',
                      border: `1px solid ${
                        isInvalid ? 'rgba(248, 81, 73, 0.5)' : isSelected ? 'rgba(52, 211, 153, 0.5)' : 'var(--line)'
                      }`,
                      color: isSelected ? '#c8f5e3' : 'var(--ink)',
                      cursor: loading || isInvalid ? 'default' : 'pointer',
                      opacity: isInvalid ? 0.55 : !isSelected ? 0.65 : 1,
                      transition: 'all 0.15s ease',
                      animation: 'tagIn 0.25s ease',
                    }}
                  >
                    <span style={{
                      fontSize: 10, color: isSelected ? 'var(--accent)' : 'var(--faint)',
                      transition: 'color 0.15s',
                    }}>
                      {isInvalid ? '✕' : isSelected ? '✓' : '○'}
                    </span>
                    <span>{it.normalized}</span>
                    <span style={{ fontSize: 9, opacity: 0.45 }}>{it.type}</span>
                  </span>
                );
              })}

              {validItems.length > 0 && (
                <span style={{ display: 'flex', gap: 4, marginLeft: 6 }}>
                  <button type="button" onClick={selectAll} disabled={loading}
                    style={{
                      fontSize: 10, padding: '3px 9px', background: 'transparent',
                      border: '1px solid var(--line)', borderRadius: 999, color: 'var(--muted)',
                      cursor: 'pointer', fontFamily: 'var(--font-body)',
                    }}>
                    All
                  </button>
                  <button type="button" onClick={deselect} disabled={loading}
                    style={{
                      fontSize: 10, padding: '3px 9px', background: 'transparent',
                      border: '1px solid var(--line)', borderRadius: 999, color: 'var(--muted)',
                      cursor: 'pointer', fontFamily: 'var(--font-body)',
                    }}>
                    None
                  </button>
                </span>
              )}
            </div>
          )}
          {parseError && (
            <div style={{
              marginTop: 8, fontSize: 12, color: '#f0b72f',
              borderTop: items.length > 0 ? '1px solid var(--line)' : 'none',
              paddingTop: items.length > 0 ? 8 : 0,
            }}>
              ⚠️ {parseError}
            </div>
          )}
        </div>

        {/* Analyze button */}
        {items.length > 0 && selected.size > 0 && (
          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{ marginTop: 12, width: '100%', padding: '13px 0', fontSize: 15 }}
          >
            {loading ? t('analyzing') : `🔍 ${t('analyze')} ${selected.size} ticker${selected.size > 1 ? 's' : ''}`}
          </button>
        )}

        {/* Hint when no tickers typed yet */}
        {value.trim() && items.length === 0 && !parsing && (
          <div style={{
            marginTop: 10, fontSize: 12, color: 'var(--muted)',
            textAlign: 'center', padding: '8px 0',
          }}>
            Type a ticker like <span className="mono" style={{ color: 'var(--cyan)', fontWeight: 600 }}>NVDA</span> or an ISIN like <span className="mono" style={{ color: 'var(--cyan)', fontWeight: 600 }}>US0378331005</span>
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
