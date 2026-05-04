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
  const [showHelp, setShowHelp] = useState(false);
  const fileRef = useRef(null);

  const validItems = parsedItems.filter(it => it.status === 'valid');
  const invalidItems = parsedItems.filter(it => it.status === 'invalid');

  const handleFile = useCallback(async (file) => {
    setError(null);
    try {
      const data = await uploadTickerFile(file);
      setParsedItems(data.items || []);
      // Auto-select all valid items
      setSelected(new Set((data.items || []).filter(it => it.status === 'valid').map(it => it.normalized)));
    } catch (e) {
      setError(`Upload failed: ${e.message}`);
    }
  }, []);

  const handleTextareaParse = useCallback(() => {
    setError(null);
    if (!textarea.trim()) return;
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
      setError('Accepted formats: .txt, .csv');
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

  const selectAll = () => setSelected(new Set(validItems.map(it => it.normalized)));
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

      let attempts = 0;
      const maxAttempts = 120;
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
          setError('Timeout: analysis took too long');
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

      {/* Usage instructions */}
      <div style={{ marginBottom: 16 }}>
        <button
          onClick={() => setShowHelp(!showHelp)}
          style={{
            fontSize: 12, padding: '4px 12px',
            background: '#21262d', border: '1px solid #30363d',
            borderRadius: 4, color: '#58a6ff', cursor: 'pointer',
          }}
        >
          {showHelp ? '▾ Hide help' : '▸ How to use'}
        </button>
        {showHelp && (
          <div style={{
            marginTop: 8, padding: 12,
            background: '#161b22', border: '1px solid #30363d',
            borderRadius: 6, fontSize: 13, color: '#8b949e', lineHeight: 1.7,
          }}>
            <strong style={{ color: '#e1e4e8' }}>Accepted formats:</strong><br />
            • <strong>Tickers:</strong> AAPL, NVDA, MSFT, GOOGL, MC.PA (one per line or comma-separated)<br />
            • <strong>ISINs:</strong> US0378331005, FR0000121014 (auto-converted to tickers when known)<br />
            <br />
            <strong style={{ color: '#e1e4e8' }}>Steps:</strong><br />
            1. Upload a .txt file or paste tickers in the textarea below<br />
            2. Select/deselect tickers from the parsed list<br />
            3. Click "Run Analysis" — each ticker takes ~20-30s<br />
            4. Review results and download the ZIP with all documents (10-K, transcripts, reports)
          </div>
        )}
      </div>

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
          Drag & drop a .txt file here or click to upload
        </div>
        <div style={{ color: '#8b949e', fontSize: 12, marginTop: 4 }}>
          One ticker per line (e.g. NVDA, MSFT, AAPL) or ISINs (e.g. US0378331005)
        </div>
      </div>

      {/* Textarea fallback */}
      <div style={{ marginBottom: 12 }}>
        <textarea
          value={textarea}
          onChange={(e) => setTextarea(e.target.value)}
          placeholder="Or paste tickers here...&#10;NVDA&#10;MSFT&#10;AAPL&#10;US0378331005"
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

      {/* Parsed tickers */}
      {parsedItems.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 13, color: '#8b949e' }}>
              {validItems.length} valid tickers — {invalidItems.length} invalid — {selected.size} selected
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button onClick={selectAll} disabled={loading}
                style={{ fontSize: 11, padding: '3px 8px', background: '#21262d', border: '1px solid #30363d', borderRadius: 3, color: '#8b949e', cursor: 'pointer' }}>
                Select all
              </button>
              <button onClick={deselectAll} disabled={loading}
                style={{ fontSize: 11, padding: '3px 8px', background: '#21262d', border: '1px solid #30363d', borderRadius: 3, color: '#8b949e', cursor: 'pointer' }}>
                Deselect all
              </button>
            </div>
          </div>

          {/* Valid tickers */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 8,
            padding: '8px', background: '#1a1d27', border: '1px solid #30363d',
            borderRadius: 6, marginBottom: invalidItems.length > 0 ? 8 : 12,
          }}>
            {validItems.map(item => {
              const isSelected = selected.has(item.normalized);
              return (
                <label
                  key={item.value}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 10px', borderRadius: 4,
                    background: isSelected ? '#1a3528' : '#21262d',
                    border: `1px solid ${isSelected ? '#238636' : '#30363d'}`,
                    cursor: loading ? 'not-allowed' : 'pointer',
                    fontSize: 13, color: '#e1e4e8',
                    transition: 'all 0.15s',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleTicker(item.normalized)}
                    disabled={loading}
                    style={{ accentColor: '#238636' }}
                  />
                  <span style={{ fontWeight: 600 }}>{item.normalized}</span>
                  <span style={{ fontSize: 10, color: '#484f58' }}>({item.type})</span>
                </label>
              );
            })}
            {validItems.length === 0 && (
              <span style={{ fontSize: 12, color: '#484f58', padding: 4 }}>No valid tickers found</span>
            )}
          </div>

          {/* Invalid tickers */}
          {invalidItems.length > 0 && (
            <div style={{
              padding: '8px', background: '#1a1d27', border: '1px solid #da3633',
              borderRadius: 6, marginBottom: 12,
            }}>
              <div style={{ fontSize: 12, color: '#f85149', fontWeight: 600, marginBottom: 6 }}>
                ⚠️ {invalidItems.length} invalid ticker(s) — not selectable:
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {invalidItems.map(item => (
                  <div
                    key={item.value}
                    title={item.error}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 4,
                      padding: '4px 8px', borderRadius: 3,
                      background: '#da363315', border: '1px solid #da3633',
                      fontSize: 12, color: '#f85149',
                    }}
                  >
                    <span style={{ fontWeight: 600, textDecoration: 'line-through' }}>
                      {item.value}
                    </span>
                    <span style={{ fontSize: 10, color: '#da3633aa' }}>
                      {item.error}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

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
            {loading ? '⏳ Running analysis...' : `🔍 Run analysis on ${selected.size} ticker(s)`}
          </button>
        </>
      )}

      {/* Spinner + progress */}
      {loading && jobStatus && (
        <div style={{
          textAlign: 'center', padding: '24px 16px', marginTop: 20,
          background: '#1a1d27', border: '1px solid #30363d', borderRadius: 8,
        }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>
            ⏳
          </div>
          <style>{`@keyframes spin { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }`}</style>
          <div style={{ color: '#e1e4e8', fontSize: 14, marginBottom: 8 }}>
            Running analysis... ({jobStatus.completed || 0}/{jobStatus.total || 0})
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
              ✅ {jobStatus.completed}/{jobStatus.total} tickers analyzed
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
              📦 Download ZIP
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
              ⚠️ Errors: {jobStatus.errors.join(', ')}
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
