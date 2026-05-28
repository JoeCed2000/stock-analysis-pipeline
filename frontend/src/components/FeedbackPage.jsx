import { useCallback, useMemo, useRef, useState, useEffect } from 'react';
import SeekingAlphaAccessPanel from './SeekingAlphaAccessPanel.jsx';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

function formatDateTime(iso) {
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso || '—';
  }
}

function statusMeta(entry, lang) {
  if (entry?.processed) {
    return {
      label: lang === 'jp' ? '反映済み' : 'Taken into account',
      background: '#23863620',
      color: '#3fb950',
      border: '#2ea04340',
    };
  }
  return {
    label: lang === 'jp' ? '確認待ち' : 'Pending',
    background: '#d2992220',
    color: '#d29922',
    border: '#d2992240',
  };
}

function scopeLabel(entry, lang) {
  if (!entry?.ticker) {
    return lang === 'jp' ? '一般' : 'General';
  }
  return entry.ticker;
}

const FEEDBACK_CATEGORY_OPTIONS = [
  { value: 'general', en: 'General', jp: '一般' },
  { value: 'ui_ux', en: 'UI / UX', jp: 'UI / UX' },
  { value: 'data_quality', en: 'Data quality', jp: 'データ品質' },
  { value: 'report_content', en: 'Report content', jp: 'レポート内容' },
  { value: 'bug', en: 'Bug', jp: 'バグ' },
  { value: 'feature_request', en: 'Feature request', jp: '機能要望' },
  { value: 'seeking_alpha_access', en: 'Seeking Alpha access', jp: 'Seeking Alpha 接続' },
];

function categoryLabel(value, lang) {
  const match = FEEDBACK_CATEGORY_OPTIONS.find((opt) => opt.value === value);
  if (!match) return value || (lang === 'jp' ? '一般' : 'General');
  return lang === 'jp' ? match.jp : match.en;
}

