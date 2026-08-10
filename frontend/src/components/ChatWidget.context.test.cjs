#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const widget = fs.readFileSync(path.join(__dirname, 'ChatWidget.jsx'), 'utf8');
const app = fs.readFileSync(path.join(__dirname, '..', 'App.jsx'), 'utf8');

assert(widget.includes('GENERAL_ACTIONS_EN') && widget.includes('GENERAL_ACTIONS_JA'),
  'Chat must provide generic actions when no stock is selected.');
assert(widget.includes('ticker ? STOCK_ACTIONS_EN : GENERAL_ACTIONS_EN'),
  'English quick actions must depend on selected stock context.');
assert(widget.includes('ticker ? STOCK_ACTIONS_JA : GENERAL_ACTIONS_JA'),
  'Japanese quick actions must depend on selected stock context.');
assert(app.includes('mode={mode}'), 'App must pass the active analysis mode to ChatWidget.');
assert(widget.includes('className="chat-widget-panel"'), 'Chat panel needs a responsive CSS hook.');
assert(widget.includes('@media (max-width: 520px)'), 'Chat panel must become a mobile bottom sheet.');

console.log('✅ ChatWidget context and responsive contract passed');
