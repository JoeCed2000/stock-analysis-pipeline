import { useRef, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const FEEDBACK_CATEGORY_OPTIONS = [
  { value: 'general', en: 'General', jp: '一般' },
  { value: 'ui_ux', en: 'UI / UX', jp: 'UI / UX' },
  { value: 'data_quality', en: 'Data quality', jp: 'データ品質' },
  { value: 'report_content', en: 'Report content', jp: 'レポート内容' },
  { value: 'bug', en: 'Bug', jp: 'バグ' },
  { value: 'feature_request', en: 'Feature request', jp: '機能要望' },
];

export default function FeedbackPage({ lang = 'en', onClose }) {
  const [ticker, setTicker] = useState('');
  const [category, setCategory] = useState('general');
  const [feedbackText, setFeedbackText] = useState('');
  const [files, setFiles] = useState([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const fileRef = useRef(null);

  const canSubmit = feedbackText.trim().length > 0 || files.length > 0;

  const handleFileChange = (event) => {
    const selected = Array.from(event.target.files || []);
    setFiles((previous) => [...previous, ...selected]);
    event.target.value = '';
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!canSubmit || sending) return;

    setSending(true);
    setError('');
    setSuccess('');

    try {
      const formData = new FormData();
      if (ticker.trim()) formData.append('ticker', ticker.trim().toUpperCase());
      formData.append('category', category || 'general');
      if (feedbackText.trim()) formData.append('text', feedbackText.trim());
      files.forEach((file) => formData.append('files', file));

      const response = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

      setTicker('');
      setCategory('general');
      setFeedbackText('');
      setFiles([]);
      setSuccess(`${lang === 'jp' ? 'フィードバックを送信しました。' : 'Feedback sent successfully.'} Reference: ${data.id || '—'}`);
    } catch (err) {
      setError(err.message || (lang === 'jp' ? '送信に失敗しました。' : 'Feedback submission failed.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ padding: '24px 16px', maxWidth: 760, margin: '0 auto' }}>
      <div style={headerStyle}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 700, color: '#e1e4e8', margin: 0 }}>
            {lang === 'jp' ? 'フィードバック' : 'Feedback'}
          </h2>
          <p style={introStyle}>
            {lang === 'jp'
              ? '気づいた問題や改善案をチームに送信できます。ティッカーは任意です。送信内容と添付ファイルは公開されません。'
              : 'Send an issue or improvement idea to the team. The ticker is optional. Your message and attachments are not published.'}
          </p>
        </div>
        <button type="button" onClick={onClose} style={secondaryButtonStyle}>
          ← {lang === 'jp' ? '戻る' : 'Back'}
        </button>
      </div>

      <div style={panelStyle}>
        <h3 style={panelTitleStyle}>{lang === 'jp' ? '新しいフィードバックを送る' : 'Send new feedback'}</h3>
        <p style={helperTextStyle}>
          {lang === 'jp'
            ? 'パスワード、Cookie、APIキーなどの機密情報は添付しないでください。'
            : 'Do not attach passwords, cookies, API keys, or other sensitive information.'}
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="feedback-ticker" style={labelStyle}>
            {lang === 'jp' ? '関連ティッカー（任意）' : 'Related ticker (optional)'}
          </label>
          <input
            id="feedback-ticker"
            type="text"
            value={ticker}
            onChange={(event) => setTicker(event.target.value.toUpperCase())}
            placeholder={lang === 'jp' ? '例: NVDA' : 'e.g. NVDA'}
            style={inputStyle}
          />

          <label htmlFor="feedback-category" style={{ ...labelStyle, marginTop: 14 }}>
            {lang === 'jp' ? 'カテゴリ' : 'Category'}
          </label>
          <select
            id="feedback-category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            style={inputStyle}
          >
            {FEEDBACK_CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {lang === 'jp' ? option.jp : option.en}
              </option>
            ))}
          </select>

          <label htmlFor="feedback-message" style={{ ...labelStyle, marginTop: 14 }}>
            {lang === 'jp' ? 'フィードバック' : 'Feedback'}
          </label>
          <textarea
            id="feedback-message"
            value={feedbackText}
            onChange={(event) => setFeedbackText(event.target.value)}
            rows={7}
            placeholder={lang === 'jp'
              ? '気づいたこと、期待した動作、実際の結果を書いてください…'
              : 'Describe what you noticed, what you expected, and what happened…'}
            style={{ ...inputStyle, resize: 'vertical', minHeight: 150 }}
          />

          <div style={{ marginTop: 14 }}>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept="image/*,application/pdf,.txt,.md,.csv,.xlsx"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
            <button type="button" onClick={() => fileRef.current?.click()} style={secondaryButtonStyle}>
              {lang === 'jp' ? 'ファイルを添付' : 'Attach files'}
            </button>
            {files.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {files.map((file, index) => (
                  <span key={`${file.name}-${index}`} style={fileChipStyle}>
                    {file.name}
                    <button
                      type="button"
                      aria-label={`${lang === 'jp' ? '削除' : 'Remove'} ${file.name}`}
                      onClick={() => setFiles((previous) => previous.filter((_, itemIndex) => itemIndex !== index))}
                      style={removeFileButtonStyle}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div aria-live="polite">
            {success && <div style={successStyle}>{success}</div>}
            {error && <div style={errorStyle}>{error}</div>}
          </div>

          <button type="submit" disabled={!canSubmit || sending} style={submitButtonStyle(canSubmit, sending)}>
            {sending
              ? (lang === 'jp' ? '送信中…' : 'Sending…')
              : (lang === 'jp' ? '送信する' : 'Send feedback')}
          </button>
        </form>
      </div>
    </div>
  );
}

const headerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  gap: 16,
  marginBottom: 20,
  flexWrap: 'wrap',
};

const introStyle = {
  margin: '7px 0 0',
  color: '#8b949e',
  fontSize: 14,
  maxWidth: 600,
  lineHeight: 1.55,
};

const panelStyle = {
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 10,
  padding: 20,
};

const panelTitleStyle = {
  margin: 0,
  color: '#e1e4e8',
  fontSize: 18,
  fontWeight: 700,
};

const labelStyle = {
  display: 'block',
  marginBottom: 6,
  color: '#c9d1d9',
  fontSize: 13,
  fontWeight: 600,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '10px 12px',
  background: '#0d1117',
  color: '#e6edf3',
  border: '1px solid #30363d',
  borderRadius: 6,
  fontSize: 14,
  fontFamily: 'inherit',
  outline: 'none',
};

const helperTextStyle = {
  color: '#8b949e',
  fontSize: 12,
  lineHeight: 1.5,
  margin: '8px 0 16px',
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
  gap: 7,
  padding: '5px 9px',
  borderRadius: 999,
  background: '#21262d',
  border: '1px solid #30363d',
  color: '#c9d1d9',
  fontSize: 12,
};

const removeFileButtonStyle = {
  border: 0,
  padding: 0,
  background: 'transparent',
  color: '#f85149',
  cursor: 'pointer',
  fontSize: 16,
  lineHeight: 1,
};

const successStyle = {
  marginTop: 14,
  padding: '10px 12px',
  background: '#23863620',
  border: '1px solid #2ea04350',
  borderRadius: 6,
  color: '#3fb950',
  fontSize: 13,
};

const errorStyle = {
  marginTop: 14,
  padding: '10px 12px',
  background: '#da363320',
  border: '1px solid #f8514950',
  borderRadius: 6,
  color: '#f85149',
  fontSize: 13,
};

const submitButtonStyle = (canSubmit, sending) => ({
  marginTop: 16,
  padding: '10px 20px',
  fontSize: 14,
  fontWeight: 600,
  background: canSubmit && !sending ? '#238636' : '#21262d',
  color: canSubmit && !sending ? '#fff' : '#6e7681',
  border: '1px solid #30363d',
  borderRadius: 6,
  cursor: canSubmit && !sending ? 'pointer' : 'not-allowed',
});
