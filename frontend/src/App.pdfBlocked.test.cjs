// Static guard for frontend PDF_BLOCKED handling.
// Run with: node frontend/src/App.pdfBlocked.test.cjs

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const source = fs.readFileSync(path.join(__dirname, 'App.jsx'), 'utf8');

assert.match(source, /phase:\s*'pdf_blocked'/, 'App must set progress.phase=pdf_blocked');
assert.match(source, /ds\?\.phase\s*===\s*'pdf_blocked'/, 'Dossier polling must detect backend pdf_blocked phase');
assert.match(source, /deep_dive_validated\s*===\s*false/, 'Dossier polling must detect persisted validator failures');
assert.match(source, /MAX_PDF_POLL_ATTEMPTS/, 'PDF button polling must have a retry cap');
assert.match(source, /status\s*===\s*422/, 'PDF button polling must stop on validator 422');

console.log('App pdf_blocked guards passed');
