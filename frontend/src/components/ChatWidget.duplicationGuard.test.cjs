#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const widget = fs.readFileSync(path.join(ROOT, 'src/components/ChatWidget.jsx'), 'utf8');
const app = fs.readFileSync(path.join(ROOT, 'src/App.jsx'), 'utf8');
const admin = fs.readFileSync(path.join(ROOT, 'src/components/AdminPage.jsx'), 'utf8');
const feedback = fs.readFileSync(path.join(ROOT, 'src/components/FeedbackPanel.jsx'), 'utf8');
const chatContext = fs.readFileSync(path.resolve(ROOT, '../backend/chat_context.py'), 'utf8');

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

assert(widget.includes('const sendingRef = useRef(false);'), 'ChatWidget must have a synchronous sendingRef guard');
assert(widget.includes('const [submitting, setSubmitting] = useState(false);'), 'ChatWidget must separate HTTP submit lock from assistant response loading');
assert(widget.includes('disabled={!input.trim() || submitting}'), 'Send button must not stay disabled for the whole assistant loading cycle');
assert(!widget.includes('disabled={!input.trim() || (loading && !streaming)}'), 'Send button must not depend on fragile loading/streaming state');
assert(widget.includes('sendingRef.current'), 'ChatWidget must use sendingRef in send lifecycle');
assert(widget.includes('const existingIdx = prev.findIndex(m => m.id === data.message_id);'), 'assistant_started must check for an existing assistant message id');
assert(widget.includes('idx === existingIdx'), 'assistant_started must update the existing message instead of blindly appending');
assert(!widget.includes("setMessages(prev => [...prev, {\n          id: data.message_id"), 'assistant_started must not blindly append duplicate assistant placeholders');
assert(!app.includes('nami_personal'), 'App must not use nami_personal audience mode');
assert(!app.includes('🧠 Nami'), 'App must not show hard-coded Nami persona badge');
assert(!admin.includes('Nami Feedback'), 'Admin feedback label must be neutral');
assert(!feedback.includes('Feedback for Nami'), 'Feedback panel label must be neutral');
assert(!widget.includes('visitor_name'), 'ChatWidget must not send a client-controlled visitor_name payload');
assert(widget.includes('visitor_id'), 'ChatWidget must scope sessions with visitor_id instead of visible persona labels');

console.log('PASS ChatWidget duplication and identity guard');
