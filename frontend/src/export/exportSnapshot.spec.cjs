// Export snapshot contract tests — SA V2.6 T1
// Run with: node frontend/src/export/exportSnapshot.spec.cjs

const assert = require('assert');

const FIXED_NOW = '2026-05-25T19:30:00.000Z';

function installFetchSpy() {
  const originalFetch = global.fetch;
  let calls = 0;
  global.fetch = (...args) => {
    calls += 1;
    throw new Error(`fetch must not be called by export snapshot: ${JSON.stringify(args)}`);
  };
  return {
    calls: () => calls,
    restore: () => { global.fetch = originalFetch; },
  };
}

function assertNoForbiddenPayload(payload) {
  const text = JSON.stringify(payload);
  const forbidden = [
    'EUR', 'FX', 'exchange rate', 'price_eur', 'fx_rate', 'exchange_rate',
    'recommendation', 'BUY', 'Buy', 'SELL', 'Sell', 'HOLD', 'Hold',
    'scoring', 'score_total', 'pe_forward', 'forward',
    'consensus', 'analyst', 'ai_narrative', 'narrative',
    'secret', 'token', 'api_key', '/home/ced', 'C:\\Users',
  ];
  for (const marker of forbidden) {
    assert(!text.includes(marker), `payload leaked forbidden marker: ${marker}`);
  }
}

