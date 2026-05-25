import { useState, useEffect, useMemo } from 'react';
import {
  VALUATION_METRICS, enrichData,
  formatMarketCap, formatEnterpriseValue, formatValuationMultiple, formatYield,
  getValuationAvailability, computeValuationMetrics,
} from './chartUtils';

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

          return (
            <div key={m.id} style={{
              textAlign: 'center', padding: '6px 3px',
              borderRight: (idx % 4 < 3) ? '1px solid #21262d' : 'none',
              borderBottom: (idx < 4) ? '1px solid #21262d' : 'none',
              cursor: evTitle ? 'help' : 'default',
            }} title={evTitle}>
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
