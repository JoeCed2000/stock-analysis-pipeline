import { useState, useCallback, useRef } from 'react';
import { uploadTickerFile, submitBatch, getBatchStatus, getBatchDownloadUrl } from '../api.js';

export default function BatchAnalysis({ onResultsReady }) {
  const [parsedItems, setParsedItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [textarea, setTextarea] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  const handleFile = useCallback(async (file) => {
    setError(null);
    try {
      const data = await uploadTickerFile(file);
      setParsedItems(data.items || []);
      setSelected(new Set(data.items?.map(it => it.normalized) || []));
    } catch (e) {
      setError(`Upload failed: ${e.message}`);
    }
  }, []);

  const handleTextareaParse = useCallback(() => {
    setError(null);
    if (!textarea.trim()) return;
    // Simulate file upload with text content
    const fakeFile = new Blob([textarea], { type: 'text/plain' });
    fakeFile.name = 'manual-input.txt';
    handleFile(fakeFile);
  }, [textarea, handleFile]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.txt') || file.name.endsWith('.csv') || file.type === 'text/plain')) {
      handleFile(file);
    } else {
      setError('Format accepté: .txt, .csv');
    }
  }, [handleFile]);

  const toggleTicker = (normalized) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(normalized)) next.delete(normalized);
      else next.add(normalized);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(parsedItems.map(it => it.normalized)));
  const deselectAll = () => setSelected(new Set());

  const startAnalysis = async () => {
    const tickers = [...selected];
    if (tickers.length === 0) return;
    setLoading(true);
    setError(null);
    setJobStatus(null);
    try {
      const { job_id } = await submitBatch(tickers);
      setJobId(job_id);

      // Poll status
      let attempts = 0;
      const maxAttempts = 120; // 120 x 3s = 6 min max
      const poll = async () => {
        const status = await getBatchStatus(job_id);
        setJobStatus(status);
        if (status.status === 'completed' || status.status === 'partial') {
          setLoading(false);
          if (onResultsReady) onResultsReady(status.results || []);
          return;
        }
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 3000);
        } else {
          setError('Timeout: analyse trop longue');
          setLoading(false);
        }
      };
      poll();
    } catch (e) {
      setError(`Batch error: ${e.message}`);
      setLoading(false);
    }
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 18, fontWeight: 600, color: '#e1e4e8', marginBottom: 16 }}>
        📦 Batch Analysis — Upload & Multi-Ticker
      </h2>

      {/* File upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? '#58a6ff' : '#30363d'}`,
          borderRadius: 8, padding: '20px', textAlign: 'center',
          background: dragOver ? '#1a2535' : '#1a1d27',
          cursor: 'pointer', marginBottom: 12,
          transition: 'all 0.2s',
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.csv"
          style={{ display: 'none' }}
          onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
        />
        <div style={{ fontSize: 32, marginBottom: 8 }}>📁</div>
        <div style={{ color: '#e1e4e8', fontSize: 14 }}>
          Glissez un fichier .txt ici ou cliquez pour uploader
        </div>
        <div style={{ color: '#8b949e', fontSize: 12, marginTop: 4 }}>
          Format: un ticker par ligne (ex: NVDA, MSFT, AAPL) ou ISINs (ex: US0378331005)
        </div>
      </div>

      {/* Textarea fallback */}
      <div style={{ marginBottom: 12 }}>
        <textarea
          value={textarea}
          onChange={(e) => setTextarea(e.target.value)}
          placeholder="Ou collez vos tickers ici...&#10;NVDA&#10;MSFT&#10;AAPL&#10;US0378331005"
          rows={4}
          disabled={loading}
          style={{
            width: '100%', padding: '10px 14px', fontSize: 14,
            background: '#1a1d27', border: '1px solid #30363d',
            borderRadius: 6, color: '#e1e4e8', resize: 'vertical',
            outline: 'none', fontFamily: 'monospace',
          }}
        />
        <button
          onClick={handleTextareaParse}
          disabled={loading || !textarea.trim()}
          style={{
            marginTop: 6, padding: '6px 14px', fontSize: 12,
            background: '#21262d', border: '1px solid #30363d',
            borderRadius: 4, color: '#8b949e', cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          📋 Parse Tickers
        </button>
      </div>

      {/* Parsed tickers checkboxes */}
      {parsedItems.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 13, color: '#8b949e' }}>
              {parsedItems.length} tickers trouvés — {selected.size} sélectionnés
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={selectAll} disabled={loading}
                style={{ fontSize: 11, padding: '3px 8px', background: '#21262d', border: '1px solid #30363d', borderRadius: 3, color: '#8b949e', cursor: 'pointer' }}>
                Tout sélectionner
              </button>
              <button onClick={deselectAll} disabled={loading}
                style={{ fontSize: 11, padding: '3px 8px', background: '#21262d', border: '1px solid #30363d', borderRadius: 3, color: '#8b949e', cursor: 'pointer' }}>
                Désélectionner
              </button>
            </div>
          </div>
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 8,
            maxHeight: 200, overflowY: 'auto', padding: '8px',
            background: '#1a1d27', border: '1px solid #30363d', borderRadius: 6,
            marginBottom: 12,
          }}>
            {parsedItems.map(item => (
              <label
                key={item.value}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '5px 10px', borderRadius: 4,
                  background: selected.has(item.normalized) ? '#1a3528' : '#21262d',
                  border: `1px solid ${selected.has(item.normalized) ? '#238636' : '#30363d'}`,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  fontSize: 13, color: '#e1e4e8',
                  transition: 'all 0.15s',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(item.normalized)}
                  onChange={() => toggleTicker(item.normalized)}
                  disabled={loading}
                  style={{ accentColor: '#238636' }}
                />
                <span style={{ fontWeight: 600 }}>{item.normalized}</span>
                <span style={{ fontSize: 10, color: '#484f58' }}>({item.type})</span>
              </label>
            ))}
          </div>

          {/* Run button */}
          <button
            onClick={startAnalysis}
            disabled={loading || selected.size === 0}
            style={{
              padding: '12px 28px', fontSize: 15, fontWeight: 600,
              background: loading ? '#30363d' : '#238636',
              color: '#fff', border: 'none', borderRadius: 6,
              cursor: loading || selected.size === 0 ? 'not-allowed' : 'pointer',
              display: 'block', margin: '0 auto',
            }}
          >
            {loading ? '⏳ Analyse en cours...' : `🔍 Analyser ${selected.size} ticker(s)`}
          </button>
        </>
      )}

      {/* Loading spinner + progress */}
      {loading && jobStatus && (
        <div style={{
          textAlign: 'center', padding: '24px 16px', marginTop: 20,
          background: '#1a1d27', border: '1px solid #30363d', borderRadius: 8,
        }}>
          <div style={{ fontSize: 32, marginBottom: 12, animation: 'spin 1s linear infinite' }}>
            ⏳
          </div>
          <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
          <div style={{ color: '#e1e4e8', fontSize: 14, marginBottom: 8 }}>
            Analyse en cours... ({jobStatus.completed || 0}/{jobStatus.total || 0})
          </div>
          <div style={{
            background: '#30363d', borderRadius: 4, height: 8, overflow: 'hidden',
            maxWidth: 300, margin: '0 auto',
          }}>
            <div style={{
              width: `${((jobStatus.completed || 0) / (jobStatus.total || 1)) * 100}%`,
              height: '100%', background: '#238636', borderRadius: 4,
              transition: 'width 0.5s',
            }} />
          </div>
        </div>
      )}

      {/* Results + Download ZIP */}
      {jobStatus && (jobStatus.status === 'completed' || jobStatus.status === 'partial') && (
        <div style={{
          marginTop: 20, padding: 16,
          background: '#1a1d27', border: '1px solid #30363d', borderRadius: 8,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ color: '#e1e4e8', fontSize: 16, fontWeight: 600 }}>
              ✅ {jobStatus.completed}/{jobStatus.total} tickers analysés
            </span>
            <a
              href={getBatchDownloadUrl(jobId)}
              download
              style={{
                padding: '10px 18px', fontSize: 14, fontWeight: 600,
                background: '#238636', color: '#fff', border: 'none',
                borderRadius: 6, cursor: 'pointer', textDecoration: 'none',
              }}
            >
              📦 Télécharger ZIP
            </a>
          </div>

          {/* Results preview */}
          {jobStatus.results?.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {jobStatus.results.map(r => (
                <div key={r.ticker} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 12px', borderRadius: 4,
                  background: '#21262d', fontSize: 13,
                }}>
                  <div>
                    <span style={{ color: '#e1e4e8', fontWeight: 600 }}>{r.ticker}</span>
                    <span style={{ color: '#8b949e', marginLeft: 8 }}>{r.company_name?.substring(0, 30)}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ color: '#8b949e' }}>Score: {r.scoring?.total}/40</span>
                    <span style={{
                      padding: '2px 8px', borderRadius: 3, fontSize: 11, fontWeight: 700,
                      background: r.decision?.includes('BUY') ? '#238636' : r.decision?.includes('HOLD') ? '#d29922' : '#da3633',
                      color: '#fff',
                    }}>
                      {r.decision}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {jobStatus.errors?.length > 0 && (
            <div style={{ marginTop: 12, fontSize: 12, color: '#f85149' }}>
              ⚠️ Erreurs: {jobStatus.errors.join(', ')}
            </div>
          )}
        </div>
      )}

      {/* Error display */}
      {error && (
        <div style={{
          marginTop: 12, padding: '10px 14px',
          background: '#da363320', border: '1px solid #da3633',
          borderRadius: 6, color: '#f85149', fontSize: 13,
        }}>
          {error}
        </div>
      )}
    </div>
  );
}
