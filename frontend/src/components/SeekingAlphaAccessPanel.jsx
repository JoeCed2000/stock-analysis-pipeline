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
  const [diagnosticCopied, setDiagnosticCopied] = useState(false);
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

        lastError = buildFailureMessage(next, lang);
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
    setMessage(`❌ ${lastError || (lang === 'jp' ? 'Seeking Alpha の確認に失敗しました。' : 'Seeking Alpha verification failed.')}`);
    setTesting(false);
    return lastResult;
  }, [lang]);

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
            : ` ⚠️ ${buildFailureMessage(probe, lang)}`;
        }
      } else {
        msg = `Imported ${next.cookie_count} cookies from .har`;
        if (probe) {
          msg += probe.ok
            ? ' ✅ Seeking Alpha access confirmed'
            : ` ⚠️ ${buildFailureMessage(probe, lang)}`;
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

  const handleCopyDiagnostic = async () => {
    const diagnostic = buildDiagnosticText(testResult || status, status);
    if (!diagnostic) return;
    try {
      await navigator.clipboard.writeText(diagnostic);
      setDiagnosticCopied(true);
      setTimeout(() => setDiagnosticCopied(false), 1800);
    } catch {
      setMessage(diagnostic);
    }
  };

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
            ? '\uD83D\uDD0E Edge / Chrome からHARをエクスポートする方法'
            : '\uD83D\uDD0E How to export HAR from Edge / Chrome'}
        </summary>
        <ol style={{ marginTop: 8, paddingLeft: 20, lineHeight: 1.8 }}>
          <li>{lang === 'jp' ? 'Edge または Chrome で Seeking Alpha にログインし、トランスクリプトページを開く' : 'In Edge or Chrome, sign in to Seeking Alpha and open a transcript page'}</li>
          <li>{lang === 'jp' ? 'F12キーでDevToolsを開き、Networkタブを選択する' : 'Press F12, then open the Network tab'}</li>
          <li>{lang === 'jp' ? 'F1キーで設定を開き、“Allow to generate HAR with sensitive data”を有効にする' : 'Press F1, enable “Allow to generate HAR with sensitive data” in the Network settings'}</li>
          <li>{lang === 'jp' ? 'Preserve log を有効にし、ページを再読み込みして中央のリクエスト一覧に行が出ることを確認する' : 'Enable Preserve log, reload the page, and make sure the middle Request List contains rows'}</li>
          <li>{lang === 'jp' ? 'Network のリクエスト一覧内の任意の行を右クリックし、“Save all as HAR with content”を選択する' : 'Right-click any row in the Network Request List, then choose “Save all as HAR with content”'}</li>
          <li>{lang === 'jp' ? '保存した .har ファイルをここにアップロードする' : 'Upload the saved .har file here'}</li>
        </ol>
        <div style={{ marginTop: 6, padding: '8px 10px', background: '#1c2333', borderLeft: '3px solid #58a6ff', borderRadius: 4, fontSize: 11 }}>
          {lang === 'jp'
            ? '💡 Cookie が不足する場合は、Seeking Alpha にログイン後、トランスクリプトページを開いた状態でHARを再エクスポートしてください。リクエスト一覧が空の場合はページを再読み込みしてください。'
            : '💡 If auth cookies are missing, re-export after signing in and opening a Seeking Alpha transcript page. If the Request List is empty, reload the page while DevTools stays open.'}
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

        <button onClick={handleCopyDiagnostic} disabled={!status && !testResult} style={{ ...btnStyle, background: '#21262d', color: '#8b949e', border: '1px solid #30363d' }}>
          {diagnosticCopied ? (lang === 'jp' ? 'コピー済み' : 'Copied') : (lang === 'jp' ? '診断をコピー' : 'Copy diagnostic')}
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
          <Meta label="Missing" value={(testResult.freshness?.missing_families || status?.freshness?.missing_families || []).join(', ') || '—'} tone={(testResult.freshness?.missing_families || status?.freshness?.missing_families || []).length ? '#d29922' : '#8b949e'} />
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

  if (testing || verificationState === 'pending') {
    return { label: 'Pending verification', bg: '#d2992220', color: '#d29922', border: '#d2992240' };
  }

  if (status?.ok || verificationState === 'verified') {
    return { label: 'Access verified', bg: '#23863620', color: '#3fb950', border: '#2ea04340' };
  }

  const missingFamilies = status?.freshness?.missing_families || [];
  if (status?.freshness?.status === 'missing_long_lived_auth' || missingFamilies.length > 0) {
    return {
      label: `Cookies incomplete · missing ${missingFamilies.join(', ') || 'session'}`,
      bg: '#d2992220',
      color: '#d29922',
      border: '#d2992240',
    };
  }

  if (status?.reason === 'blocked_perimeterx') {
    return { label: 'Blocked by PerimeterX', bg: '#da363320', color: '#f85149', border: '#f8514940' };
  }

  if (verificationState === 'failed') {
    return { label: 'Verification failed', bg: '#da363320', color: '#f85149', border: '#f8514940' };
  }

  if (status?.configured) {
    return isFeedbackMode
      ? { label: `Cookies received · ${status.cookie_count}`, bg: '#1f6feb20', color: '#58a6ff', border: '#1f6feb40' }
      : { label: `Configured · ${status.cookie_count} cookies`, bg: '#1f6feb20', color: '#58a6ff', border: '#1f6feb40' };
  }
  return { label: 'Not configured', bg: '#da363320', color: '#f85149', border: '#f8514940' };
}

