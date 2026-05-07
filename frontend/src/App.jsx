import { useState, useRef, useEffect } from 'react';
import TickerInput from './components/TickerInput.jsx';
import BatchAnalysis from './components/BatchAnalysis.jsx';
import AnalysisCard from './components/AnalysisCard.jsx';
import ReportView from './components/ReportView.jsx';
import AboutSection from './components/AboutSection.jsx';
import SmartLoader from './components/SmartLoader.jsx';
import SkeletonCard from './components/SkeletonCard.jsx';
import LanguageSelector from './components/LanguageSelector.jsx';
import AdminPage from './components/AdminPage.jsx';
import { analyzeTickers } from './api.js';
import translations from './i18n.js';

const ESTIMATED_SEC_PER_TICKER = 22;

export default function App() {
  const [mode, setMode] = useState('single');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reportResult, setReportResult] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 0, ticker: '' });
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
  const progressRef = useRef(null);

  const t = (key) => translations[lang]?.[key] || translations.en[key] || key;

  const handleViewReport = (result) => {
    setReportResult(result);
  };

  const handleAnalyze = async (tickers) => {
    setLoading(true);
    setError(null);
    setResults([]);

    const total = tickers.length;
    setProgress({ current: 0, total, ticker: tickers[0] || '' });

    let current = 0;
    const intervalMs = (ESTIMATED_SEC_PER_TICKER * 1000) / total;
    progressRef.current = setInterval(() => {
      current = Math.min(current + 1, total);
      setProgress({ current, total, ticker: tickers[current] || '' });
    }, intervalMs);

    try {
      const data = await analyzeTickers(tickers, lang);
      if (data.errors?.length > 0) {
        setError(`Errors: ${data.errors.join(', ')}`);
      }
      setResults(data.results || []);
    } catch (e) {
      if (e.status === 422 && e.body) {
        setError(e.body?.detail?.message || e.message);
      } else {
        setError(e.message);
      }
    } finally {
      clearInterval(progressRef.current);
      setLoading(false);
      setProgress({ current: total, total, ticker: '' });
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
      {loading && progress.total > 0 && (
        <>
          <SmartLoader
            total={progress.total}
            current={progress.current}
            ticker={progress.ticker}
            t={t}
          />

          <div style={{
            textAlign: 'center', color: '#8b949e', fontSize: 12,
            marginTop: 16, marginBottom: 8,
          }}>
            {t('analysisDuration')}
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

      {results.length > 0 && (
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

      {reportResult && (
        <ReportView ticker={reportResult.ticker} result={reportResult} onClose={() => setReportResult(null)} t={t} lang={lang} />
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
