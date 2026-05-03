import { useState } from 'react';
import TickerInput from './components/TickerInput.jsx';
import AnalysisCard from './components/AnalysisCard.jsx';
import ReportView from './components/ReportView.jsx';
import { analyzeTickers } from './api.js';

export default function App() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reportTicker, setReportTicker] = useState(null);

  const handleAnalyze = async (tickers) => {
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const data = await analyzeTickers(tickers);
      if (data.errors?.length > 0) {
        setError(`Erreurs: ${data.errors.join(', ')}`);
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
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', marginBottom: 6 }}>
          📈 Stock Analysis Pipeline
        </h1>
        <p style={{ fontSize: 13, color: '#8b949e' }}>
          Analyse fondamentale automatisée — BUY / HOLD / SELL basé sur 8 critères
        </p>
      </div>

      <TickerInput onAnalyze={handleAnalyze} loading={loading} />

      {error && (
        <div style={{
          background: '#da363320', border: '1px solid #da3633',
          borderRadius: 6, padding: '12px 16px', marginBottom: 16,
          color: '#f85149', fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#8b949e' }}>
          ⏳ Analyse en cours... (peut prendre 30-60s par ticker)
        </div>
      )}

      {results.length > 0 && (
        <div style={{
          display: 'flex', gap: 16, flexWrap: 'wrap',
          justifyContent: 'center',
        }}>
          {results.map(r => (
            <AnalysisCard
              key={r.ticker}
              result={r}
              onViewReport={setReportTicker}
            />
          ))}
        </div>
      )}

      {reportTicker && (
        <ReportView ticker={reportTicker} onClose={() => setReportTicker(null)} />
      )}
    </div>
  );
}
