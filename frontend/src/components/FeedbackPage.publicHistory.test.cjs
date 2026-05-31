#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const sourcePath = path.join(__dirname, 'FeedbackPage.jsx');
const source = fs.readFileSync(sourcePath, 'utf8');

assert(
  !source.includes("import ChatWidget from './ChatWidget.jsx'"),
  'FeedbackPage must not mount its own ChatWidget; App owns the global widget so conversation continuity survives route changes.'
);

assert(
  !/<ChatWidget\b/.test(source),
  'FeedbackPage must not render a second chat widget on #feedback.'
);

assert(
  source.includes('const note = publicNote(entry, lang);') && source.includes('{note}') && !source.includes('{entry.notes}'),
  'Feedback history must render sanitized customer-facing status updates instead of raw operational notes.'
);

assert(
  source.includes("Google PDF feedback is linked to the attached documents below") &&
    source.includes('annotated PDFs for pages 1, 5, 7 and 9') &&
    source.includes('Google のPDFに関するコメント'),
  'Google PDF feedback notes must explicitly link remarks to the main Google PDF and annotated page PDFs in EN/JP.'
);

assert(
  source.includes('friendlyFileLabel(fileName, entry, lang)'),
  'Feedback attachment links must show customer-friendly labels instead of raw hashed filenames.'
);

assert(
  source.includes('<SeekingAlphaAccessPanel mode="feedback" lang={lang} />'),
  'Seeking Alpha cookie access panel must remain visible on the feedback page.'
);

console.log('✅ FeedbackPage public history/chat continuity guards passed');
