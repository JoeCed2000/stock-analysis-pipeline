const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const sourcePath = path.join(__dirname, 'AdminPage.jsx');
const source = fs.readFileSync(sourcePath, 'utf8');
const apiSource = fs.readFileSync(path.join(ROOT, 'src/api.js'), 'utf8');

function assert(condition, message) {
  if (!condition) {
    console.error(`❌ ${message}`);
    process.exit(1);
  }
}

assert(
  source.includes('fetch(`${API}/admin/feedback`'),
  'Admin feedback viewer must use the protected admin endpoint'
);

assert(
  !source.includes('fetch(`${API}/feedback`)'),
  'Admin feedback viewer must not depend on public global feedback history'
);

assert(
  source.includes('setFeedbacks(Array.isArray(fbRes) ? fbRes : [])'),
  'Admin feedback viewer must read the protected endpoint array response safely'
);

assert(
  source.includes('getFeedbackAttachmentUrl(fb._ticker || fb.ticker, f, adminKey)'),
  'Admin feedback attachments must use the decorated bucket (_ticker) so historical/general feedback files resolve correctly, and carry the admin key because /api/feedback-file is protected'
);

assert(
  source.includes("headers: adminKey ? { 'X-API-Key': adminKey } : {}"),
  'Admin feedback fetch must send the operator-supplied key; the static bundle cannot embed CED_CONTROL_KEY'
);

assert(
  source.includes('sessionStorage.setItem(ADMIN_KEY_STORAGE, next)') && !/\blocalStorage\s*\./.test(source),
  'Admin key must never be written to localStorage — it would outlive the tab on a shared machine'
);

assert(
  source.includes('fetch(`${API}/search-stats`)'),
  'Admin search stats must use public read-only /api/search-stats so the static production admin page does not require embedding an admin secret'
);

assert(
  source.includes('const searchParams = new URLSearchParams'),
  'Admin search history must build URLSearchParams so filters are encoded safely'
);

assert(
  source.includes("searchParams.set('user_agent', userAgentFilter.trim())"),
  'Admin search history must expose a User Agent filter query param'
);

assert(
  source.includes("searchParams.set('error', errorFilter.trim())"),
  'Admin search history must expose an Error filter query param'
);

assert(
  source.includes('fetch(`${API}/recent-searches?${searchParams.toString()}`)'),
  'Admin search history must use public read-only /api/recent-searches with encoded filters so the table remains visible in production'
);

assert(
  source.includes('Filtered rows') && source.includes('Clear filters'),
  'Admin search history must show filtered-row feedback and a clear action'
);

assert(
  !source.includes('fetch(`${API}/admin/search-stats`)'),
  'Admin search stats viewer must not call protected /api/admin/search-stats from the static frontend'
);

assert(
  !source.includes('fetch(`${API}/admin/recent-searches'),
  'Admin search history viewer must not call protected /api/admin/recent-searches from the static frontend'
);

assert(
  !apiSource.includes('/admin/recent-searches'),
  'Shared fetchRecentSearches helper must not call protected /api/admin/recent-searches from the static frontend'
);

assert(
  apiSource.includes('/recent-searches?limit=${limit}'),
  'Shared fetchRecentSearches helper must call public read-only /api/recent-searches'
);

console.log('✅ AdminPage protected feedback history guard passed');
