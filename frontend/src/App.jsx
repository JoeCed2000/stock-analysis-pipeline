import { useState } from 'react';
import TickerInput from './components/TickerInput.jsx';
import BatchAnalysis from './components/BatchAnalysis.jsx';
import AnalysisCard from './components/AnalysisCard.jsx';
import ReportView from './components/ReportView.jsx';
import AboutSection from './components/AboutSection.jsx';
import { analyzeTickers } from './api.js';

export default function App() {
  const [mode, setMode] = useState('single');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reportTicker, setReportTicker] = useState(null);
  const [reportScoring, setReportScoring] = useState(null);

  const handleViewReport = (ticker, scoring) => {
    setReportTicker(ticker);
    setReportScoring(scoring || null);
  };

  const handleAnalyze = async (tickers) => {
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const data = await analyzeTickers(tickers);
      if (data.errors?.length > 0) {
        setError(`Errors: ${data.errors.join(', ')}`);
      }
      setResults(data.results || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 6 }}>
          📈 Stock Analysis Pipeline
        </h1>
        <p style={{ fontSize: 13, color: '#8b949e', marginBottom: 16 }}>
          Automated fundamental analysis — BUY / HOLD / SELL based on 8 criteria
        </p>

        <AboutSection />

        {/* Mode tabs */}
        <div style={{ display: 'flex', gap: 2, background: '#1a1d27', border: '1px solid #30363d', borderRadius: 6, padding: 3, width: 'fit-content' }}>
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

      {/* Single mode */}
      {mode === 'single' && (
        <TickerInput onAnalyze={handleAnalyze} loading={loading} />
      )}

      {/* Batch mode */}
      {mode === 'batch' && (
        <BatchAnalysis onResultsReady={(results) => setResults(results)} />
      )}

      {/* Loading spinner */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <style>{`
            @keyframes hermesspin {
              0%   { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
          <div style={{
            display: 'inline-block',
            width: 40, height: 40,
            border: '3px solid #30363d',
            borderTop: '3px solid #58a6ff',
            borderRadius: '50%',
            animation: 'hermesspin 0.7s linear infinite',
            marginBottom: 16,
          }} />
          <div style={{ color: '#8b949e', fontSize: 14 }}>Please wait — analyzing tickers…</div>
          <div style={{ color: '#484f58', fontSize: 11, marginTop: 6 }}>
            Each ticker takes ~20–30 seconds
          </div>
        </div>
      )}

      {error && (
        <div style={{
          background: '#da363320', border: '1px solid #da3633',
          borderRadius: 6, padding: '12px 16px', marginBottom: 16,
          color: '#f85149', fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {results.length > 0 && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16,
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
    </div>
  );
}
