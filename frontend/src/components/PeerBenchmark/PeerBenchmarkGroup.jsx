import { useState, useEffect, useMemo } from 'react';

/**
 * PeerBenchmarkGroup — V2.5 Group 9: Peer-relative benchmarks.
 *
 * Fetches /api/peer-benchmark/{ticker} and renders:
 *   1. Summary Card — group_name + sample_size + confidence
 *   2. Relative Valuation Table — valuation multiples vs peers
 *   3. Quality vs Peers Table — quality & profitability metrics vs peers
 *
 * Props:
 *   ticker — stock ticker symbol
 *   result — analysis result object
 *   t     — i18n translation function
 */

// ── Metric display metadata ──
const VALUATION_METRICS = [
  { key: 'pe_ttm',     label: 'P/E TTM' },
  { key: 'ps_ttm',     label: 'P/S TTM' },
  { key: 'ev_ebitda',  label: 'EV/EBITDA' },
  { key: 'p_fcf',      label: 'P/FCF' },
  { key: 'pe_forward', label: 'P/E Fwd' },
  { key: 'peg_ratio',  label: 'PEG' },
];

const QUALITY_METRICS = [
  { key: 'gross_margin',     label: 'Gross Margin' },
  { key: 'operating_margin', label: 'Op Margin' },
  { key: 'net_margin',       label: 'Net Margin' },
  { key: 'roic',             label: 'ROIC' },
  { key: 'roe',              label: 'ROE' },
  { key: 'roa',              label: 'ROA' },
  { key: 'fcf_yield',        label: 'FCF Yield' },
  { key: 'debt_to_equity',   label: 'D/E' },
  { key: 'debt_to_ebitda',   label: 'Debt/EBITDA' },
];

const STATUS_COLORS = {
  available: '#3fb950',
  limited:   '#d29922',
  unavailable: '#f85149',
};

// ── Format helpers ──
function fmtMultiple(v) {
  if (v == null) return '—';
  return v.toFixed(1);
}

function fmtPercent(v) {
  if (v == null) return '—';
  return `${v.toFixed(1)}%`;
}

function fmtRatio(v) {
  if (v == null) return '—';
  return v.toFixed(2);
}

const METRIC_FORMATTERS = {
  pe_ttm:     fmtMultiple,
  ps_ttm:     fmtMultiple,
  ev_ebitda:  fmtMultiple,
  p_fcf:      fmtMultiple,
  pe_forward: fmtMultiple,
  peg_ratio:  fmtRatio,
  gross_margin:     fmtPercent,
  operating_margin: fmtPercent,
  net_margin:       fmtPercent,
  roic:             fmtPercent,
  roe:              fmtPercent,
  roa:              fmtPercent,
  fcf_yield:        fmtPercent,
  debt_to_equity:   fmtRatio,
  debt_to_ebitda:   fmtRatio,
};

