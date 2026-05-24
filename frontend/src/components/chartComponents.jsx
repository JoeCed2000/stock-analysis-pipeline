import {
  METRICS, CHART_COLORS, PERIOD_OPTIONS, VIEW_MODES,
  formatValue, formatAxis, formatQuarter, fmtPct, pctChange,
  calculateStats, getMetricUnit, getKpiLabels, getFooterLabels, getModeSubtitle,
} from './chartUtils';

// ── KPI Box ──
function KpiBox({ label, value, color, bold }) {
  return (
    <div style={{ minWidth: 80 }}>
      <div style={{ fontSize: 9, color: '#6e7681', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{
        fontSize: bold ? 15 : 13, fontWeight: bold ? 700 : 500,
        color, lineHeight: 1.2,
      }}>
        {value}
      </div>
    </div>
  );
}

// ── KPI Header ──
function MetricKpiHeader({ stats, metric, viewMode, color, effectivePeriod }) {
  const isPctView = viewMode !== 'absolute';
  const kpiLabels = getKpiLabels(viewMode);
  const growthLabel = `${effectivePeriod}Q Growth`;
  const trendColor = stats.qoq != null && stats.qoq >= 0 ? '#238636' : '#da3633';
  const growthColor = stats.totalChange != null && stats.totalChange >= 0 ? '#238636' : '#da3633';

  return (
    <div style={{
      display: 'flex', gap: 20, flexWrap: 'wrap',
      padding: '10px 14px', marginBottom: 8,
      background: '#0d1117', borderRadius: 6,
      border: '1px solid #21262d',
    }}>
      {isPctView ? (
        <>
          <KpiBox label={kpiLabels.latest} value={fmtPct(stats.latest)} color={color} bold />
          <KpiBox label={kpiLabels.peak} value={fmtPct(stats.peak)} color={stats.peak >= 0 ? '#238636' : '#da3633'} />
          <KpiBox label={kpiLabels.low} value={fmtPct(stats.low)} color={stats.low >= 0 ? '#238636' : '#da3633'} />
          <KpiBox label={kpiLabels.avg} value={fmtPct(stats.avg)} color="#e1e4e8" />
        </>
      ) : (
        <>
          <KpiBox label={kpiLabels.latest} value={formatValue(stats.latest, metric)} color={color} bold />
          <KpiBox label="QoQ" value={fmtPct(stats.qoq)} color={trendColor} />
          <KpiBox label={growthLabel} value={fmtPct(stats.totalChange)} color={growthColor} />
          <KpiBox label={kpiLabels.peak} value={formatValue(stats.peak, metric)} color="#e1e4e8" />
          <KpiBox label={kpiLabels.avg} value={formatValue(stats.avg, metric)} color="#e1e4e8" />
        </>
      )}
    </div>
  );
}

// ── View Mode Toggle ──
function MetricModeToggle({ viewMode, onChange, color, effectivePeriod }) {
  return (
    <div style={{ display: 'flex', gap: 1, background: '#1c2128', borderRadius: 4, padding: 2, border: '1px solid #30363d' }}>
      {VIEW_MODES.map(v => (
        <button
          key={v.key}
          onClick={() => onChange(v.key)}
          style={{
            padding: '4px 10px', fontSize: 10, fontWeight: viewMode === v.key ? 600 : 400,
            border: 'none', borderRadius: 3,
            background: viewMode === v.key ? `${color}22` : 'transparent',
            color: viewMode === v.key ? color : '#8b949e',
            cursor: 'pointer', transition: 'all 0.2s',
          }}
        >
          {v.key === 'growth' ? `${effectivePeriod}Q Growth` : v.label}
        </button>
      ))}
    </div>
  );
}

// ── Period Selector ──
function PeriodSelector({ period, effectivePeriod, maxAvailable, onChange, color }) {
  return (
    <div style={{ display: 'flex', gap: 1, marginLeft: 'auto', background: '#1c2128', borderRadius: 4, padding: 2, border: '1px solid #30363d' }}>
      {PERIOD_OPTIONS.map(p => {
        const available = p <= maxAvailable;
        return (
          <button
            key={p}
            onClick={() => { if (available) onChange(p); }}
            disabled={!available}
            title={!available ? 'Not enough historical data' : `Show last ${p} quarters`}
            style={{
              padding: '4px 8px', fontSize: 10, fontWeight: effectivePeriod === p ? 600 : 400,
              border: 'none', borderRadius: 3,
              background: effectivePeriod === p ? `${color}22` : 'transparent',
              color: effectivePeriod === p ? color : available ? '#8b949e' : '#484f58',
              cursor: available ? 'pointer' : 'not-allowed', transition: 'all 0.2s',
              opacity: available ? 1 : 0.4,
            }}
          >
            {p}Q
          </button>
        );
      })}
    </div>
  );
}

// ── Metric Tabs ──
function MetricTabs({ metric, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 2, marginBottom: 8 }}>
      {METRICS.map(m => (
        <button
          key={m.key}
          onClick={() => onChange(m.key)}
          style={{
            flex: 1, padding: '5px 0', fontSize: 11, fontWeight: metric === m.key ? 600 : 400,
            border: `1px solid ${metric === m.key ? CHART_COLORS[m.key] : '#3a4050'}`,
            borderRadius: 4,
            background: metric === m.key ? `${CHART_COLORS[m.key]}18` : '#161b22',
            color: metric === m.key ? CHART_COLORS[m.key] : '#c0c8d0',
            cursor: 'pointer', transition: 'all 0.25s',
          }}
          onMouseEnter={e => {
            if (metric !== m.key) {
              e.target.style.background = '#1c2128';
              e.target.style.color = '#d2d9e0';
            }
          }}
          onMouseLeave={e => {
            if (metric !== m.key) {
              e.target.style.background = '#161b22';
              e.target.style.color = '#c0c8d0';
            }
          }}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

// ── Chart Tooltip ──
function ChartTooltip({ tooltip, metric, metricKey, sorted, firstQuarter, avg, avgDisplay, growthLabel, color, isPctView, viewMode, w, h, pad }) {
  if (!tooltip) return null;

  // Smart placement: if point is in top 55% of chart, place below; otherwise above
  const chartH = h - pad.top - pad.bottom;
  const isUpper = tooltip.y < pad.top + chartH * 0.55;

  return (
    <div style={{
      position: 'absolute',
      left: Math.min(Math.max(tooltip.x, 130), w - 130),
      ...(isUpper ? { top: tooltip.y + 16 } : { bottom: h - tooltip.y + 12 }),
      transform: 'translateX(-50%)',
      background: '#161b22', border: `1px solid ${color}44`,
      borderRadius: 8, padding: '8px 12px', color: '#c9d1d9',
      fontSize: 11, pointerEvents: 'none', zIndex: 10,
      whiteSpace: 'nowrap', boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color }}>{formatQuarter(tooltip.quarter)}</div>
      <div style={{ color, fontWeight: 600, marginBottom: 3 }}>
        {isPctView ? fmtPct(tooltip.displayVal) : formatValue(tooltip.displayVal, metricKey)}
      </div>
      {!isPctView && tooltip.i > 0 && (
        <div style={{ color: '#9ba3ae', marginTop: 1 }}>
          QoQ: <span style={{ color: pctChange(tooltip[metricKey], sorted[tooltip.i - 1]?.[metricKey]) >= 0 ? '#238636' : '#da3633' }}>
            {fmtPct(pctChange(tooltip[metricKey], sorted[tooltip.i - 1]?.[metricKey]))}
          </span>
        </div>
      )}
      {!isPctView && (
        <div style={{ color: '#9ba3ae', marginTop: 1 }}>
          {growthLabel}: <span style={{ color: pctChange(tooltip[metricKey], firstQuarter[metricKey]) >= 0 ? '#238636' : '#da3633' }}>
            {fmtPct(pctChange(tooltip[metricKey], firstQuarter[metricKey]))}
          </span>
        </div>
      )}
      {!isPctView && (
        <div style={{ color: '#9ba3ae', marginTop: 1 }}>
          vs avg: <span style={{ color: tooltip[metricKey] >= avg ? '#238636' : '#da3633' }}>
            {fmtPct(pctChange(tooltip[metricKey], avg))}
          </span>
        </div>
      )}
      {isPctView && tooltip.i > 0 && (
        <div style={{ color: '#9ba3ae', marginTop: 1 }}>
          Abs: <span style={{ color: '#e1e4e8' }}>{formatValue(tooltip[metricKey], metricKey)}</span>
        </div>
      )}
    </div>
  );
}

// ── Chart Footer ──
function ChartFooter({ low, peak, periodLabel, footerLabels, isPctView, metric }) {
  const formatDisplay = (val) => {
    if (val == null) return 'N/A';
    if (isPctView) return fmtPct(val);
    return formatValue(val, metric);
  };

  return (
    <div style={{
      background: '#0d1117', borderRadius: '0 0 6px 6px',
      borderTop: '1px solid #21262d', padding: '8px 14px 6px',
    }}>
      <div style={{
        display: 'flex', gap: 16, fontSize: 10, color: '#9ba3ae', marginBottom: 3,
      }}>
        <span>{footerLabels.low}: <b style={{ color: '#e1e4e8' }}>{formatDisplay(low)}</b></span>
        <span>{footerLabels.high}: <b style={{ color: '#e1e4e8' }}>{formatDisplay(peak)}</b></span>
        <span style={{ marginLeft: 'auto' }}>{periodLabel}</span>
      </div>
      <div style={{ fontSize: 9, color: '#6e7681', textAlign: 'right' }}>
        Source: SEC filings · Yahoo Finance · Updated May 2026
      </div>
    </div>
  );
}

export {
  KpiBox, MetricKpiHeader, MetricModeToggle, PeriodSelector,
  MetricTabs, ChartTooltip, ChartFooter,
};
