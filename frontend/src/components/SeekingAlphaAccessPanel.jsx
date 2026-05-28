import { useCallback, useEffect, useState } from 'react';
import {
  clearSeekingAlphaAccess,
  getSeekingAlphaAccessStatus,
  saveSeekingAlphaAccess,
  testSeekingAlphaAccess,
} from '../api.js';

const DEFAULT_TICKER = 'NVDA';

export default function SeekingAlphaAccessPanel() {
  const [status, setStatus] = useState(null);
  const [cookieHeader, setCookieHeader] = useState('');
  const [testTicker, setTestTicker] = useState(DEFAULT_TICKER);
  const [testResult, setTestResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getSeekingAlphaAccessStatus();
      setStatus(next);
    } catch (err) {
      setMessage(err.message || 'Unable to load Seeking Alpha status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSave = async () => {
    if (!cookieHeader.trim()) {
      setMessage('Paste the full Cookie header first.');
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      const next = await saveSeekingAlphaAccess(cookieHeader);
      setStatus(next);
      setCookieHeader('');
      setMessage(`Cookies stored server-side (${next.cookie_count} cookies).`);
    } catch (err) {
      setMessage(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setMessage('');
    try {
      const next = await testSeekingAlphaAccess(testTicker || DEFAULT_TICKER);
      setStatus(next);
      setTestResult(next);
      setMessage(next.ok ? 'Seeking Alpha access looks good.' : `Seeking Alpha test failed: ${next.reason}`);
    } catch (err) {
      setMessage(err.message || 'Connectivity test failed');
    } finally {
      setTesting(false);
    }
  };

  const handleClear = async () => {
    setClearing(true);
    setMessage('');
    try {
      const next = await clearSeekingAlphaAccess();
      setStatus(next);
      setTestResult(null);
      setMessage('Stored Seeking Alpha cookies cleared.');
    } catch (err) {
      setMessage(err.message || 'Clear failed');
    } finally {
      setClearing(false);
    }
  };

  const statusBadge = status?.configured
    ? { label: `Configured · ${status.cookie_count} cookies`, bg: '#23863620', color: '#3fb950' }
    : { label: 'Not configured', bg: '#da363320', color: '#f85149' };

  return (
    <div style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#e1e4e8' }}>🔐 Seeking Alpha Access</div>
          <div style={{ fontSize: 12, color: '#8b949e', marginTop: 4 }}>
            Cookies stay server-side only. The UI never reads them back.
          </div>
        </div>
        <span style={{ fontSize: 12, padding: '4px 10px', borderRadius: 999, background: statusBadge.bg, color: statusBadge.color }}>
          {loading && !status ? 'Loading…' : statusBadge.label}
        </span>
      </div>

      <textarea
        value={cookieHeader}
        onChange={(e) => setCookieHeader(e.target.value)}
        placeholder="Paste the full Cookie header from Seeking Alpha here"
        spellCheck={false}
        style={{
          width: '100%', minHeight: 88, resize: 'vertical',
          background: '#0d1117', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 8,
          padding: 12, fontSize: 12, fontFamily: 'monospace', boxSizing: 'border-box',
          marginBottom: 12,
        }}
      />

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <button onClick={handleSave} disabled={saving} style={{ ...btnStyle, background: '#238636', color: '#fff', border: '1px solid #2ea043' }}>
          {saving ? 'Saving…' : 'Save cookies'}
        </button>
        <button onClick={handleClear} disabled={clearing || !status?.configured} style={{ ...btnStyle, background: '#21262d', color: '#c9d1d9', border: '1px solid #30363d' }}>
          {clearing ? 'Clearing…' : 'Clear'}
        </button>
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
          {testing ? 'Testing…' : 'Test transcript access'}
        </button>
        <button onClick={refresh} disabled={loading} style={{ ...btnStyle, background: '#21262d', color: '#8b949e', border: '1px solid #30363d' }}>
          Refresh
        </button>
      </div>

      {message && (
        <div style={{ fontSize: 12, color: message.includes('failed') ? '#f85149' : '#8b949e', marginBottom: testResult ? 10 : 0 }}>
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
    return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso;
  }
}

function trimUrl(url) {
  if (!url) return '—';
  return url.replace('https://seekingalpha.com', '') || '/';
}

const btnStyle = {
  padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600,
};