async function test_export_snapshot_nvda_fixture_returns_required_public_immutable_contract() {
  const { buildExportSnapshot, EXPORT_ALLOWED_ENUMS } = await import('./exportSnapshot.js');

  assert.deepStrictEqual(EXPORT_ALLOWED_ENUMS.source, ['yfinance', 'finnhub', 'curated_config', 'cache', 'unknown']);
  assert.deepStrictEqual(EXPORT_ALLOWED_ENUMS.served_from, ['live', 'cache', 'stale_cache', 'unknown']);
  assert.deepStrictEqual(EXPORT_ALLOWED_ENUMS.status, ['ok', 'partial', 'cached', 'na', 'stale', 'unknown']);

  const snapshot = buildExportSnapshot({
    result: {
      ticker: 'NVDA',
      company_name: 'NVIDIA Corporation',
      currency: 'USD',
      decision: 'BUY',
      scoring: { total: 33 },
      price_native: 126.5,
      market_cap: 3100000000000,
      retrieved_at: '2026-05-25T18:12:00.000Z',
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
    valuation_context: {
      status: 'ok',
      context: { context_summary: { confidence: 'medium', warnings: [] } },
    },
    peer_benchmark: {
      status: 'available',
      source: 'curated_config',
      served_from: 'cache',
      peer_context: { available: true, group_id: 'semiconductors_ai', sample_size: 5, total_peers: 6 },
      benchmarks: { pe_ttm: { status: 'available', value: 41.2, peer_median: 35.1, label: 'above peer median' } },
      warnings: [],
    },
    build: { app: 'sa-pipeline', version: 'v2.6-test' },
  }, { generatedAt: FIXED_NOW });

  const expectedKeys = [
    'ticker', 'company_name', 'currency', 'selected_group', 'selected_period', 'selected_mode',
    'generated_at', 'quote_timestamp', 'fundamentals_timestamp', 'market_data_status',
    'source', 'served_from', 'status', 'build', 'groups', 'valuation', 'valuation_context',
    'peer_benchmark', 'warnings',
  ];
  assert.deepStrictEqual(Object.keys(snapshot), expectedKeys);
  assert(Object.isFrozen(snapshot), 'root snapshot must be frozen');
  assert(Object.isFrozen(snapshot.valuation), 'nested valuation contract must be frozen');
  assert(Object.isFrozen(snapshot.groups), 'groups array must be frozen');

  assert.strictEqual(snapshot.ticker, 'NVDA');
  assert.strictEqual(snapshot.company_name, 'NVIDIA Corporation');
  assert.strictEqual(snapshot.currency, 'USD');
  assert.strictEqual(snapshot.selected_group, 'valuation');
  assert.strictEqual(snapshot.selected_period, '2026Q1');
  assert.strictEqual(snapshot.selected_mode, 'current');
  assert.strictEqual(snapshot.generated_at, FIXED_NOW);
  assert.strictEqual(snapshot.quote_timestamp, '2026-05-25T18:00:00.000Z');
  assert.strictEqual(snapshot.fundamentals_timestamp, '2026-05-20T00:00:00.000Z');
  assert.strictEqual(snapshot.source, 'yfinance');
  assert.strictEqual(snapshot.served_from, 'live');
  assert.strictEqual(snapshot.status, 'ok');
  assert.strictEqual(snapshot.market_data_status, 'ok');
  assert.strictEqual(snapshot.valuation.metrics[0].formatted_value, '41.2x');
  assert.strictEqual(snapshot.groups.find(g => g.id === 'valuation').metrics.length, 2);
  assertNoForbiddenPayload(snapshot);
}

async function test_export_snapshot_aapl_fixture_strips_non_usd_and_forbidden_fields_centrally() {
  const { buildExportSnapshot } = await import('./exportSnapshot.js');

  const snapshot = buildExportSnapshot({
    result: {
      ticker: 'AAPL',
      company_name: 'Apple Inc.',
      currency: 'EUR',
      price_eur: 185,
      fx_rate: 0.92,
      exchange_rate: 0.92,
      recommendation: 'BUY',
      decision: 'HOLD',
      scoring: { total: 29 },
      score_total: 29,
      ai_narrative: 'Looks attractive',
      secret_token: 'secret-token',
      local_path: '/home/ced/private/aapl.json',
    },
    valuation: {
      source: 'finnhub',
      served_from: 'cache',
      status: 'cached',
      quote_currency: 'EUR',
      pe_forward: 23.4,
      metrics: {
        pe_ttm: { value: 29.1, formatted_value: '29.1x', notes: 'EUR quote and FX note' },
        pe_forward: 23.4,
        price_eur: 185,
        api_key: 'secret-key',
      },
    },
    peer_benchmark: {
      source: 'curated_config',
      status: 'limited',
      consensus: 'outperform',
      analyst_count: 42,
      summary: { stance: 'Hold until exchange rate improves' },
      benchmarks: {
        pe_forward: { value: 23.4 },
        pe_ttm: { status: 'available', value: 29.1, peer_median: 28.8 },
      },
      debug_path: 'C:\\Users\\ced\\debug.json',
    },
  }, { generatedAt: FIXED_NOW });

  assert.strictEqual(snapshot.currency, 'USD');
  assert.strictEqual(snapshot.source, 'finnhub');
  assert.strictEqual(snapshot.served_from, 'cache');
  assert.strictEqual(snapshot.status, 'cached');
  assert.strictEqual(snapshot.peer_benchmark.status, 'partial');
  assert(!('quote_currency' in snapshot.valuation), 'nested quote_currency must be stripped instead of rewritten to USD');
  assert.deepStrictEqual(snapshot.warnings, [], 'non-USD input must not create visible currency/FX warnings');
  assertNoForbiddenPayload(snapshot);
}

async function test_export_snapshot_tsla_fixture_normalizes_na_values_and_unknown_enums() {
  const { buildExportSnapshot, normalizeExportNA } = await import('./exportSnapshot.js');

  assert.strictEqual(normalizeExportNA(null), 'N/A');
  assert.strictEqual(normalizeExportNA(undefined), 'N/A');
  assert.strictEqual(normalizeExportNA(Number.NaN), 'N/A');
  assert.strictEqual(normalizeExportNA(Number.POSITIVE_INFINITY), 'N/A');
  assert.strictEqual(normalizeExportNA(''), 'N/A');
  assert.strictEqual(normalizeExportNA('—'), 'N/A');
  assert.strictEqual(normalizeExportNA(0), 0);

  const snapshot = buildExportSnapshot({
    result: { ticker: 'TSLA', company_name: '', currency: 'USD' },
    selected_group: '',
    selected_period: null,
    selected_mode: undefined,
    valuation: {
      source: 'random_vendor',
      served_from: 'edge-node-7',
      status: 'unavailable',
      quote_timestamp: null,
      fundamentals_timestamp: undefined,
      metrics: [
        { key: 'ps_ttm', label: '', value: Number.NaN, formatted_value: '—', unit: '' },
      ],
    },
  }, { generatedAt: FIXED_NOW });

  assert.strictEqual(snapshot.company_name, 'N/A');
  assert.strictEqual(snapshot.selected_group, 'N/A');
  assert.strictEqual(snapshot.selected_period, 'N/A');
  assert.strictEqual(snapshot.selected_mode, 'N/A');
  assert.strictEqual(snapshot.source, 'unknown');
  assert.strictEqual(snapshot.served_from, 'unknown');
  assert.strictEqual(snapshot.status, 'na');
  assert.strictEqual(snapshot.quote_timestamp, 'N/A');
  assert.strictEqual(snapshot.fundamentals_timestamp, 'N/A');
  assert.strictEqual(snapshot.valuation.metrics[0].label, 'N/A');
  assert.strictEqual(snapshot.valuation.metrics[0].value, null);
  assert.strictEqual(snapshot.valuation.metrics[0].formatted_value, 'N/A');
  assert.strictEqual(snapshot.valuation.metrics[0].unit, 'N/A');
}

async function test_export_snapshot_creation_never_calls_fetch_or_xhr() {
  const { buildExportSnapshot } = await import('./exportSnapshot.js');
  const spy = installFetchSpy();
  const input = { result: { ticker: 'NVDA', company_name: 'NVIDIA', currency: 'USD' } };
  const before = JSON.stringify(input);
  try {
    const snapshot = buildExportSnapshot(input, { generatedAt: FIXED_NOW });
    assert.strictEqual(snapshot.ticker, 'NVDA');
    assert.strictEqual(JSON.stringify(input), before, 'snapshot creation must not mutate input props');
    assert.strictEqual(spy.calls(), 0, 'snapshot creation must not call fetch');
  } finally {
    spy.restore();
  }
}

(async () => {
  const tests = [
    test_export_snapshot_nvda_fixture_returns_required_public_immutable_contract,
    test_export_snapshot_aapl_fixture_strips_non_usd_and_forbidden_fields_centrally,
    test_export_snapshot_tsla_fixture_normalizes_na_values_and_unknown_enums,
    test_export_snapshot_creation_never_calls_fetch_or_xhr,
  ];
  for (const test of tests) {
    await test();
    console.log(`✅ ${test.name}`);
  }
  console.log(`\n${tests.length}/${tests.length} export snapshot contract tests passed`);
})().catch(err => {
  console.error(err);
  process.exit(1);
});
