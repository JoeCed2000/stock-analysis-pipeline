import { useState, useEffect, useRef } from 'react';
import { getTickerDownloadUrl, getDossierStatus, countDossierSections, fetchQuarters } from '../api.js';
import ScoringChart from './ScoringChart.jsx';
import FeedbackPanel from './FeedbackPanel.jsx';

const SCORE_COLORS = {
  BUY: '#238636',
  'HOLD / BUY ON PULLBACK': '#d29922',
  'HOLD fragile': '#d29922',
  'SELL or AVOID': '#da3633',
};

const CONVICTION_COLORS = {
  High: '#238636',
  Moderate: '#d29922',
  Low: '#da3633',
};

function getConvictionLevel(conviction, scoring) {
  // Use scoring for language-agnostic classification
  // Falls back to string matching for backward compat
  if (scoring?.total >= 32) return 'High';
  if (scoring?.total >= 26) return 'Moderate';
  if (scoring?.total < 18) return 'Low';
  // Fallback: string matching (EN only)
  if (!conviction) return 'Moderate';
  const c = conviction.toLowerCase();
  if (c.includes('high') || c.includes('strong')) return 'High';
  if (c.includes('low') || c.includes('weak') || c.includes('fragile')) return 'Low';
  return 'Moderate';
}

function getInsight(scoring, t) {
  if (!scoring) return null;
  const s = scoring;
  const key = (() => {
    if (s.business_momentum >= 4) return 'insight_momentum';
    if (s.valuation_risk <= 2 && s.business_momentum >= 3) return 'insight_undervalued';
    if (s.financial_strength >= 4 && s.profitability >= 4) return 'insight_fundamentals';
    if (s.moat >= 4) return 'insight_moat';
    if (s.management >= 4) return 'insight_management';
    if (s.growth >= 4 && s.business_momentum >= 3) return 'insight_growth';
    if (s.valuation_risk <= 2) return 'insight_valuation_concern';
    if (s.geopolitical_risk <= 2) return 'insight_geopolitical';
    return 'insight_mixed';
  })();
  return t ? t(key) : key;
}

export function canDownloadDossier(status, countdown) {
  return Boolean(
    status?.ready === true
    && status?.verified === true
    && status?.download_enabled === true
    && countdown <= 0
  );
}