export default function PeerBenchmarkGroup({ ticker, result, t }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    fetch(`/api/peer-benchmark/${ticker}`)
      .then(r => r.json())
      .then(d => {
        if (d.detail) setError(d.detail);
        else setData(d);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [ticker]);

  const peerCtx = data?.peer_context || {};
  const benchmarks = data?.benchmarks || {};
  const summary = data?.summary || {};
  const warnings = data?.warnings || [];
  const apiStatus = data?.status || 'unavailable';

  // ── Loading state ──
  if (loading) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #21262d',
        borderRadius: 10, padding: '12px 14px', marginTop: 0,
      }}>
        <div style={{ fontSize: 10, color: '#484f58', textAlign: 'center' }}>
          {t ? t('peer_loading') : 'Loading peer benchmark...'}
        </div>
      </div>
    );
  }

  // ── Error / unavailable state ──
  if (error || !data) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #21262d',
        borderRadius: 10, padding: '12px 14px',
      }}>
        <div style={{ fontSize: 10, color: '#484f58', textAlign: 'center' }}>
          {t ? t('peer_unavailable') : 'Peer benchmark unavailable'}
        </div>
        {error && (
          <div style={{ fontSize: 8, color: '#f85149', textAlign: 'center', marginTop: 4 }}>
            {error}
          </div>
        )}
      </div>
    );
  }

  // ── If peer_context says unavailable ──
  if (!peerCtx.available) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #21262d',
        borderRadius: 10, padding: 0, overflow: 'hidden',
      }}>
        <GroupHeader
          label={t ? t('peer_benchmark') : 'Peer Benchmark'}
          status={apiStatus}
          statusColor={STATUS_COLORS[apiStatus] || '#484f58'}
        />
        <div style={{ padding: '10px 12px', fontSize: 10, color: '#8b949e', textAlign: 'center' }}>
          {t ? t('peer_not_available') : 'This ticker has no peer benchmark data available'}
        </div>
        {warnings.length > 0 && (
          <div style={{ padding: '4px 12px 8px' }}>
            {warnings.map((w, i) => (
              <div key={i} style={{ fontSize: 8, color: '#d29922' }}>⚠ {w}</div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Available state: full benchmark ──
  const confidenceColors = {
    high:               { bg: 'rgba(63,185,80,0.15)', fg: '#3fb950' },
    medium:             { bg: 'rgba(210,153,34,0.15)', fg: '#d29922' },
    low:                { bg: 'rgba(248,81,73,0.15)', fg: '#f85149' },
    'no data available': { bg: 'rgba(72,79,88,0.15)', fg: '#484f58' },
    'insufficient data': { bg: 'rgba(72,79,88,0.15)', fg: '#484f58' },
  };
  const confStyle = confidenceColors[summary.confidence] || confidenceColors['no data available'];

  return (
    <div style={{
      background: '#161b22', border: '1px solid #21262d',
      borderRadius: 10, padding: 0, overflow: 'hidden',
    }}>
      {/* Section header */}
      <GroupHeader
        label={t ? t('peer_benchmark') : 'Peer Benchmark'}
        status={apiStatus}
        statusColor={STATUS_COLORS[apiStatus] || '#484f58'}
      />

      {/* ── Summary Card ── */}
      <div style={{
        padding: '8px 10px', borderBottom: '1px solid #21262d',
        background: 'rgba(56,139,253,0.06)',
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: 4,
        }}>
          <span style={{ fontSize: 10, fontWeight: 600, color: '#c9d1d9' }}>
            {peerCtx.group_label || peerCtx.group_id || 'Peer Group'}
            {' · '}
            {peerCtx.sample_size}/{peerCtx.total_peers} peers
          </span>
          <span style={{
            fontSize: 7, fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: 0.5, padding: '1px 5px', borderRadius: 4,
            background: confStyle.bg, color: confStyle.fg,
          }}>
            {summary.confidence} confidence
          </span>
        </div>
        {/* Category summaries */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {[
            { key: t ? t('peer_valuation') : 'Valuation', text: summary.relative_valuation },
            { key: t ? t('peer_growth') : 'Growth', text: summary.growth_support },
            { key: t ? t('peer_quality') : 'Quality', text: summary.quality_support },
          ].map(({ key, text }) => (
            <span key={key} style={{
              fontSize: 7, fontWeight: 500,
              padding: '1px 4px', borderRadius: 3,
              background: 'rgba(72,79,88,0.1)', color: '#8b949e',
            }}>
              {key}: {text}
            </span>
          ))}
        </div>
        {/* Warnings */}
        {warnings.length > 0 && (
          <div style={{ marginTop: 4, fontSize: 7, color: '#d29922', lineHeight: 1.4 }}>
            {warnings.map((w, i) => (
              <div key={i}>⚠ {w}</div>
            ))}
          </div>
        )}
      </div>

      {/* ── Relative Valuation Table ── */}
      <div style={{ borderBottom: '1px solid #21262d' }}>
        <TableSection
          title={t ? t('peer_relative_valuation') : 'Relative Valuation vs Peers'}
          metrics={VALUATION_METRICS}
          benchmarks={benchmarks}
          t={t}
        />
      </div>

      {/* ── Quality vs Peers Table ── */}
      <div>
        <TableSection
          title={t ? t('peer_quality_peers') : 'Quality vs Peers'}
          metrics={QUALITY_METRICS}
          benchmarks={benchmarks}
          t={t}
        />
      </div>
    </div>
  );
}

// ── Sub-components ──

function GroupHeader({ label, status, statusColor }) {
  return (
    <div style={{
      padding: '8px 12px 6px', borderBottom: '1px solid #21262d',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    }}>
      <span style={{ fontSize: 10, fontWeight: 600, color: '#c9d1d9', letterSpacing: 0.3 }}>
        {label}
      </span>
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
        background: statusColor,
        title: `Data status: ${status}`,
      }} />
    </div>
  );
}

function TableSection({ title, metrics, benchmarks, t }) {
  const availableMetrics = metrics.filter(m => benchmarks[m.key]);

  if (availableMetrics.length === 0) {
    return (
      <div>
        <div style={{
          padding: '6px 10px', fontSize: 9, fontWeight: 600,
          color: '#8b949e', letterSpacing: 0.3,
        }}>
          {title}
        </div>
        <div style={{ padding: '6px 10px', fontSize: 9, color: '#484f58', textAlign: 'center' }}>
          {t ? t('peer_no_data') : 'No data available'}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{
        padding: '6px 10px 2px', fontSize: 9, fontWeight: 600,
        color: '#8b949e', letterSpacing: 0.3,
      }}>
        {title}
      </div>
      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 0.8fr 0.8fr 1.2fr',
        gap: 0, padding: '2px 10px 4px',
      }}>
        <span style={thStyle}>{t ? t('peer_col_metric') : 'Metric'}</span>
        <span style={thStyle}>{t ? t('peer_col_company') : 'Company'}</span>
        <span style={thStyle}>{t ? t('peer_col_median') : 'Median'}</span>
        <span style={thStyle}>{t ? t('peer_col_context') : 'Context'}</span>
      </div>
      {/* Table rows */}
      {availableMetrics.map(m => {
        const b = benchmarks[m.key];
        const formatter = METRIC_FORMATTERS[m.key] || fmtMultiple;
        const hasData = b.status === 'available';
        const labelShort = hasData
          ? simplifyLabel(b.label, m.key)
          : (b.label || 'N/A');

        return (
          <div key={m.key} style={{
            display: 'grid',
            gridTemplateColumns: '1fr 0.8fr 0.8fr 1.2fr',
            gap: 0, padding: '3px 10px',
            borderTop: '1px solid #21262d30',
            cursor: hasData ? 'help' : 'default',
          }} title={hasData ? b.label : undefined}>
            <span style={{ fontSize: 9, color: '#e1e4e8', fontWeight: 500 }}>
              {m.label}
            </span>
            <span style={{ fontSize: 9, color: hasData ? '#58a6ff' : '#484f58', fontWeight: 600 }}>
              {hasData ? formatter(b.value) : '—'}
            </span>
            <span style={{ fontSize: 9, color: '#8b949e' }}>
              {hasData ? formatter(b.peer_median) : '—'}
            </span>
            <span style={{ fontSize: 8, color: labelColor(b), lineHeight: 1.4 }}>
              {labelShort}
              {b.percentile_rank != null && (
                <span style={{ color: '#484f58', marginLeft: 2 }}>
                  ({Math.round(b.percentile_rank)}%ile)
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Helpers ──

const thStyle = {
  fontSize: 7, fontWeight: 600, color: '#484f58',
  textTransform: 'uppercase', letterSpacing: 0.5,
};

function simplifyLabel(fullLabel, metricKey) {
  // Extract just the direction: "above peer median" / "below peer median" / "premium" / "discount"
  if (!fullLabel) return '';
  if (fullLabel.includes('premium')) return '↑ premium';
  if (fullLabel.includes('discount')) return '↓ discount';
  if (fullLabel.includes('above peer median')) return '↑ above median';
  if (fullLabel.includes('below peer median')) return '↓ below median';
  if (fullLabel.includes('matches peer median')) return '≈ median';
  return fullLabel.length > 30 ? fullLabel.substring(0, 28) + '…' : fullLabel;
}

function labelColor(benchmark) {
  if (!benchmark || benchmark.status !== 'available') return '#484f58';
  const label = benchmark.label || '';
  if (label.includes('above peer median') || label.includes('premium')) return '#e1e4e8';
  if (label.includes('below peer median') || label.includes('discount')) return '#e1e4e8';
  return '#8b949e';
}
