import { useState, useEffect } from 'react';

const STEPS = [
  'Fetching financial data…',
  'Processing ratios & metrics…',
  'Scoring fundamentals…',
  'Generating insights…',
];

export default function SmartLoader({ total, current, ticker, t }) {
  const [step, setStep] = useState(0);

  // Cycle through steps every 2.5s
  useEffect(() => {
    const interval = setInterval(() => {
      setStep(s => (s + 1) % STEPS.length);
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
          background: 'linear-gradient(90deg, #238636, #58a6ff)',
          borderRadius: 6,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Step indicator */}
      <div style={{
        display: 'flex', justifyContent: 'center', gap: 24,
        flexWrap: 'wrap', marginBottom: 24,
      }}>
        {STEPS.map((s, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 12,
            color: i === step ? '#e1e4e8' : i < step ? '#484f58' : '#30363d',
            fontWeight: i === step ? 600 : 400,
            transition: 'color 0.3s',
          }}>
            <span style={{
              display: 'inline-block', width: 16, height: 16, borderRadius: '50%',
              background: i === step ? '#58a6ff' : i < step ? '#238636' : '#21262d',
              fontSize: 9, lineHeight: '16px', textAlign: 'center',
              color: i < step ? '#fff' : 'transparent',
              transition: 'background 0.3s',
            }}>
              {i < step ? '✓' : ''}
            </span>
            <span style={{ whiteSpace: 'nowrap' }}>{s}</span>
          </div>
        ))}
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
