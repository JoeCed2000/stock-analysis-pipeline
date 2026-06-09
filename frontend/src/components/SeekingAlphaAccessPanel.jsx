import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getSeekingAlphaAccessStatus,
  testSeekingAlphaAccess,
  uploadSeekingAlphaHar,
} from '../api.js';

const DEFAULT_TICKER = 'NVDA';
const RETRY_ATTEMPTS = 4;
const RETRY_DELAY_MS = 1800;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export default function SeekingAlphaAccessPanel({ mode = 'admin', lang = 'en' }) {
  const isFeedbackMode = mode === 'feedback';
  const [status, setStatus] = useState(null);
  const [testTicker, setTestTicker] = useState(DEFAULT_TICKER);
  const [testResult, setTestResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [verificationState, setVerificationState] = useState('idle'); // idle | pending | verified | failed
  const [message, setMessage] = useState('');
  const [uploadingHar, setUploadingHar] = useState(false);
  const harInputRef = useRef(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getSeekingAlphaAccessStatus();
      setStatus(next);
      if (!next?.configured) {
        setVerificationState('idle');
        setTestResult(null);
      }
    } catch (err) {
      setMessage(err.message || 'Unable to load Seeking Alpha status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const runVerification = useCallback(async ({
    ticker = DEFAULT_TICKER,
    attempts = RETRY_ATTEMPTS,
    delayMs = RETRY_DELAY_MS,
    auto = false,
  } = {}) => {
    setTesting(true);
    setVerificationState('pending');
    if (auto) {
      setMessage('Cookies received / pending verification…');
    } else {
      setMessage('Running transcript access check…');
    }

    let lastResult = null;
    let lastError = '';

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        const next = await testSeekingAlphaAccess(ticker || DEFAULT_TICKER);
        lastResult = next;
        setStatus(next);
        setTestResult(next);

        if (next.ok) {
          setVerificationState('verified');
          setMessage('✅ Seeking Alpha transcript access verified (HTTP 200).');
          setTesting(false);
          return next;
        }

        lastError = next.reason || 'denied';
      } catch (err) {
        lastError = err.message || 'request_error';
      }

      if (attempt < attempts) {
        setVerificationState('pending');
        setMessage(`Cookies received / pending verification (${attempt}/${attempts - 1} retry)…`);
        await wait(delayMs);
      }
    }

    setVerificationState('failed');
    setMessage(`❌ Seeking Alpha verification failed: ${lastError || 'unknown_error'}`);
    setTesting(false);
    return lastResult;
  }, []);

  const handleTest = async () => {
    await runVerification({
      ticker: testTicker || DEFAULT_TICKER,
      attempts: 1,
      auto: false,
    });
  };

  const handleHarUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    const name = (file.name || '').toLowerCase();
    if (!name.endsWith('.har') && !name.endsWith('.json')) {
      setMessage(
        lang === 'jp'
          ? '.har ファイルのみ対応しています'
          : 'Only .har files are accepted'
      );
      return;
    }

    setUploadingHar(true);
    setMessage('');

    try {
      const next = await uploadSeekingAlphaHar(file);
      setStatus(next);

      const probe = next.probe;
      let msg;
      if (lang === 'jp') {
        msg = `.har から ${next.cookie_count} Cookie をインポートしました`;
        if (probe) {
          msg += probe.ok
            ? ' ✅ Seeking Alpha アクセス確認済み'
            : ` ⚠️ プローブ失敗: ${probe.reason || '?'}`;
        }
      } else {
        msg = `Imported ${next.cookie_count} cookies from .har`;
        if (probe) {
          msg += probe.ok
            ? ' ✅ Seeking Alpha access confirmed'
            : ` ⚠️ Probe failed: ${probe.reason || '?'}`;
        }
      }
      setMessage(msg);
      if (probe) {
        setTestResult({ ...probe, ticker: 'NVDA', url: `https://seekingalpha.com/symbol/NVDA/earnings/transcripts` });
        setVerificationState(probe.ok ? 'verified' : 'failed');
      }

      if (isFeedbackMode) {
        await runVerification({
          ticker: testTicker || DEFAULT_TICKER,
          attempts: RETRY_ATTEMPTS,
          delayMs: RETRY_DELAY_MS,
          auto: true,
        });
      }
    } catch (err) {
      setVerificationState('failed');
      setMessage(err.message || 'HAR upload failed');
    } finally {
      setUploadingHar(false);
      // Reset file input so the same file can be re-uploaded
      if (harInputRef.current) harInputRef.current.value = '';
    }
  };

  const statusBadge = buildStatusBadge({
    isFeedbackMode,
    status,
    loading,
    testing,
    verificationState,
  });

  const isErrorMessage = verificationState === 'failed' || message.includes('failed') || message.includes('❌');
  const panelTitle = isFeedbackMode
    ? (lang === 'jp' ? '🔐 Seeking Alpha 接続（Cookie）' : '🔐 Seeking Alpha Access (cookies)')
    : '🔐 Seeking Alpha Access';
  const panelSubtitle = isFeedbackMode
    ? (lang === 'jp'
      ? 'Cookie はサーバー側のみで保管されます。HAR ファイルをアップロードしてください。'
      : 'Cookies are stored server-side only. Upload a .har file to configure access.')
    : 'Cookies stay server-side only. The UI never reads them back.';

  return (
    <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#e1e4e8' }}>{panelTitle}</div>
          <div style={{ fontSize: 12, color: '#8b949e', marginTop: 4 }}>
            {panelSubtitle}
          </div>
        </div>
        <span style={{ fontSize: 12, padding: '4px 10px', borderRadius: 999, background: statusBadge.bg, color: statusBadge.color, border: `1px solid ${statusBadge.border}` }}>
          {statusBadge.label}
        </span>
      </div>

      {/* ── HAR upload (only input method) ── */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input
          ref={harInputRef}
          type="file"
          accept=".har,.json"
          onChange={handleHarUpload}
          disabled={uploadingHar}
          id="sa-har-upload"
          style={{ display: 'none' }}
        />
        <label
          htmlFor="sa-har-upload"
          style={{
            ...btnStyle,
            display: 'inline-block',
            background: uploadingHar ? '#21262d' : '#1f6feb',
            color: uploadingHar ? '#8b949e' : '#fff',
            border: uploadingHar ? '1px solid #30363d' : '1px solid #388bfd',
            cursor: uploadingHar ? 'not-allowed' : 'pointer',
            opacity: uploadingHar ? 0.6 : 1,
          }}
        >
          {uploadingHar
            ? (lang === 'jp' ? 'アップロード中…' : 'Uploading…')
            : (lang === 'jp' ? '.har をアップロード (100 MB)' : 'Upload .har (100 MB)')}
        </label>
      </div>

      {/* ── HAR export help (collapsible) ── */}
      <details style={{ marginBottom: 12, fontSize: 12, color: '#8b949e', background: '#0d1117', border: '1px solid #21262d', borderRadius: 8, padding: '10px 14px' }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#c9d1d9' }}>
          {lang === 'jp'
            ? '\uD83D\uDD0E Chrome\u304B\u3089HAR\u3092\u30A8\u30AF\u30B9\u30DD\u30FC\u30C8\u3059\u308B\u65B9\u6CD5'
            : '\uD83D\uDD0E How to export HAR from Chrome?'}
        </summary>
        <ol style={{ marginTop: 8, paddingLeft: 20, lineHeight: 1.8 }}>
          <li>{lang === 'jp' ? 'F12\u30AD\u30FC\u3092\u62BC\u3057\u3066Chrome DevTools\u3092\u958B\u304F' : 'Press F12 to open Chrome DevTools'}</li>
          <li>{lang === 'jp' ? 'F1\u30AD\u30FC\u3092\u62BC\u3057\u3066\u8A2D\u5B9A\u3092\u958B\u304F' : 'Press F1 to open Settings'}</li>
          <li>{lang === 'jp' ? '\u201CNetwork\u201D\u30BB\u30AF\u30B7\u30E7\u30F3\u307E\u3067\u30B9\u30AF\u30ED\u30FC\u30EB\u3057\u3001\u201CAllow to generate HAR with sensitive data\u201D\u306B\u30C1\u30A7\u30C3\u30AF\uFF08\u8A8D\u8A3CCookie\u3092\u53D6\u5F97\u3059\u308B\u305F\u3081\uFF09' : 'Scroll to Network section, check \u201CAllow to generate HAR with sensitive data\u201D (this captures auth cookies)'}</li>
          <li>{lang === 'jp' ? '\u8A2D\u5B9A\u3092\u9589\u3058\u3001\u201CPreserve log\u201D\u306B\u30C1\u30A7\u30C3\u30AF' : 'Close Settings, check \u201CPreserve log\u201D'}</li>
          <li>{lang === 'jp' ? '\u30ED\u30B0\u30A4\u30F3\u3057\u305F\u72B6\u614B\u3067Seeking Alpha\u306B\u30A2\u30AF\u30BB\u30B9\u3059\u308B' : 'Navigate to Seeking Alpha while logged in'}</li>
          <li>{lang === 'jp' ? '\u4E0B\u77E2\u5370\u3092\u30AF\u30EA\u30C3\u30AF\u3057\u3066\u300CExport HAR with sensitive data\u300D' : 'Click the down arrow \u2192 \u201CExport HAR with sensitive data\u201D'}</li>
        </ol>
        <div style={{ marginTop: 6, padding: '8px 10px', background: '#1c2333', borderLeft: '3px solid #58a6ff', borderRadius: 4, fontSize: 11 }}>
          {lang === 'jp'
            ? '\uD83D\uDCA1 \u8A8D\u8A3CCookie\u304CHAR\u306B\u542B\u307E\u308C\u3066\u3044\u306A\u3044\u5834\u5408\u3001\u30B9\u30C6\u30C3\u30D73\u306E\u8A2D\u5B9A\u304C\u30AA\u30D5\u306B\u306A\u3063\u3066\u3044\u308B\u53EF\u80FD\u6027\u304C\u3042\u308A\u307E\u3059\u3002\u518D\u5EA6\u624B\u9806\u3092\u78BA\u8A8D\u3057\u3066\u304F\u3060\u3055\u3044\u3002'
            : '\uD83D\uDCA1 If the .har doesn\u2019t contain auth cookies, step 3 may have been missed. Re-export with the setting enabled.'}
        </div>
      </details>

      {/* ── Test + Refresh toolbar ── */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <input
          value={testTicker}
          onChange={(e) => setTestTicker(e.target.value.toUpperCase())}
          placeholder="Ticker"
          maxLength={10}
          style={{
            width: 96, padding: '8px 10px', background: '#0d1117', color: '#c9d1d9',
            border: '1px solid #30363d', borderRadius: 8, fontSize: 12, fontFamily: 'monospace',
          }}
        />

        <button onClick={handleTest} disabled={testing} style={{ ...btnStyle, background: '#1f6feb', color: '#fff', border: '1px solid #388bfd' }}>
          {testing
            ? (lang === 'jp' ? '確認中…' : 'Testing…')
            : (isFeedbackMode
              ? (lang === 'jp' ? '今すぐ再確認' : 'Retest now')
              : 'Test transcript access')}
        </button>

        <button onClick={refresh} disabled={loading} style={{ ...btnStyle, background: '#21262d', color: '#8b949e', border: '1px solid #30363d' }}>
          {lang === 'jp' ? '更新' : 'Refresh'}
        </button>
      </div>

      {message && (
        <div style={{ fontSize: 12, color: isErrorMessage ? '#f85149' : '#8b949e', marginBottom: testResult ? 10 : 0 }}>
          {message}
        </div>
      )}

      {testResult && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8,
          padding: 12, background: '#0d1117', border: '1px solid #21262d', borderRadius: 8,
        }}>
          <Meta label="Result" value={testResult.ok ? 'Authenticated' : testResult.reason || 'Blocked'} tone={testResult.ok ? '#3fb950' : '#f85149'} />
          <Meta label="Ticker" value={testResult.ticker || DEFAULT_TICKER} />
          <Meta label="HTTP" value={testResult.status_code ? String(testResult.status_code) : '—'} />
          <Meta label="Updated" value={formatTime(status?.updated_at)} />
          <Meta label="Tested" value={formatTime(testResult.tested_at)} />
          <Meta label="URL" value={trimUrl(testResult.url)} />
        </div>
      )}
    </div>
  );
}

