import { useState, useEffect } from 'react';
import TickerInput from './components/TickerInput.jsx';
import BatchAnalysis from './components/BatchAnalysis.jsx';
import AnalysisCard from './components/AnalysisCard.jsx';
import SmartLoader from './components/SmartLoader.jsx';
import SkeletonCard from './components/SkeletonCard.jsx';
import AboutSection from './components/AboutSection.jsx';
import LanguageSelector from './components/LanguageSelector.jsx';
import AdminPage from './components/AdminPage.jsx';
import FeedbackPage from './components/FeedbackPage.jsx';
import ChatWidget from './components/ChatWidget.jsx';
import NotFound from './components/NotFound.jsx';
import { analyzeTickersAsync, getJobStatus, getDossierStatus, countDossierSections, testSeekingAlphaAccess } from './api.js';
import translations from './i18n.js';
import SearchMonitor from './components/SearchMonitor.jsx';
import AuroraBackground from './components/AuroraBackground.jsx';
// BUILD: v3 — explicit loading state machine, no fake timer progress
const API_BASE = import.meta.env.VITE_API_URL || '/api';

const INITIAL_PROGRESS = {
  current: 0,
  total: 0,
  ticker: '',
  companyName: '',
  phase: 'idle',
  phaseText: '',
  percent: 0,
};

function deriveJobPhase(progressText = '') {
  const text = String(progressText || '').toLowerCase();
  if (text.includes('deep-dive') || text.includes('pdf')) {
    return { phase: 'generating', percent: 68, phaseText: progressText };
  }
  if (text.includes('start') || text.includes('analysis')) {
    return { phase: 'fetching', percent: 35, phaseText: progressText };
  }
  return { phase: 'fetching', percent: 42, phaseText: progressText || 'Processing analysis…' };
}

