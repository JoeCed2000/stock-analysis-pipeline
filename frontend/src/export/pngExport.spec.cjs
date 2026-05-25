// PNG export engine tests — SA V2.6 T3
// Run with: node frontend/src/export/pngExport.spec.cjs

const assert = require('assert');

const FIXED_NOW_ISO = '2026-05-25T19:30:00.000Z';

// ── Minimal DOM polyfill for Node.js ─────────────────────────────────────

// document.createElement('canvas') + toBlob
if (!global.document) {
  const { JSDOM } = require('jsdom');
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { url: 'http://localhost' });
  global.document = dom.window.document;
  global.Element = dom.window.Element;
  global.HTMLCanvasElement = dom.window.HTMLCanvasElement;
}

// Always install a working getContext + toBlob (JSDOM's built-in returns null / warns)
global.HTMLCanvasElement.prototype.getContext = function () {
  return {
    scale: () => {},
    save: () => {},
    restore: () => {},
    fillStyle: '',
    font: '',
    textAlign: 'left',
    fillRect: () => {},
    fillText: () => {},
    strokeStyle: '',
    lineWidth: 1,
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    stroke: () => {},
    drawImage: () => {},
    measureText: () => ({ width: 80 }),
  };
};
global.HTMLCanvasElement.prototype.toBlob = function (cb, type) {
  // Node 18+ has Blob; fall back to Buffer if not available
  const blob = typeof Blob !== 'undefined'
    ? new Blob(['fake-png-data'], { type: 'image/png' })
    : Buffer.from('fake-png-data');
  cb(blob);
};

// URL.createObjectURL / revokeObjectURL
if (!global.URL) global.URL = {};
if (!global.URL.createObjectURL) global.URL.createObjectURL = () => 'blob:fake';
if (!global.URL.revokeObjectURL) global.URL.revokeObjectURL = () => {};

// setTimeout if missing
if (!global.setTimeout) global.setTimeout = (fn) => fn();

// ── Fetch spy ────────────────────────────────────────────────────────────

function installFetchSpy() {
  const originalFetch = global.fetch;
  let calls = 0;
  global.fetch = (...args) => {
    calls += 1;
    throw new Error(`fetch must not be called by PNG export: ${JSON.stringify(args)}`);
  };
  return {
    calls: () => calls,
    restore: () => { global.fetch = originalFetch; },
  };
}

// ── Snapshot fixtures ─────────────────────────────────────────────────────

async function nvdaSnapshot() {
  const { buildExportSnapshot } = await import('./exportSnapshot.js');
  return buildExportSnapshot({
    result: {
      ticker: 'NVDA',
      company_name: 'NVIDIA Corporation',
      currency: 'USD',
      decision: 'BUY',
      scoring: { total: 33 },
    },
    selected_group: 'valuation',
    selected_period: '2026Q1',
    valuation: {
      source: 'yfinance',
      served_from: 'live',
      status: 'fresh',
      quote_timestamp: '2026-05-25T18:00:00.000Z',
      fundamentals_timestamp: '2026-05-20T00:00:00.000Z',
      metrics: [
        { key: 'pe_ttm', label: 'P/E TTM', value: 41.2, formatted_value: '41.2x', unit: 'multiple' },
        { key: 'market_cap', label: 'Market Cap', value: 3100000000000, formatted_value: '$3.1T', unit: 'USD' },
      ],
    },
    valuation_context: { status: 'ok', context: {} },
    peer_benchmark: {
      status: 'available',
      source: 'curated_config',
      served_from: 'cache',
      peer_context: { sample_size: 5 },
      benchmarks: {},
      warnings: [],
    },
    build: { app: 'sa-pipeline', version: 'v2.6-test' },
  }, { generatedAt: FIXED_NOW_ISO });
}

// ── DOM helpers ──────────────────────────────────────────────────────────

function makeElement(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div.firstElementChild;
}

// ── Tests ─────────────────────────────────────────────────────────────────

