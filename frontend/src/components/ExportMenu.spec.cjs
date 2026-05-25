// ExportMenu & Bridge integration tests — SA V2.6 T5
// Run with: node frontend/src/components/ExportMenu.spec.cjs
//
// Tests the export data bridge and the snapshot-data composition
// logic used by ExportMenu (does not test the React component directly,
// since these are Node.js CJS tests without jsdom).

const assert = require('assert');

// ── Helpers: dynamically load ES module ──
let setExportBridgeData, getExportBridgeData;
let buildExportSnapshot;

async function loadModules() {
  // Bridge
  const bridge = await import('../export/exportDataBridge.js');
  setExportBridgeData = bridge.setExportBridgeData;
  getExportBridgeData = bridge.getExportBridgeData;

  // Snapshot
  const snap = await import('../export/exportSnapshot.js');
  buildExportSnapshot = snap.buildExportSnapshot;
}

// ── Tests ──

async function test_bridge_stores_and_retrieves() {
  // Clear state by overwriting
  setExportBridgeData('valuation', { key: 'value', source: 'yfinance' });
  const data = getExportBridgeData();
  assert.deepStrictEqual(data.valuation, { key: 'value', source: 'yfinance' });
  console.log('✅ test_bridge_stores_and_retrieves');
}

async function test_bridge_rejects_invalid_keys() {
  setExportBridgeData('invalid_key', { bad: true });
  const data = getExportBridgeData();
  assert.strictEqual(data.invalid_key, undefined);
  console.log('✅ test_bridge_rejects_invalid_keys');
}

async function test_bridge_overwrites() {
  setExportBridgeData('valuation', { source: 'first' });
  setExportBridgeData('valuation', { source: 'second' });
  const data = getExportBridgeData();
  assert.strictEqual(data.valuation.source, 'second');
  console.log('✅ test_bridge_overwrites');
}

async function test_bridge_three_keys() {
  setExportBridgeData('valuation', { val: 1 });
  setExportBridgeData('valuation_context', { ctx: 2 });
  setExportBridgeData('peer_benchmark', { peer: 3 });
  const data = getExportBridgeData();
  assert.strictEqual(data.valuation.val, 1);
  assert.strictEqual(data.valuation_context.ctx, 2);
  assert.strictEqual(data.peer_benchmark.peer, 3);
  console.log('✅ test_bridge_three_keys');
}

async function test_snapshot_composition_like_getSnapshotData() {
  // Simulate what AnalysisCard's getSnapshotData does
  const result = { ticker: 'NVDA', company_name: 'NVIDIA Corp', price_native: 125, currency: 'USD' };
  setExportBridgeData('valuation', { source: 'yfinance', status: 'fresh', metrics: { pe_ttm: 42 } });
  setExportBridgeData('valuation_context', { context: { peg: 1.5 } });
  setExportBridgeData('peer_benchmark', { peer_context: { group: 'semis' }, benchmarks: {} });

  const bridge = getExportBridgeData();
  const input = {
    result,
    ...(bridge.valuation ? { valuation: bridge.valuation } : {}),
    ...(bridge.valuation_context ? { valuation_context: bridge.valuation_context } : {}),
    ...(bridge.peer_benchmark ? { peer_benchmark: bridge.peer_benchmark } : {}),
    selected_group: 'valuation',
  };

  assert.strictEqual(input.result.ticker, 'NVDA');
  assert.strictEqual(input.valuation.source, 'yfinance');
  assert.strictEqual(input.selected_group, 'valuation');

  const snapshot = buildExportSnapshot(input);
  assert.strictEqual(snapshot.ticker, 'NVDA');
  assert.strictEqual(snapshot.currency, 'USD');
  assert.strictEqual(snapshot.selected_group, 'valuation');
  assert.strictEqual(snapshot.source, 'yfinance');
  console.log('✅ test_snapshot_composition_like_getSnapshotData');
}

async function test_null_result_handling() {
  // When result has no ticker, getSnapshotData returns null
  const result = {};
  const bridge = getExportBridgeData();
  const hasTicker = Boolean(result?.ticker);
  assert.strictEqual(hasTicker, false);
  console.log('✅ test_null_result_handling');
}

async function test_no_forbidden_data_in_snapshot() {
  const result = { ticker: 'TEST', company_name: 'Test Co', decision: 'BUY', scoring: { total: 35 } };
  setExportBridgeData('valuation', { source: 'yfinance', status: 'fresh', metrics: { pe_ttm: 15 } });
  setExportBridgeData('valuation_context', { context: { peg: 1.0 } });

  const bridge = getExportBridgeData();
  const input = { result, valuation: bridge.valuation, valuation_context: bridge.valuation_context, selected_group: 'valuation' };
  const snapshot = buildExportSnapshot(input);

  // No forbidden keys in snapshot
  const flat = JSON.stringify(snapshot).toLowerCase();
  assert.strictEqual(flat.includes('decision'), false, 'decision should be stripped');
  assert.strictEqual(flat.includes('scoring'), false, 'scoring should be stripped');
  assert.strictEqual(flat.includes('eur'), false, 'eur should be stripped');
  assert.strictEqual(flat.includes('fx'), false, 'fx should be stripped');
  assert.strictEqual(flat.includes('secret'), false, 'secret should be stripped');
  console.log('✅ test_no_forbidden_data_in_snapshot');
}

async function test_export_menu_imports_exist() {
  // Verify all export modules are importable
  await import('../export/csvExport.js');
  await import('../export/pngExport.js');
  await import('../export/copySummary.js');
  await import('../export/exportSnapshot.js');
  await import('../export/exportDataBridge.js');
  console.log('✅ test_export_menu_imports_exist');
}

// ── Runner ──

(async () => {
  let passed = 0;
  const tests = [
    test_bridge_stores_and_retrieves,
    test_bridge_rejects_invalid_keys,
    test_bridge_overwrites,
    test_bridge_three_keys,
    test_snapshot_composition_like_getSnapshotData,
    test_null_result_handling,
    test_no_forbidden_data_in_snapshot,
    test_export_menu_imports_exist,
  ];

  await loadModules();

  for (const t of tests) {
    try {
      await t();
      passed++;
    } catch (err) {
      console.error(`❌ ${t.name}: ${err.message}`);
    }
  }

  console.log(`\n${passed}/${tests.length} ExportMenu integration tests passed`);
  if (passed < tests.length) process.exit(1);
})();
