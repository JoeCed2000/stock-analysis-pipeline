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
  !source.includes('fetch(`${API}/admin/feedback`)'),
  'Admin feedback viewer must not call protected /api/admin/feedback from the static frontend'
);

assert(
  source.includes('fetch(`${API}/feedback`)'),
  'Admin feedback viewer should use public read-only /api/feedback so visible feedback history does not require embedding an admin secret'
);

assert(
  /setFeedbacks\(\(fbRes\?\.entries\s*\|\|\s*\[\]\)\)/.test(source),
  'Admin feedback viewer must read the public feedback response shape { entries: [...] }'
);

assert(
  source.includes('getFeedbackAttachmentUrl(fb._ticker || fb.ticker, f)'),
  'Admin feedback attachments must use the decorated bucket (_ticker) so historical/general feedback files resolve correctly'
);

assert(
  source.includes('fetch(`${API}/search-stats`)'),
  'Admin search stats must use public read-only /api/search-stats so the static production admin page does not require embedding an admin secret'
);

assert(
  source.includes('fetch(`${API}/recent-searches?limit=${PAGE_SIZE}&offset=${offset}`)'),
  'Admin search history must use public read-only /api/recent-searches so the table remains visible in production'
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

console.log('✅ AdminPage feedback public history guard passed');
