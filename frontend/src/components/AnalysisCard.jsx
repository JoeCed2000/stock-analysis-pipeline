import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchQuarters } from '../api.js';
import { SCORE_COLORS, CONVICTION_COLORS, getConvictionLevel, getInsight, canDownloadDossier, scorePercent, scoreBarColor } from './AnalysisUtils.js';
import useDossierPolling from './useDossierPolling.js';
import { getTickerDownloadUrl, getCompanyOverviewDownloadUrl } from '../api.js';
import ScoringChart from './ScoringChart.jsx';
import MetricsHistoryChart from './MetricsHistoryChart.jsx';
import ValuationGroup from './ValuationGroup.jsx';
import PeerBenchmarkGroup from './PeerBenchmark/PeerBenchmarkGroup.jsx';
import ExportMenu from './ExportMenu.jsx';
import CacheIndicator from './CacheIndicator.jsx';
import { getExportBridgeData } from '../export/exportDataBridge.js';

export { canDownloadDossier } from './AnalysisUtils.js';

function useCountUp(target, duration = 900) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (typeof window === 'undefined' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVal(target);
      return undefined;
    }
    let raf;
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min((now - t0) / duration, 1);
      setVal(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return val;
}

function ScoreRing({ total, color }) {
  const displayed = useCountUp(total);
  const R = 34;
  const C = 2 * Math.PI * R;
  const pct = Math.max(0, Math.min(1, scorePercent(total) / 100));
  return (
    <div style={{ position: 'relative', width: 92, height: 92, margin: '0 auto' }}>
      <svg width="92" height="92" viewBox="0 0 92 92" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="46" cy="46" r={R} fill="none" stroke="rgba(125,155,195,0.14)" strokeWidth="6" />
        <circle
          cx="46" cy="46" r={R} fill="none"
          stroke={color} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - pct)}
          style={{
            '--ring-c': C,
            animation: 'ringDraw 1.1s cubic-bezier(0.3, 0.7, 0.3, 1) both',
            filter: `drop-shadow(0 0 6px ${color}66)`,
          }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
      }}>
        <span className="mono" style={{ fontSize: 24, fontWeight: 700, color, lineHeight: 1, textShadow: `0 0 18px ${color}55` }}>
          {displayed}
        </span>
        <span className="mono" style={{ fontSize: 9, color: 'var(--faint)', marginTop: 2 }}>/40</span>
      </div>
    </div>
  );
}