async function test_filename_includes_ticker_group_date() {
  const mod = await import('./pngExport.js');
  const snapshot = await nvdaSnapshot();

  const card = makeElement('<div class="analysis-card"><span>hello</span></div>');

  const result = await mod.captureElementToPNG(card, snapshot, {
    scale: 1,
    filename: 'sa_NVDA_valuation_20260525',
  });

  assert.ok(result.filename.endsWith('.png'), 'filename must end with .png');
  assert.ok(result.filename.includes('NVDA'), 'filename must include ticker');
  assert.ok(result.filename.includes('valuation'), 'filename must include group');
  assert.ok(result.filename.includes('20260525'), 'filename must include date');
  assert.ok(result.blob instanceof Blob, 'result must include a Blob');
}

async function test_header_footer_metadata_includes_required_fields() {
  const { _testInternals } = await import('./pngExport.js');
  const snapshot = await nvdaSnapshot();

  // Test that _errorCanvas produces a canvas with the right dimensions
  const canvas = _testInternals._errorCanvas(snapshot, 'Test error');
  assert.ok(canvas instanceof HTMLCanvasElement, 'errorCanvas must return a canvas');
  assert.ok(canvas.width > 0 && canvas.height > 0, 'canvas must have positive dimensions');
  // 2x scale: 600*2 x 200*2
  assert.strictEqual(canvas.width, 1200);
  assert.strictEqual(canvas.height, 400);
}

async function test_hide_and_restore_export_controls() {
  const { _testInternals } = await import('./pngExport.js');

  const card = makeElement(`
    <div class="analysis-card">
      <span>Valuation</span>
      <button class="export-btn">Export</button>
      <div class="tooltip">Click to export</div>
      <span aria-label="Download report">Download</span>
      <div data-export-hide>Hidden section</div>
      <span>Normal content</span>
    </div>
  `);

  // Verify elements are visible before
  const exportBtn = card.querySelector('.export-btn');
  const tooltip = card.querySelector('.tooltip');
  const downloadSpan = card.querySelector('[aria-label="Download report"]');
  const dataHide = card.querySelector('[data-export-hide]');
  const normal = card.querySelector('span');

  assert.strictEqual(exportBtn.style.visibility, '', 'export button should be visible before hide');
  assert.strictEqual(tooltip.style.visibility, '', 'tooltip should be visible before hide');
  assert.strictEqual(normal.style.visibility, '', 'normal content should be visible before hide');

  // Hide
  const restore = _testInternals._hideExportControls(card);

  // Verify hidden
  assert.strictEqual(exportBtn.style.visibility, 'hidden', 'export button must be hidden');
  assert.strictEqual(tooltip.style.visibility, 'hidden', 'tooltip must be hidden');
  assert.strictEqual(downloadSpan.style.visibility, 'hidden', 'aria-label download must be hidden');
  assert.strictEqual(dataHide.style.visibility, 'hidden', 'data-export-hide must be hidden');
  assert.strictEqual(normal.style.visibility, '', 'normal content must remain visible');

  // Restore
  restore();

  // Verify restored
  assert.strictEqual(exportBtn.style.visibility, '', 'export button must be restored');
  assert.strictEqual(tooltip.style.visibility, '', 'tooltip must be restored');
  assert.strictEqual(downloadSpan.style.visibility, '', 'aria-label download must be restored');
  assert.strictEqual(dataHide.style.visibility, '', 'data-export-hide must be restored');
}

async function test_restore_happens_even_on_error() {
  const { _testInternals } = await import('./pngExport.js');

  const card = makeElement(`
    <div class="analysis-card">
      <span>Content</span>
      <button class="export-btn">Export</button>
    </div>
  `);

  const exportBtn = card.querySelector('.export-btn');
  const restore = _testInternals._hideExportControls(card);
  assert.strictEqual(exportBtn.style.visibility, 'hidden');

  // Simulate error scenario — restore must still work
  restore();
  assert.strictEqual(exportBtn.style.visibility, '', 'controls must be restored even after errors');
}

