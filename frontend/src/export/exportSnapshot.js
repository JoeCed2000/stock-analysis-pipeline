import {
  EXPORT_ALLOWED_ENUMS,
  EXPORT_METRIC_ROW_FIELDS,
  EXPORT_NA,
  EXPORT_SNAPSHOT_VERSION,
  FORBIDDEN_EXPORT_KEY_PATTERNS,
  FORBIDDEN_EXPORT_VALUE_PATTERNS,
} from './exportConstants.js';

export {
  EXPORT_ALLOWED_ENUMS,
  EXPORT_METRIC_ROW_FIELDS,
  EXPORT_NA,
  EXPORT_SNAPSHOT_VERSION,
};

const METADATA_KEYS = new Set([
  'source',
  'served_from',
  'status',
  'quote_timestamp',
  'fundamentals_timestamp',
  'market_data_status',
  'currency',
  'metrics',
  'warnings',
]);

export function isForbiddenExportKey(key) {
  const text = String(key || '');
  return FORBIDDEN_EXPORT_KEY_PATTERNS.some(pattern => pattern.test(text));
}

function hasForbiddenStringValue(value) {
  if (typeof value !== 'string') return false;
  return FORBIDDEN_EXPORT_VALUE_PATTERNS.some(pattern => pattern.test(value));
}

export function normalizeExportNA(value) {
  if (value === null || value === undefined) return EXPORT_NA;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : EXPORT_NA;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return EXPORT_NA;
    const lower = trimmed.toLowerCase();
    if (trimmed === '—' || lower === 'n/a' || lower === 'na' || lower === 'no data available') {
      return EXPORT_NA;
    }
    if (hasForbiddenStringValue(trimmed)) return EXPORT_NA;
    return trimmed;
  }
  return value;
}

function isNAToken(value) {
  return normalizeExportNA(value) === EXPORT_NA;
}

function shouldPreserveMetricNull(path) {
  return path[path.length - 1] === 'value' && path.includes('metrics');
}

export function sanitizeExportValue(value, path = []) {
  if (shouldPreserveMetricNull(path) && (value === null || value === undefined || isNAToken(value))) {
    return null;
  }
  const leafKey = path[path.length - 1];
  if ((leafKey === 'status' || leafKey === 'market_data_status') && String(value).toLowerCase() === 'na') {
    return 'na';
  }

  const normalized = normalizeExportNA(value);
  if (normalized === EXPORT_NA) return EXPORT_NA;

  if (Array.isArray(normalized)) {
    return normalized
      .map((entry, index) => sanitizeExportValue(entry, path.concat(String(index))))
      .filter(entry => entry !== undefined);
  }

  if (normalized && typeof normalized === 'object') {
    const cleaned = {};
    for (const [key, entryValue] of Object.entries(normalized)) {
      if (isForbiddenExportKey(key)) continue;
      if (key === 'currency' || key.endsWith('_currency')) {
        if (path.length === 0 && key === 'currency') cleaned[key] = 'USD';
        continue;
      }
      const cleanedValue = sanitizeExportValue(entryValue, path.concat(key));
      if (cleanedValue !== undefined) cleaned[key] = cleanedValue;
    }
    return cleaned;
  }

  return normalized;
}

export function normalizeExportSource(source) {
  const normalized = String(normalizeExportNA(source)).toLowerCase();
  return EXPORT_ALLOWED_ENUMS.source.includes(normalized) ? normalized : 'unknown';
}

export function normalizeExportServedFrom(servedFrom) {
  const normalized = String(normalizeExportNA(servedFrom)).toLowerCase();
  return EXPORT_ALLOWED_ENUMS.served_from.includes(normalized) ? normalized : 'unknown';
}

export function normalizeExportStatus(status, fallback = 'unknown') {
  const normalized = String(normalizeExportNA(status)).toLowerCase();
  if (normalized === EXPORT_NA.toLowerCase()) return fallback;
  if (['ok', 'fresh', 'available'].includes(normalized)) return 'ok';
  if (['partial', 'limited'].includes(normalized)) return 'partial';
  if (normalized === 'cached') return 'cached';
  if (['stale', 'stale_cache'].includes(normalized)) return 'stale';
  if (['na', 'n/a', 'unavailable', 'not_available'].includes(normalized)) return 'na';
  return EXPORT_ALLOWED_ENUMS.status.includes(normalized) ? normalized : 'unknown';
}

export function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  for (const key of Object.getOwnPropertyNames(value)) {
    deepFreeze(value[key]);
  }
  return Object.freeze(value);
}

function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function normalizeTimestamp(value) {
  return normalizeExportNA(value);
}

function safeString(value) {
  return normalizeExportNA(value);
}