function buildStatusBadge({ isFeedbackMode, status, loading, testing, verificationState }) {
  if (loading && !status) {
    return { label: 'Loading…', bg: '#21262d', color: '#8b949e', border: '#30363d' };
  }

  if (isFeedbackMode) {
    if (testing || verificationState === 'pending') {
      return { label: 'Pending verification', bg: '#d2992220', color: '#d29922', border: '#d2992240' };
    }
    if (verificationState === 'verified') {
      return { label: 'Access verified', bg: '#23863620', color: '#3fb950', border: '#2ea04340' };
    }
    if (verificationState === 'failed') {
      return { label: 'Verification failed', bg: '#da363320', color: '#f85149', border: '#f8514940' };
    }
    if (status?.configured) {
      return { label: `Cookies received · ${status.cookie_count}`, bg: '#1f6feb20', color: '#58a6ff', border: '#1f6feb40' };
    }
    return { label: 'Not configured', bg: '#da363320', color: '#f85149', border: '#f8514940' };
  }

  if (status?.configured) {
    return { label: `Configured · ${status.cookie_count} cookies`, bg: '#23863620', color: '#3fb950', border: '#2ea04340' };
  }
  return { label: 'Not configured', bg: '#da363320', color: '#f85149', border: '#f8514940' };
}

function Meta({ label, value, tone = '#c9d1d9' }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: '#8b949e', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 12, color: tone, wordBreak: 'break-word' }}>{value || '—'}</div>
    </div>
  );
}

function formatTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function trimUrl(url) {
  if (!url) return '—';
  return url.replace('https://seekingalpha.com', '') || '/';
}

const btnStyle = {
  padding: '8px 12px',
  borderRadius: 8,
  cursor: 'pointer',
  fontSize: 12,
  fontWeight: 600,
};
