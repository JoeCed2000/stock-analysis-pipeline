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

assert(!source.includes('loadHistory') && !source.includes('setHistory'),
  'The public feedback page must not fetch every visitor submission.');
assert(!source.includes('<SeekingAlphaAccessPanel'),
  'The public feedback page must not expose Seeking Alpha cookie administration.');
assert(!source.includes('Submitted feedback') && !source.includes('history.map('),
  'The public feedback page must not render global submission history.');
assert(source.includes('Reference:') && source.includes('data.id'),
  'A successful public submission must show its own reference without exposing other feedback.');

console.log('✅ FeedbackPage privacy/chat continuity guards passed');