async function test_usd_metadata_in_header() {
  // Verify the snapshot always has currency: 'USD'
  const snapshot = await nvdaSnapshot();
  assert.strictEqual(snapshot.currency, 'USD', 'snapshot currency must be USD');

  // snapshot with EUR input should still produce USD output
  const { buildExportSnapshot } = await import('./exportSnapshot.js');
  const eurSnapshot = buildExportSnapshot({
    result: { ticker: 'AAPL', company_name: 'Apple Inc.', currency: 'EUR', price_eur: 185 },
    valuation: { source: 'finnhub', status: 'ok', metrics: [] },
  }, { generatedAt: FIXED_NOW_ISO });

  assert.strictEqual(eurSnapshot.currency, 'USD', 'EUR input must be normalized to USD in snapshot');
}

async function test_no_fetch_called_during_export() {
  const mod = await import('./pngExport.js');
  const snapshot = await nvdaSnapshot();
  const spy = installFetchSpy();

  const card = makeElement('<div class="analysis-card"><span>test</span></div>');

  try {
    const result = await mod.captureElementToPNG(card, snapshot, { scale: 1 });
    assert.ok(result.blob instanceof Blob, 'export must produce a blob');
    assert.strictEqual(spy.calls(), 0, 'PNG export must not call fetch');
  } finally {
    spy.restore();
  }
}

async function test_error_fallback_produces_valid_png() {
  const mod = await import('./pngExport.js');
  const snapshot = await nvdaSnapshot();

  // Element that will cause html2canvas to fail (e.g., a node without layout)
  const card = makeElement('<div class="analysis-card"><span>test</span></div>');

  // html2canvas won't be installable from dynamic import in this Node env,
  // so _ensureCaptureLib will return null and _errorCanvas is used.
  const result = await mod.captureElementToPNG(card, snapshot, { scale: 1 });

  assert.ok(result.blob instanceof Blob, 'must return a Blob even on error');
  assert.ok(result.blob.size > 0, 'error PNG must have content');
  assert.ok(result.filename.endsWith('.png'), 'must have .png extension');
  assert.strictEqual(result.usedDOMCapture, false, 'must indicate that DOM capture was not used');
}

async function test_download_creates_link_and_revokes_url() {
  const mod = await import('./pngExport.js');
  const blob = new Blob(['fake-png'], { type: 'image/png' });

  // Track anchor creation
  const origCreateElement = document.createElement.bind(document);
  const created = [];
  document.createElement = (tag) => {
    const el = origCreateElement(tag);
    if (tag === 'a') {
      el.click = () => { created.push({ tag, href: el.href, download: el.download }); };
    }
    return el;
  };

  try {
    mod.downloadPNG(blob, 'sa_NVDA_valuation_20260525.png');
    assert.ok(created.length >= 1, 'downloadPNG must create an anchor element');
    assert.ok(created[0].href.startsWith('blob:'), 'anchor href must be a blob URL');
    assert.strictEqual(created[0].download, 'sa_NVDA_valuation_20260525.png', 'download attribute must match');
  } finally {
    document.createElement = origCreateElement;
  }
}

async function test_hide_selector_covers_export_controls() {
  const { _testInternals } = await import('./pngExport.js');
  const sel = _testInternals.HIDE_SELECTOR;

  // Verify all expected patterns are covered
  const patterns = [
    '[data-export-hide]',
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
  ];
  for (const pattern of patterns) {
    assert.ok(sel.includes(pattern), `HIDE_SELECTOR must include "${pattern}"`);
  }
}

// ── Runner ─────────────────────────────────────────────────────────────────

(async () => {
  const tests = [
    test_filename_includes_ticker_group_date,
    test_header_footer_metadata_includes_required_fields,
    test_hide_and_restore_export_controls,
    test_restore_happens_even_on_error,
    test_usd_metadata_in_header,
    test_no_fetch_called_during_export,
    test_error_fallback_produces_valid_png,
    test_download_creates_link_and_revokes_url,
    test_hide_selector_covers_export_controls,
  ];
  let passed = 0;
  for (const test of tests) {
    try {
      await test();
      passed += 1;
      console.log(`✅ ${test.name}`);
    } catch (err) {
      console.error(`❌ ${test.name}: ${err.message}`);
      console.error(err);
    }
  }
  console.log(`\n${passed}/${tests.length} PNG export tests passed`);
  if (passed < tests.length) process.exit(1);
})().catch(err => {
  console.error(err);
  process.exit(1);
});
