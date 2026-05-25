// CSV Export Engine tests — SA V2.6 T2
// Run with: node frontend/src/export/csvExport.spec.cjs

const assert = require('assert');

const FIXED_NOW = '2026-05-25T19:30:00.000Z';

function installFetchSpy() {
  const originalFetch = global.fetch;
  let calls = 0;
  global.fetch = (...args) => {
    calls += 1;
    throw new Error(`fetch must not be called by CSV export: ${JSON.stringify(args)}`);
  };
  return {
    calls: () => calls,
    restore: () => { global.fetch = originalFetch; },
  };
}

// ── Fixtures ──────────────────────────────────────────────────────────────

async function makeSnapshot(overrides = {}) {
  const { buildExportSnapshot } = await import('./exportSnapshot.js');
  return buildExportSnapshot({
    result: {
      ticker: 'NVDA',
      company_name: 'NVIDIA Corporation',
      currency: 'USD',
    },
    selected_group: 'valuation',
    selected_period: '2026Q1',
    selected_mode: 'current',
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
    peer_benchmark: {
      status: 'available',
      source: 'curated_config',
      served_from: 'cache',
      peer_context: { available: true },
      benchmarks: {
        pe_ttm: { status: 'available', value: 41.2, peer_median: 35.1, label: 'above peer median' },
      },
    },
    build: { app: 'sa-pipeline', version: 'v2.6-test' },
    ...overrides,
  }, { generatedAt: FIXED_NOW });
}

function parseCsv(csvText) {
  const lines = csvText.trim().split('\n');
  if (lines.length === 0) return { header: [], rows: [] };

  const header = lines[0].split(',').map(h => h.trim());
  const rows = lines.slice(1).map(line => {
    const values = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"') {
          if (i + 1 < line.length && line[i + 1] === '"') {
            current += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          current += ch;
        }
      } else {
        if (ch === '"') {
          inQuotes = true;
        } else if (ch === ',') {
          values.push(current);
          current = '';
        } else {
          current += ch;
        }
      }
    }
    values.push(current);

    const row = {};
    header.forEach((h, idx) => { row[h] = values[idx] ?? ''; });
    return row;
  });
  return { header, rows };
}

// ── Tests ─────────────────────────────────────────────────────────────────

async function test_generateCsv_current_group_yields_correct_columns() {
  const { generateCsv } = await import('./csvExport.js');
  const snapshot = await makeSnapshot();

  const csv = generateCsv(snapshot, 'current-group');
  const { header, rows } = parseCsv(csv);

  const expectedHeader = [
    'ticker', 'company', 'currency', 'group', 'metric', 'value',
    'formatted_value', 'unit', 'mode', 'period', 'source', 'status',
    'served_from', 'timestamp', 'notes',
  ];
  assert.deepStrictEqual(header, expectedHeader, 'CSV header must match the 15-column contract');

  // Current group = valuation (selected_group=valuation)
  assert.strictEqual(rows.length, 2, 'NVDA valuation fixture has 2 metrics');
  assert.strictEqual(rows[0].ticker, 'NVDA');
  assert.strictEqual(rows[0].company, 'NVIDIA Corporation');
  assert.strictEqual(rows[0].currency, 'USD');
  assert.strictEqual(rows[0].group, 'Valuation');
  assert.strictEqual(rows[0].metric, 'pe_ttm');
  assert.strictEqual(rows[0].value, '41.2');
  assert.strictEqual(rows[0].formatted_value, '41.2x');
  assert.strictEqual(rows[0].unit, 'multiple');
  assert.strictEqual(rows[0].mode, 'current');
  assert.strictEqual(rows[0].period, '2026Q1');
  assert.strictEqual(rows[0].source, 'yfinance');
  assert.strictEqual(rows[0].status, 'ok');
  assert.strictEqual(rows[0].served_from, 'live');
  // Metrics inherit group timestamp (valuation.quote_timestamp), not generated_at
  assert.strictEqual(rows[0].timestamp, '2026-05-25T18:00:00.000Z');
  assert.strictEqual(rows[0].notes, 'N/A');

  assert.strictEqual(rows[1].metric, 'market_cap');
  assert.strictEqual(rows[1].value, '3100000000000');
  assert.strictEqual(rows[1].formatted_value, '$3.1T');
}