export default function AnalysisCard({ result, onViewReport, t, lang }) {
  const { ticker, company_name, decision, scoring, conviction,
          price_native, currency, price_eur, market_cap, sector, retrieved_at } = result || {};

  const cardRef = useRef(null);

  const handleTilt = (e) => {
    const el = cardRef.current;
    if (!el || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(1100px) rotateX(${(-py * 3.2).toFixed(2)}deg) rotateY(${(px * 4.2).toFixed(2)}deg) translateY(-3px)`;
    el.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`);
    el.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`);
  };

  const resetTilt = () => {
    const el = cardRef.current;
    if (el) el.style.transform = '';
  };

  if (!result) return null;

  const color = SCORE_COLORS[decision] || '#8b949e';
  const total = scoring?.total || 0;
  const level = getConvictionLevel(conviction, scoring);
  const convictionColor = CONVICTION_COLORS[level];
  const insight = getInsight(scoring, t);

  const dossierStatus = useDossierPolling(ticker);
  const [downloadState, setDownloadState] = useState('idle');
  const [showChart, setShowChart] = useState(false);
  const downloadTimerRef = useRef(null);

  const [quarters, setQuarters] = useState([]);
  const [selectedQuarter, setSelectedQuarter] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchQuarters(ticker).then(data => {
      if (!cancelled) {
        const qs = data.quarters || [];
        setQuarters(qs);
        if (qs.length > 0) setSelectedQuarter(qs[0]);
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [ticker]);

  useEffect(() => {
    return () => { if (downloadTimerRef.current) clearTimeout(downloadTimerRef.current); };
  }, []);

  const downloadReady = canDownloadDossier(dossierStatus);
  const verificationBlocked = dossierStatus?.ready === true
    && dossierStatus?.verified === false
    && (dossierStatus?.phase === 'failed' || dossierStatus?.deep_dive_validated === false);

  const getSnapshotData = useCallback(() => {
    if (!result?.ticker) return null;
    const bridge = getExportBridgeData();
    return { result, ...(bridge.valuation ? { valuation: bridge.valuation } : {}),
      ...(bridge.valuation_context ? { valuation_context: bridge.valuation_context } : {}),
      ...(bridge.peer_benchmark ? { peer_benchmark: bridge.peer_benchmark } : {}),
      selected_group: 'valuation' };
  }, [result]);

  const handleDownload = async () => {
    if (downloadState === 'downloading') return;
    setDownloadState('downloading');
    const url = getTickerDownloadUrl(ticker, lang, selectedQuarter);
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl; a.download = `${ticker}_dossier.zip`;
      document.body.appendChild(a); a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(blobUrl); }, 100);
      setDownloadState('success');
      if (downloadTimerRef.current) clearTimeout(downloadTimerRef.current);
      downloadTimerRef.current = setTimeout(() => setDownloadState('idle'), 3000);
    } catch (err) {
      console.error('Download failed:', err);
      setDownloadState('error');
      if (downloadTimerRef.current) clearTimeout(downloadTimerRef.current);
      downloadTimerRef.current = setTimeout(() => setDownloadState('idle'), 5000);
    }
  };

  const phaseLabel = () => {
    switch (dossierStatus?.phase) {
      case 'scoring': return `⚡ ${t('scoringAnalysis')} ${dossierStatus?.sectionsReady ?? '?'}/7`;
      case 'scored': return `📊 ${lang === 'jp' ? 'スコア完了・PDF生成待ち' : 'Score ready. PDF pending...'}`;
      case 'pdf_generating': return `⏳ ${lang === 'jp' ? 'PDF生成中... (4〜7分)' : 'Generating PDF... (4-7 min)'}`;
      case 'pdf_validating': return `📋 ${lang === 'jp' ? 'PDF検証中...' : 'Validating PDF...'}`;
      case 'failed': return `⚠️ ${lang === 'jp' ? '生成失敗' : 'Generation failed'}`;
      default: return `${t('buildingDossier')} ${dossierStatus?.sectionsReady ?? '?'}/7`;
    }
  };

  return (
    <div ref={cardRef} className="card-holo" style={cardStyle}
      onMouseMove={handleTilt}
      onMouseLeave={resetTilt}>

      {/* ── DECISION HAIRLINE ── */}
      <div aria-hidden="true" style={{
        height: 2,
        background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
        boxShadow: `0 0 14px ${color}88`,
      }} />

      {/* ── HEADER ── */}
      <div style={headerStyle}>
        <div>
          <div className="mono" style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink)', letterSpacing: '0.06em' }}>{ticker}</div>
          <div style={{ fontSize: 9, color: 'var(--muted)', marginTop: 2 }}>{company_name}</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ExportMenu getSnapshotData={getSnapshotData} t={t} lang={lang} disabled={!result?.ticker} />
          {quarters.length > 1 && (
            <select value={selectedQuarter || quarters[0]} onChange={e => setSelectedQuarter(e.target.value)}
              style={quarterSelectStyle}>
              {quarters.map(q => <option key={q} value={q}>{q}</option>)}
            </select>
          )}
          <div style={{
            padding: '3px 10px', borderRadius: 999, fontSize: 10, fontWeight: 800,
            background: `${color}22`, color, border: `1px solid ${color}77`,
            letterSpacing: '0.08em', boxShadow: `0 0 14px ${color}33`,
          }}>
            {t(decision) || decision}
          </div>
        </div>
      </div>

      {/* ── SCORE ── */}
      <div style={{ padding: '12px 14px 10px', textAlign: 'center' }}>
        <ScoreRing total={total} color={scoreBarColor(total)} />
        <div style={{ fontSize: 8, color: 'var(--faint)', marginTop: 6, textTransform: 'uppercase', letterSpacing: '0.18em' }}>Composite Score</div>
        {result.data_quality && (
          <div style={dataQualityStyle(result.data_quality)}>
            {result.data_quality === 'complete' ? '🟢 ' : result.data_quality === 'partial' ? '🟡 ' : '🔴 '}
            {t(result.data_quality) || result.data_quality}
          </div>
        )}
      </div>

      {/* ── KEY METRICS ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 0, borderTop: '1px solid rgba(125,155,195,0.12)', borderBottom: '1px solid rgba(125,155,195,0.12)' }}>
        <MetricBox label="Price" value={price_native ? `${price_native.toFixed(0)} ${currency}` : '—'} />
        <MetricBox label="Mkt Cap" value={market_cap ? `${(market_cap / 1e12).toFixed(1)}T` : '—'} border />
        <MetricBox label="Sector" value={sector || '—'} />
        <MetricBox label="Retrieved" value={retrieved_at ? new Date(retrieved_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'} border />
      </div>

      {/* ── CACHE ── */}
      <div style={{ padding: '4px 14px', borderBottom: '1px solid rgba(125,155,195,0.12)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <CacheIndicator ticker={ticker} />
        <a
          href={getCompanyOverviewDownloadUrl(ticker)}
          target="_blank"
          rel="noreferrer"
          style={{
            fontSize: 11,
            color: 'var(--cyan)',
            background: 'rgba(125,155,195,0.12)',
            padding: '4px 10px',
            borderRadius: 6,
            textDecoration: 'none',
            border: '1px solid rgba(125,155,195,0.22)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}
        >
          🏢 {lang === 'jp' ? '会社概要をダウンロード' : 'Company Overview'}
        </a>
      </div>

      {/* ── VALUATION ── */}
      <div data-export-group="valuation" style={{ padding: '0 14px 4px', borderBottom: '1px solid rgba(125,155,195,0.12)' }}>
        <ValuationGroup ticker={ticker} result={result} />
      </div>

      {/* ── PEER BENCHMARK ── */}
      <div style={{ padding: '0 14px 4px', borderBottom: '1px solid rgba(125,155,195,0.12)' }}>
        <PeerBenchmarkGroup ticker={ticker} result={result} t={t} />
      </div>

      {/* ── AI INSIGHT ── */}
      {insight && (
        <div style={{ padding: '6px 14px', fontSize: 10, color: 'var(--muted)', background: 'rgba(125,155,195,0.06)', borderBottom: '1px solid rgba(125,155,195,0.12)', fontStyle: 'italic' }}>
          {insight}
        </div>
      )}

      {/* ── CHART ── */}
      <div style={{ padding: '8px 14px 4px' }}>
        <ScoringChart scoring={scoring} height={90} />
      </div>

      {/* ── ACTIONS ── */}
      <div style={{ padding: '8px 14px 6px', display: 'flex', gap: 6 }}>
        {dossierStatus?.verified ? (
          <button onClick={() => onViewReport(result, selectedQuarter)}
            style={actionBtnStyle}
            onMouseEnter={e => e.target.style.background = 'rgba(125,155,195,0.22)'}
            onMouseLeave={e => e.target.style.background = 'rgba(125,155,195,0.12)'}>
            📄 {t('viewFullReport')}</button>
        ) : (
          <div style={actionPlaceholderStyle}>
            📄 {lang === 'jp' ? '生成中...' : 'Building PDF...'}</div>
        )}
        <button onClick={() => setShowChart(s => !s)}
          style={{ width: 32, padding: '5px 0', fontSize: 12, background: showChart ? '#1f6feb' : 'rgba(125,155,195,0.12)',
            border: `1px solid ${showChart ? '#388bfd' : 'rgba(125,155,195,0.22)'}`, borderRadius: 5,
            color: showChart ? '#fff' : 'var(--muted)', cursor: 'pointer', transition: 'background 0.15s',
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          title={lang === 'jp' ? '指標履歴チャート' : 'Metrics history chart'}>📊</button>
        {downloadReady ? (
          <button onClick={handleDownload}
            style={{ ...downloadBtnStyle, background: downloadBtnColor(), border: downloadBtnBorder(),
              cursor: downloadState === 'downloading' ? 'wait' : 'pointer' }}>
            {downloadState === 'downloading' ? t('downloadingDossier')
              : downloadState === 'success' ? t('downloadComplete')
              : downloadState === 'error' ? t('downloadFailed')
              : `${t('downloadDossier')} (${dossierStatus?.sectionsReady ?? '?'}/7)`}</button>
        ) : verificationBlocked ? (
          <div style={errorPlaceholderStyle}>
            ⚠️ {lang === 'jp' ? '検証失敗' : 'Verification failed'} · {dossierStatus?.sectionsReady ?? '?'}/7</div>
        ) : dossierStatus?.phase === 'failed' ? (
          <button onClick={() => onViewReport(result, selectedQuarter)}
            style={retryBtnStyle}
            onMouseEnter={e => e.target.style.background = '#6b3030'}
            onMouseLeave={e => e.target.style.background = '#3d1f1f'}>
            🔄 {lang === 'jp' ? 'PDFを再試行' : 'Retry PDF'}</button>
        ) : (
          <div style={actionPlaceholderStyle}>
            {phaseLabel()}
            {dossierStatus?.pollFailures >= 3 && (
              <span style={{ display: 'block', fontSize: 9, color: '#d29922', marginTop: 2 }}>
                {lang === 'jp' ? 'ステータス再試行中' : 'Retrying status'}</span>)}
            {dossierStatus?.jp_degraded && (
              <span style={{ display: 'block', fontSize: 9, color: '#d29922', marginTop: 2 }}>
                🇯🇵 {lang === 'jp' ? '日本語訳の生成に失敗しました（英語のみ）' : 'JP translation unavailable (EN only)'}</span>)}
          </div>
        )}
      </div>

      {/* ── METRICS HISTORY CHART ── */}
      {showChart && (
        <div style={{ padding: '4px 14px 10px', borderTop: '1px solid rgba(125,155,195,0.12)' }}>
          <MetricsHistoryChart ticker={ticker} height={220} />
        </div>
      )}

      {/* ── CONVICTION ── */}
      <div style={{ padding: '4px 14px 10px', textAlign: 'center' }}>
        <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 3, fontSize: 8, fontWeight: 700,
          background: `${convictionColor}20`, color: convictionColor, border: `1px solid ${convictionColor}40`,
          textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {t(level)} {t('conviction')}</span>
      </div>

    </div>
  );
}

function MetricBox({ label, value, border }) {
  return (
    <div style={{ textAlign: 'center', padding: '5px 4px', borderLeft: border ? '1px solid rgba(125,155,195,0.12)' : 'none', borderRight: border ? '1px solid rgba(125,155,195,0.12)' : 'none' }}>
      <div style={{ fontSize: 8, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: '0.14em', marginBottom: 2 }}>{label}</div>
      <div className="mono" style={{ fontSize: 11, fontWeight: 600, color: 'var(--ink)' }}>{value}</div>
    </div>
  );
}

const cardStyle = { padding: 0, width: '100%' };
const headerStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px 8px', borderBottom: '1px solid rgba(125,155,195,0.12)' };
const quarterSelectStyle = { background: 'rgba(125,155,195,0.06)', border: '1px solid rgba(125,155,195,0.22)', borderRadius: 4, color: 'var(--cyan)', fontSize: 9, fontWeight: 500, padding: '2px 4px', cursor: 'pointer', outline: 'none', maxWidth: 68 };
const actionBtnStyle = { flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500, background: 'rgba(125,155,195,0.12)', border: '1px solid rgba(125,155,195,0.22)', borderRadius: 5, color: 'var(--cyan)', cursor: 'pointer', transition: 'background 0.15s' };
const actionPlaceholderStyle = { flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500, background: 'rgba(125,155,195,0.06)', border: '1px solid rgba(125,155,195,0.22)', borderRadius: 5, color: 'var(--muted)', textAlign: 'center' };
const errorPlaceholderStyle = { flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500, background: '#3d1f1f', border: '1px solid #6b3030', borderRadius: 5, color: '#f85149', textAlign: 'center' };
const retryBtnStyle = { flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500, background: '#3d1f1f', border: '1px solid #f85149', borderRadius: 5, color: '#f85149', cursor: 'pointer', transition: 'background 0.15s' };
const downloadBtnStyle = { flex: 1, padding: '5px 0', fontSize: 10, fontWeight: 500, borderRadius: 5, color: '#fff', cursor: 'pointer', textDecoration: 'none', textAlign: 'center', transition: 'background 0.15s, border 0.15s', fontFamily: 'inherit' };

function downloadBtnColor() { return '#238636'; }
function downloadBtnBorder() { return '1px solid #2ea043'; }

function dataQualityStyle(dq) {
  return { display: 'inline-block', marginTop: 4, padding: '1px 8px', borderRadius: 3, fontSize: 8, fontWeight: 700,
    background: dq === 'complete' ? '#23863620' : dq === 'partial' ? '#d2992220' : '#da363320',
    color: dq === 'complete' ? '#238636' : dq === 'partial' ? '#d29922' : '#da3633',
    border: `1px solid ${dq === 'complete' ? '#23863640' : dq === 'partial' ? '#d2992240' : '#da363340'}`,
    textTransform: 'uppercase', letterSpacing: 0.5 };
}
