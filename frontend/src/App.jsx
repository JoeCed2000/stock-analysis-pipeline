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
import { analyzeTickersAsync, getJobStatus, getDossierStatus, countDossierSections, getSeekingAlphaAccessStatus, testSeekingAlphaAccess } from './api.js';
import translations from './i18n.js';
import SearchMonitor from './components/SearchMonitor.jsx';
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
    return 'en';
  });

  const [audienceMode, setAudienceMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('audienceMode');
      if (saved) return saved;
    }
    return 'nami_personal';
  });

  const handleLanguageChange = (newLang) => {
    setLang(newLang);
    if (typeof window !== 'undefined') {
      localStorage.setItem('lang', newLang);
    }
  };

  useEffect(() => {
    let alive = true;

    const refreshSeekingAlphaStatus = async () => {
      try {
        // Use the TEST endpoint for real connectivity check, not just cookie presence
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
  }, []);

  const t = (key, params) => {
    let str = translations[lang]?.[key] || translations.en[key] || key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        str = str.replaceAll(`{${k}}`, v);
      }
    }
    return str;
  };

  const handleViewReport = async (result, quarter) => {
    // Open the deep-dive PDF in a new tab with current language, quarter, and audience mode
    const params = new URLSearchParams();
    if (quarter) params.set('quarter', quarter);
    if (lang === 'jp') params.set('lang', 'jp');
    if (audienceMode !== 'nami_personal') params.set('audience_mode', audienceMode);
    const qs = params.toString();
    const pdfUrl = `${API_BASE}/report/${result.ticker}/pdf${qs ? '?' + qs : ''}`;
    
    // GET the URL and check status. If 200 → open; if 202 → poll
    try {
      const checkRes = await fetch(pdfUrl);
      if (checkRes.status === 200) {
        // PDF ready — open blob URL for inline viewing
        const blob = await checkRes.blob();
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank', 'noopener');
      } else if (checkRes.status === 202) {
        // Generation in progress — poll until ready
        const toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:12px 18px;border-radius:8px;z-index:9999;font-size:13px';
        toast.textContent = `📊 Generating deep-dive for ${result.ticker}...`;
        document.body.appendChild(toast);
        
        const poll = async () => {
          const res = await fetch(pdfUrl);
          if (res.status === 200) {
            toast.textContent = `✅ Deep-dive ready for ${result.ticker}`;
            setTimeout(() => toast.remove(), 2000);
            const blob = await res.blob();
            const blobUrl = URL.createObjectURL(blob);
            window.open(blobUrl, '_blank', 'noopener');
          } else if (res.status === 202) {
            toast.textContent = `📊 Generating deep-dive for ${result.ticker}...`;
            setTimeout(poll, 5000);
          } else {
            toast.textContent = `❌ Failed to generate deep-dive for ${result.ticker}`;
            setTimeout(() => toast.remove(), 5000);
          }
        };
        setTimeout(poll, 3000);
      } else {
        // Unexpected status — show error
        const toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:12px 18px;border-radius:8px;z-index:9999;font-size:13px';
        toast.textContent = `⚠️ Report not available for ${result.ticker} (${checkRes.status})`;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
      }
    } catch (e) {
      // Network error — show error toast
      const toast = document.createElement('div');
      toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:12px 18px;border-radius:8px;z-index:9999;font-size:13px';
      toast.textContent = `⚠️ Cannot reach report for ${result.ticker}`;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 5000);
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

      // Poll until done (max 10 min)
      const MAX_POLLS = 200; // 200 * 3s = 10 min
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
        setError('Analysis timed out after 10 minutes. The data may still be processing — try again or check back later.');
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
    <div className="app" style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px' }}>
      {show404 ? (
        <NotFound t={t} onBack={() => { window.location.hash = ''; }} />
      ) : showAdmin ? (
        <AdminPage t={t} onClose={() => { window.location.hash = ''; }} />
      ) : showFeedback ? (
        <FeedbackPage lang={lang} onClose={() => { window.location.hash = ''; }} />
      ) : (
      <>{/* Header — centered */}
      <div style={{ marginBottom: 24, textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={() => { window.location.hash = '#feedback'; }}
            style={{
              padding: '8px 14px',
              fontSize: 13,
              fontWeight: 600,
              background: '#21262d',
              color: '#c9d1d9',
              border: '1px solid #30363d',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            💬 Feedback
          </button>
          <span
            title={saAccess.error || ''}
            style={{
              fontSize: 12,
              padding: '5px 10px',
              borderRadius: 999,
              border: '1px solid #30363d',
              background: saAccess.loading
                ? '#21262d'
                : saAccess.configured === true
                  ? '#23863620'
                  : saAccess.configured === false
                    ? '#da363320'
                    : '#d2992220',
              color: saAccess.loading
                ? '#8b949e'
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
          <select
            value={audienceMode}
            onChange={(e) => {
              setAudienceMode(e.target.value);
              localStorage.setItem('audienceMode', e.target.value);
            }}
            style={{
              marginLeft: 8, padding: '4px 8px', fontSize: 12,
              background: '#161b22', color: '#c9d1d9', border: '1px solid #30363d',
              borderRadius: 6, cursor: 'pointer',
            }}
            title={audienceMode === 'client_report' ? 'Client-ready PDF (no Nami language)' : 'Personal notes for Nami'}
          >
            <option value="nami_personal">🧠 Nami</option>
            <option value="client_report">📋 Client</option>
          </select>
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 4 }}>
          {t('siteTitle')}
        </h1>
        <p style={{ fontSize: 13, color: '#8b949e' }}>
          {t('siteSubtitle')}
        </p>

        {!loading && (
        <div style={{ marginTop: 16 }}>
          <AboutSection t={t} />
        </div>
        )}

        {/* Mode tabs — centered, hidden during analysis */}
        {!loading && (
        <div style={{
          display: 'flex', justifyContent: 'center', marginTop: 16,
        }}>
          <div className="mode-tabs" style={{
            display: 'flex', gap: 2, background: '#1a1d27',
            border: '1px solid #30363d', borderRadius: 6, padding: 3,
          }}>
            <button
              onClick={() => { setMode('single'); setResults([]); setError(null); }}
              style={{
                padding: '8px 20px', fontSize: 14, fontWeight: 500,
                background: mode === 'single' ? '#238636' : 'transparent',
                color: mode === 'single' ? '#fff' : '#8b949e',
                border: 'none', borderRadius: 4, cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {t('quickAnalysis')}
            </button>
            <button
              onClick={() => { setMode('batch'); setResults([]); setError(null); }}
              style={{
                padding: '8px 20px', fontSize: 14, fontWeight: 500,
                background: mode === 'batch' ? '#238636' : 'transparent',
                color: mode === 'batch' ? '#fff' : '#8b949e',
                border: 'none', borderRadius: 4, cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {t('batchAnalysis')}
            </button>
          </div>
        </div>
        )}
      </div>

      {/* Single mode */}
      {mode === 'single' && (
        <TickerInput onAnalyze={handleAnalyze} loading={loading} t={t} />
      )}

      {/* Batch mode */}
      {mode === 'batch' && (
        <BatchAnalysis onResultsReady={(results) => setResults(results)} t={t} />
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
          background: '#da363320', border: '1px solid #da3633',
          borderRadius: 6, padding: '12px 16px', marginTop: 16,
          color: '#f85149', fontSize: 13, textAlign: 'center',
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
          animation: 'fadeInUp 0.4s ease',
        }}>
          {results.map(r => (
            <AnalysisCard
              key={r.ticker}
              result={r}
              onViewReport={handleViewReport}
              t={t}
              lang={lang}
            />
          ))}
        </div>
      )}

      <style>{`
        @keyframes fadeInUp {
          0%   { opacity: 0; transform: translateY(12px); }
          100% { opacity: 1; transform: translateY(0); }
        }

        /* ── Responsive ── */
        @media (max-width: 768px) {
          .app { padding: 12px 8px !important; }
          .app h1 { font-size: 18px !important; }
          .app .mode-tabs { flex-wrap: wrap; gap: 1px; }
          .app .mode-tabs button { padding: 6px 12px !important; font-size: 12px !important; }
          .results-grid { grid-template-columns: 1fr !important; }
        }

        @media (max-width: 480px) {
          .app { padding: 8px 4px !important; }
          .app h1 { font-size: 16px !important; }
          .app p { font-size: 11px !important; }
        }
      `}</style>
      </>)}

      {/* Live Chat Widget — global, always visible */}
      <ChatWidget
        lang="ja"
        ticker={results.length > 0 ? results[0].ticker : null}
        pdfTitle={results.length > 0 ? `${results[0].ticker} Deep Dive Report` : null}
      />

    </div>
  );
}