async function test_generateCsv_full_analysis_yields_all_groups() {
  const { generateCsv } = await import('./csvExport.js');
  const snapshot = await makeSnapshot({
    valuation_context: {
      status: 'ok',
      context: { confidence: 'high' },
    },
  });

  const csv = generateCsv(snapshot, 'full-analysis');
  const { rows } = parseCsv(csv);

  // valuation (2 metrics) + peer_benchmark (1 metric from benchmarks map)
  assert(rows.length >= 3, `expected at least 3 rows across groups, got ${rows.length}`);

  const groups = [...new Set(rows.map(r => r.group))];
  assert(groups.includes('Valuation'), 'must include Valuation group');
  assert(groups.includes('Peer Benchmark'), 'must include Peer Benchmark group');

  // Check currency is always USD
  for (const row of rows) {
    assert.strictEqual(row.currency, 'USD', `currency must be USD, got ${row.currency}`);
  }

  // No forbidden data
  const csvText = JSON.stringify(rows);
  assert(!csvText.includes('EUR'), 'must not contain EUR');
  assert(!csvText.includes('BUY'), 'must not contain BUY');
  assert(!csvText.includes('FX'), 'must not contain FX');
}

async function test_generateCsv_empty_snapshot_returns_header_only() {
  const { generateCsv } = await import('./csvExport.js');
  const { buildExportSnapshot } = await import('./exportSnapshot.js');

  const snapshot = buildExportSnapshot({
    result: { ticker: 'EMPTY', company_name: 'No Data Inc.', currency: 'USD' },
  }, { generatedAt: FIXED_NOW });

  const csv = generateCsv(snapshot, 'current-group');
  const lines = csv.trim().split('\n');
  assert.strictEqual(lines.length, 1, 'empty snapshot should yield header only');
  assert(lines[0].startsWith('ticker,company,currency'), `unexpected header: ${lines[0]}`);
}

async function test_csv_escaping_commas_quotes_newlines() {
  const { csvEscapeField } = await import('./csvExport.js');

  // Plain value — no wrapping
  assert.strictEqual(csvEscapeField('hello'), 'hello');
  assert.strictEqual(csvEscapeField(42), '42');
  assert.strictEqual(csvEscapeField(null), '');
  assert.strictEqual(csvEscapeField(undefined), '');

  // Comma — must be wrapped
  assert.strictEqual(csvEscapeField('hello, world'), '"hello, world"');

  // Double-quote — must be doubled and wrapped
  assert.strictEqual(csvEscapeField('say "hello"'), '"say ""hello"""');

  // Newline — must be wrapped
  assert.strictEqual(csvEscapeField('line1\nline2'), '"line1\nline2"');

  // Carriage return — must be wrapped
  assert.strictEqual(csvEscapeField('line1\rline2'), '"line1\rline2"');

  // Combination
  assert.strictEqual(csvEscapeField('a,"b"\nc'), '"a,""b""\nc"');
}

async function test_formula_neutralization() {
  const { neutralizeFormula, csvEscapeField, generateCsv } = await import('./csvExport.js');
  const { buildExportSnapshot } = await import('./exportSnapshot.js');

  // = prefix
  assert.strictEqual(neutralizeFormula('=SUM(A1)'), '\t=SUM(A1)');
  assert.strictEqual(neutralizeFormula('=1+1'), '\t=1+1');

  // + prefix
  assert.strictEqual(neutralizeFormula('+SUM(A1)'), '\t+SUM(A1)');

  // - prefix
  assert.strictEqual(neutralizeFormula('-SUM(A1)'), '\t-SUM(A1)');

  // @ prefix
  assert.strictEqual(neutralizeFormula('@SUM(A1)'), '\t@SUM(A1)');

  // Non-formula values pass through
  assert.strictEqual(neutralizeFormula('hello'), 'hello');
  assert.strictEqual(neutralizeFormula(41.2), 41.2);
  assert.strictEqual(neutralizeFormula(null), null);
  assert.strictEqual(neutralizeFormula(''), '');

  // No false positives: minus inside a word
  assert.strictEqual(neutralizeFormula('non-formula'), 'non-formula');
  assert.strictEqual(neutralizeFormula('a=b'), 'a=b'); // doesn't START with =

  // Integration: formula strings in snapshot are neutralized in CSV output
  const snapshot = buildExportSnapshot({
    result: { ticker: 'TEST', company_name: 'Test Corp', currency: 'USD' },
    selected_group: 'valuation',
    valuation: {
      source: 'yfinance',
      status: 'ok',
      metrics: [
        { key: 'formula_test', value: null, formatted_value: '=NA()', unit: '' },
      ],
    },
  }, { generatedAt: FIXED_NOW });

  const csv = generateCsv(snapshot, 'current-group');
  const lines = csv.split('\n');
  assert(lines.some(l => l.includes('\t=NA()')), 'formula in formatted_value must be neutralized');
}

