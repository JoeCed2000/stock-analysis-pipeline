import {
  METRIC_CATEGORIES, CHART_COLORS, PERIOD_OPTIONS, VIEW_MODES,
  formatValue, formatAxis, formatQuarter, fmtPct, pctChange,
  calculateStats, getMetricUnit, getKpiLabels, getFooterLabels, getModeSubtitle,
  getMetricDefinition, getMetricLabel, getMetricColor, metricIsAvailable,
  getAvailableCategories, yoyIsAvailable,
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
  const yoyColor = stats.yoy != null && stats.yoy >= 0 ? '#238636' : '#da3633';

  const formatKpi = (val) => {
    if (val == null) return 'N/A';
    if (isPctView) return fmtPct(val);
    return formatValue(val, metric);
  };

  return (
    <div style={{
      display: 'flex', gap: 20, flexWrap: 'wrap',
      padding: '10px 14px', marginBottom: 8,
      background: '#0d1117', borderRadius: 6,
      border: '1px solid #21262d',
    }}>
      {isPctView ? (
        <>
          <KpiBox label={kpiLabels.latest} value={formatKpi(stats.latest)} color={color} bold />
          <KpiBox label={kpiLabels.peak} value={formatKpi(stats.peak)} color={stats.peak >= 0 ? '#238636' : '#da3633'} />
          <KpiBox label={kpiLabels.low} value={formatKpi(stats.low)} color={stats.low >= 0 ? '#238636' : '#da3633'} />
          <KpiBox label={kpiLabels.avg} value={formatKpi(stats.avg)} color="#e1e4e8" />
        </>
      ) : (
        <>
          <KpiBox label={kpiLabels.latest} value={formatKpi(stats.latest)} color={color} bold />
          {viewMode === 'yoy' ? (
            <KpiBox label="YoY" value={fmtPct(stats.yoy)} color={yoyColor} />
          ) : (
            <>
              <KpiBox label="QoQ" value={fmtPct(stats.qoq)} color={trendColor} />
              <KpiBox label={growthLabel} value={fmtPct(stats.totalChange)} color={growthColor} />
            </>
          )}
          {stats.yoy != null && viewMode !== 'yoy' && (
            <KpiBox label="YoY" value={fmtPct(stats.yoy)} color={yoyColor} />
          )}
          <KpiBox label={kpiLabels.peak} value={formatKpi(stats.peak)} color="#e1e4e8" />
          <KpiBox label={kpiLabels.avg} value={formatKpi(stats.avg)} color="#e1e4e8" />
        </>
      )}
    </div>
  );
}

// ── Category Selector ──
function CategorySelector({ categories, activeCategory, onChange, color }) {
  return (
    <div style={{ display: 'flex', gap: 2, marginBottom: 6 }}>
      {categories.map(cat => (
        <button
          key={cat.key}
          onClick={() => onChange(cat.key)}
          style={{
            flex: 1, padding: '5px 8px', fontSize: 10, fontWeight: activeCategory === cat.key ? 600 : 400,
            border: `1px solid ${activeCategory === cat.key ? color : '#3a4050'}`,
            borderRadius: 4,
            background: activeCategory === cat.key ? `${color}15` : '#161b22',
            color: activeCategory === cat.key ? color : '#c0c8d0',
            cursor: 'pointer', transition: 'all 0.25s',
          }}
        >
          {cat.label}
        </button>
      ))}
    </div>
  );
}

// ── Metric Tabs (within a category) ──
function MetricTabs({ category, metric, onChange, sortedData }) {
  const metrics = category?.metrics || [];
  if (metrics.length <= 1) return null;

  return (
    <div style={{ display: 'flex', gap: 2, marginBottom: 8, flexWrap: 'wrap' }}>
      {metrics.map(m => {
        const available = metricIsAvailable(sortedData, m.key);
        const active = metric === m.key;
        const mColor = getMetricColor(m.key);
        return (
          <button
            key={m.key}
            onClick={() => { if (available) onChange(m.key); }}
            disabled={!available}
            title={!available ? 'Not enough data for this metric' : m.label}
            style={{
              padding: '4px 10px', fontSize: 10, fontWeight: active ? 600 : 400,
              border: `1px solid ${active ? mColor : '#3a4050'}`,
              borderRadius: 4,
              background: active ? `${mColor}18` : '#161b22',
              color: active ? mColor : available ? '#c0c8d0' : '#484f58',
              cursor: available ? 'pointer' : 'not-allowed',
              transition: 'all 0.25s',
              opacity: available ? 1 : 0.4,
            }}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

// ── View Mode Toggle ──
function MetricModeToggle({ viewMode, onChange, color, effectivePeriod, yoyAvailable }) {
  const modes = yoyAvailable
    ? VIEW_MODES
    : VIEW_MODES.filter(m => m.key !== 'yoy');

  return (
    <div style={{ display: 'flex', gap: 1, background: '#1c2128', borderRadius: 4, padding: 2, border: '1px solid #30363d' }}>
      {modes.map(v => {
        const disabled = v.key === 'yoy' && !yoyAvailable;
        return (
          <button
            key={v.key}
            onClick={() => { if (!disabled) onChange(v.key); }}
            disabled={disabled}
            title={disabled ? 'Need at least 8 quarters for YoY' : v.label}
            style={{
              padding: '4px 10px', fontSize: 10, fontWeight: viewMode === v.key ? 600 : 400,
              border: 'none', borderRadius: 3,
              background: viewMode === v.key ? `${color}22` : 'transparent',
              color: viewMode === v.key ? color : disabled ? '#484f58' : '#8b949e',
              cursor: disabled ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
              opacity: disabled ? 0.4 : 1,
            }}
          >
            {v.key === 'growth' ? `${effectivePeriod}Q Growth` : v.label}
          </button>
        );
      })}
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

// ── Chart Tooltip ──
function ChartTooltip({ tooltip, metricKey, sorted, firstQuarter, avg, avgDisplay, growthLabel, color, isPctView, viewMode, w, h, pad }) {
  if (!tooltip) return null;

  const chartH = h - pad.top - pad.bottom;
  const isUpper = tooltip.y < pad.top + chartH * 0.55;
  const metricLabel = getMetricLabel(metricKey);

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
      {!isPctView && tooltip.i >= 4 && (
        <div style={{ color: '#9ba3ae', marginTop: 1 }}>
          YoY: <span style={{ color: pctChange(tooltip[metricKey], sorted[tooltip.i - 4]?.[metricKey]) >= 0 ? '#238636' : '#da3633' }}>
            {fmtPct(pctChange(tooltip[metricKey], sorted[tooltip.i - 4]?.[metricKey]))}
          </span>
        </div>
      )}
      {!isPctView && viewMode !== 'growth' && viewMode !== 'yoy' && (
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
      {isPctView && (
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
        Source: SEC filings · Yahoo Finance · Build {typeof __BUILD_COMMIT__ !== 'undefined' ? __BUILD_COMMIT__ : 'dev'} · {typeof __BUILD_DATE__ !== 'undefined' ? __BUILD_DATE__ : new Date().toISOString().slice(0, 10)}
      </div>
    </div>
  );
}

export {
  KpiBox, MetricKpiHeader, CategorySelector, MetricTabs,
  MetricModeToggle, PeriodSelector, ChartTooltip, ChartFooter,
};