function buildFailureMessage(result, lang = 'en') {
  const reason = result?.reason || 'unknown_error';
  const missingFamilies = result?.freshness?.missing_families || [];
  if (reason === 'blocked_perimeterx') {
    return lang === 'jp'
      ? `Seeking Alpha がこのCookieセットをブロックしています。${missingFamilies.length ? `不足しているCookieファミリー: ${missingFamilies.join(', ')}。` : ''}ログイン済みのトランスクリプトページからHARを再エクスポートしてください。`
      : `Seeking Alpha blocks this cookie set. ${missingFamilies.length ? `Missing cookie family: ${missingFamilies.join(', ')}. ` : ''}Re-export HAR from a logged-in transcript page with sensitive cookies enabled.`;
  }
  if (result?.freshness?.status === 'missing_long_lived_auth' || missingFamilies.length > 0) {
    return lang === 'jp'
      ? `Cookie は受信済みですが、セッションCookieが不足しています: ${missingFamilies.join(', ') || 'session'}。ログイン済みのトランスクリプトページからHARを再エクスポートしてください。`
      : `Cookies were received, but session cookies are missing: ${missingFamilies.join(', ') || 'session'}. Re-export HAR from a logged-in transcript page.`;
  }
  if (reason === 'mpw_locked_even_with_playwright') {
    return lang === 'jp'
      ? 'Seeking Alpha はログイン後も記事をプレビュー扱いにしています。アカウント権限またはCookieを確認してください。'
      : 'Seeking Alpha still serves the article as preview-only after login. Check account access or re-export cookies.';
  }
  return lang === 'jp'
    ? `Seeking Alpha の確認に失敗しました: ${reason}`
    : `Seeking Alpha verification failed: ${reason}`;
}

function buildDiagnosticText(result, status) {
  const freshness = result?.freshness || status?.freshness || {};
  const payload = {
    configured: status?.configured ?? result?.configured ?? null,
    cookie_count: status?.cookie_count ?? result?.cookie_count ?? null,
    ok: result?.ok ?? null,
    authenticated: result?.authenticated ?? null,
    reachable: result?.reachable ?? null,
    reason: result?.reason || null,
    freshness_status: freshness.status || null,
    missing_families: freshness.missing_families || [],
    tested_at: result?.tested_at || null,
    updated_at: status?.updated_at || null,
  };
  return JSON.stringify(payload, null, 2);
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
