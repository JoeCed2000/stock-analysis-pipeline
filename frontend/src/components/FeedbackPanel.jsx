import { useState, useRef } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

export default function FeedbackPanel({ ticker, t, lang }) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!text.trim() && files.length === 0) return;

    setSending(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('ticker', ticker);
      formData.append('text', text);
      for (const f of files) {
        formData.append('files', f);
      }

      const res = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      setSent(true);
      setText('');
      setFiles([]);
      setTimeout(() => setSent(false), 4000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    setFiles(prev => [...prev, ...selected]);
  };

  const removeFile = (idx) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
  };

  return (
    <div style={{
      background: '#161b22',
      border: '1px solid #30363d',
      borderRadius: 8,
      padding: 16,
      marginTop: 16,
    }}>
      <h4 style={{ margin: '0 0 12px 0', color: '#e1e4e8', fontSize: 14 }}>
        💬 {lang === 'ja' ? 'フィードバック' : 'Feedback for Nami'}
      </h4>

      <form onSubmit={handleSubmit}>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder={lang === 'ja'
            ? '気づいた点、修正依頼、提案があればここに記入してください…'
            : 'Notes, corrections, or suggestions…'}
          rows={4}
          style={{
            width: '100%',
            background: '#0d1117',
            border: '1px solid #30363d',
            borderRadius: 6,
            color: '#c9d1d9',
            padding: '10px 12px',
            fontSize: 13,
            resize: 'vertical',
            fontFamily: 'inherit',
            boxSizing: 'border-box',
          }}
        />

        {/* File upload area */}
        <div style={{ marginTop: 10 }}>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="image/*,application/pdf,.txt,.md,.json,.csv,.xlsx"
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            style={{
              background: '#21262d',
              border: '1px solid #30363d',
              borderRadius: 6,
              color: '#8b949e',
              padding: '8px 14px',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            📎 {lang === 'ja' ? 'ファイルを添付' : 'Attach files'}
          </button>

          {/* File list */}
          {files.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {files.map((f, i) => (
                <div key={i} style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  background: '#21262d',
                  borderRadius: 4,
                  padding: '4px 10px',
                  marginRight: 8,
                  marginBottom: 4,
                  fontSize: 12,
                  color: '#c9d1d9',
                }}>
                  📄 {f.name}
                  <span
                    onClick={() => removeFile(i)}
                    style={{ cursor: 'pointer', color: '#f85149', marginLeft: 4 }}
                  >
                    ✕
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="submit"
            disabled={sending || (!text.trim() && files.length === 0)}
            style={{
              background: sent ? '#238636' : '#1f6feb',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              padding: '8px 20px',
              fontSize: 13,
              fontWeight: 500,
              cursor: sending ? 'wait' : 'pointer',
              opacity: sending ? 0.7 : 1,
            }}
          >
            {sent ? '✅ Sent!' : sending ? '⏳ Sending…' : '📤 Send Feedback'}
          </button>

          {error && (
            <span style={{ color: '#f85149', fontSize: 12 }}>❌ {error}</span>
          )}
        </div>
      </form>
    </div>
  );
}
