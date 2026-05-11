import { useState, useEffect } from 'react';
import TickerInput from './components/TickerInput.jsx';
import BatchAnalysis from './components/BatchAnalysis.jsx';
import AnalysisCard from './components/AnalysisCard.jsx';
import AboutSection from './components/AboutSection.jsx';
import SmartLoader from './components/SmartLoader.jsx';
import SkeletonCard from './components/SkeletonCard.jsx';
import LanguageSelector from './components/LanguageSelector.jsx';
import AdminPage from './components/AdminPage.jsx';
import { analyzeTickersAsync, getJobStatus, getDossierStatus, countDossierSections } from './api.js';
import translations from './i18n.js';

// BUILD: v2 — SmartLoader 4-step activity, t() interpolation, skeleton loading
const API_BASE = import.meta.env.VITE_API_URL || '';

const ESTIMATED_SEC_PER_TICKER = 22;

export default function App() {
  const [mode, setMode] = useState('single');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dossierPhase, setDossierPhase] = useState(false); // true when building dossier after analysis
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 0, ticker: '', companyName: '' });
  const [showAdmin, setShowAdmin] = useState(() => window.location.hash === '#admin');

  useEffect(() => {
    const onHashChange = () => setShowAdmin(window.location.hash === '#admin');
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

  const handleLanguageChange = (newLang) => {
    setLang(newLang);
    if (typeof window !== 'undefined') {
      localStorage.setItem('lang', newLang);
    }
  };

  const t = (key, params) => {
    let str = translations[lang]?.[key] || translations.en[key] || key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        str = str.replaceAll(`{${k}}`, v);
      }
    }
    return str;
  };

  const handleViewReport = async (result) => {
    // Open the deep-dive PDF in a new tab with current language
    // If PDF doesn't exist yet (202), poll until ready
    const langParam = lang === 'ja' || lang === 'jp' ? '?lang=ja' : '';
    const pdfUrl = `${API_BASE}/report/${result.ticker}/pdf${langParam}`;
    
    // Check if PDF is ready or needs generation
    try {
      const checkRes = await fetch(pdfUrl, { method: 'HEAD' });
      if (checkRes.status === 202) {
        // Generation in progress — poll until ready
        const toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:12px 18px;border-radius:8px;z-index:9999;font-size:13px';
        toast.textContent = `📊 Generating deep-dive for ${result.ticker}...`;
        document.body.appendChild(toast);
        
        const poll = async () => {
          const res = await fetch(pdfUrl, { method: 'HEAD' });
          if (res.status === 200) {
            toast.textContent = `✅ Deep-dive ready for ${result.ticker}`;
            setTimeout(() => toast.remove(), 2000);
            window.open(pdfUrl, '_blank', 'noopener');
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
        // PDF exists — open directly
        window.open(pdfUrl, '_blank', 'noopener');
      }
    } catch (e) {
      // Fallback: open directly
      window.open(pdfUrl, '_blank', 'noopener');
    }
  };

  const handleAnalyze = async (tickers) => {
    setLoading(true);
    setError(null);
    setResults([]);

    const total = tickers.length;
    setProgress({ current: 0, total, ticker: tickers[0] || '' });

    // Fake progress ticker while polling
    let current = 0;
    const intervalMs = (ESTIMATED_SEC_PER_TICKER * 1000) / total;
    const progressTimer = setInterval(() => {
      current = Math.min(current + 1, total);
      setProgress(p => ({ ...p, current }));
    }, intervalMs);

    try {
      // Submit async job — returns immediately with job_id
      const { job_id } = await analyzeTickersAsync(tickers, lang);

      // Poll until done (max 10 min)
      const MAX_POLLS = 200; // 200 * 3s = 10 min
      let timedOut = true;
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise(r => setTimeout(r, 3000));
        try {
          const job = await getJobStatus(job_id);

          if (job.status === 'done') {
            const data = job.result;
            if (data?.errors?.length > 0) {
              setError(`Errors: ${data.errors.join(', ')}`);
            }
            // Don't show cards yet — wait for dossier to be fully built
            const resultsList = data?.results || [];
            setDossierPhase(true);
            setProgress({ current: total, total, ticker: resultsList[0]?.ticker || '' });
            timedOut = false;

            // Poll dossier status for each ticker (wait up to 6 min)
            for (const r of resultsList) {
              let dossierReady = false;
              for (let d = 0; d < 120; d++) {
                await new Promise(r2 => setTimeout(r2, 3000));
                try {
                  const ds = await getDossierStatus(r.ticker);
                  if (ds && ds.ready) {
                    dossierReady = true;
                    break;
                  }
                  // Update progress text with section count
                  const sectionCount = countDossierSections(ds?.files || []);
                  setProgress(p => ({
                    ...p,
                    ticker: `📊 Building dossier… ${sectionCount}/7`,
                  }));
                } catch {
                  // transient — keep polling
                }
              }
              if (!dossierReady) {
                console.warn(`Dossier timeout for ${r.ticker} — showing card anyway`);
              }
            }

            setResults(resultsList);
            setDossierPhase(false);
            break;
          }
          if (job.status === 'error') {
            setError(job.error || 'Analysis failed');
            timedOut = false;
            break;
          }
          // Still processing — update progress text
          if (job.progress) {
            setProgress(p => ({ ...p, ticker: job.progress }));
          }
        } catch (pollErr) {
          // Transient network error during poll — keep trying
          console.warn('Poll error:', pollErr.message);
        }
      }
      if (timedOut) {
        setError('Analysis timed out after 10 minutes. The data may still be processing — try again or check back later.');
      }
    } catch (e) {
      if (e.status === 422 && e.body) {
        setError(e.body?.detail?.message || e.message);
      } else {
        setError(e.message);
      }
    } finally {
      clearInterval(progressTimer);
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px' }}>
      {showAdmin ? (
        <AdminPage t={t} onClose={() => { window.location.hash = ''; }} />
      ) : (
      <>{/* Header — centered */}
      <div style={{ marginBottom: 24, textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: 8 }}>
          <LanguageSelector lang={lang} onLanguageChange={handleLanguageChange} />
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
          <div style={{
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
      {!loading && mode === 'single' && (
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 400px))', gap: 20, marginTop: 16, justifyContent: 'center' }}>
          {Array.from({ length: progress.total }, (_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {results.length > 0 && !dossierPhase && (
        <div style={{
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
      `}</style>
      </>)}
    </div>
  );
}
