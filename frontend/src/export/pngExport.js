/**
 * SA V2.6 T3 — PNG Export Engine
 *
 * Lazy-loads html2canvas to capture the active group/card DOM element at 2×
 * device-pixel ratio. Before capture, export controls (menus, buttons,
 * tooltips, hover-only elements) are hidden; after capture they are restored.
 * A metadata header/footer is rendered directly on the canvas so the exported
 * image always carries ticker, group, USD, generated_at, source, status,
 * served_from, and quote timestamp — even if those values are not currently
 * visible on screen.
 *
 * ## Dependency justification (html2canvas)
 *
 * The acceptance criteria require capturing the *actual rendered DOM element*
 * so the exported image reflects the user's current screen state. Pure Canvas
 * rendering would redraw metrics from the snapshot and could diverge from the
 * live UI. html2canvas is the lightest widely-adopted DOM→Canvas library
 * (~14 KB gzipped, zero sub-dependencies). It is lazy-loaded via dynamic
 * import so it adds zero bytes to the initial bundle and lands in its own
 * code-split chunk. Without it the export falls back to a plain error PNG
 * rather than silently producing wrong output.
 */

import {
  EXPORT_NA,
  EXPORT_SNAPSHOT_VERSION,
} from './exportConstants.js';
import {
  normalizeExportNA,
} from './exportSnapshot.js';

// ── Capture library ────────────────────────────────────────────────────────

/** @type {Function|null} lazily-resolved html2canvas default export */
let _html2canvas = null;

/** @type {boolean} true once we have attempted (and possibly failed) the import */
let _libLoadAttempted = false;

/**
 * Lazily import html2canvas.  Returns the default export on success, null on
 * failure.  The first failure caches so we never retry inside the same
 * page load — every subsequent call returns null instantly.
 */
async function _ensureCaptureLib() {
  if (_libLoadAttempted) return _html2canvas;
  _libLoadAttempted = true;
  try {
    const mod = await import('html2canvas');
    _html2canvas = mod.default || mod;
    return _html2canvas;
  } catch (_err) {
    // html2canvas is optional — export still works but won't capture the DOM.
    return null;
  }
}

// ── Control hiding / restoring ─────────────────────────────────────────────

const HIDE_SELECTOR = [
  '[data-export-hide]',          // explicit opt-in marker
  '[aria-label*="export" i]',
  '[aria-label*="download" i]',
  '[title*="export" i]',
  '[title*="download" i]',
  '.export-menu',
  '.export-btn',
  '.download-btn',
  '.tooltip',
  '[role="tooltip"]',
  '[data-tooltip]',
  'button[data-hover-only]',
].join(',');

/**
 * Walk `root` (and the root itself) collecting every element matching
 * HIDE_SELECTOR.  Store the original `visibility` style so we can restore it.
 *
 * Returns a **restore function** that the caller MUST invoke after capture.
 */
function _hideExportControls(root) {
  const hidden = [];

  const walk = (el) => {
    if (!el || !el.matches) return;
    try {
      if (el.matches(HIDE_SELECTOR)) {
        hidden.push({ el, visibility: el.style.visibility });
        el.style.visibility = 'hidden';
      }
    } catch (_) { /* ignore non-Element nodes */ }
    if (el.children) {
      for (const child of el.children) walk(child);
    }
  };

  walk(root);

  return function _restore() {
    for (const { el, visibility } of hidden) {
      el.style.visibility = visibility || '';
    }
  };
}

// ── Canvas header / footer rendering ──────────────────────────────────────

const HEADER_HEIGHT = 52;
const FOOTER_HEIGHT = 36;
const PADDING_X = 16;

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} snapshot  – frozen export snapshot from buildExportSnapshot
 * @param {number} width
 * @param {number} totalHeight
 */
function _drawHeader(ctx, snapshot, width, totalHeight) {
  const y = 0;
  // background bar
  ctx.fillStyle = '#161b22';
  ctx.fillRect(0, y, width, HEADER_HEIGHT);

  // left side: ticker / company / group
  ctx.fillStyle = '#58a6ff';
  ctx.font = 'bold 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
  const ticker = normalizeExportNA(snapshot.ticker);
  const company = normalizeExportNA(snapshot.company_name);
  const groupLabel = snapshot.groups?.find(g => g.selected)?.label
    ?? normalizeExportNA(snapshot.selected_group)
    ?? '—';

  ctx.fillText(`${ticker}  ·  ${company}`, PADDING_X, 18);

  ctx.fillStyle = '#8b949e';
  ctx.font = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
  ctx.fillText(`Group: ${groupLabel}`, PADDING_X, 38);

  // right side: USD + build version
  ctx.fillStyle = '#3fb950';
  ctx.font = 'bold 12px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
  ctx.textAlign = 'right';
  ctx.fillText('USD', width - PADDING_X, 18);

  ctx.fillStyle = '#484f58';
  ctx.font = '10px monospace';
  const build = snapshot.build?.contract ?? EXPORT_SNAPSHOT_VERSION;
  ctx.fillText(`build: ${build}`, width - PADDING_X, 38);

  ctx.textAlign = 'left';

  // separator line
  ctx.strokeStyle = '#30363d';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, HEADER_HEIGHT);
  ctx.lineTo(width, HEADER_HEIGHT);
  ctx.stroke();
}