export default function AnalysisCard({ result, onViewReport, t, lang }) {
  const { ticker, company_name, decision, scoring, conviction,
          price_native, currency, price_eur, market_cap, sector, retrieved_at } = result || {};

  if (!result) return null;

  const color = SCORE_COLORS[decision] || '#8b949e';
  const total = scoring?.total || 0;
  const level = getConvictionLevel(conviction, scoring);
  const convictionColor = CONVICTION_COLORS[level];
  const insight = getInsight(scoring, t);

  // ── Dossier polling ──
  const [dossierStatus, setDossierStatus] = useState({ sectionsReady: 0, pollFailures: 0 });
  const [countdown, setCountdown] = useState(null);
  const [downloadState, setDownloadState] = useState('idle'); // idle | downloading | success | error
  const pollRef = useRef(null);
  const countdownRef = useRef(null);
  const failedPollsRef = useRef(0);
  const downloadTimerRef = useRef(null);
  const ESTIMATED_SECS = 5; // dossier is now synchronous — ready in <5s

  // ── Quarter selector ──
  const [quarters, setQuarters] = useState([]);
  const [selectedQuarter, setSelectedQuarter] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchQuarters(ticker).then(data => {
      if (!cancelled) {
        const qs = (data.quarters || []).slice(0, 4);
        setQuarters(qs);
        if (qs.length > 0) setSelectedQuarter(qs[0]);
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [ticker]);

  useEffect(() => {
    let cancelled = false;
    let poles = 0;
    const poll = async () => {
      try {
        const status = await getDossierStatus(ticker);
        if (!cancelled) {
          failedPollsRef.current = 0;
          poles++;
          const sectionCount = countDossierSections(status.files || []);
          setDossierStatus({ ...status, sectionsReady: sectionCount, poles, pollFailures: 0 });
          // Stop polling only after a terminal verification state or timeout.
          const terminalVerification = status.download_enabled === true
            || (status.ready === true && status.deep_dive_validated === false);
          if ((terminalVerification && countdownRef.current <= 0) || poles >= 30) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch (error) {
        failedPollsRef.current += 1;
        console.warn('Dossier status poll failed', error);
        if (!cancelled) {
          setDossierStatus(prev => ({
            ...(prev || {}),
            sectionsReady: prev?.sectionsReady ?? 0,
            pollFailures: failedPollsRef.current,
          }));
        }
      }
    };
    poll(); // immediate
    pollRef.current = setInterval(poll, 5000); // every 5s
    return () => { cancelled = true; clearInterval(pollRef.current); };
  }, [ticker]);

  // Countdown timer — starts on first non-empty status, counts down from ESTIMATED_SECS
  useEffect(() => {
    if (dossierStatus && dossierStatus.sectionsReady > 0 && countdown === null) {
      setCountdown(ESTIMATED_SECS);
    }
  }, [dossierStatus, countdown]);

  useEffect(() => {
    if (countdown === null || countdown <= 0) return;
    countdownRef.current = countdown;
    const timer = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // Cleanup download timer on unmount
  useEffect(() => {
    return () => { if (downloadTimerRef.current) clearTimeout(downloadTimerRef.current); };
  }, []);

  const scorePercent = (total / 40) * 100;
  const scoreBarColor = total >= 32 ? '#238636' : total >= 26 ? '#d29922' : '#da3633';
  const downloadReady = canDownloadDossier(dossierStatus, countdown);
  const verificationBlocked = dossierStatus?.ready === true
    && dossierStatus?.verified === false
    && countdown <= 0;

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #21262d',
      borderRadius: 10, padding: 0, width: '100%',
      boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
      transition: 'box-shadow 0.2s, transform 0.15s',
      overflow: 'hidden',
    }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.5)'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.3)'; }}
    >
      {/* ── HEADER ── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '10px 14px 8px', borderBottom: '1px solid #21262d',
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#e1e4e8', letterSpacing: 0.5 }}>
            {ticker}
          </div>
          <div style={{ fontSize: 9, color: '#8b949e', marginTop: 1 }}>
            {company_name}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* Quarter selector */}
          {quarters.length > 1 && (
            <select
              value={selectedQuarter || quarters[0]}
              onChange={e => setSelectedQuarter(e.target.value)}
              style={{
                background: '#161b22', border: '1px solid #30363d',
                borderRadius: 4, color: '#58a6ff', fontSize: 9,
                fontWeight: 500, padding: '2px 4px', cursor: 'pointer',
                outline: 'none', maxWidth: 68,
              }}
            >
              {quarters.map(q => (
                <option key={q} value={q}>{q}</option>
              ))}
            </select>
          )}
          <div style={{
            padding: '3px 8px', borderRadius: 5, fontSize: 10, fontWeight: 800,
            background: color, color: '#fff',
            letterSpacing: 0.5,
          }}>
            {t(decision) || decision}
          </div>
        </div>
      </div>

      {/* ── SCORE (compact) ── */}
      <div style={{ padding: '10px 14px 8px', textAlign: 'center' }}>
        <div style={{ fontSize: 24, fontWeight: 800, color: scoreBarColor, lineHeight: 1 }}>
          {total}<span style={{ fontSize: 12, fontWeight: 400, color: '#8b949e' }}>/40</span>
        </div>
        <div style={{ fontSize: 8, color: '#484f58', marginTop: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
          Composite Score
        </div>
        {/* Score bar */}
        <div style={{
          marginTop: 6, background: '#161b22', borderRadius: 3, height: 4, overflow: 'hidden',
        }}>
          <div style={{
            width: `${scorePercent}%`, height: '100%',
            background: scoreBarColor, borderRadius: 3,
            transition: 'width 0.6s ease',
          }} />
        </div>
      </div>

      {/* ── KEY METRICS (compact) ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
        gap: 0, borderTop: '1px solid #21262d', borderBottom: '1px solid #21262d',
      }}>
        <MetricBox label="Price" value={price_native ? `${price_native.toFixed(0)} ${currency}` : '—'} />
        <MetricBox label="Mkt Cap" value={market_cap ? `${(market_cap / 1e12).toFixed(1)}T` : '—'} border />
        <MetricBox label="Sector" value={sector || '—'} />
        <MetricBox label="Retrieved" value={retrieved_at ? new Date(retrieved_at).toLocaleString('en-GB', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) : '—'} border />
      </div>

      {/* ── AI INSIGHT ── */}
      {insight && (
        <div style={{
          padding: '6px 14px', fontSize: 10, color: '#8b949e',
          background: '#161b22', borderBottom: '1px solid #21262d',
          fontStyle: 'italic',
        }}>
          {insight}
        </div>
      )}

      {/* ── CHART ── */}
      <div style={{ padding: '8px 14px 4px' }}>
        <ScoringChart scoring={scoring} height={90} />
      </div>

      {/* ── ACTIONS ── */}
      <div style={{ padding: '8px 14px 6px', display: 'flex', gap: 6 }}>
        <button
          onClick={() => onViewReport(result)}
          style={{
            flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500,
            background: '#21262d', border: '1px solid #30363d',
            borderRadius: 5, color: '#58a6ff', cursor: 'pointer',
            transition: 'background 0.15s',
          }}
          onMouseEnter={e => e.target.style.background = '#30363d'}
          onMouseLeave={e => e.target.style.background = '#21262d'}
        >
          📄 {t('viewFullReport')}
        </button>
        {downloadReady ? (
          <button
            onClick={async () => {
              if (downloadState === 'downloading') return;
              setDownloadState('downloading');
              const url = getTickerDownloadUrl(ticker, lang, selectedQuarter);
              try {
                const resp = await fetch(url);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const blob = await resp.blob();
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = `${ticker}_dossier.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
                setDownloadState('success');
                if (downloadTimerRef.current) clearTimeout(downloadTimerRef.current);
                downloadTimerRef.current = setTimeout(() => setDownloadState('idle'), 3000);
              } catch (err) {
                console.error('Download failed:', err);
                setDownloadState('error');
                if (downloadTimerRef.current) clearTimeout(downloadTimerRef.current);
                downloadTimerRef.current = setTimeout(() => setDownloadState('idle'), 5000);
              }
            }}
            style={{
              flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500,
              background: downloadState === 'success' ? '#238636'
                : downloadState === 'error' ? '#da3633'
                : downloadState === 'downloading' ? '#1f6feb'
                : '#238636',
              border: downloadState === 'success' ? '1px solid #2ea043'
                : downloadState === 'error' ? '1px solid #f85149'
                : downloadState === 'downloading' ? '1px solid #388bfd'
                : '1px solid #2ea043',
              borderRadius: 5, color: '#fff', cursor: downloadState === 'downloading' ? 'wait' : 'pointer',
              textDecoration: 'none', textAlign: 'center',
              transition: 'background 0.15s, border 0.15s', fontFamily: 'inherit',
            }}
            onMouseEnter={e => {
              if (downloadState === 'success') e.target.style.background = '#2ea043';
              else if (downloadState === 'error') e.target.style.background = '#f85149';
              else if (downloadState !== 'downloading') e.target.style.background = '#2ea043';
            }}
            onMouseLeave={e => {
              if (downloadState === 'success') e.target.style.background = '#238636';
              else if (downloadState === 'error') e.target.style.background = '#da3633';
              else if (downloadState === 'downloading') e.target.style.background = '#1f6feb';
              else e.target.style.background = '#238636';
            }}
          >
            {downloadState === 'downloading' ? t('downloadingDossier')
              : downloadState === 'success' ? t('downloadComplete')
              : downloadState === 'error' ? t('downloadFailed')
              : `${t('downloadDossier')} (${dossierStatus?.sectionsReady ?? '?'}/7)`}
          </button>
        ) : verificationBlocked ? (
          <div style={{
            flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500,
            background: '#3d1f1f', border: '1px solid #6b3030',
            borderRadius: 5, color: '#f85149', textAlign: 'center',
          }}>
            ⚠️ {lang === 'ja' ? '検証失敗' : 'Verification failed'} · {dossierStatus?.sectionsReady ?? '?'}/7
          </div>
        ) : (
          <div style={{
            flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500,
            background: '#161b22', border: '1px solid #30363d',
            borderRadius: 5, color: '#8b949e', textAlign: 'center',
          }}>
            {countdown > 0
              ? `⏳ ${countdown}s · ${dossierStatus?.sectionsReady ?? '?'}/7`
              : `${t('buildingDossier')} ${dossierStatus?.sectionsReady ?? '?'}/7`}
            {dossierStatus?.estimated_seconds > 0 && (
              <span style={{ display: 'block', fontSize: 9, color: '#484f58', marginTop: 2 }}>
                {lang === 'ja' ? t('estimatedSingle') : t('estimatedSingle')}
              </span>
            )}
            {dossierStatus?.pollFailures >= 3 && (
              <span style={{ display: 'block', fontSize: 9, color: '#d29922', marginTop: 2 }}>
                {lang === 'ja' ? 'ステータス再試行中' : 'Retrying status'}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── CONVICTION ── */}
      <div style={{
        padding: '4px 14px 10px', textAlign: 'center',
      }}>
        <span style={{
          display: 'inline-block', padding: '2px 8px', borderRadius: 3,
          fontSize: 8, fontWeight: 700,
          background: `${convictionColor}20`, color: convictionColor,
          border: `1px solid ${convictionColor}40`,
          textTransform: 'uppercase', letterSpacing: 0.5,
        }}>
          {t(level)} {t('conviction')}
        </span>
      </div>

      {/* ── NAMI FEEDBACK ── */}
      <FeedbackPanel ticker={result.ticker} t={t} lang={lang} />
    </div>
  );
}

function MetricBox({ label, value, border }) {
  return (
    <div style={{
      textAlign: 'center', padding: '5px 4px',
      borderLeft: border ? '1px solid #21262d' : 'none',
      borderRight: border ? '1px solid #21262d' : 'none',
    }}>
      <div style={{ fontSize: 8, color: '#484f58', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 1 }}>
        {label}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: '#e1e4e8' }}>
        {value}
      </div>
    </div>
  );
}