export default function FeedbackPage({ lang = 'en', onClose }) {
  const [ticker, setTicker] = useState('');
  const [category, setCategory] = useState('general');
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [latestId, setLatestId] = useState(null);
  const fileRef = useRef(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/feedback`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setHistory(data.entries || []);
    } catch (err) {
      setError(err.message || 'Failed to load feedback');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const counts = useMemo(() => ({
    total: history.length,
    pending: history.filter((entry) => !entry.processed).length,
    processed: history.filter((entry) => entry.processed).length,
  }), [history]);

  const canSubmit = text.trim().length > 0 || files.length > 0;

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    setFiles((prev) => [...prev, ...selected]);
    e.target.value = '';
  };

  const removeFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit || sending) return;

    setSending(true);
    setError('');
    setSuccess('');

    try {
      const formData = new FormData();
      if (ticker.trim()) {
        formData.append('ticker', ticker.trim().toUpperCase());
      }
      formData.append('category', category || 'general');
      if (text.trim()) {
        formData.append('text', text.trim());
      }
      files.forEach((file) => formData.append('files', file));

      const res = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }

      setTicker('');
      setCategory('general');
      setText('');
      setFiles([]);
      setLatestId(data.id || null);
      setSuccess(lang === 'jp' ? 'フィードバックを送信しました。' : 'Feedback sent successfully.');
      await loadHistory();
    } catch (err) {
      setError(err.message || 'Feedback submission failed');
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ padding: '24px 16px', maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', margin: 0 }}>
            💬 {lang === 'jp' ? 'フィードバック' : 'Feedback'}
          </h2>
          <p style={{ margin: '6px 0 0 0', color: '#8b949e', fontSize: 13, maxWidth: 720, lineHeight: 1.5 }}>
            {lang === 'jp'
              ? 'ティッカーに依存しない製品フィードバックページです。関連ティッカーは任意入力で、送信済みの内容・日付・ステータスをここで確認できます。'
              : 'Dedicated product feedback page. The ticker is optional, and every submission stays visible here with its date and status.'}
          </p>
        </div>
        <button
          onClick={onClose}
          style={{
            padding: '8px 16px',
            fontSize: 13,
            background: '#21262d',
            color: '#c9d1d9',
            border: '1px solid #30363d',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          ← {lang === 'jp' ? '戻る' : 'Back'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, marginBottom: 18 }}>
        <SummaryCard label={lang === 'jp' ? '総件数' : 'Total'} value={counts.total} color="#58a6ff" />
        <SummaryCard label={lang === 'jp' ? '確認待ち' : 'Pending'} value={counts.pending} color="#d29922" />
        <SummaryCard label={lang === 'jp' ? '反映済み' : 'Taken into account'} value={counts.processed} color="#3fb950" />
      </div>

      <div className="feedback-page-grid" style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 420px) 1fr', gap: 18, alignItems: 'start' }}>
        <div>
          <SeekingAlphaAccessPanel mode="feedback" lang={lang} />

          <div style={panelStyle}>
            <h3 style={panelTitleStyle}>{lang === 'jp' ? '新しいフィードバックを送る' : 'Send new feedback'}</h3>
          <p style={helperTextStyle}>
            {lang === 'jp'
              ? 'ティッカーを入力すると、その銘柄の最新 Deep Dive PDF が自動で添付されます。空欄のままなら一般フィードバックとして保存されます。'
              : 'If you add a ticker, the latest deep-dive PDF for that ticker is auto-attached. Leave it blank for general product feedback.'}
          </p>

          <form onSubmit={handleSubmit}>
            <label style={labelStyle}>
              {lang === 'jp' ? '関連ティッカー（任意）' : 'Related ticker (optional)'}
            </label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder={lang === 'jp' ? '例: NVDA' : 'e.g. NVDA'}
              style={inputStyle}
            />

            <label style={{ ...labelStyle, marginTop: 12 }}>
              {lang === 'jp' ? 'カテゴリ' : 'Category'}
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={inputStyle}
            >
              {FEEDBACK_CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {lang === 'jp' ? opt.jp : opt.en}
                </option>
              ))}
            </select>

            <label style={{ ...labelStyle, marginTop: 12 }}>
              {lang === 'jp' ? 'フィードバック' : 'Feedback'}
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              placeholder={lang === 'jp'
                ? '気づいたこと、直したい点、改善案を書いてください…'
                : 'Describe what you noticed, what should change, or what has already been taken into account…'}
              style={{ ...inputStyle, resize: 'vertical', minHeight: 140 }}
            />

            <div style={{ marginTop: 12 }}>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept="image/*,application/pdf,.txt,.md,.json,.csv,.xlsx"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <button type="button" onClick={() => fileRef.current?.click()} style={secondaryButtonStyle}>
                📎 {lang === 'jp' ? 'ファイルを添付' : 'Attach files'}
              </button>
              {files.length > 0 && (
                <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {files.map((file, index) => (
                    <span key={`${file.name}-${index}`} style={fileChipStyle}>
                      📄 {file.name}
                      <button type="button" onClick={() => removeFile(index)} style={removeFileButtonStyle}>✕</button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {success && <div style={successStyle}>✅ {success}</div>}
            {error && <div style={errorStyle}>❌ {error}</div>}

            <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <button type="submit" disabled={!canSubmit || sending} style={submitButtonStyle(canSubmit, sending)}>
                {sending
                  ? (lang === 'jp' ? '送信中…' : 'Sending…')
                  : (lang === 'jp' ? '送信する' : 'Send feedback')}
              </button>
              <span style={helperTextStyle}>
                {lang === 'jp'
                  ? '送信後、このページにすぐ履歴が表示されます。'
                  : 'After submission, the history below refreshes immediately.'}
              </span>
            </div>
          </form>
          </div>
        </div>

        <div style={panelStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
            <h3 style={panelTitleStyle}>{lang === 'jp' ? '送信済みフィードバック' : 'Submitted feedback'}</h3>
            <button type="button" onClick={loadHistory} style={secondaryButtonStyle}>
              ↻ {lang === 'jp' ? '更新' : 'Refresh'}
            </button>
          </div>

          {loading ? (
            <div style={emptyStateStyle}>{lang === 'jp' ? '読み込み中…' : 'Loading feedback history…'}</div>
          ) : history.length === 0 ? (
            <div style={emptyStateStyle}>{lang === 'jp' ? 'まだフィードバックはありません。' : 'No feedback yet.'}</div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {history.map((entry) => {
                const meta = statusMeta(entry, lang);
                const isLatest = latestId && entry.id === latestId;
                return (
                  <div
                    key={entry.id}
                    style={{
                      border: `1px solid ${isLatest ? '#388bfd' : '#30363d'}`,
                      borderRadius: 8,
                      background: isLatest ? '#0f1f33' : '#0d1117',
                      padding: 14,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                        <span style={scopeBadgeStyle(entry)}>{scopeLabel(entry, lang)}</span>
                        <span style={categoryBadgeStyle}>
                          {categoryLabel(entry.category || 'general', lang)}
                        </span>
                        <span style={{
                          fontSize: 11,
                          padding: '3px 8px',
                          borderRadius: 999,
                          background: meta.background,
                          color: meta.color,
                          border: `1px solid ${meta.border}`,
                          fontWeight: 600,
                        }}>
                          {meta.label}
                        </span>
                        <span style={{ color: '#8b949e', fontSize: 12 }}>
                          {formatDateTime(entry.submitted_at)}
                        </span>
                      </div>
                      {entry.files?.length > 0 && (
                        <span style={{ color: '#8b949e', fontSize: 12 }}>
                          📎 {entry.files.length} {lang === 'jp' ? '件' : entry.files.length > 1 ? 'files' : 'file'}
                        </span>
                      )}
                    </div>

                    <div style={{ marginTop: 10, color: '#e6edf3', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {entry.text || (lang === 'jp' ? '（添付ファイルのみ）' : '(attachments only)')}
                    </div>

                    {entry.processed_at && (
                      <div style={{ marginTop: 10, color: '#8b949e', fontSize: 12 }}>
                        {lang === 'jp' ? '反映日' : 'Taken into account on'}: {formatDateTime(entry.processed_at)}
                      </div>
                    )}

                    {entry.notes && (
                      <div style={{ marginTop: 8, padding: '10px 12px', background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#c9d1d9', fontSize: 13, lineHeight: 1.5 }}>
                        <strong style={{ color: '#d29922' }}>{lang === 'jp' ? 'メモ' : 'Notes'}:</strong> {entry.notes}
                      </div>
                    )}

                    {entry.files?.length > 0 && (
                      <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {entry.files.map((fileName) => {
                          const bucket = encodeURIComponent(entry._ticker || entry.ticker || 'GENERAL');
                          const encodedFile = encodeURIComponent(fileName);
                          const href = `${API_BASE}/feedback-file/${bucket}/${encodedFile}`;
                          return (
                            <a
                              key={`${entry.id}-${fileName}`}
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ ...fileChipStyle, textDecoration: 'none' }}
                              title={lang === 'jp' ? '新しいタブで開く' : 'Open in new tab'}
                            >
                              📄 {fileName}
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <style>{`
        @media (max-width: 900px) {
          .feedback-page-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}

function SummaryCard({ label, value, color }) {
  return (
    <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: '14px 16px' }}>
      <div style={{ fontSize: 11, color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

const panelStyle = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 10,
  padding: 18,
};

const panelTitleStyle = {
  margin: 0,
  color: '#e1e4e8',
  fontSize: 18,
  fontWeight: 700,
};

const helperTextStyle = {
  color: '#8b949e',
  fontSize: 12,
  lineHeight: 1.5,
};

const labelStyle = {
  display: 'block',
  color: '#c9d1d9',
  fontSize: 13,
  fontWeight: 600,
  marginBottom: 6,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  background: '#0d1117',
  color: '#e6edf3',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: '10px 12px',
  fontSize: 14,
  fontFamily: 'inherit',
};

const secondaryButtonStyle = {
  padding: '8px 14px',
  fontSize: 13,
  background: '#21262d',
  color: '#c9d1d9',
  border: '1px solid #30363d',
  borderRadius: 6,
  cursor: 'pointer',
};

const fileChipStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  background: '#21262d',
  color: '#c9d1d9',
  border: '1px solid #30363d',
  borderRadius: 999,
  padding: '6px 10px',
  fontSize: 12,
};

const removeFileButtonStyle = {
  background: 'transparent',
  border: 'none',
  color: '#f85149',
  cursor: 'pointer',
  padding: 0,
  fontSize: 12,
};

const successStyle = {
  marginTop: 12,
  padding: '10px 12px',
  borderRadius: 8,
  background: '#23863620',
  color: '#3fb950',
  border: '1px solid #2ea04340',
  fontSize: 13,
};

const errorStyle = {
  marginTop: 12,
  padding: '10px 12px',
  borderRadius: 8,
  background: '#da363320',
  color: '#f85149',
  border: '1px solid #f8514940',
  fontSize: 13,
};

const emptyStateStyle = {
  padding: 24,
  textAlign: 'center',
  color: '#8b949e',
  fontSize: 13,
  background: '#0d1117',
  border: '1px dashed #30363d',
  borderRadius: 8,
};

const submitButtonStyle = (canSubmit, sending) => ({
  padding: '10px 18px',
  fontSize: 14,
  fontWeight: 600,
  background: canSubmit ? '#1f6feb' : '#21262d',
  color: canSubmit ? '#fff' : '#6e7681',
  border: 'none',
  borderRadius: 8,
  cursor: canSubmit && !sending ? 'pointer' : 'not-allowed',
  opacity: sending ? 0.7 : 1,
});

const scopeBadgeStyle = (entry) => ({
  display: 'inline-flex',
  alignItems: 'center',
  padding: '3px 8px',
  borderRadius: 999,
  background: entry?.ticker ? '#0d1117' : '#1f2937',
  color: entry?.ticker ? '#58a6ff' : '#c9d1d9',
  border: `1px solid ${entry?.ticker ? '#1f6feb40' : '#30363d'}`,
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: '0.3px',
});

const categoryBadgeStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '3px 8px',
  borderRadius: 999,
  background: '#161b22',
  color: '#8b949e',
  border: '1px solid #30363d',
  fontSize: 11,
  fontWeight: 600,
};