async function test_csv_na_handling() {
  const { generateCsv } = await import('./csvExport.js');
  const { buildExportSnapshot } = await import('./exportSnapshot.js');

  const snapshot = buildExportSnapshot({
    result: { ticker: 'NA', company_name: '', currency: 'USD' },
    selected_group: 'valuation',
    valuation: {
      source: 'yfinance',
      served_from: 'live',
      status: 'ok',
      metrics: [
        { key: 'na_test', value: null, formatted_value: null, unit: '' },
      ],
    },
  }, { generatedAt: FIXED_NOW });

  const csv = generateCsv(snapshot, 'current-group');
  const { rows } = parseCsv(csv);

  assert.strictEqual(rows.length, 1);
  assert.strictEqual(rows[0].company, 'N/A', 'empty company_name must be N/A');
  assert.strictEqual(rows[0].value, '', 'null value becomes empty string in CSV (via csvEscapeField)');
  assert.strictEqual(rows[0].formatted_value, 'N/A', 'null formatted_value must be N/A');
  assert.strictEqual(rows[0].notes, 'N/A', 'missing notes must be N/A');
}

async function test_buildCsvFilename() {
  const { buildCsvFilename } = await import('./csvExport.js');
  const { buildExportSnapshot } = await import('./exportSnapshot.js');

  const snapshot = buildExportSnapshot({
    result: { ticker: 'NVDA', company_name: 'NVIDIA', currency: 'USD' },
    selected_group: 'valuation',
    valuation: {
      source: 'yfinance',
      status: 'ok',
      metrics: [{ key: 'pe_ttm', value: 41.2, formatted_value: '41.2x', unit: 'multiple' }],
    },
  }, { generatedAt: FIXED_NOW });

  // Current group mode
  const currentName = buildCsvFilename(snapshot, 'current-group');
  assert.strictEqual(currentName, 'NVDA_valuation_2026-05-25.csv');

  // Full analysis mode
  const fullName = buildCsvFilename(snapshot, 'full-analysis');
  assert.strictEqual(fullName, 'NVDA_full_analysis_2026-05-25.csv');
}

async function test_filename_sanitization() {
  const { sanitizeFilenameSegment } = await import('./csvExport.js');

  assert.strictEqual(sanitizeFilenameSegment('NVDA'), 'NVDA');
  assert.strictEqual(sanitizeFilenameSegment('NVIDIA Corporation'), 'NVIDIA_Corporation');
  assert.strictEqual(sanitizeFilenameSegment('  spaces  '), 'spaces');
  // Reminder: the sanitizer strips non-alphanumeric except _-
  assert.strictEqual(sanitizeFilenameSegment(''), 'export');
  assert.strictEqual(sanitizeFilenameSegment(null), 'export');
}

async function test_csv_export_never_calls_fetch() {
  const { generateCsv, downloadCsv } = await import('./csvExport.js');

  // Mock document for downloadCsv
  const createdAnchors = [];
  global.document = {
    createElement: (tag) => {
      const el = { href: '', download: '', style: {}, click: () => {} };
      if (tag === 'a') createdAnchors.push(el);
      return el;
    },
    body: { appendChild: () => {}, removeChild: () => {} },
  };
  global.Blob = class MockBlob {
    constructor(parts, opts) { this._parts = parts; this._type = opts?.type; }
  };
  global.URL = { createObjectURL: () => 'blob:test', revokeObjectURL: () => {} };

  const snapshot = await makeSnapshot();
  const spy = installFetchSpy();

  try {
    const csv = generateCsv(snapshot, 'current-group');
    assert(csv.length > 0, 'generateCsv must produce output');
    assert.strictEqual(spy.calls(), 0, 'generateCsv must not call fetch');

    // downloadCsv shouldn't call fetch either
    const filename = 'NVDA_valuation_2026-05-25.csv';
    downloadCsv(csv, filename);
    assert.strictEqual(spy.calls(), 0, 'downloadCsv must not call fetch');

    // Verify BOM is present in Blob
    assert.strictEqual(createdAnchors.length, 1, 'downloadCsv must create one anchor');
  } finally {
    spy.restore();
    delete global.document;
    delete global.Blob;
    delete global.URL;
  }
}

async function test_downloadCsv_includes_utf8_bom() {
  // Re-install mocks
  const blobParts = [];
  global.document = {
    createElement: () => ({ href: '', download: '', style: {}, click: () => {} }),
    body: { appendChild: () => {}, removeChild: () => {} },
  };
  global.Blob = class MockBlob {
    constructor(parts, opts) {
      blobParts.push(...parts);
      this._type = opts?.type;
      this.type = opts?.type;
    }
  };
  global.URL = { createObjectURL: () => 'blob:test', revokeObjectURL: () => {} };

  const { downloadCsv } = await import('./csvExport.js');
  downloadCsv('header\nvalue\n', 'test.csv');

  assert.strictEqual(blobParts.length, 1, 'Blob should have exactly one part (BOM + CSV)');
  const combined = blobParts[0];
  assert(combined.startsWith('\uFEFF'), 'CSV Blob must start with UTF-8 BOM');
  assert(combined.includes('header\n'), 'CSV content must follow BOM');

  delete global.document;
  delete global.Blob;
  delete global.URL;
}

