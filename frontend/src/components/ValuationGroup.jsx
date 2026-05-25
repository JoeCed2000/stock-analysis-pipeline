import { useState, useEffect, useMemo } from 'react';
import {
  VALUATION_METRICS, enrichData,
  formatMarketCap, formatEnterpriseValue, formatValuationMultiple, formatYield,
  getValuationAvailability, computeValuationMetrics,
} from './chartUtils';
import { fetchValuationContext } from '../api.js';
import { setExportBridgeData } from '../export/exportDataBridge.js';

const STATUS_COLORS = {
  fresh: '#3fb950',
  cached: '#d29922',
  stale: '#f85149',
  unavailable: '#484f58',
};

/**
 * ValuationGroup — displays 8 valuation metrics in a 4×2 grid.
 * Props:
 *   ticker — stock ticker symbol
 *   result — analysis result object (has market_cap, price_native, currency)
 *
 * Fetches /api/valuation/{ticker} for market metadata (status, source, served_from,
 * ev_source, quote_timestamp, quote_currency) — then fetches /api/metrics-history/{ticker}
 * for quarterly fundamentals to compute valuation multiples.
 */
export default function ValuationGroup({ ticker, result }) {
  const [valuationMeta, setValuationMeta] = useState(null);
  const [quarters, setQuarters] = useState(null);
  const [valuationContext, setValuationContext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ── Fetch market metadata from valuation API ──
  useEffect(() => {
    if (!ticker) return;
    fetch(`/api/valuation/${ticker}`)
      .then(r => r.json())
      .then(d => {
        if (d.detail) setError(d.detail);
        else setValuationMeta(d);
      })
      .catch(e => setError(e.message));
  }, [ticker]);

  // ── Fetch quarterly fundamentals ──
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    fetch(`/api/metrics-history/${ticker}`)
      .then(r => r.json())
      .then(d => {
        if (d.error) setError(d.error);
        else setQuarters(d.quarters || []);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [ticker]);

  // ── Fetch valuation context (V2.4) ──
  useEffect(() => {
    if (!ticker) return;
    fetchValuationContext(ticker)
      .then(d => setValuationContext(d || null))
      .catch(() => setValuationContext(null));
  }, [ticker]);

  const enriched = useMemo(() => {
    if (!quarters || quarters.length < 2) return null;
    const sorted = [...quarters].reverse();
    return enrichData(sorted);
  }, [quarters]);

  const metrics = useMemo(() => {
    if (!enriched) return null;
    return computeValuationMetrics(enriched, {
      market_cap: result?.market_cap,
      price_native: result?.price_native,
      currency: result?.currency || 'USD',
    });
  }, [enriched, result]);

  // ── Export bridge (V2.6 T5) ──
  useEffect(() => {
    if (valuationMeta) {
      setExportBridgeData('valuation', { ...valuationMeta, metrics: metrics || {} });
    }
    if (valuationContext) {
      setExportBridgeData('valuation_context', valuationContext);
    }
  }, [valuationMeta, metrics, valuationContext]);

  // ── Market metadata from valuation API (NOT local heuristics) ──
  const apiStatus = valuationMeta?.status || 'unavailable';
  const apiSource = valuationMeta?.source || 'unknown';
  const servedFrom = valuationMeta?.served_from || 'unknown';
  const quoteCurrency = valuationMeta?.quote_currency || 'USD';
  const evSource = valuationMeta?.ev_source || null;
  const quoteTimestamp = valuationMeta?.quote_timestamp;

  const quoteLabel = quoteTimestamp
    ? new Date(quoteTimestamp).toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short', year: '2-digit',
      })
    : '—';

  // ── V2.4: Enriched tooltip builder ──
  const buildTooltip = (metricKey) => {
    const latest = enriched ? enriched[enriched.length - 1] : null;
    const price = result?.price_native;
    const mktCap = result?.market_cap;
    const ctxTs = valuationContext?.quote_timestamp;
    const ctxSource = valuationContext?.source || 'unknown';
    const ctxStatus = valuationContext?.status || 'unavailable';
    const ctxCurrency = valuationContext?.currency || 'USD';
    const fmtTs = ctxTs
      ? new Date(ctxTs).toLocaleString('en-GB', {
          day: '2-digit', month: 'short', year: '2-digit',
          hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
        })
      : 'N/A';

    const formulaMap = {
      pe_ttm:    { formula: 'P/E TTM = Price / EPS TTM',
                   a: { label: 'Price', val: price },
                   b: { label: 'EPS TTM', val: latest?.eps_ttm } },
      ps_ttm:    { formula: 'P/S TTM = Market Cap / Revenue TTM',
                   a: { label: 'Market Cap', val: mktCap },
                   b: { label: 'Revenue TTM', val: latest?.revenue_ttm } },
      ev_ebitda: { formula: 'EV/EBITDA = Enterprise Value / EBITDA TTM',
                   a: { label: 'Enterprise Value', val: metrics?.enterprise_value },
                   b: { label: 'EBITDA TTM', val: latest?.ebitda_ttm } },
      p_fcf:     { formula: 'P/FCF = Market Cap / Free Cash Flow TTM',
                   a: { label: 'Market Cap', val: mktCap },
                   b: { label: 'FCF TTM', val: latest?.free_cash_flow_ttm } },
      fcf_yield: { formula: 'FCF Yield = Free Cash Flow TTM / Market Cap',
                   a: { label: 'FCF TTM', val: latest?.free_cash_flow_ttm },
                   b: { label: 'Market Cap', val: mktCap } },
    };

    const info = formulaMap[metricKey];
    if (!info) return null;

    const fmt = (v) => {
      if (v == null) return 'N/A';
      const abs = Math.abs(v);
      if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
      if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
      if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
      return `$${v.toFixed(2)}`;
    };

    return [
      info.formula,
      `${info.a.label}: ${fmt(info.a.val)} | ${info.b.label}: ${fmt(info.b.val)}`,
      `Quote: ${fmtTs}`,
      `Currency: ${ctxCurrency} | Source: ${ctxSource} | Status: ${ctxStatus}`,
    ].join('\n');
  };

  // ── V2.4: Format support label for display ──
  const formatSupportBadge = (level) => {
    if (!level || level === 'n/a') return null;
    const colors = {
      strong:   { bg: 'rgba(63,185,80,0.15)', fg: '#3fb950' },
      moderate: { bg: 'rgba(210,153,34,0.15)', fg: '#d29922' },
      weak:     { bg: 'rgba(248,81,73,0.15)', fg: '#f85149' },
      negative: { bg: 'rgba(248,81,73,0.18)', fg: '#f85149' },
      high:     { bg: 'rgba(63,185,80,0.15)', fg: '#3fb950' },
      medium:   { bg: 'rgba(210,153,34,0.15)', fg: '#d29922' },
      low:      { bg: 'rgba(248,81,73,0.15)', fg: '#f85149' },
    };
    const c = colors[level] || { bg: 'rgba(72,79,88,0.15)', fg: '#484f58' };
    return { bg: c.bg, fg: c.fg, label: level };
  };

  const contextSummary = valuationContext?.context?.context_summary || null;

  if (loading) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #21262d',
        borderRadius: 10, padding: '12px 14px', marginTop: 0,
      }}>
        <div style={{ fontSize: 10, color: '#484f58', textAlign: 'center' }}>
          Loading valuation data...
        </div>
      </div>
    );
  }

  if (error || !metrics) {
    return (
      <div style={{
        background: '#161b22', border: '1px solid #21262d',
        borderRadius: 10, padding: '12px 14px',
      }}>
        <div style={{ fontSize: 10, color: '#484f58', textAlign: 'center' }}>
          Valuation data unavailable
        </div>
      </div>
    );
  }

  const formatVal = (val, fmt) => {
    const currency = metrics.currency;
    if (fmt === 'cap') return formatMarketCap(val, currency);
    if (fmt === 'multiple') return formatValuationMultiple(val);
    if (fmt === 'yield') return formatYield(val);
    return val?.toFixed?.(1) ?? 'N/A';
  };

  return (
    <div style={{
      background: '#161b22', border: '1px solid #21262d',
      borderRadius: 10, padding: 0, overflow: 'hidden',
    }}>
      {/* Section header */}
      <div style={{
        padding: '8px 12px 6px', borderBottom: '1px solid #21262d',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: '#c9d1d9', letterSpacing: 0.3 }}>
          Valuation
        </span>
        <span style={{
          display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
          background: STATUS_COLORS[apiStatus] || '#484f58',
          title: `Data status: ${apiStatus}`,
        }} />
      </div>

      {/* ── V2.4: Valuation Context Summary Card ── */}
      {contextSummary && contextSummary.signals_available > 0 && (
        <div style={{
          padding: '6px 10px', borderBottom: '1px solid #21262d',
          background: 'rgba(56,139,253,0.06)',
        }}>
          {/* Top row: Level label + Confidence */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: 4,
          }}>
            <span style={{ fontSize: 9, fontWeight: 600, color: '#c9d1d9' }}>
              {contextSummary.valuation_level_label || 'N/A — insufficient data'}
            </span>
            {(() => {
              const badge = formatSupportBadge(contextSummary.confidence);
              return badge ? (
                <span style={{
                  fontSize: 7, fontWeight: 600, textTransform: 'uppercase',
                  letterSpacing: 0.5, padding: '1px 5px', borderRadius: 4,
                  background: badge.bg, color: badge.fg,
                }}>
                  {badge.label} confidence
                </span>
              ) : null;
            })()}
          </div>
          {/* Bottom row: Growth / Profitability / Cashflow badges */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { key: 'Growth', level: contextSummary.growth_support },
              { key: 'Profitability', level: contextSummary.profitability_support },
              { key: 'Cashflow', level: contextSummary.cashflow_support },
            ].map(({ key, level }) => {
              const badge = formatSupportBadge(level);
              return (
                <span key={key} style={{
                  fontSize: 7, fontWeight: 500, textTransform: 'uppercase',
                  letterSpacing: 0.4, padding: '1px 4px', borderRadius: 3,
                  background: badge ? badge.bg : 'rgba(72,79,88,0.1)',
                  color: badge ? badge.fg : '#484f58',
                }}>
                  {key}: {level || 'n/a'}
                </span>
              );
            })}
          </div>
          {/* Warnings */}
          {contextSummary.warnings && contextSummary.warnings.length > 0 && (
            <div style={{ marginTop: 4, fontSize: 7, color: '#f85149', lineHeight: 1.4 }}>
              {contextSummary.warnings.map((w, i) => (
                <div key={i}>⚠ {w}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 4×2 metric grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 0 }}>
        {VALUATION_METRICS.map((m, idx) => {
          const val = metrics[m.key];
          const avail = getValuationAvailability(val, quoteTimestamp);
          const displayed = formatVal(val, m.format);

          // Enterprise Value cell gets ev_source tooltip
          const isEv = m.key === 'enterprise_value';
          const evTitle = isEv && evSource
            ? `EV source: ${evSource}`
            : undefined;

          // V2.4: Enriched tooltip for 5 key valuation multiples
          const enrichedKeys = ['pe_ttm', 'ps_ttm', 'ev_ebitda', 'p_fcf', 'fcf_yield'];
          const enrichedTooltip = enrichedKeys.includes(m.key) ? buildTooltip(m.key) : null;

          const cellTitle = enrichedTooltip || evTitle;

          return (
            <div key={m.id} style={{
              textAlign: 'center', padding: '6px 3px',
              borderRight: (idx % 4 < 3) ? '1px solid #21262d' : 'none',
              borderBottom: (idx < 4) ? '1px solid #21262d' : 'none',
              cursor: cellTitle ? 'help' : 'default',
            }} title={cellTitle}>
              <div style={{
                fontSize: 8, color: '#484f58', textTransform: 'uppercase',
                letterSpacing: 0.5, marginBottom: 2,
              }}>
                {m.label}
              </div>
              <div style={{
                fontSize: 11, fontWeight: 600, color: avail.available ? '#e1e4e8' : '#484f58',
                lineHeight: 1.3,
              }}>
                {displayed}
              </div>
              {/* Mini status bar for freshness */}
              {avail.available && (
                <div style={{
                  margin: '2px auto 0', width: 12, height: 2,
                  borderRadius: 1,
                  background: STATUS_COLORS[avail.status] || '#484f58',
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* Footer — uses real API fields */}
      <div style={{
        padding: '5px 10px', borderTop: '1px solid #21262d',
        fontSize: 8, color: '#484f58', textAlign: 'center',
        display: 'flex', justifyContent: 'center', gap: 8, flexWrap: 'wrap',
      }}>
        <span>
          Market data:{' '}
          <span style={{ color: STATUS_COLORS[apiStatus] || '#484f58', fontWeight: 500 }}>
            {apiStatus}
          </span>
        </span>
        <span>·</span>
        <span>Source: {apiSource}</span>
        <span>·</span>
        <span>Served from {servedFrom}</span>
        <span>·</span>
        <span>Currency: {quoteCurrency}</span>
        <span>·</span>
        <span>Quote: {quoteLabel}</span>
      </div>
    </div>
  );
}
