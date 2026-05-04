import { useState, useRef } from 'react';
import TickerInput from './components/TickerInput.jsx';
import BatchAnalysis from './components/BatchAnalysis.jsx';
import AnalysisCard from './components/AnalysisCard.jsx';
import ReportView from './components/ReportView.jsx';
import AboutSection from './components/AboutSection.jsx';
import SmartLoader from './components/SmartLoader.jsx';
import SkeletonCard from './components/SkeletonCard.jsx';
import { analyzeTickers } from './api.js';

const ESTIMATED_SEC_PER_TICKER = 22;

export default function App() {
  const [mode, setMode] = useState('single');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reportTicker, setReportTicker] = useState(null);
  const [reportScoring, setReportScoring] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 0, ticker: '' });
  const progressRef = useRef(null);

  const handleViewReport = (ticker, scoring) => {
    setReportTicker(ticker);
    setReportScoring(scoring || null);
  };

  const handleAnalyze = async (tickers) => {
    setLoading(true);
    setError(null);
    setResults([]);

    const total = tickers.length;
    setProgress({ current: 0, total, ticker: tickers[0] || '' });

    // Simulate progress while waiting for backend
    let current = 0;
    const intervalMs = (ESTIMATED_SEC_PER_TICKER * 1000) / total;
    progressRef.current = setInterval(() => {
      current = Math.min(current + 1, total - 1);
      setProgress({ current, total, ticker: tickers[current] || '' });
    }, intervalMs);

    try {
      const data = await analyzeTickers(tickers);
      if (data.errors?.length > 0) {
        setError(`Errors: ${data.errors.join(', ')}`);
      }
      setResults(data.results || []);
    } catch (e) {
      // Handle 422 validation errors (invalid tickers)
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
      {/* Header — centered */}
      <div style={{ marginBottom: 24, textAlign: 'center' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 4 }}>
          📈 Stock Analysis
        </h1>
        <p style={{ fontSize: 13, color: '#8b949e' }}>
          Automated fundamental analysis — BUY / HOLD / SELL based on 8 criteria
        </p>

        <div style={{ marginTop: 16 }}>
          <AboutSection />
        </div>

        {/* Mode tabs — centered */}
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
              🔍 Quick Analysis
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
              📦 Batch (Upload + ZIP)
            </button>
          </div>
        </div>
      </div>

      {/* Single mode */}
      {mode === 'single' && (
        <TickerInput onAnalyze={handleAnalyze} loading={loading} />
      )}

      {/* Batch mode */}
      {mode === 'batch' && (
        <BatchAnalysis onResultsReady={(results) => setResults(results)} />
      )}

      {/* Smart loading — replaces old double spinner */}
      {loading && progress.total > 0 && (
        <>
          <SmartLoader
            total={progress.total}
            current={progress.current}
            ticker={progress.ticker}
          />

          {/* Skeleton cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 400px))',
            gap: 20, marginTop: 24, justifyContent: 'center',
          }}>
            {Array.from({ length: progress.total }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
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
            />
          ))}
        </div>
      )}

      {reportTicker && (
        <ReportView ticker={reportTicker} scoring={reportScoring} onClose={() => { setReportTicker(null); setReportScoring(null); }} />
      )}

      <style>{`
        @keyframes fadeInUp {
          0%   { opacity: 0; transform: translateY(12px); }
          100% { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