function labelizeMetricKey(key) {
  const safeKey = safeString(key);
  if (safeKey === EXPORT_NA) return EXPORT_NA;
  return safeKey
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function toMetricValue(value) {
  return isNAToken(value) ? null : sanitizeExportValue(value, ['metrics', 'value']);
}

function toFormattedValue(row, value) {
  const formatted = row.formatted_value ?? row.formattedValue ?? row.display_value ?? row.displayed ?? row.display ?? row.formatted;
  if (!isNAToken(formatted)) return safeString(formatted);
  if (value === null) return EXPORT_NA;
  return safeString(String(value));
}

function metricRowFromObject(rowInput, defaults = {}) {
  const row = asObject(sanitizeExportValue(rowInput));
  const key = safeString(row.key ?? defaults.key);
  if (key === EXPORT_NA || isForbiddenExportKey(key)) return null;

  const rawValue = row.value ?? row.raw_value ?? row.rawValue ?? row.current ?? row.amount;
  const value = toMetricValue(rawValue);
  const hasProvidedLabel = Object.prototype.hasOwnProperty.call(row, 'label');
  const label = hasProvidedLabel ? safeString(row.label) : labelizeMetricKey(key);
  const status = value === null ? 'na' : normalizeExportStatus(row.status ?? defaults.status, 'unknown');

  return {
    key,
    label,
    value,
    formatted_value: toFormattedValue(row, value),
    unit: safeString(row.unit ?? defaults.unit),
    status,
    source: normalizeExportSource(row.source ?? defaults.source),
    served_from: normalizeExportServedFrom(row.served_from ?? defaults.served_from),
    timestamp: normalizeTimestamp(row.timestamp ?? defaults.timestamp),
    notes: safeString(row.notes ?? row.note ?? row.label_context ?? defaults.notes),
  };
}

function metricRowsFromObjectMap(metrics, defaults = {}) {
  return Object.entries(asObject(metrics))
    .map(([key, entryValue]) => {
      if (isForbiddenExportKey(key)) return null;
      const rowInput = entryValue && typeof entryValue === 'object' && !Array.isArray(entryValue)
        ? { key, ...entryValue }
        : { key, value: entryValue, formatted_value: isNAToken(entryValue) ? EXPORT_NA : String(entryValue) };
      return metricRowFromObject(rowInput, defaults);
    })
    .filter(Boolean);
}

export function buildMetricRows(metricsInput, defaults = {}) {
  if (Array.isArray(metricsInput)) {
    return metricsInput
      .map(entry => metricRowFromObject(entry, defaults))
      .filter(Boolean);
  }
  if (metricsInput && typeof metricsInput === 'object') {
    return metricRowsFromObjectMap(metricsInput, defaults);
  }
  return [];
}

function valuationMetricsInput(valuationInput) {
  if (valuationInput.metrics !== undefined) return valuationInput.metrics;
  if (valuationInput.values !== undefined) return valuationInput.values;
  const candidates = {};
  for (const [key, value] of Object.entries(valuationInput)) {
    if (!METADATA_KEYS.has(key) && !isForbiddenExportKey(key)) candidates[key] = value;
  }
  return candidates;
}

function peerBenchmarkMetricRows(peerInput, defaults = {}) {
  return buildMetricRows(peerInput.benchmarks, {
    ...defaults,
    notes: undefined,
  }).map(row => {
    const benchmark = asObject(peerInput.benchmarks?.[row.key]);
    return {
      ...row,
      notes: safeString(benchmark.label ?? benchmark.context ?? row.notes),
    };
  });
}

function buildGroups({ selectedGroup, valuation, valuationMetrics, valuationContext, peerBenchmark, peerMetrics }) {
  const groups = [];
  if (valuationMetrics.length > 0 || valuation.status !== 'unknown') {
    groups.push({
      id: 'valuation',
      label: 'Valuation',
      selected: selectedGroup === 'valuation',
      status: valuation.status,
      source: valuation.source,
      served_from: valuation.served_from,
      timestamp: valuation.quote_timestamp,
      metrics: valuationMetrics,
    });
  }

  if (Object.keys(valuationContext.context || {}).length > 0) {
    groups.push({
      id: 'valuation_context',
      label: 'Valuation Context',
      selected: selectedGroup === 'valuation_context',
      status: valuationContext.status,
      source: valuationContext.source,
      served_from: valuation.served_from,
      timestamp: valuationContext.quote_timestamp,
      metrics: [],
    });
  }

  if (Object.keys(peerBenchmark.peer_context || {}).length > 0 || peerMetrics.length > 0) {
    groups.push({
      id: 'peer_benchmark',
      label: 'Peer Benchmark',
      selected: selectedGroup === 'peer_benchmark',
      status: peerBenchmark.status,
      source: peerBenchmark.source,
      served_from: peerBenchmark.served_from,
      timestamp: peerBenchmark.quote_timestamp,
      metrics: peerMetrics,
    });
  }

  return groups;
}

function buildGeneratedWarnings() {
  return [];
}

function buildMetadata(input, valuationInput, peerInput) {
  const source = normalizeExportSource(valuationInput.source ?? input.source ?? peerInput.source);
  const servedFrom = normalizeExportServedFrom(valuationInput.served_from ?? input.served_from ?? peerInput.served_from);
  const status = normalizeExportStatus(valuationInput.status ?? input.status ?? peerInput.status, 'unknown');
  const quoteTimestamp = normalizeTimestamp(
    valuationInput.quote_timestamp ?? input.quote_timestamp ?? peerInput.quote_timestamp ?? input.result?.quote_timestamp,
  );
  const fundamentalsTimestamp = normalizeTimestamp(
    valuationInput.fundamentals_timestamp ?? input.fundamentals_timestamp ?? input.result?.fundamentals_timestamp,
  );
  return { source, servedFrom, status, quoteTimestamp, fundamentalsTimestamp };
}

export function buildExportSnapshot(input = {}, options = {}) {
  const result = asObject(input.result);
  const valuationInput = asObject(input.valuation ?? input.valuationMetrics);
  const contextInput = asObject(input.valuation_context ?? input.valuationContext);
  const peerInput = asObject(input.peer_benchmark ?? input.peerBenchmark);
  const metadata = buildMetadata(input, valuationInput, peerInput);
  const generatedAt = options.generatedAt
    ?? (options.now instanceof Date ? options.now.toISOString() : options.now)
    ?? new Date().toISOString();

  const valuationMetrics = buildMetricRows(valuationMetricsInput(valuationInput), {
    source: metadata.source,
    served_from: metadata.servedFrom,
    status: metadata.status,
    timestamp: metadata.quoteTimestamp,
    unit: EXPORT_NA,
  });

  const valuation = {
    source: metadata.source,
    served_from: metadata.servedFrom,
    status: metadata.status,
    quote_timestamp: metadata.quoteTimestamp,
    fundamentals_timestamp: metadata.fundamentalsTimestamp,
    metrics: valuationMetrics,
  };

  const valuationContext = {
    status: normalizeExportStatus(contextInput.status ?? metadata.status, metadata.status),
    source: normalizeExportSource(contextInput.source ?? metadata.source),
    quote_timestamp: normalizeTimestamp(contextInput.quote_timestamp ?? metadata.quoteTimestamp),
    context: sanitizeExportValue(contextInput.context ?? {}),
  };

  const peerBenchmark = {
    status: normalizeExportStatus(peerInput.status, peerInput.status === undefined ? 'unknown' : 'unknown'),
    source: normalizeExportSource(peerInput.source),
    served_from: normalizeExportServedFrom(peerInput.served_from),
    quote_timestamp: normalizeTimestamp(peerInput.quote_timestamp ?? metadata.quoteTimestamp),
    peer_context: sanitizeExportValue(peerInput.peer_context ?? {}),
    summary: sanitizeExportValue(peerInput.summary ?? {}),
    benchmarks: sanitizeExportValue(peerInput.benchmarks ?? {}),
    warnings: sanitizeExportValue(peerInput.warnings ?? []),
  };

  const peerMetrics = peerBenchmarkMetricRows(peerInput, {
    source: peerBenchmark.source,
    served_from: peerBenchmark.served_from,
    status: peerBenchmark.status,
    timestamp: peerBenchmark.quote_timestamp,
    unit: EXPORT_NA,
  });

  const selectedGroup = safeString(input.selected_group ?? input.selectedGroup);
  const inputWarnings = Array.isArray(input.warnings) ? input.warnings : [];
  const sanitizedWarnings = sanitizeExportValue(inputWarnings.concat(buildGeneratedWarnings()));
  const warnings = Array.isArray(sanitizedWarnings)
    ? sanitizedWarnings.filter(warning => warning !== EXPORT_NA)
    : [];

  // Keep this insertion order stable: downstream tests and export modules rely on it.
  const rawSnapshot = {
    ticker: result.ticker,
    company_name: result.company_name,
    currency: 'USD',
    selected_group: selectedGroup,
    selected_period: input.selected_period ?? input.selectedPeriod,
    selected_mode: input.selected_mode ?? input.selectedMode,
    generated_at: generatedAt,
    quote_timestamp: metadata.quoteTimestamp,
    fundamentals_timestamp: metadata.fundamentalsTimestamp,
    market_data_status: metadata.status,
    source: metadata.source,
    served_from: metadata.servedFrom,
    status: metadata.status,
    build: {
      contract: EXPORT_SNAPSHOT_VERSION,
      ...(asObject(sanitizeExportValue(input.build))),
    },
    groups: buildGroups({
      selectedGroup,
      valuation,
      valuationMetrics,
      valuationContext,
      peerBenchmark,
      peerMetrics,
    }),
    valuation,
    valuation_context: valuationContext,
    peer_benchmark: peerBenchmark,
    warnings,
  };

  return deepFreeze(sanitizeExportValue(rawSnapshot));
}