async function test_generateCsv_respects_selected_group_only() {
  const { generateCsv } = await import('./csvExport.js');
  const snapshot = await makeSnapshot({
    selected_group: 'peer_benchmark', // explicitly select peer group
    peer_benchmark: {
      status: 'available',
      source: 'curated_config',
      served_from: 'cache',
      benchmarks: {
        market_cap: { status: 'available', value: 500e9, label: 'test' },
      },
    },
  });

  // Now valuation has selected=false, peer has selected=true
  // Check the snapshot's groups
  const peerGroup = snapshot.groups.find(g => g.selected);
  assert(peerGroup, 'one group must be selected');
  assert.strictEqual(peerGroup.id, 'peer_benchmark', 'peer_benchmark must be selected');

  const csv = generateCsv(snapshot, 'current-group');
  const { rows } = parseCsv(csv);

  assert(rows.length > 0, 'current-group CSV must have rows');
  for (const row of rows) {
    assert.strictEqual(row.group, 'Peer Benchmark', 'only the selected group should appear');
  }
}

async function test_csv_values_preserved_from_snapshot_no_api_calls() {
  const { generateCsv } = await import('./csvExport.js');
  const snapshot = await makeSnapshot();
  const spy = installFetchSpy();

  try {
    // Run generateCsv multiple times — should always use snapshot, never fetch
    for (let i = 0; i < 3; i++) {
      const csv = generateCsv(snapshot, 'full-analysis');
      const { rows } = parseCsv(csv);
      assert(rows.length > 0, `run ${i}: must produce rows`);
      assert.strictEqual(spy.calls(), 0, `run ${i}: must not call fetch`);
    }
  } finally {
    spy.restore();
  }
}

async function test_no_forbidden_data_in_csv_output() {
  const { generateCsv } = await import('./csvExport.js');
  const { buildExportSnapshot } = await import('./exportSnapshot.js');

  // Build a snapshot with forbidden fields that T1 already strips
  const snapshot = buildExportSnapshot({
    result: {
      ticker: 'BAD',
      company_name: 'BadCorp',
      currency: 'EUR',
      recommendation: 'BUY',
      scoring: { total: 99 },
      secret: 'leaked',
      local_path: '/home/ced/token.txt',
    },
    valuation: {
      source: 'yfinance',
      status: 'ok',
      metrics: [
        { key: 'pe_forward', value: 23.4, formatted_value: '23.4x', unit: 'multiple' },
      ],
    },
    peer_benchmark: {
      source: 'curated_config',
      status: 'available',
      benchmarks: {
        pe_ttm: { value: 29.1, peer_median: 28.8, label: 'above median' },
      },
      consensus: 'outperform',
    },
  }, { generatedAt: FIXED_NOW });

  const csv = generateCsv(snapshot, 'full-analysis');
  const csvText = csv;

  // T1 strips forbidden fields, so CSV must not contain them
  const forbidden = ['EUR', 'BUY', 'SELL', 'HOLD', 'recommendation',
    'consensus', 'analyst', 'scoring', 'pe_forward', 'forward',
    'secret', 'token', 'api_key', '/home/ced', 'C:\\Users'];
  for (const marker of forbidden) {
    assert(!csvText.includes(marker), `CSV output leaked forbidden marker: "${marker}"`);
  }

  // USD must be present
  assert(csvText.includes('USD'), 'currency column must contain USD');
}

// ── Test runner ───────────────────────────────────────────────────────────

(async () => {
  const tests = [
    test_generateCsv_current_group_yields_correct_columns,
    test_generateCsv_full_analysis_yields_all_groups,
    test_generateCsv_empty_snapshot_returns_header_only,
    test_csv_escaping_commas_quotes_newlines,
    test_formula_neutralization,
    test_csv_na_handling,
    test_buildCsvFilename,
    test_filename_sanitization,
    test_csv_export_never_calls_fetch,
    test_downloadCsv_includes_utf8_bom,
    test_generateCsv_respects_selected_group_only,
    test_csv_values_preserved_from_snapshot_no_api_calls,
    test_no_forbidden_data_in_csv_output,
  ];

  let passed = 0;
  let failed = 0;

  for (const test of tests) {
    try {
      await test();
      console.log(`✅ ${test.name}`);
      passed++;
    } catch (err) {
      console.error(`❌ ${test.name}`);
      console.error(`   ${err.message}`);
      failed++;
    }
  }

  console.log(`\n${passed}/${tests.length} CSV export tests passed`);
  if (failed > 0) {
    console.error(`${failed} test(s) failed`);
    process.exit(1);
  }
})().catch(err => {
  console.error(err);
  process.exit(1);
});
