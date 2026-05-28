const STEP_KEYS = ['step_fetching', 'step_ratios', 'step_scoring', 'step_insights'];

const PHASE_TO_STEP = {
  idle: 0,
  queued: 0,
  fetching: 1,
  generating: 2,
  finalizing: 3,
  done: 3,
  error: 3,
};

const PHASE_LABEL_FALLBACK = {
  idle: 'Idle',
  queued: 'Queued',
  fetching: 'Fetching financial data',
  generating: 'Generating analysis',
  finalizing: 'Finalizing dossier',
  done: 'Completed',
  error: 'Error',
};

const PHASE_BASE_PERCENT = {
  idle: 0,
  queued: 8,
  fetching: 35,
  generating: 65,
  finalizing: 85,
  done: 100,
  error: 100,
};

const ACTIVITIES_BY_PHASE = {
  queued: ['act_init'],
  fetching: ['act_fetch_is', 'act_fetch_bs', 'act_fetch_cf', 'act_parse_docs'],
  generating: ['act_calc_ratios', 'act_compare_peers', 'act_score_growth', 'act_score_momentum'],
  finalizing: ['act_score_value', 'act_score_profit', 'act_prep_insights', 'act_finalize'],
  done: ['act_finalize'],
  error: ['act_finalize'],
};

const PHASE_ORDER = ['queued', 'fetching', 'generating', 'finalizing', 'done'];

function clampPercent(value) {
  if (value == null || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export default function SmartLoader({
  total,
  current,
  ticker,
  companyName,
  phase = 'queued',
  phaseText = '',
  percent = null,
  t,
}) {
  const safePhase = PHASE_TO_STEP[phase] != null ? phase : 'queued';
  const step = PHASE_TO_STEP[safePhase];

  const explicitPct = clampPercent(percent);
  const fallbackPct = clampPercent(
    total > 0 ? (current / total) * 100 : PHASE_BASE_PERCENT[safePhase],
  );
  const pct = percent == null ? fallbackPct : explicitPct;

  const phaseLabel = phaseText || t?.(safePhase) || PHASE_LABEL_FALLBACK[safePhase] || PHASE_LABEL_FALLBACK.queued;

  const phaseRank = PHASE_ORDER.indexOf(safePhase);
  const doneActs = [];
  for (let i = 0; i < Math.max(0, phaseRank); i += 1) {
    const p = PHASE_ORDER[i];
    doneActs.push(...(ACTIVITIES_BY_PHASE[p] || []));
  }

  const currentActs = ACTIVITIES_BY_PHASE[safePhase] || ACTIVITIES_BY_PHASE.queued;
  const activeAct = currentActs[0] || '';

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #21262d',
      borderRadius: 12, padding: '40px 28px', marginTop: 20,
      maxWidth: 560, margin: '20px auto 0',
    }}>
      {/* ── Ticker / Company Name ── */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 13, color: '#8b949e', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
          {ticker ? (t?.('currentTicker') || 'Current ticker') : (t?.('loading') || 'Loading')}
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

      {/* ── Phase indicator ── */}
      <div style={{
        fontSize: 15, color: '#e1e4e8', fontWeight: 600,
        marginBottom: 20,
      }}>
        {t?.('stepLabel', { step: step + 1, total: STEP_KEYS.length }) || `Step ${step + 1} of ${STEP_KEYS.length}`}
        <span style={{ fontSize: 13, color: '#8b949e', fontWeight: 400, marginLeft: 10 }}>
          — {phaseLabel}
        </span>
      </div>

      {/* ── Progress bar ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          fontSize: 12, color: '#8b949e', marginBottom: 6,
        }}>
          <span>{current} / {total} {t?.('tickersProcessed') || 'tickers processed'}</span>
          <span>{pct}%</span>
        </div>
        <div style={{
          background: '#161b22', borderRadius: 6, height: 8,
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${pct}%`, height: '100%',
            background: 'linear-gradient(90deg, #1f6feb, #58a6ff)',
            borderRadius: 6,
            transition: 'width 0.5s ease',
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
          const isDone = i < step;
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 11,
              color: isCurrent ? '#e1e4e8' : isDone ? '#8b949e' : '#6e7681',
              fontWeight: isCurrent ? 600 : 400,
              transition: 'color 0.3s',
              flex: 1, justifyContent: 'center',
            }}>
              <span style={{
                display: 'inline-block', width: 14, height: 14, borderRadius: '50%',
                background: isCurrent ? '#58a6ff' : isDone ? '#1f6feb' : '#30363d',
                transition: 'background 0.3s',
                flexShrink: 0,
              }} />
              <span style={{
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                maxWidth: 72,
              }}>{t?.(key) || key}</span>
            </div>
          );
        })}
      </div>

      {/* ── Activity log ── */}
      <div style={{
        background: '#161b22', borderRadius: 8,
        border: '1px solid #21262d',
        padding: '14px 16px', marginBottom: 16,
      }}>
        <div style={{ fontSize: 11, color: '#484f58', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
          {t?.('activityLog') || 'Activity log'}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {[...doneActs, ...currentActs].map((key) => {
            const isDone = doneActs.includes(key);
            const isActive = !isDone && key === activeAct;
            return (
              <div key={`${key}-${isDone ? 'done' : 'active'}`} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 12,
                color: isActive ? '#e1e4e8' : isDone ? '#8b949e' : '#484f58',
                fontWeight: isActive ? 500 : 400,
              }}>
                <span style={{
                  fontSize: 12, width: 16, textAlign: 'center', flexShrink: 0,
                  color: isActive ? '#58a6ff' : isDone ? '#58a6ff' : '#30363d',
                }}>
                  {isDone ? '●' : isActive ? '●' : '·'}
                </span>
                <span>{t?.(key) || key}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Pulse / still-alive indicator ── */}
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8,
        color: '#484f58', fontSize: 11, marginBottom: 8,
      }}>
        <span style={{
          display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
          background: '#58a6ff',
          animation: 'pulse-dot 1.2s ease-in-out infinite',
        }} />
        <span>{t?.('sourcesIncluded') || 'Sources and calculations will be included in the final report'}</span>
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
