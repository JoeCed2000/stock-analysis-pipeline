import { useState, useEffect } from 'react';
import { setExportBridgeData } from '../../export/exportDataBridge.js';

/**
 * PeerBenchmarkGroup — V2.5 Group 9: Peer-relative benchmarks.
 *
 * NOTE:
 * The current backend contract returns a valuation/context-focused metric set
 * (pe_ttm, ps_ttm, pb_ratio, pe_forward, peg_ratio, total_debt).
 * This component mirrors that contract and renders explicit per-metric
 * unavailable reasons when a metric is missing for the ticker/peer set.
 */

// ── Metric display metadata aligned with backend contract ──
const VALUATION_METRICS = [
  { key: 'pe_ttm', label: 'P/E TTM' },
  { key: 'ps_ttm', label: 'P/S TTM' },
  { key: 'pb_ratio', label: 'P/B' },
];

const CONTEXT_METRICS = [
  { key: 'pe_forward', label: 'P/E Fwd' },
  { key: 'peg_ratio', label: 'PEG' },
  { key: 'total_debt', label: 'Total Debt' },
];

const STATUS_COLORS = {
  available: '#3fb950',
  limited: '#d29922',
  unavailable: '#f85149',
};

// ── Format helpers ──
function fmtMultiple(v) {
  if (v == null) return '—';
  return v.toFixed(1);
}

function fmtRatio(v) {
  if (v == null) return '—';
  return v.toFixed(2);
}

function fmtMoney(v) {
  if (v == null) return '—';
  const abs = Math.abs(v);
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}

const METRIC_FORMATTERS = {
  pe_ttm: fmtMultiple,
  ps_ttm: fmtMultiple,
  pb_ratio: fmtMultiple,
  pe_forward: fmtMultiple,
  peg_ratio: fmtRatio,
  total_debt: fmtMoney,
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

  // ── Export bridge (V2.6 T5) ──
  useEffect(() => {
    if (data) setExportBridgeData('peer_benchmark', data);
  }, [data]);

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
    high: { bg: 'rgba(63,185,80,0.15)', fg: '#3fb950' },
    medium: { bg: 'rgba(210,153,34,0.15)', fg: '#d29922' },
    low: { bg: 'rgba(248,81,73,0.15)', fg: '#f85149' },
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

      {/* ── Context table (aligned with backend keys) ── */}
      <div>
        <TableSection
          title={t ? t('peer_quality_peers') : 'Forward / Balance Context vs Peers'}
          subtitle={
            t
              ? undefined
              : 'Rendered from current backend contract (pe_forward, peg_ratio, total_debt) with explicit unavailable reasons.'
          }
          metrics={CONTEXT_METRICS}
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

function TableSection({ title, subtitle, metrics, benchmarks, t }) {
  const rows = metrics.map((m) => {
    const benchmark = benchmarks[m.key] || null;
    const formatter = METRIC_FORMATTERS[m.key] || fmtMultiple;
    const hasData = benchmark?.status === 'available';

    let reason = '';
    if (!benchmark) {
      reason = t ? t('peer_no_data') : 'Not returned by backend contract';
    } else if (!hasData) {
      reason = benchmark.label || benchmark.status || (t ? t('peer_no_data') : 'No data available');
    }

    return {
      metric: m,
      benchmark,
      hasData,
      formatter,
      reason,
    };
  });

  const availableCount = rows.filter((r) => r.hasData).length;

  return (
    <div>
      <div style={{
        padding: subtitle ? '6px 10px 1px' : '6px 10px 2px',
        fontSize: 9,
        fontWeight: 600,
        color: '#8b949e',
        letterSpacing: 0.3,
      }}>
        {title}
      </div>

      {subtitle && (
        <div style={{ padding: '0 10px 6px', fontSize: 8, color: '#6e7681', lineHeight: 1.4 }}>
          {subtitle}
        </div>
      )}

      {availableCount === 0 && (
        <div style={{ padding: '0 10px 6px', fontSize: 8, color: '#d29922', lineHeight: 1.4 }}>
          ⚠ {t ? t('peer_no_data') : 'No available metrics in this section for current ticker/peer sample.'}
        </div>
      )}

      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 0.9fr 0.9fr 1.4fr',
        gap: 0,
        padding: '2px 10px 4px',
      }}>
        <span style={thStyle}>{t ? t('peer_col_metric') : 'Metric'}</span>
        <span style={thStyle}>{t ? t('peer_col_company') : 'Company'}</span>
        <span style={thStyle}>{t ? t('peer_col_median') : 'Median'}</span>
        <span style={thStyle}>{t ? t('peer_col_context') : 'Context'}</span>
      </div>

      {/* Table rows */}
      {rows.map(({ metric, benchmark, hasData, formatter, reason }) => {
        const labelShort = hasData
          ? simplifyLabel(benchmark.label, metric.key)
          : `N/A — ${reason}`;

        return (
          <div
            key={metric.key}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 0.9fr 0.9fr 1.4fr',
              gap: 0,
              padding: '3px 10px',
              borderTop: '1px solid #21262d30',
              cursor: hasData ? 'help' : 'default',
            }}
            title={hasData ? benchmark.label : reason}
          >
            <span style={{ fontSize: 9, color: '#e1e4e8', fontWeight: 500 }}>
              {metric.label}
            </span>
            <span style={{ fontSize: 9, color: hasData ? '#58a6ff' : '#484f58', fontWeight: 600 }}>
              {hasData ? formatter(benchmark.value) : '—'}
            </span>
            <span style={{ fontSize: 9, color: hasData ? '#8b949e' : '#484f58' }}>
              {hasData ? formatter(benchmark.peer_median) : '—'}
            </span>
            <span style={{ fontSize: 8, color: hasData ? labelColor(benchmark) : '#d29922', lineHeight: 1.4 }}>
              {labelShort}
              {hasData && benchmark.percentile_rank != null && (
                <span style={{ color: '#484f58', marginLeft: 2 }}>
                  ({Math.round(benchmark.percentile_rank)}%ile)
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
  fontSize: 7,
  fontWeight: 600,
  color: '#484f58',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
};

function simplifyLabel(fullLabel) {
  if (!fullLabel) return '';
  if (fullLabel.includes('premium')) return '↑ premium';
  if (fullLabel.includes('discount')) return '↓ discount';
  if (fullLabel.includes('above peer median')) return '↑ above median';
  if (fullLabel.includes('below peer median')) return '↓ below median';
  if (fullLabel.includes('matches peer median')) return '≈ median';
  return fullLabel.length > 36 ? `${fullLabel.substring(0, 34)}…` : fullLabel;
}

function labelColor(benchmark) {
  if (!benchmark || benchmark.status !== 'available') return '#484f58';
  const label = benchmark.label || '';
  if (label.includes('above peer median') || label.includes('premium')) return '#e1e4e8';
  if (label.includes('below peer median') || label.includes('discount')) return '#e1e4e8';
  return '#8b949e';
}
