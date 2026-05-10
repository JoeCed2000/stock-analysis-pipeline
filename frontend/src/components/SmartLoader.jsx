import { useState, useEffect } from 'react';

const STEP_KEYS = ['step_fetching', 'step_ratios', 'step_scoring', 'step_insights'];

// Activity log entries — cycled through to give a live feel
const ACTIVITY_KEYS = [
  ['act_init', 'act_fetch_is', 'act_fetch_bs', 'act_fetch_cf'],
  ['act_fetch_filings', 'act_fetch_estimates', 'act_fetch_sources', 'act_parse_docs'],
  ['act_calc_ratios', 'act_compare_peers', 'act_score_growth', 'act_score_momentum'],
  ['act_score_value', 'act_score_profit', 'act_prep_insights', 'act_finalize'],
];

export default function SmartLoader({ total, current, ticker, companyName, t }) {
  const [step, setStep] = useState(0);
  const [activityIdx, setActivityIdx] = useState(0);
  const [doneActs, setDoneActs] = useState(new Set());

  // Cycle steps
  useEffect(() => {
    const interval = setInterval(() => {
      setStep(s => (s + 1) % STEP_KEYS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  // Cycle activity items within current step
  useEffect(() => {
    const acts = ACTIVITY_KEYS[step % ACTIVITY_KEYS.length] || [];
    setActivityIdx(0);
    setDoneActs(new Set()); // reset on step change

    if (acts.length <= 1) {
      setDoneActs(new Set(acts));
      return;
    }

    let idx = 0;
    const interval = setInterval(() => {
      idx++;
      if (idx >= acts.length) {
        clearInterval(interval);
        setDoneActs(new Set(acts));
      } else {
        setActivityIdx(idx);
        setDoneActs(prev => new Set([...prev, acts[idx - 1]]));
      }
    }, 1200);
    return () => clearInterval(interval);
  }, [step]);

  const pct = total > 0 ? Math.min(Math.round((current / total) * 100), 99) : 0;
  const currentActs = ACTIVITY_KEYS[step % ACTIVITY_KEYS.length] || [];
  const activeAct = currentActs[activityIdx] || currentActs[currentActs.length - 1] || '';

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #21262d',
      borderRadius: 12, padding: '40px 28px', marginTop: 20,
      maxWidth: 560, margin: '20px auto 0',
    }}>
      {/* ── Ticker / Company Name ── */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
          {ticker ? t('currentTicker') || 'Current ticker' : t('loading')}
        </div>
        {ticker && (
          <div style={{ fontSize: 26, fontWeight: 700, color: '#e1e4e8' }}>
            <span style={{ color: '#58a6ff' }}>{ticker}</span>
            {companyName && (
              <span style={{ fontSize: 16, fontWeight: 400, color: '#8b949e', marginLeft: 10 }}>
                — {companyName}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Step indicator ── */}
      <div style={{
        fontSize: 15, color: '#e1e4e8', fontWeight: 600,
        marginBottom: 20,
      }}>
        {t('stepLabel', { step: step + 1, total: STEP_KEYS.length }) || `Step ${step + 1} of ${STEP_KEYS.length}`}
        <span style={{ fontSize: 13, color: '#8b949e', fontWeight: 400, marginLeft: 10 }}>
          — {t(currentActs[activityIdx] || STEP_KEYS[step])}
        </span>
      </div>

      {/* ── Progress bar ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          fontSize: 12, color: '#8b949e', marginBottom: 6,
        }}>
          <span>{current} / {total} {t('tickersProcessed') || 'tickers processed'}</span>
          <span>{t('estimatedDuration') || 'Est. 3–5 min'}</span>
        </div>
        <div style={{
          background: '#161b22', borderRadius: 6, height: 8,
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${pct}%`, height: '100%',
            background: 'linear-gradient(90deg, #1f6feb, #58a6ff)',
            borderRadius: 6,
            transition: 'width 0.6s ease',
          }} />
        </div>
      </div>

      {/* ── Workflow steps ── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        marginBottom: 28, gap: 4,
      }}>
        {STEP_KEYS.map((key, i) => {
          const isCurrent = i === step;
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 11,
              color: isCurrent ? '#e1e4e8' : '#8b949e',
              fontWeight: isCurrent ? 600 : 400,
              transition: 'color 0.3s',
              flex: 1, justifyContent: 'center',
            }}>
              <span style={{
                display: 'inline-block', width: 14, height: 14, borderRadius: '50%',
                background: isCurrent ? '#58a6ff' : '#30363d',
                transition: 'background 0.3s',
                flexShrink: 0,
              }} />
              <span style={{
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                maxWidth: 70,
              }}>{t(key)}</span>
            </div>
          );
        })}
      </div>

      {/* ── Live activity log ── */}
      <div style={{
        background: '#161b22', borderRadius: 8,
        border: '1px solid #21262d',
        padding: '14px 16px', marginBottom: 16,
      }}>
        <div style={{ fontSize: 11, color: '#484f58', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          {t('activityLog') || 'Activity log'}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {currentActs.map((key, i) => {
            const isDone = doneActs.has(key);
            const isActive = !isDone && key === activeAct;
            return (
              <div key={key} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 12,
                color: isActive ? '#e1e4e8' : isDone ? '#8b949e' : '#484f58',
                fontWeight: isActive ? 500 : 400,
                transition: 'color 0.3s',
              }}>
                <span style={{
                  fontSize: 12, width: 16, textAlign: 'center', flexShrink: 0,
                  color: isActive ? '#58a6ff' : isDone ? '#58a6ff' : '#30363d',
                }}>
                  {isDone ? '●' : isActive ? '●' : '·'}
                </span>
                <span>{t(key)}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Pulse / Still alive indicator + footer ── */}
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8,
        color: '#484f58', fontSize: 11, marginBottom: 8,
      }}>
        <span style={{
          display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
          background: '#58a6ff',
          animation: 'pulse-dot 1.2s ease-in-out infinite',
        }} />
        <span>{t('sourcesIncluded') || 'Sources and calculations will be included in the final report'}</span>
      </div>

      <style>{`
        @keyframes pulse-dot {
          0%, 100% { opacity: 0.25; transform: scale(0.8); }
          50%      { opacity: 1;    transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}
