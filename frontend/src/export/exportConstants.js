/**
 * SA V2.6 export snapshot constants.
 *
 * These enums are intentionally narrow because CSV, PNG and Copy Summary exports
 * must share one public-safe contract. Unknown upstream values are mapped to
 * `unknown` (or `na` for explicitly unavailable status) instead of leaking raw
 * provider/debug states into export payloads.
 */
export const EXPORT_ALLOWED_ENUMS = Object.freeze({
  source: Object.freeze(['yfinance', 'finnhub', 'curated_config', 'cache', 'unknown']),
  served_from: Object.freeze(['live', 'cache', 'stale_cache', 'unknown']),
  status: Object.freeze(['ok', 'partial', 'cached', 'na', 'stale', 'unknown']),
});

export const EXPORT_SNAPSHOT_VERSION = 'sa-v2.6-export-snapshot-v1';
export const EXPORT_NA = 'N/A';

/**
 * Required shape for every group metric row in the snapshot.
 * CSV can flatten this directly; PNG/Copy can render formatted_value without
 * guessing precision. Raw unavailable values stay null while the display value
 * is always `N/A`.
 */
export const EXPORT_METRIC_ROW_FIELDS = Object.freeze([
  'key',
  'label',
  'value',
  'formatted_value',
  'unit',
  'status',
  'source',
  'served_from',
  'timestamp',
  'notes',
]);

/**
 * Central forbidden-key policy. Matching keys are omitted entirely so even the
 * serialized JSON cannot leak forbidden concepts such as FX/EUR fields,
 * recommendations, scoring, forward/consensus data, secrets or local paths.
 */
export const FORBIDDEN_EXPORT_KEY_PATTERNS = Object.freeze([
  /(^|[_-])eur($|[_-])/i,
  /price[_-]?eur/i,
  /(^|[_-])fx($|[_-])/i,
  /exchange[_-]?rate/i,
  /recommendation/i,
  /rating/i,
  /decision/i,
  /conviction/i,
  /(^|[_-])scoring($|[_-])/i,
  /score[_-]?total/i,
  /global[_-]?score/i,
  /composite[_-]?score/i,
  /pe[_-]?forward/i,
  /forward/i,
  /consensus/i,
  /analyst/i,
  /ai[_-]?narrative/i,
  /narrative/i,
  /secret/i,
  /token/i,
  /api[_-]?key/i,
  /password/i,
  /authorization/i,
  /cookie/i,
  /debug/i,
  /stack/i,
  /trace/i,
  /local[_-]?path/i,
  /file[_-]?path/i,
  /source[_-]?path/i,
  /workspace/i,
  /home[_-]?dir/i,
]);

/**
 * Forbidden string values are normalized to `N/A` when encountered as values.
 * Forbidden keys are stricter: they are dropped entirely by the sanitizer.
 */
export const FORBIDDEN_EXPORT_VALUE_PATTERNS = Object.freeze([
  /\b(BUY|SELL|HOLD)\b/i,
  /\bEUR\b/i,
  /\bFX\b/i,
  /exchange\s*rate/i,
  /non[-\s]?USD/i,
  /recommendation/i,
  /consensus/i,
  /analyst/i,
  /ai[_-]?narrative/i,
  /api[_-]?key/i,
  /secret/i,
  /token/i,
  /\/home\/ced\b/i,
  /\/mnt\/[a-z]\//i,
  /[A-Z]:\\Users\\/i,
  /\\Users\\/i,
  /[A-Z]:\\\\Users\\\\/,
  /\\\\Users\\\\/,
]);