function _drawFooter(ctx, snapshot, width, totalHeight) {
  const y = totalHeight - FOOTER_HEIGHT;

  // separator line
  ctx.strokeStyle = '#30363d';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, y);
  ctx.lineTo(width, y);
  ctx.stroke();

  // background bar
  ctx.fillStyle = '#161b22';
  ctx.fillRect(0, y, width, FOOTER_HEIGHT);

  ctx.fillStyle = '#8b949e';
  ctx.font = '10px monospace';

  const generated = normalizeExportNA(snapshot.generated_at);
  const source = normalizeExportNA(snapshot.source);
  const status = normalizeExportNA(snapshot.status);
  const servedFrom = normalizeExportNA(snapshot.served_from);
  const quoteTs = normalizeExportNA(snapshot.quote_timestamp);

  const left = `generated: ${generated}`;
  ctx.fillText(left, PADDING_X, y + 14);

  const right = `source: ${source}  ·  status: ${status}  ·  served: ${servedFrom}`;
  ctx.textAlign = 'right';
  ctx.fillText(right, width - PADDING_X, y + 14);

  ctx.fillText(`quote: ${quoteTs}`, width - PADDING_X, y + 30);

  ctx.textAlign = 'left';
}

// ── Fallback error canvas ──────────────────────────────────────────────────

function _errorCanvas(snapshot, message) {
  const scale = 2;
  const w = 600;
  const h = 200;
  const canvas = document.createElement('canvas');
  canvas.width = w * scale;
  canvas.height = h * scale;
  const ctx = canvas.getContext('2d');
  ctx.scale(scale, scale);

  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, w, h);

  _drawHeader(ctx, snapshot, w, h);
  _drawFooter(ctx, snapshot, w, h);

  ctx.fillStyle = '#f85149';
  ctx.font = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(message ?? 'PNG export failed', w / 2, h / 2 - 10);

  ctx.fillStyle = '#8b949e';
  ctx.font = '11px monospace';
  ctx.fillText('The snapshot data is still available via CSV or Copy Summary.', w / 2, h / 2 + 14);

  ctx.textAlign = 'left';
  return canvas;
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Capture a DOM element to a PNG blob at 2× device-pixel ratio.
 *
 * @param {Element}  element   – the DOM element to capture (e.g. the active group container)
 * @param {object}   snapshot  – frozen export snapshot from `buildExportSnapshot`
 * @param {object}   [options]
 * @param {number}   [options.scale]     – override scale (default: 2)
 * @param {string}   [options.filename]  – suggested filename stem (without extension)
 * @returns {Promise<{blob: Blob, filename: string}>}
 */
export async function captureElementToPNG(element, snapshot, options = {}) {
  const scale = options.scale ?? 2;
  const now = new Date();

  // ── 1. Hide export controls inside the element ──
  const restore = _hideExportControls(element);

  /** @type {HTMLCanvasElement} */
  let canvas;
  let usedDOMCapture = false;

  try {
    // ── 2. Try DOM capture via html2canvas ──
    const html2canvas = await _ensureCaptureLib();
    if (html2canvas) {
      canvas = await html2canvas(element, {
        scale,
        useCORS: true,
        allowTaint: false,
        backgroundColor: '#0d1117',
        logging: false,
      });
      usedDOMCapture = true;
    } else {
      // No capture library available — produce an error canvas
      canvas = _errorCanvas(snapshot, 'Capture library not available');
    }
  } catch (captureErr) {
    // Capture failed — produce an error canvas instead of throwing
    console.warn('PNG export capture failed, using error fallback', captureErr);
    canvas = _errorCanvas(snapshot, 'Capture failed');
  } finally {
    // ── 3. ALWAYS restore controls ──
    restore();
  }

  // ── 4. Overlay header / footer on the captured canvas ──
  // We render into a new composite canvas to avoid mutating the capture result.
  const compositeW = canvas.width;
  const headerPixels = HEADER_HEIGHT * scale;
  const footerPixels = FOOTER_HEIGHT * scale;
  const compositeH = canvas.height + headerPixels + footerPixels;

  const composite = document.createElement('canvas');
  composite.width = compositeW;
  composite.height = compositeH;
  const ctx = composite.getContext('2d');

  // Dark background for the whole composite
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, compositeW, compositeH);

  // Draw header at top
  ctx.save();
  ctx.scale(scale, scale);
  _drawHeader(ctx, snapshot, compositeW / scale, compositeH / scale);
  ctx.restore();

  // Draw captured content in the middle
  ctx.drawImage(canvas, 0, headerPixels);

  // Draw footer at bottom
  ctx.save();
  ctx.scale(scale, scale);
  _drawFooter(ctx, snapshot, compositeW / scale, compositeH / scale);
  ctx.restore();

  // ── 5. Convert to PNG blob ──
  const blob = await new Promise((resolve, reject) => {
    composite.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('Canvas toBlob returned null'))),
      'image/png',
    );
  });

  // ── 6. Build filename ──
  const ticker = normalizeExportNA(snapshot.ticker);
  const groupId = normalizeExportNA(snapshot.selected_group);
  const yyyy = now.getUTCFullYear();
  const mm = String(now.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(now.getUTCDate()).padStart(2, '0');
  const stem = options.filename
    ?? `sa_${ticker}_${groupId}_${yyyy}${mm}${dd}`;

  return { blob, filename: `${stem}.png`, usedDOMCapture };
}

/**
 * Trigger a browser download of the PNG blob.
 *
 * @param {Blob}   blob      – PNG image blob from `captureElementToPNG`
 * @param {string} filename  – suggested filename (e.g. "sa_NVDA_valuation_20260525.png")
 */
export function downloadPNG(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke after a short delay so the browser has time to start the download
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

/**
 * Test helper — exposed so the spec can verify control hiding without
 * actually running html2canvas.
 */
export const _testInternals = {
  HIDE_SELECTOR,
  _hideExportControls,
  _errorCanvas,
};
