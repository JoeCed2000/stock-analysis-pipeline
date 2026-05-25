// Copy Summary Engine tests — SA V2.6 T4
// Run with: node frontend/src/export/copySummary.spec.cjs

const assert = require('assert');

const FIXED_NOW = '2026-05-25T19:30:00.000Z';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function installFetchSpy() {
  const originalFetch = global.fetch;
  let calls = 0;
  global.fetch = (...args) => {
    calls += 1;
    throw new Error(`fetch must not be called by copy summary: ${JSON.stringify(args)}`);
  };
  return {
    calls: () => calls,
    restore: () => { global.fetch = originalFetch; },
  };
}

function makeFakeNavigator(options = {}) {
  const clipboard = {
    writeText: null,
    ...options,
  };
  return { clipboard: clipboard.writeText ? clipboard : undefined };
}

function makeFakeDocument(execCommandReturns = true) {
  const children = [];
  return {
    body: {
      children,
      appendChild(el) { children.push(el); },
      removeChild() { /* noop */ },
    },
    createElement(tag) {
      return { tagName: tag, value: '', style: {}, select() {} };
    },
    execCommand(cmd) {
      return execCommandReturns;
    },
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function nvdaFixture() {
  return {
    ticker: 'NVDA',
    company_name: 'NVIDIA Corporation',
    currency: 'USD',
    source: 'yfinance',
    status: 'ok',
    served_from: 'live',
    generated_at: FIXED_NOW,
    quote_timestamp: '2026-05-25T18:00:00.000Z',
    fundamentals_timestamp: '2026-05-20T00:00:00.000Z',
    market_data_status: 'ok',
    selected_group: 'valuation',
    selected_period: '2026Q1',
    selected_mode: 'current',
    build: { contract: 'sa-v2.6-export-snapshot-v1' },
    groups: [
      {
        id: 'valuation',
        label: 'Valuation',
        selected: true,
        status: 'ok',
        source: 'yfinance',
        served_from: 'live',
        timestamp: '2026-05-25T18:00:00.000Z',
        metrics: [
          { key: 'pe_ttm', label: 'P/E TTM', value: 41.2, formatted_value: '41.2x', unit: 'multiple', status: 'ok', source: 'yfinance', served_from: 'live', timestamp: '2026-05-25T18:00:00.000Z', notes: 'N/A' },
          { key: 'market_cap', label: 'Market Cap', value: 3100000000000, formatted_value: '$3.1T', unit: 'USD', status: 'ok', source: 'yfinance', served_from: 'live', timestamp: '2026-05-25T18:00:00.000Z', notes: 'N/A' },
        ],
      },
    ],
    valuation: {},
    valuation_context: { context: {} },
    peer_benchmark: { peer_context: {} },
    warnings: [],
  };
}

function tslaNAFixture() {
  return {
    ticker: 'TSLA',
    company_name: 'N/A',
    currency: 'USD',
    source: 'unknown',
    status: 'na',
    served_from: 'unknown',
    generated_at: FIXED_NOW,
    quote_timestamp: 'N/A',
    fundamentals_timestamp: 'N/A',
    market_data_status: 'na',
    selected_group: 'N/A',
    build: { contract: 'sa-v2.6-export-snapshot-v1' },
    groups: [
      {
        id: 'valuation',
        label: 'Valuation',
        selected: false,
        status: 'na',
        source: 'unknown',
        served_from: 'unknown',
        timestamp: 'N/A',
        metrics: [
          { key: 'ps_ttm', label: 'N/A', value: null, formatted_value: 'N/A', unit: 'N/A', status: 'na', source: 'unknown', served_from: 'unknown', timestamp: 'N/A', notes: 'N/A' },
        ],
      },
    ],
    valuation: {},
    valuation_context: { context: {} },
    peer_benchmark: { peer_context: {} },
    warnings: [],
  };
}

function emptyGroupsFixture() {
  return {
    ticker: 'EMPTY',
    company_name: 'Empty Inc.',
    currency: 'USD',
    source: 'cache',
    status: 'cached',
    served_from: 'cache',
    generated_at: FIXED_NOW,
    quote_timestamp: 'N/A',
    fundamentals_timestamp: 'N/A',
    market_data_status: 'cached',
    selected_group: 'N/A',
    build: { contract: 'sa-v2.6-export-snapshot-v1' },
    groups: [],
    valuation: {},
    valuation_context: { context: {} },
    peer_benchmark: { peer_context: {} },
    warnings: [],
  };
}

function multiGroupFixture() {
  const base = nvdaFixture();
  return {
    ...base,
    groups: [
      {
        id: 'valuation',
        label: 'Valuation',
        selected: false,
        status: 'ok',
        source: 'yfinance',
        served_from: 'live',
        timestamp: '2026-05-25T18:00:00.000Z',
        metrics: [
          { key: 'pe_ttm', label: 'P/E TTM', value: 41.2, formatted_value: '41.2x', unit: 'multiple', status: 'ok', source: 'yfinance', served_from: 'live', timestamp: '2026-05-25T18:00:00.000Z', notes: 'N/A' },
        ],
      },
      {
        id: 'peer_benchmark',
        label: 'Peer Benchmark',
        selected: true,
        status: 'ok',
        source: 'curated_config',
        served_from: 'cache',
        timestamp: '2026-05-23T00:00:00.000Z',
        metrics: [
          { key: 'pe_ttm_vs_peer', label: 'P/E TTM vs Peer Median', value: -6.1, formatted_value: '6.1 above', unit: 'N/A', status: 'ok', source: 'curated_config', served_from: 'cache', timestamp: '2026-05-23T00:00:00.000Z', notes: 'N/A' },
        ],
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Forbidden wording assertion
// ---------------------------------------------------------------------------

const FORBIDDEN_SUMMARY_TOKENS = [
  'BUY', 'buy',
  'SELL', 'sell',
  'HOLD',
  'undervalued', 'Undervalued', 'UNDERVALUED',
  'overvalued', 'Overvalued', 'OVERVALUED',
  'recommendation', 'Recommendation',
  'scoring', 'Scoring',
  'global_score', 'global score',
  'forward', 'Forward', // but NOT "Served" which has "forward" nowhere
  'consensus', 'Consensus',
  'analyst', 'Analyst',
  'narrative', 'Narrative',
];

function assertNoForbiddenTokens(text, label) {
  for (const token of FORBIDDEN_SUMMARY_TOKENS) {
    assert(!text.includes(token), `${label}: leaked forbidden token "${token}"`);
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function test_nvda_generates_correct_summary() {
  const { generateCopySummary } = await import('./copySummary.js');
  const output = generateCopySummary(nvdaFixture());

  // Header
  assert(output.includes('**NVDA — NVIDIA Corporation**'), 'header missing');

  // Metadata line
  assert(output.includes('Currency: USD'), 'currency missing');
  assert(output.includes('Source: yfinance'), 'source missing');
  assert(output.includes('Status: ok'), 'status missing');
  assert(output.includes('Served: live'), 'served_from missing');

  // Timestamps
  assert(output.includes(`Generated: ${FIXED_NOW}`), 'generated_at missing');
  assert(output.includes('Quote: 2026-05-25T18:00:00.000Z'), 'quote_timestamp missing');
  assert(output.includes('Fundamentals: 2026-05-20T00:00:00.000Z'), 'fundamentals_timestamp missing');

  // Group
  assert(output.includes('Valuation — 2 metrics'), 'group label + count missing');
  assert(output.includes('P/E TTM: 41.2x'), 'pe_ttm metric missing');
  assert(output.includes('Market Cap: $3.1T'), 'market_cap metric missing');

  assertNoForbiddenTokens(output, 'NVDA summary');
}

async function test_tsla_nas_are_clean() {
  const { generateCopySummary } = await import('./copySummary.js');
  const output = generateCopySummary(tslaNAFixture());

  // N/A values should appear as "N/A", not empty or broken
  assert(output.includes('N/A'), 'N/A should appear in output');
  assert(!output.includes('null'), 'null must not appear');
  assert(!output.includes('undefined'), 'undefined must not appear');
  assert(!output.includes('NaN'), 'NaN must not appear');

  // Header
  assert(output.includes('**TSLA — N/A**'), 'N/A company should display');

  // Source/status
  assert(output.includes('Source: unknown'));
  assert(output.includes('Status: na'));
  assert(output.includes('Served: unknown'));

  // Timestamps
  assert(output.includes('Quote: N/A'));
  assert(output.includes('Fundamentals: N/A'));

  // N/A metrics
  assert(output.includes('N/A: N/A'), 'N/A label: N/A formatted_value');

  assertNoForbiddenTokens(output, 'TSLA N/A summary');
}

async function test_usd_currency_present() {
  const { generateCopySummary } = await import('./copySummary.js');
  const output = generateCopySummary(nvdaFixture());

  // Must explicitly say "Currency: USD"
  assert(output.includes('Currency: USD'), 'Currency: USD must be present');

  // Must NOT contain EUR
  assert(!output.includes('EUR'), 'EUR must not appear');
  assert(!output.includes('FX'), 'FX must not appear');
}

async function test_empty_groups_handled_gracefully() {
  const { generateCopySummary } = await import('./copySummary.js');
  const output = generateCopySummary(emptyGroupsFixture());

  // Header and metadata still present
  assert(output.includes('**EMPTY — Empty Inc.**'));
  assert(output.includes('Currency: USD'));
  assert(output.includes('Source: cache'));

  // No metrics section when groups is empty
  assert(!output.includes('metrics'), 'should not mention metrics when groups empty');
}

async function test_multi_group_selects_selected() {
  const { generateCopySummary } = await import('./copySummary.js');
  const output = generateCopySummary(multiGroupFixture());

  // Should show Peer Benchmark (selected: true), not Valuation
  assert(output.includes('Peer Benchmark — 1 metric'), 'selected group must be shown');
  assert(!output.includes('Valuation — 1 metric'), 'unselected group must not appear');
}

async function test_forbidden_wording_comprehensive() {
  const { generateCopySummary } = await import('./copySummary.js');

  // Use NVDA fixture as base
  const fixture = nvdaFixture();

  // Simulate worst case: if T1 sanitizer somehow missed forbidden words
  // in label/formatted_value, they must still not appear in the summary
  // (and they wouldn't because T1 strips them — but we assert defensively)
  const output = generateCopySummary(fixture);
  assertNoForbiddenTokens(output, 'NVDA defensive');

  // TSLA N/A fixture
  const outputNA = generateCopySummary(tslaNAFixture());
  assertNoForbiddenTokens(outputNA, 'TSLA N/A defensive');
}

async function test_no_fetch_during_generation() {
  const { generateCopySummary, copyToClipboard } = await import('./copySummary.js');
  const spy = installFetchSpy();

  try {
    // generateCopySummary is synchronous — cannot call fetch
    generateCopySummary(nvdaFixture());
    assert.strictEqual(spy.calls(), 0, 'generateCopySummary must not call fetch');

    // copyToClipboard without navigator
    const fakeNav = makeFakeNavigator();
    const fakeDoc = makeFakeDocument();
    await copyToClipboard('test text', { _navigator: fakeNav, _document: fakeDoc });
    assert.strictEqual(spy.calls(), 0, 'copyToClipboard must not call fetch');

    // copySummaryToClipboard
    const { copySummaryToClipboard } = await import('./copySummary.js');
    await copySummaryToClipboard(nvdaFixture(), { _navigator: fakeNav, _document: fakeDoc });
    assert.strictEqual(spy.calls(), 0, 'copySummaryToClipboard must not call fetch');
  } finally {
    spy.restore();
  }
}

async function test_clipboard_api_success() {
  const { copyToClipboard } = await import('./copySummary.js');

  let writtenText = null;
  const fakeNav = makeFakeNavigator({
    writeText: async (text) => { writtenText = text; },
  });
  const fakeDoc = makeFakeDocument();

  const result = await copyToClipboard('Hello clipboard', {
    _navigator: fakeNav,
    _document: fakeDoc,
  });

  assert.strictEqual(result.ok, true, 'clipboard API should succeed');
  assert.strictEqual(result.text, 'Hello clipboard');
  assert.strictEqual(writtenText, 'Hello clipboard', 'writeText should be called');
}

async function test_clipboard_fallback_path() {
  const { copyToClipboard } = await import('./copySummary.js');

  // Clipboard API throws → falls back to execCommand
  let execCalls = 0;
  const fakeNav = makeFakeNavigator({
    writeText: async () => { throw new Error('denied'); },
  });
  const fakeDoc = {
    body: { children: [], appendChild(el) { this.children.push(el); }, removeChild() {} },
    createElement(tag) { return { tagName: tag, value: '', style: {}, select() {} }; },
    execCommand(cmd) { execCalls++; return true; },
  };

  const result = await copyToClipboard('Fallback text', {
    _navigator: fakeNav,
    _document: fakeDoc,
  });

  assert.strictEqual(result.ok, true, 'fallback should succeed');
  assert.strictEqual(result.text, 'Fallback text');
  assert.strictEqual(execCalls, 1, 'execCommand should be called once');
}

async function test_clipboard_api_rejected_falls_back() {
  const { copyToClipboard } = await import('./copySummary.js');

  let fallbackUsed = false;
  const fakeNav = makeFakeNavigator({
    writeText: async () => { throw new DOMException('Not allowed', 'NotAllowedError'); },
  });
  const fakeDoc = {
    body: { children: [], appendChild(el) { this.children.push(el); }, removeChild() {} },
    createElement(tag) { return { tagName: tag, value: '', style: {}, select() {} }; },
    execCommand(cmd) { fallbackUsed = true; return true; },
  };

  await copyToClipboard('Rejected API, fallback', {
    _navigator: fakeNav,
    _document: fakeDoc,
  });

  assert.strictEqual(fallbackUsed, true, 'fallback must trigger when Clipboard API throws');
}

async function test_no_navigator_no_doc_returns_error() {
  const { copyToClipboard } = await import('./copySummary.js');

  const result = await copyToClipboard('Nowhere to copy', {
    _navigator: undefined,
    _document: undefined,
  });

  assert.strictEqual(result.ok, false);
  assert(result.error, 'error should be present');
  assert(result.text === 'Nowhere to copy', 'text should still be available');
}

async function test_copy_summary_to_clipboard_integration() {
  const { copySummaryToClipboard } = await import('./copySummary.js');

  let writtenText = null;
  const fakeNav = makeFakeNavigator({
    writeText: async (text) => { writtenText = text; },
  });
  const fakeDoc = makeFakeDocument();

  const result = await copySummaryToClipboard(nvdaFixture(), {
    _navigator: fakeNav,
    _document: fakeDoc,
  });

  assert.strictEqual(result.ok, true);
  assert(writtenText.includes('**NVDA — NVIDIA Corporation**'), 'summary header in clipboard text');
  assert(writtenText.includes('Currency: USD'), 'currency in clipboard text');
  assert(writtenText.includes('P/E TTM: 41.2x'), 'metrics in clipboard text');
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

(async () => {
  const tests = [
    test_nvda_generates_correct_summary,
    test_tsla_nas_are_clean,
    test_usd_currency_present,
    test_empty_groups_handled_gracefully,
    test_multi_group_selects_selected,
    test_forbidden_wording_comprehensive,
    test_no_fetch_during_generation,
    test_clipboard_api_success,
    test_clipboard_fallback_path,
    test_clipboard_api_rejected_falls_back,
    test_no_navigator_no_doc_returns_error,
    test_copy_summary_to_clipboard_integration,
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

  console.log(`\n${passed}/${tests.length} passed`);
  if (failed > 0) {
    console.error(`${failed} test(s) failed`);
    process.exit(1);
  }
})();
