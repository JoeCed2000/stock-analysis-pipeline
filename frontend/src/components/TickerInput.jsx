import { useState } from 'react';

const PRESETS = [
  { label: 'NVDA', tickers: 'NVDA' },
  { label: 'NVDA+MSFT', tickers: 'NVDA,MSFT' },
  { label: 'FAANG', tickers: 'AAPL,MSFT,NVDA,GOOGL,META' },
  { label: '5 tickers', tickers: 'NVDA,MSFT,ASML,MC.PA,AAPL' },
];

export default function TickerInput({ onAnalyze, loading }) {
  const [value, setValue] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const tickers = value.split(',').map(t => t.trim().toUpperCase()).filter(Boolean);
    if (tickers.length > 0) onAnalyze(tickers);
  };

  const handlePreset = (tickers) => {
    const list = tickers.split(',').map(t => t.trim().toUpperCase());
    setValue(tickers);
    onAnalyze(list);
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Tickers (e.g. NVDA,MSFT,AAPL)"
          disabled={loading}
          style={{
            flex: 1, padding: '10px 14px', fontSize: 15,
            background: '#1a1d27', border: '1px solid #30363d',
            borderRadius: 6, color: '#e1e4e8', outline: 'none',
          }}
        />
        <button
          type="submit"
          disabled={loading || !value.trim()}
          style={{
            padding: '10px 20px', fontSize: 15, fontWeight: 600,
            background: loading ? '#30363d' : '#238636',
            color: '#fff', border: 'none', borderRadius: 6,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '⏳ Running...' : '🔍 Analyze'}
        </button>
      </form>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {PRESETS.map(p => (
          <button
            key={p.label}
            onClick={() => handlePreset(p.tickers)}
            disabled={loading}
            style={{
              padding: '4px 10px', fontSize: 12,
              background: '#1a1d27', border: '1px solid #30363d',
              borderRadius: 4, color: '#8b949e', cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