export default function App() {
  const [mode, setMode] = useState('single');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dossierPhase, setDossierPhase] = useState(false); // true when building dossier after analysis
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(INITIAL_PROGRESS);
  const [showAdmin, setShowAdmin] = useState(() => window.location.hash === '#admin');
  const [showFeedback, setShowFeedback] = useState(() => window.location.hash === '#feedback');
  const [saAccess, setSaAccess] = useState({ loading: true, configured: null, error: null });
  const [show404, setShow404] = useState(() => {
    const h = window.location.hash;
    return h && h !== '#admin' && h !== '#feedback';
  });

  useEffect(() => {
    const onHashChange = () => {
      const h = window.location.hash;
      setShowAdmin(h === '#admin');
      setShowFeedback(h === '#feedback');
      setShow404(Boolean(h) && h !== '#admin' && h !== '#feedback');
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  const [lang, setLang] = useState(() => {
    // Persist language across refreshes
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('lang');
      if (saved && translations[saved]) return saved;
    }
    return 'jp';
  });

  const [audienceMode] = useState(() => {
    // Clear stale manual/persona selector state; chat identity is visitor_id-based.
    if (typeof window !== 'undefined') {
      localStorage.removeItem('audienceMode');
    }
    return 'client_report';
  });

  const handleLanguageChange = (newLang) => {
    setLang(newLang);
    if (typeof window !== 'undefined') {
      localStorage.setItem('lang', newLang);
    }
  };

  useEffect(() => {
    if (show404) {
      setSaAccess({ loading: false, configured: null, error: null });
      return undefined;
    }

    let alive = true;

    const refreshSeekingAlphaStatus = async () => {
      try {
        // Use the TEST endpoint for real connectivity check, not just cookie presence.
        // The server-side probe is public/read-only and never exposes cookie values;
        // poll it on the homepage because that is where the SA badge is rendered.
        const data = await testSeekingAlphaAccess();
        if (!alive) return;
        setSaAccess({
          loading: false,
          configured: !!data?.configured,
          authenticated: !!data?.authenticated,
          ok: !!data?.ok,
          statusCode: data?.status_code,
          error: null,
        });
      } catch (err) {
        if (!alive) return;
        setSaAccess({ loading: false, configured: null, authenticated: false, ok: false, error: err?.message || 'status_error' });
      }
    };

    refreshSeekingAlphaStatus();
    const timer = setInterval(refreshSeekingAlphaStatus, 60000);

    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [show404]);

  const t = (key, params) => {
    let str = translations[lang]?.[key] || translations.en[key] || key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        str = str.replaceAll(`{${k}}`, v);
      }
    }
    return str;
  };

  const showToast = (text, ttlMs = 5000) => {
    const toast = document.createElement('div');
    toast.style.cssText = 'position:fixed;top:20px;right:20px;background:rgba(11,18,33,0.9);backdrop-filter:blur(12px);border:1px solid rgba(125,155,195,0.3);color:#e7edf6;padding:12px 18px;border-radius:12px;z-index:9999;font-size:13px;box-shadow:0 12px 40px rgba(2,6,14,0.6)';
    toast.textContent = text;
    document.body.appendChild(toast);
    if (ttlMs) setTimeout(() => toast.remove(), ttlMs);
    return toast;
  };

  const handleViewReport = async (result) => {
    const params = new URLSearchParams();
    if (lang === 'jp') params.set('lang', 'jp');
    params.set('audience_mode', audienceMode);
    const qs = params.toString();
    const pdfUrl = `${API_BASE}/report/${result.ticker}/pdf${qs ? '?' + qs : ''}`;

    // Claim the tab synchronously, inside the user gesture: a window.open that
    // runs after an await is swallowed by popup blockers. 'noopener' is NOT
    // passed here because it forces window.open to return null, which would
    // both lose the handle and fire a false "allow pop-ups" warning — the
    // opener is severed manually instead.
    const reportWindow = window.open('', '_blank');
    if (!reportWindow) {
      showToast(`⚠️ Allow pop-ups to open the ${result.ticker} report`, 7000);
      return;
    }
    reportWindow.opener = null;

    const showInTab = (message) => {
      try {
        reportWindow.document.title = `${result.ticker} — deep dive`;
        reportWindow.document.body.style.cssText = 'margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:#0b1221;color:#e7edf6;font:14px system-ui,sans-serif';
        reportWindow.document.body.textContent = message;
      } catch { /* tab navigated away or closed by the user */ }
    };
    const closeTab = () => { try { reportWindow.close(); } catch { /* already closed */ } };
    const openBlob = async (res) => {
      const blob = await res.blob();
      reportWindow.location.replace(URL.createObjectURL(blob));
    };

    showInTab(`Generating deep-dive for ${result.ticker}…`);

    try {
      const checkRes = await fetch(pdfUrl);
      if (checkRes.status === 200) {
        await openBlob(checkRes);
        return;
      }
      if (checkRes.status === 422) {
        let detail = null;
        try { detail = await checkRes.json(); } catch { detail = null; }
        closeTab();
        showToast(`⛔ PDF blocked for ${result.ticker}: ${detail?.detail?.message || 'validation failed'}`, 9000);
        return;
      }
      if (checkRes.status !== 202) {
        closeTab();
        showToast(`⚠️ Report not available for ${result.ticker} (${checkRes.status})`);
        return;
      }

      // 202 — generation in progress. Poll with a hard cap so a stuck backend
      // cannot spin the tab forever (WIKI 2026-05-31 PDF_BLOCKED contract).
      const toast = showToast(`📊 Generating deep-dive for ${result.ticker}...`, 0);
      const MAX_PDF_POLL_ATTEMPTS = 36; // 36 * 5s = 3 min cap for transient generation
      let pollAttempts = 0;
      const poll = async () => {
        pollAttempts += 1;
        let res;
        try {
          res = await fetch(pdfUrl);
        } catch {
          closeTab();
          toast.textContent = `⚠️ Cannot reach report for ${result.ticker}`;
          setTimeout(() => toast.remove(), 5000);
          return;
        }
        if (res.status === 200) {
          toast.textContent = `✅ Deep-dive ready for ${result.ticker}`;
          setTimeout(() => toast.remove(), 2000);
          await openBlob(res);
        } else if (res.status === 422) {
          let detail = null;
          try { detail = await res.json(); } catch { detail = null; }
          closeTab();
          toast.textContent = `⛔ PDF blocked for ${result.ticker}: ${detail?.detail?.message || 'validation failed'}`;
          setTimeout(() => toast.remove(), 9000);
        } else if (res.status === 202 && pollAttempts < MAX_PDF_POLL_ATTEMPTS) {
          setTimeout(poll, 5000);
        } else if (res.status === 202) {
          closeTab();
          toast.textContent = `⏱️ PDF generation timed out for ${result.ticker}`;
          setTimeout(() => toast.remove(), 9000);
        } else {
          closeTab();
          toast.textContent = `❌ Failed to generate deep-dive for ${result.ticker}`;
          setTimeout(() => toast.remove(), 5000);
        }
      };
      setTimeout(poll, 3000);
    } catch {
      closeTab();
      showToast(`⚠️ Cannot reach report for ${result.ticker}`);
    }
  };

  const handleAnalyze = async (tickers) => {
    setLoading(true);
    setDossierPhase(false);
    setError(null);
    setResults([]);

    const normalizedTickers = (tickers || [])
      .map((tk) => String(tk || '').trim().toUpperCase())
      .filter(Boolean);
    const total = normalizedTickers.length;

    if (total === 0) {
      setLoading(false);
      return;
    }

    setProgress({
      ...INITIAL_PROGRESS,
      current: 0,
      total,
      ticker: normalizedTickers[0],
      phase: 'queued',
      phaseText: 'Queued…',
      percent: 8,
    });

    try {
      // Submit async job — returns immediately with job_id
      const { job_id } = await analyzeTickersAsync(normalizedTickers, lang);
      setProgress((p) => ({
        ...p,
        phase: 'fetching',
        phaseText: 'Starting analysis…',
        percent: Math.max(p.percent, 20),
      }));

      // Poll until done (max 20 min). JP deep-dive dossiers can exceed 10 min
      // because the pipeline generates EN + JP reports and validates both.
      const MAX_POLLS = 400; // 400 * 3s = 20 min
      let timedOut = true;
      for (let i = 0; i < MAX_POLLS; i += 1) {
        await new Promise((r) => setTimeout(r, 3000));
        try {
          const job = await getJobStatus(job_id);

          if (job.status === 'done') {
            timedOut = false;
            const data = job.result;
            if (data?.errors?.length > 0) {
              setError(`Errors: ${data.errors.join(', ')}`);
            }

            // Don't show cards yet — wait for dossier to be fully built
            const resultsList = data?.results || [];
            const resultsCount = Math.max(resultsList.length, 1);
            setDossierPhase(true);
            setProgress((p) => ({
              ...p,
              current: 0,
              total: resultsList.length || p.total,
              ticker: resultsList[0]?.ticker || p.ticker,
              phase: 'finalizing',
              phaseText: t('buildingDossier') || '📊 Building dossier…',
              percent: Math.max(p.percent, 78),
            }));

            // Poll dossier status for each ticker (wait up to 6 min)
            for (let idx = 0; idx < resultsList.length; idx += 1) {
              const r = resultsList[idx];
              let dossierReady = false;

              for (let d = 0; d < 120; d += 1) {
                await new Promise((r2) => setTimeout(r2, 3000));
                try {
                  const ds = await getDossierStatus(r.ticker);
                  if (ds?.phase === 'pdf_blocked' || ds?.deep_dive_validated === false) {
                    setProgress((p) => ({
                      ...p,
                      current: idx,
                      ticker: r.ticker,
                      phase: 'pdf_blocked',
                      phaseText: t('pdf_blocked') || 'PDF generation blocked — data validation failed',
                      percent: 100,
                    }));
                    const issues = Array.isArray(ds?.verification_issues) && ds.verification_issues.length > 0
                      ? `: ${ds.verification_issues.join('; ')}`
                      : '';
                    setError(`PDF generation blocked for ${r.ticker}${issues}`);
                    return;
                  }

                  const sectionCount = countDossierSections(ds?.files || []);
                  const tickerProgress = (idx + Math.min(sectionCount, 7) / 7) / resultsCount;
                  const pct = 78 + (tickerProgress * 20);

                  setProgress((p) => ({
                    ...p,
                    current: idx,
                    ticker: r.ticker,
                    phase: 'finalizing',
                    phaseText: `📊 Building dossier… ${sectionCount}/7`,
                    percent: Math.max(p.percent, Math.min(98, pct)),
                  }));

                  if (ds && ds.verified) {
                    dossierReady = true;
                    setProgress((p) => ({
                      ...p,
                      current: idx + 1,
                      ticker: r.ticker,
                      phase: 'finalizing',
                      phaseText: `✅ ${r.ticker} dossier verified`,
                      percent: Math.max(p.percent, Math.min(99, 78 + (((idx + 1) / resultsCount) * 20))),
                    }));
                    break;
                  }
                } catch {
                  // transient — keep polling
                }
              }

              if (!dossierReady) {
                console.warn(`Dossier timeout for ${r.ticker} — showing card anyway`);
              }
            }

            setProgress((p) => ({
              ...p,
              current: resultsList.length,
              total: resultsList.length || p.total,
              phase: 'done',
              phaseText: 'Analysis complete',
              percent: 100,
            }));
            setResults(resultsList);
            setDossierPhase(false);
            break;
          }

          if (job.status === 'error') {
            setProgress((p) => ({
              ...p,
              phase: 'error',
              phaseText: job.error || 'Analysis failed',
              percent: 100,
            }));
            setError(job.error || 'Analysis failed');
            timedOut = false;
            break;
          }

          // Still processing — update phase from backend progress
          const phaseUpdate = deriveJobPhase(job.progress);
          setProgress((p) => ({
            ...p,
            phase: phaseUpdate.phase,
            phaseText: phaseUpdate.phaseText,
            percent: Math.max(p.percent, phaseUpdate.percent),
          }));
        } catch (pollErr) {
          // Transient network error during poll — keep trying
          console.warn('Poll error:', pollErr.message);
        }
      }

      if (timedOut) {
        setProgress((p) => ({
          ...p,
          phase: 'error',
          phaseText: 'Analysis timed out',
          percent: 100,
        }));
        setError('Analysis timed out after 20 minutes. The data may still be processing — try again or check back later.');
      }
    } catch (e) {
      setProgress((p) => ({
        ...p,
        phase: 'error',
        phaseText: e.message || 'Analysis failed',
        percent: 100,
      }));
      if (e.status === 422 && e.body) {
        setError(e.body?.detail?.message || e.message);
      } else {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  };


  return (
    <div className="app" style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px', position: 'relative', zIndex: 1 }}>
      <AuroraBackground />
      {show404 ? (
        <NotFound t={t} onBack={() => { window.location.hash = ''; }} />
      ) : showAdmin ? (
        <AdminPage t={t} onClose={() => { window.location.hash = ''; }} />
      ) : showFeedback ? (
        <FeedbackPage lang={lang} onClose={() => { window.location.hash = ''; }} />
      ) : (
      <>{/* Header — centered */}
      <div style={{ marginBottom: 28, textAlign: 'center' }}>
        <div className="reveal" style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: 26, gap: 8, flexWrap: 'wrap', '--d': '0.05s' }}>
          <button
            className="chip"
            onClick={() => { window.location.hash = '#feedback'; }}
            style={{
              padding: '8px 16px',
              fontSize: 12.5,
              fontWeight: 600,
              color: '#c9d5e4',
              cursor: 'pointer',
            }}
          >
            💬 Feedback
          </button>
          <span
            className="chip"
            title={saAccess.error || ''}
            style={{
              fontSize: 12,
              padding: '6px 12px',
              color: saAccess.loading
                ? '#8fa1b8'
                : saAccess.configured === true
                  ? '#3fb950'
                  : saAccess.configured === false
                    ? '#f85149'
                    : '#d29922',
            }}
          >
            {saAccess.loading
              ? 'SA: checking…'
              : saAccess.ok && saAccess.authenticated
                ? 'SA: connected ✅'
                : saAccess.configured === true
                  ? 'SA: expired ⚠️'
                  : saAccess.configured === false
                    ? 'SA: no cookies'
                    : 'SA: unknown'}
          </span>
          <LanguageSelector lang={lang} onLanguageChange={handleLanguageChange} />
        </div>

        <div className="reveal" style={{ marginBottom: 14, '--d': '0.15s' }}>
          <span className="hero-eyebrow">AI Equity Research</span>
        </div>
        <h1 className="hero-title reveal" style={{ marginBottom: 12, '--d': '0.25s' }}>
          {(() => {
            // Emoji cannot sit inside background-clip:text (it becomes a solid
            // gradient block), so split a leading emoji out of the gradient span.
            const raw = t('siteTitle');
            const m = raw.match(/^(\p{Extended_Pictographic}️?)\s*(.*)$/u);
            const emoji = m ? m[1] : null;
            const text = m ? m[2] : raw;
            return (
              <>
                {emoji && <span className="hero-emoji" aria-hidden="true">{emoji}</span>}
                <span className="grad">{text}</span>
              </>
            );
          })()}
        </h1>
        <p className="hero-sub reveal" style={{ '--d': '0.4s' }}>
          {t('siteSubtitle')}
        </p>

        {!loading && (
        <div className="reveal" style={{ marginTop: 18, '--d': '0.5s' }}>
          <AboutSection t={t} />
        </div>
        )}

        {/* Mode tabs — centered, hidden during analysis */}
        {!loading && (
        <div className="reveal" style={{
          display: 'flex', justifyContent: 'center', marginTop: 18, '--d': '0.55s',
        }}>
          <div className="mode-tabs">
            <button
              className={`mode-tab${mode === 'single' ? ' active' : ''}`}
              onClick={() => { setMode('single'); setResults([]); setError(null); }}
            >
              {t('quickAnalysis')}
            </button>
            <button
              className={`mode-tab${mode === 'batch' ? ' active' : ''}`}
              onClick={() => { setMode('batch'); setResults([]); setError(null); }}
            >
              {t('batchAnalysis')}
            </button>
          </div>
        </div>
        )}
      </div>

      {/* Single mode */}
      {mode === 'single' && (
        <div className="reveal" style={{ '--d': '0.65s' }}>
          <TickerInput onAnalyze={handleAnalyze} loading={loading} t={t} />
        </div>
      )}

      {/* Batch mode */}
      {mode === 'batch' && (
        <div className="reveal" style={{ '--d': '0.65s' }}>
          <BatchAnalysis onResultsReady={(results) => setResults(results)} t={t} />
        </div>
      )}

      {/* Smart loading */}
      {(loading || dossierPhase) && progress.total > 0 && (
        <>
          <SmartLoader
            total={progress.total}
            current={progress.current}
            ticker={progress.ticker}
            companyName={progress.companyName}
            phase={progress.phase}
            phaseText={progress.phaseText}
            percent={progress.percent}
            t={t}
          />

          <div style={{
            textAlign: 'center', color: '#8b949e', fontSize: 12,
            marginTop: 16, marginBottom: 8,
          }}>
            {dossierPhase ? t('buildingDossier') || '📊 Building dossier…' : t('analysisDuration')}
          </div>
        </>
      )}

      {error && (
        <div style={{
          background: 'rgba(218, 54, 51, 0.12)', border: '1px solid rgba(248, 81, 73, 0.45)',
          backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
          borderRadius: 12, padding: '12px 16px', marginTop: 16,
          color: '#f85149', fontSize: 13, textAlign: 'center',
          boxShadow: '0 0 24px rgba(248, 81, 73, 0.08)',
        }}>
          {error}
        </div>
      )}

      {/* Show skeletons during loading and dossier building */}
      {(loading || dossierPhase) && progress.total > 0 && (
        <div className="results-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 400px))', gap: 20, marginTop: 16, justifyContent: 'center' }}>
          {Array.from({ length: progress.total }, (_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {results.length > 0 && !dossierPhase && (
        <div className="results-grid" style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 400px))', gap: 20,
          marginTop: 16, justifyContent: 'center',
        }}>
          {results.map((r, i) => (
            <div key={r.ticker} style={{ animation: `fadeInUp 0.6s cubic-bezier(0.2, 0.7, 0.3, 1) ${i * 0.12}s both` }}>
              <AnalysisCard
                result={r}
                onViewReport={handleViewReport}
                t={t}
                lang={lang}
              />
            </div>
          ))}
        </div>
      )}

      <style>{`
        /* ── Responsive ── */
        @media (max-width: 768px) {
          .app { padding: 12px 8px !important; }
          .app .hero-title { font-size: 30px !important; }
          .app .mode-tabs { flex-wrap: wrap; }
          .app .mode-tabs button { padding: 7px 14px !important; font-size: 12px !important; }
          .results-grid { grid-template-columns: 1fr !important; }
        }

        @media (max-width: 480px) {
          .app { padding: 8px 4px !important; }
          .app .hero-title { font-size: 26px !important; }
          .app .hero-sub { font-size: 12px !important; }
        }
      `}</style>
      </>)}

      {/* Live Chat Widget — global, always visible */}
      <ChatWidget
        lang={lang}
        mode={mode}
        ticker={results.length > 0 ? results[0].ticker : null}
        pdfTitle={results.length > 0 ? `${results[0].ticker} Deep Dive Report` : null}
      />

    </div>
  );
}
