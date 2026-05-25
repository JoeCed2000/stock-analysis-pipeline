/**
 * SA V2.6 — Export Data Bridge
 *
 * Minimal module-level store so child components (ValuationGroup,
 * PeerBenchmarkGroup) can publish their loaded data, and ExportMenu
 * can collect it at click time without modifying component APIs or
 * triggering extra network calls.
 *
 * All values are replaced on each publish — no accumulation, no history.
 */
const _store = {};

const EXPORT_BRIDGE_KEYS = ['valuation', 'valuation_context', 'peer_benchmark'];

/**
 * Set export data for a given key.  Overwrites any previous value.
 * @param {string} key   One of 'valuation', 'valuation_context', 'peer_benchmark'
 * @param {object} data  Sanitizable data payload
 */
export function setExportBridgeData(key, data) {
  if (!EXPORT_BRIDGE_KEYS.includes(key)) return;
  _store[key] = data;
}

/**
 * Return a shallow snapshot of all bridge data (does NOT mutate the store).
 * @returns {object}
 */
export function getExportBridgeData() {
  return { ..._store };
}
