/**
 * SA V2.6 T2 — CSV Export Engine
 *
 * Pure functions: take a frozen export snapshot (from buildExportSnapshot) and
 * produce a CSV string plus a browser download trigger. No fetch/XHR, no UI
 * wiring — that belongs to T5/T6.
 */

import { EXPORT_NA } from './exportConstants.js';

// ── Formula neutralization ────────────────────────────────────────────────

const FORMULA_TRIGGER_RE = /^[=+\-@]/;

/**
 * Prefix formula-triggering characters with a tab to prevent Excel/sheets
 * from interpreting the cell as a formula. Safe fields (numbers, null, non-
 * trigger strings) pass through unchanged.
 */
export function neutralizeFormula(value) {
  if (value == null) return value;
  // Only string values can trigger formula injection — numbers, booleans,
  // and other non-string primitives are safe as-is.
  if (typeof value !== 'string') return value;
  return FORMULA_TRIGGER_RE.test(value) ? `\t${value}` : value;
}

// ── CSV escaping ──────────────────────────────────────────────────────────

/**
 * Escape a single CSV field per RFC 4180:
 * - Wrap in double-quotes if the field contains a comma, double-quote,
 *   newline, or carriage return.
 * - Double any embedded double-quotes.
 */
export function csvEscapeField(value) {
  if (value == null) return '';
  const str = String(value);
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// ── Filename helpers ──────────────────────────────────────────────────────

/**
 * Sanitize a filename segment: strip non-alphanumeric chars except underscore
 * and hyphen, replace whitespace with underscore, collapse runs.
 */
export function sanitizeFilenameSegment(raw) {
  if (!raw || String(raw).trim() === '') return 'export';
  return String(raw)
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^a-zA-Z0-9_-]/g, '')
    .replace(/_+/g, '_')
    .replace(/-+/g, '-')
    .replace(/^[_-]+|[_-]+$/g, '')
    || 'export';
}

/**
 * Build a CSV filename from snapshot metadata.
 *
 *   current-group  →  {ticker}_{group_id}_YYYY-MM-DD.csv
 *   full-analysis  →  {ticker}_full_analysis_YYYY-MM-DD.csv
 */
export function buildCsvFilename(snapshot, mode) {
  const ticker = sanitizeFilenameSegment(snapshot.ticker);
  const date = extractDatePart(snapshot.generated_at ?? new Date().toISOString());

  if (mode === 'current-group') {
    const selectedGroup = (snapshot.groups ?? []).find(g => g.selected);
    const groupId = sanitizeFilenameSegment(selectedGroup?.id ?? 'data');
    return `${ticker}_${groupId}_${date}.csv`;
  }

  // full-analysis
  return `${ticker}_full_analysis_${date}.csv`;
}

function extractDatePart(isoString) {
  try {
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) throw new Error('invalid date');
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  } catch {
    const fallback = new Date();
    return `${fallback.getFullYear()}-${String(fallback.getMonth() + 1).padStart(2, '0')}-${String(fallback.getDate()).padStart(2, '0')}`;
  }
}

// ── CSV header ────────────────────────────────────────────────────────────

const CSV_HEADER = [
  'ticker',
  'company',
  'currency',
  'group',
  'metric',
  'value',
  'formatted_value',
  'unit',
  'mode',
  'period',
  'source',
  'status',
  'served_from',
  'timestamp',
  'notes',
];

// ── Row builders ──────────────────────────────────────────────────────────

/**
 * Build a metadata baseline that applies to every CSV row from this snapshot.
 */
function rowBaseline(snapshot) {
  return {
    ticker: snapshot.ticker ?? EXPORT_NA,
    company: snapshot.company_name ?? EXPORT_NA,
    currency: snapshot.currency ?? 'USD',
    mode: snapshot.selected_mode ?? snapshot.selectedMode ?? EXPORT_NA,
    period: snapshot.selected_period ?? snapshot.selectedPeriod ?? EXPORT_NA,
  };
}

/**
 * Flatten one group → array of CSV row objects (one per metric).
 */
function rowsFromGroup(group, baseline) {
  const metrics = group.metrics ?? [];
  if (metrics.length === 0) return [];

  return metrics.map(metric => ({
    ...baseline,
    group: group.label ?? group.id ?? EXPORT_NA,
    metric: metric.key ?? EXPORT_NA,
    value: metric.value,
    formatted_value: metric.formatted_value ?? EXPORT_NA,
    unit: metric.unit ?? EXPORT_NA,
    source: metric.source ?? group.source ?? EXPORT_NA,
    status: metric.status ?? group.status ?? EXPORT_NA,
    served_from: metric.served_from ?? group.served_from ?? EXPORT_NA,
    timestamp: metric.timestamp ?? group.timestamp ?? EXPORT_NA,
    notes: metric.notes ?? EXPORT_NA,
  }));
}

/**
 * Serialize a row object into a CSV line.
 */
function rowToCsvLine(row) {
  return CSV_HEADER
    .map(col => neutralizeFormula(row[col]))
    .map(csvEscapeField)
    .join(',');
}

// ── Public API ────────────────────────────────────────────────────────────

/**
 * Generate a CSV string from an export snapshot.
 *
 * @param {object} snapshot  Frozen snapshot from buildExportSnapshot()
 * @param {'current-group'|'full-analysis'} mode
 * @returns {string}  CSV content (UTF-8, no BOM — caller prepends if desired)
 */
export function generateCsv(snapshot, mode = 'current-group') {
  const groups = snapshot.groups ?? [];
  const baseline = rowBaseline(snapshot);

  let targetGroups;
  if (mode === 'current-group') {
    const selected = groups.find(g => g.selected);
    targetGroups = selected ? [selected] : [];
  } else {
    targetGroups = groups;
  }

  const lines = [CSV_HEADER.join(',')];

  for (const group of targetGroups) {
    const rows = rowsFromGroup(group, baseline);
    for (const row of rows) {
      lines.push(rowToCsvLine(row));
    }
  }

  // Ensure at least header-only output
  if (lines.length === 1) {
    // Append an empty line at minimum so the file isn't just a header.
    // But the spec doesn't require mock rows — just a valid CSV.
  }

  return `${lines.join('\n')}\n`;
}

/**
 * Trigger a browser download of a CSV string. Uses Blob + Object URL; caller
 * is responsible for revoking the URL after a short timeout (the download
 * anchor click is synchronous in modern browsers).
 *
 * @param {string} csvContent  CSV text
 * @param {string} filename    e.g. "NVDA_valuation_2026-05-25.csv"
 */
export function downloadCsv(csvContent, filename) {
  const bom = '\uFEFF';
  const blob = new Blob([bom + csvContent], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  // Free the object URL after the download initiates.
  setTimeout(() => {
    try { URL.revokeObjectURL(url); } catch { /* best-effort cleanup */ }
  }, 150);
}
