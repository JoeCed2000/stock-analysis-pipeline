import { useState, useEffect } from 'react';

const STEP_KEYS = ['step_fetching', 'step_ratios', 'step_scoring', 'step_insights'];

export default function SmartLoader({ total, current, ticker, t }) {
  const [step, setStep] = useState(0);

  // Cycle through steps every 2.5s
  useEffect(() => {
    const interval = setInterval(() => {
      setStep(s => (s + 1) % STEP_KEYS.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  const pct = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #21262d',
      borderRadius: 10, padding: '32px 24px', marginTop: 20,
      textAlign: 'center',
    }}>
      {/* Tick counter */}
      <div style={{ fontSize: 22, fontWeight: 700, color: '#e1e4e8', marginBottom: 4 }}>
        {ticker
          ? <span>{t('analyzing')} <span style={{ color: '#58a6ff' }}>{ticker}</span></span>
          : t('loading')}
      </div>

      <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 20 }}>
        {current} / {total} tickers
      </div>

      {/* Progress bar */}
      <div style={{
        background: '#161b22', borderRadius: 6, height: 6,
        overflow: 'hidden', marginBottom: 20, maxWidth: 400, margin: '0 auto 20px',
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: '#58a6ff',
          borderRadius: 6,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Step indicator — all circles stay neutral blue, no false green checkmarks */}
      <div style={{
        display: 'flex', justifyContent: 'center', gap: 24,
        flexWrap: 'wrap', marginBottom: 24,
      }}>
        {STEP_KEYS.map((key, i) => {
          const isCurrent = i === step;
          return (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 12,
            color: isCurrent ? '#e1e4e8' : '#484f58',
            fontWeight: isCurrent ? 600 : 400,
            transition: 'color 0.3s',
          }}>
            <span style={{
              display: 'inline-block', width: 16, height: 16, borderRadius: '50%',
              background: isCurrent ? '#58a6ff' : '#30363d',
              transition: 'background 0.3s',
            }} />
            <span style={{ whiteSpace: 'nowrap' }}>{t(key)}</span>
          </div>
        )})}
      </div>

      {/* Pulse dot */}
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8,
        color: '#8b949e', fontSize: 11,
      }}>
        <span style={{
          display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
          background: '#58a6ff',
          animation: 'pulse-dot 1.2s ease-in-out infinite',
        }} />
        {t('processing')}
      </div>

      <style>{`
        @keyframes pulse-dot {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%      { opacity: 1;   transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}
