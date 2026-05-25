/**
 * SA V2.6 T4 — Copy Summary Engine
 *
 * Generates a short Markdown/text summary from the T1 export snapshot
 * and copies it to the system clipboard. No network calls, no
 * recomputation, no forbidden wording.
 *
 * The snapshot is already sanitized by the T1 contract — this module
 * only reads and formats, never mutates.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function safeStr(value) {
  if (value === null || value === undefined) return 'N/A';
  return String(value);
}

function timestampStr(value) {
  return safeStr(value);
}

// ---------------------------------------------------------------------------
// Summary generation
// ---------------------------------------------------------------------------

/**
 * Generate a short Markdown/text summary from a T1 export snapshot.
 *
 * @param {object} snapshot  Frozen, sanitized snapshot from buildExportSnapshot()
 * @returns {string}         Short formatted summary suitable for clipboard paste
 */
export function generateCopySummary(snapshot) {
  const lines = [];

  // ── Header ────────────────────────────────────────────────────────────
  const header = `**${safeStr(snapshot.ticker)} — ${safeStr(snapshot.company_name)}**`;
  lines.push(header);

  // ── Metadata row ──────────────────────────────────────────────────────
  const meta = [
    `Currency: ${safeStr(snapshot.currency)}`,
    `Source: ${safeStr(snapshot.source)}`,
    `Status: ${safeStr(snapshot.status)}`,
    `Served: ${safeStr(snapshot.served_from)}`,
  ];
  lines.push(meta.join(' | '));

  // ── Timestamps ────────────────────────────────────────────────────────
  const times = [
    `Generated: ${timestampStr(snapshot.generated_at)}`,
    `Quote: ${timestampStr(snapshot.quote_timestamp)}`,
    `Fundamentals: ${timestampStr(snapshot.fundamentals_timestamp)}`,
  ];
  lines.push(times.join(' | '));
  lines.push('');

  // ── Selected group metrics ────────────────────────────────────────────
  const groups = Array.isArray(snapshot.groups) ? snapshot.groups : [];
  if (groups.length > 0) {
    const selected = groups.find(g => g.selected) || groups[0];
    const label = safeStr(selected.label);
    const metrics = Array.isArray(selected.metrics) ? selected.metrics : [];

    if (metrics.length === 0) {
      lines.push(`${label} — no metrics`);
    } else {
      lines.push(`${label} — ${metrics.length} metric${metrics.length !== 1 ? 's' : ''}`);
      for (const m of metrics) {
        lines.push(`  ${safeStr(m.label)}: ${safeStr(m.formatted_value)}`);
      }
    }
  }

  return lines.join('\n');
}

// ---------------------------------------------------------------------------
// Clipboard
// ---------------------------------------------------------------------------

/**
 * Copy text to the system clipboard.
 *
 * Tries the modern Clipboard API first; falls back to the
 * `document.execCommand('copy')` textarea trick when unavailable or
 * rejected.
 *
 * @param {string} text       Text to copy
 * @param {object} [options]  Injectable overrides for testing
 * @param {object} [options._navigator]  navigator-like object
 * @param {object} [options._document]   document-like object
 * @returns {Promise<{ok: boolean, text: string, error?: string}>}
 */
export async function copyToClipboard(text, options = {}) {
  const nav = options._navigator ?? (typeof navigator !== 'undefined' ? navigator : undefined);
  const doc = options._document ?? (typeof document !== 'undefined' ? document : undefined);

  // Clipboard API path
  if (nav?.clipboard?.writeText) {
    try {
      await nav.clipboard.writeText(text);
      return { ok: true, text };
    } catch {
      // Fall through to fallback
    }
  }

  // execCommand fallback
  return execCommandFallback(text, doc);
}

function execCommandFallback(text, doc) {
  if (!doc) {
    return { ok: false, text, error: 'no document object for fallback' };
  }

  const area = doc.createElement('textarea');
  area.value = text;
  area.style.position = 'fixed';
  area.style.opacity = '0';
  doc.body.appendChild(area);
  area.select();

  try {
    doc.execCommand('copy');
    return { ok: true, text };
  } catch (err) {
    return { ok: false, text, error: String(err) };
  } finally {
    doc.body.removeChild(area);
  }
}

/**
 * Generate summary from a snapshot and copy it to the clipboard in one call.
 *
 * @param {object} snapshot  T1 export snapshot
 * @param {object} [options] Passed through to copyToClipboard()
 * @returns {Promise<{ok: boolean, text: string, error?: string}>}
 */
export async function copySummaryToClipboard(snapshot, options = {}) {
  const text = generateCopySummary(snapshot);
  return copyToClipboard(text, options);
}
