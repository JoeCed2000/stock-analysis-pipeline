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
          <li>{lang === 'jp' ? 'F12\u30AD\u30FC\uFF08\u307E\u305F\u306FCtrl+Shift+I\uFF09\u3092\u62BC\u3057\u3066Chrome DevTools\u3092\u958B\u304F' : 'Press F12 (or Ctrl+Shift+I) to open Chrome DevTools'}</li>
          <li>{lang === 'jp' ? '\u201CNetwork\u201D\u30BF\u30D6\u306B\u79FB\u52D5\u3059\u308B' : 'Go to the "Network" tab'}</li>
          <li>{lang === 'jp' ? 'Network\u30BF\u30D6\u3092\u958B\u3044\u305F\u307E\u307E\u3001seekingalpha.com\u306B\u30A2\u30AF\u30BB\u30B9\u3057\u3066\u30ED\u30B0\u30A4\u30F3\u3059\u308B' : 'Keep the Network tab open, then navigate to seekingalpha.com and log in'}</li>
          <li>{lang === 'jp' ? '\u30D5\u30A3\u30EB\u30BF\u30FC\u30DC\u30C3\u30AF\u30B9\u306B\u201Cseekingalpha\u201D\u3068\u5165\u529B\u3057\u3066\u30EA\u30AF\u30A8\u30B9\u30C8\u3092\u7D5E\u308A\u8FBC\u3080' : 'In the filter box, type "seekingalpha" to filter requests'}</li>
          <li>{lang === 'jp' ? '\u30CD\u30C3\u30C8\u30EF\u30FC\u30AF\u30EA\u30AF\u30A8\u30B9\u30C8\u30C6\u30FC\u30D6\u30EB\u5185\u3067\u53F3\u30AF\u30EA\u30C3\u30AF \u2192 "Save all as HAR with content"' : 'Right-click anywhere in the network request table \u2192 "Save all as HAR with content"'}</li>
        </ol>
        <div style={{ marginTop: 6, padding: '8px 10px', background: '#1c2333', borderLeft: '3px solid #58a6ff', borderRadius: 4, fontSize: 11 }}>
          {lang === 'jp'
            ? '\uD83D\uDCA1 \u88DC\u8DB3: "Request List"\u306F\u6280\u8853\u7684\u306AHAR\u7528\u8A9E\u3067\u3059 \u2014 \u3053\u306E\u30C6\u30FC\u30D6\u30EB\u306E\u3053\u3068\u3092\u6307\u3057\u3066\u3044\u307E\u3059\u3002Chrome\u306B\u30E9\u30D9\u30EB\u306F\u3042\u308A\u307E\u305B\u3093\u304C\u3001\u3053\u306E\u30C6\u30FC\u30D6\u30EB\u304CRequest List\u3067\u3059\u3002'
            : '\uD83D\uDCA1 Note: "Request List" is a technical HAR term \u2014 it refers to this exact table. Chrome doesn\'t label it, but the table IS the Request List.'}
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
