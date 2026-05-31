// Static guard for SmartLoader's PDF_BLOCKED state.
// Run with: node frontend/src/components/SmartLoader.pdfBlocked.test.cjs

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, 'SmartLoader.jsx'), 'utf8');

assert.match(source, /pdf_blocked:\s*3/, 'pdf_blocked must map to the final workflow step');
assert.match(source, /pdf_blocked:\s*'PDF generation blocked/, 'pdf_blocked needs a clear label');
assert.match(source, /pdf_blocked:\s*100/, 'pdf_blocked must stop at 100% instead of looking queued');
assert.match(source, /pdf_blocked:\s*\['act_pdf_blocked'\]/, 'pdf_blocked needs a dedicated activity');
assert.match(source, /act_pdf_blocked/, 'pdf_blocked activity key must be present');

console.log('SmartLoader pdf_blocked guards passed');
