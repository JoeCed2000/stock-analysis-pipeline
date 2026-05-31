const fs = require('fs');
const path = require('path');

const sourcePath = path.join(__dirname, 'AdminPage.jsx');
const source = fs.readFileSync(sourcePath, 'utf8');

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

console.log('✅ AdminPage feedback public history guard passed');
