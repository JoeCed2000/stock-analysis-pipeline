import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_URL || '/api';
const WS_BASE = (() => {
  const api = API_BASE.replace('/api', '');
  const url = api.startsWith('http') ? api : window.location.origin;
  return url.replace(/^http/, 'ws');
})();

const VISITOR_ID_KEY = 'chat_visitor_id';

function getOrCreateVisitorId() {
  let vid = localStorage.getItem(VISITOR_ID_KEY);
  if (!vid) {
    vid = crypto.randomUUID();
    localStorage.setItem(VISITOR_ID_KEY, vid);
  }
  return vid;
}

function uid() {
  return 'ik_' + Math.random().toString(36).slice(2, 10);
}

function normalizeChatLanguage(lang) {
  return String(lang || 'ja').toLowerCase().startsWith('en') ? 'en' : 'ja';
}

function mergeChatMessages(existingMessages, incomingMessages) {
  const merged = [...existingMessages];

  for (const incoming of incomingMessages || []) {
    const byId = merged.findIndex((m) => m.id === incoming.id);
    if (byId >= 0) {
      merged[byId] = { ...merged[byId], ...incoming };
      continue;
    }

    if (incoming.role === 'user') {
      const optimisticIdx = merged.findIndex((m) =>
        m.role === 'user'
        && String(m.id || '').startsWith('ik_')
        && m.content === incoming.content
      );
      if (optimisticIdx >= 0) {
        merged[optimisticIdx] = { ...merged[optimisticIdx], ...incoming };
        continue;
      }
    }

    merged.push(incoming);
  }

  return merged.sort((a, b) => new Date(a.created_at || 0) - new Date(b.created_at || 0));
}

// ── Quick action suggestions ─────────────────────────────────────────────
const QUICK_ACTIONS_JA = [
  'この銘柄の要点を教えて',
  '主なリスクは？',
  '強気シナリオと弱気シナリオを比較して',
  'PDFの内容を簡単にまとめて',
  '分かりにくい部分を報告する',
  'バグを報告する',
];

const QUICK_ACTIONS_EN = [
  'Give me the key takeaways for this stock',
  'What are the main risks?',
  'Compare the bull and bear cases',
  'Summarize this PDF briefly',
  'Report something confusing',
  'Report a bug',
];

const CHAT_COPY = {
  ja: {
    connectError: '接続に失敗しました',
    sendError: '送信に失敗しました',
    statusOnline: '🟢 オンライン',
    statusReconnecting: '🟡 再接続中…',
    statusOffline: '🔴 オフライン',
    openTitle: 'チャットを開く',
    closeLabel: '閉じる',
    header: '💬 アシスタント',
    greeting: '👋 こんにちは！',
    intro: '分析レポートについてのご質問や、フィードバックをいつでもお聞かせください。',
    errorFallback: '[エラーが発生しました]',
    typing: '入力中…',
    copyTitle: 'コピー',
    copied: '✅ コピー済',
    copy: '📋 コピー',
    thinking: '考え中...',
    placeholder: 'この分析について質問してください…',
    retry: '🔄 再試行',
  },
  en: {
    connectError: 'Failed to connect',
    sendError: 'Failed to send message',
    statusOnline: '🟢 Online',
    statusReconnecting: '🟡 Reconnecting…',
    statusOffline: '🔴 Offline',
    openTitle: 'Open chat',
    closeLabel: 'Close',
    header: '💬 Assistant',
    greeting: '👋 Hello!',
    intro: 'Ask any question about the analysis report, or share feedback at any time.',
    errorFallback: '[An error occurred]',
    typing: 'Typing…',
    copyTitle: 'Copy',
    copied: '✅ Copied',
    copy: '📋 Copy',
    thinking: 'Thinking...',
    placeholder: 'Ask a question about this analysis…',
    retry: '🔄 Retry',
  },
};

// ── ChatWidget ──────────────────────────────────────────────────────────
export default function ChatWidget({ lang = 'ja', ticker, pdfId, pdfTitle, currentUrl }) {
  const chatLang = normalizeChatLanguage(lang);
  const copy = CHAT_COPY[chatLang];
  const quickActions = chatLang === 'en' ? QUICK_ACTIONS_EN : QUICK_ACTIONS_JA;
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamingMsgId, setStreamingMsgId] = useState(null);
  const [error, setError] = useState('');
  const [wsStatus, setWsStatus] = useState('disconnected'); // connected | disconnected | reconnecting
  const timersRef = useRef([]);
  const sendingRef = useRef(false);
  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const reconnectTimer = useRef(null);

  // ── Initialize session ────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const visitorId = getOrCreateVisitorId();
        const res = await fetch(`${API_BASE}/chat/session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language: chatLang, visitor_id: visitorId }),
        });
        if (res.ok && !cancelled) {
          const data = await res.json();
          setSessionId(data.session_id);
          // Persist server-side visitor_id (in case backend generated one)
          if (data.visitor_id) {
            localStorage.setItem(VISITOR_ID_KEY, data.visitor_id);
          }
          // Load history
          const histRes = await fetch(`${API_BASE}/chat/history?session_id=${data.session_id}`);
          if (histRes.ok) {
            const histData = await histRes.json();
            setMessages(histData.messages || []);
          }
        }
      } catch (e) {
        if (!cancelled) setError(copy.connectError);
      }
    }
    init();
    return () => { cancelled = true; };
  }, [chatLang, copy.connectError]);

  // ── WebSocket ──────────────────────────────────────────────────────
  const connectWs = useCallback(() => {
    if (!sessionId) return;
    try {
      const ws = new WebSocket(`${WS_BASE}/api/chat/ws?session_id=${sessionId}`);
      wsRef.current = ws;
      ws.onopen = () => {
        setWsStatus('connected');
        setError('');
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleWsEvent(data);
        } catch (e) {
          // ignore parse errors
        }
      };
      ws.onclose = () => {
        setWsStatus('disconnected');
        // Auto-reconnect after 2s
        reconnectTimer.current = setTimeout(() => {
          setWsStatus('reconnecting');
          connectWs();
        }, 2000);
      };
      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      setWsStatus('disconnected');
    }
  }, [sessionId]);

  useEffect(() => {
    if (sessionId) connectWs();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
      timersRef.current.forEach(t => clearTimeout(t));
      timersRef.current = [];
    };
  }, [sessionId, connectWs]);

  // ── Handle WebSocket events ────────────────────────────────────────
  const handleWsEvent = useCallback((data) => {
    switch (data.event) {
      case 'assistant_started':
        setStreaming(true);
        setStreamingMsgId(data.message_id);
        setMessages(prev => {
          const existingIdx = prev.findIndex(m => m.id === data.message_id);
          const assistantMsg = {
            id: data.message_id,
            role: 'assistant',
            content: '',
            status: 'processing',
            created_at: new Date().toISOString(),
          };
          if (existingIdx >= 0) {
            return prev.map((m, idx) => (
              idx === existingIdx
                ? { ...assistantMsg, ...m, status: m.status || 'processing' }
                : m
            ));
          }
          return [...prev, assistantMsg];
        });
        break;
      case 'assistant_delta':
        setMessages(prev => prev.map(m =>
          m.id === data.message_id ? { ...m, content: m.content + (data.delta || '') } : m
        ));
        break;
      case 'assistant_completed':
        setStreaming(false);
        setStreamingMsgId(null);
        setLoading(false);
        sendingRef.current = false;
        setMessages(prev => prev.map(m =>
          m.id === data.message_id ? { ...m, status: 'completed' } : m
        ));
        break;
      case 'assistant_error':
        setStreaming(false);
        setStreamingMsgId(null);
        setLoading(false);
        sendingRef.current = false;
        setMessages(prev => prev.map(m =>
          m.id === data.message_id
            ? { ...m, content: m.content || copy.errorFallback, status: 'failed' }
            : m
        ));
        break;
      default:
        break;
    }
  }, [copy.errorFallback]);

  // ── Scroll to bottom ────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  // ── Send message ────────────────────────────────────────────────────
  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || !sessionId || submitting || sendingRef.current) return;
    sendingRef.current = true;
    setSubmitting(true);
    const trimmed = text.trim();
    setInput('');
    setLoading(true);
    setError('');

    const userMsg = {
      id: uid(),
      role: 'user',
      content: trimmed,
      status: 'completed',
      created_at: new Date().toISOString(),
    };
    const idempotencyKey = userMsg.id;
    setMessages(prev => [...prev, userMsg]);

    try {
      const res = await fetch(`${API_BASE}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message: trimmed,
          idempotency_key: idempotencyKey,
          context: {
            current_url: currentUrl || window.location.href,
            route: window.location.hash || '/',
            ticker: ticker || null,
            pdf_id: pdfId || null,
            pdf_title: pdfTitle || null,
            client_language: chatLang,
          },
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }
      const sendData = await res.json();
      setSubmitting(false);
      sendingRef.current = false;
      if (sendData.user_message_id) {
        setMessages(prev => prev.map(m =>
          m.id === userMsg.id ? { ...m, id: sendData.user_message_id } : m
        ));
      }
      // REST fallback: if WebSocket doesn't respond within 5s, poll history
      const restTimeout = setTimeout(async () => {
        if (!sessionId) return;
        try {
          const histRes = await fetch(`${API_BASE}/chat/history?session_id=${sessionId}`);
          if (histRes.ok) {
            const histData = await histRes.json();
            const msgs = histData.messages || [];
            setMessages(prev => mergeChatMessages(prev, msgs));
            // Check if any message is still processing
            const hasProcessing = msgs.some(m => m.status === 'processing' && m.role === 'assistant');
            if (!hasProcessing) {
              setLoading(false);
              setStreaming(false);
              sendingRef.current = false;
            }
          }
        } catch {}
      }, 5000);

      // Safety timeout: force-reset loading after 15s
      const safetyTimeout = setTimeout(() => {
        setLoading(false);
        setStreaming(false);
        sendingRef.current = false;
      }, 15000);

      // Store for cleanup
      timersRef.current.push(restTimeout, safetyTimeout);
    } catch (e) {
      setError(e.message || copy.sendError);
      setLoading(false);
      setSubmitting(false);
      sendingRef.current = false;
    }
  }, [sessionId, submitting, ticker, pdfId, pdfTitle, currentUrl, chatLang, copy.sendError]);

  // ── Keyboard handler ────────────────────────────────────────────────
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }, [input, sendMessage]);

  // ── Retry last failed message ───────────────────────────────────────
  const retryMessage = useCallback((msg) => {
    sendMessage(msg.content);
  }, [sendMessage]);

  // ── Copy message ──────────────────────────────────────────────────
  const [copiedId, setCopiedId] = useState(null);
  const copyMessage = useCallback(async (msg) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = msg.content;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  }, []);
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  // ── Get status display ──────────────────────────────────────────────
  const statusText = wsStatus === 'connected' ? copy.statusOnline
    : wsStatus === 'reconnecting' ? copy.statusReconnecting
    : copy.statusOffline;

  // ── Bubble ──────────────────────────────────────────────────────────
  if (!open) {
    return (
      <div style={bubbleContainerStyle}>
        <button
          onClick={() => setOpen(true)}
          style={bubbleStyle}
          title={copy.openTitle}
          aria-label={copy.openTitle}
        >
          💬
        </button>
      </div>
    );
  }

  // ── Panel ───────────────────────────────────────────────────────────
  return (
    <div style={panelContainerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#e6edf3' }}>
            {copy.header}
          </div>
          <div style={{ fontSize: 11, color: '#8b949e', marginTop: 2 }}>
            {statusText}
            {ticker && <span style={{ marginLeft: 8, color: '#58a6ff' }}>{ticker}</span>}
            {pdfTitle && <span style={{ marginLeft: 6, color: '#d29922' }}>· PDF</span>}
          </div>
        </div>
        <button onClick={() => setOpen(false)} style={closeButtonStyle} aria-label={copy.closeLabel}>
          ✕
        </button>
      </div>

      {/* Messages */}
      <div style={messagesContainerStyle}>
        {messages.length === 0 && !streaming && (
          <div style={welcomeStyle}>
            <p style={{ margin: '0 0 8px 0', fontSize: 15 }}>{copy.greeting}</p>
            <p style={{ margin: 0, color: '#8b949e' }}>
              {copy.intro}
            </p>
            <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {quickActions.map((action, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(action)}
                  style={quickActionStyle}
                >
                  {action}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} style={msg.role === 'user' ? userMsgWrap : assistantMsgWrap}>
            <div style={msg.role === 'user' ? userBubbleStyle : assistantBubbleStyle}>
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{msg.content || (msg.status === 'processing' ? '…' : '')}</div>
              {msg.status === 'processing' && !streaming && (
                <span style={typingStyle}>{copy.typing}</span>
              )}
              {msg.status === 'failed' && (
                <button onClick={() => retryMessage(msg)} style={retryButtonStyle}>
                  {copy.retry}
                </button>
              )}
              {msg.role === 'assistant' && msg.content && msg.status === 'completed' && (
                <button
                  onClick={() => copyMessage(msg)}
                  style={copyButtonStyle}
                  title={copy.copyTitle}
                >
                  {copiedId === msg.id ? copy.copied : copy.copy}
                </button>
              )}
            </div>
            <div style={timeStyle}>
              {msg.created_at ? new Date(msg.created_at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }) : ''}
            </div>
          </div>
        ))}

        {streaming && streamingMsgId && messages.find(m => m.id === streamingMsgId)?.content === '' && (
          <div style={typingIndicatorStyle}>
            <span className="chat-typing-dot">●</span>
            <span className="chat-typing-dot">●</span>
            <span className="chat-typing-dot">●</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && (
        <div style={chatErrorStyle}>
          ⚠️ {error}
          <button onClick={() => setError('')} style={{ ...closeButtonStyle, fontSize: 14, color: '#f85149' }}>✕</button>
        </div>
      )}

      {/* Thinking indicator */}
      {loading && !streaming && (
        <div style={thinkingStyle}>
          <span className="chat-typing-dot">●</span>
          <span className="chat-typing-dot">●</span>
          <span className="chat-typing-dot">●</span>
          <span style={{ marginLeft: 8, fontSize: 12, color: '#8b949e' }}>{copy.thinking}</span>
        </div>
      )}

      {/* Input */}
      <div style={inputContainerStyle}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={copy.placeholder}
          rows={2}
          style={chatInputStyle}
          disabled={false}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || submitting}
          style={sendButtonStyle(!input.trim() || submitting)}
        >
          ➤
        </button>
      </div>

      <style>{`
        .chat-typing-dot {
          animation: chat-blink 1.4s infinite both;
          color: #8b949e;
          font-size: 6px;
          margin: 0 2px;
        }
        .chat-typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .chat-typing-dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes chat-blink {
          0%, 80%, 100% { opacity: 0.2; }
          40% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────

const bubbleContainerStyle = {
  position: 'fixed',
  bottom: 20,
  right: 20,
  zIndex: 9999,
};

const bubbleStyle = {
  width: 54,
  height: 54,
  borderRadius: 28,
  background: 'linear-gradient(135deg, #238636, #2ea043)',
  border: '2px solid #3fb95040',
  color: '#fff',
  fontSize: 24,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  boxShadow: '0 4px 20px rgba(35,134,54,0.4)',
  transition: 'transform 0.2s, box-shadow 0.2s',
  lineHeight: 1,
  padding: 0,
};

const panelContainerStyle = {
  position: 'fixed',
  bottom: 20,
  right: 20,
  width: 380,
  maxWidth: 'calc(100vw - 40px)',
  height: 560,
  maxHeight: 'calc(100vh - 100px)',
  background: '#161b22',
  border: '1px solid #30363d',
  borderRadius: 12,
  boxShadow: '0 8px 40px rgba(0,0,0,0.6)',
  display: 'flex',
  flexDirection: 'column',
  zIndex: 9999,
  overflow: 'hidden',
};

const headerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '14px 16px',
  borderBottom: '1px solid #30363d',
  background: '#0d1117',
  flexShrink: 0,
};

const closeButtonStyle = {
  background: 'none',
  border: 'none',
  color: '#8b949e',
  fontSize: 18,
  cursor: 'pointer',
  padding: '4px 8px',
  lineHeight: 1,
};

const messagesContainerStyle = {
  flex: 1,
  overflowY: 'auto',
  padding: '14px 16px',
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
};

const welcomeStyle = {
  textAlign: 'center',
  color: '#e6edf3',
  padding: '20px 0',
};

const quickActionStyle = {
  padding: '6px 12px',
  fontSize: 12,
  background: '#21262d',
  color: '#c9d1d9',
  border: '1px solid #30363d',
  borderRadius: 16,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};

const userMsgWrap = { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' };
const assistantMsgWrap = { display: 'flex', flexDirection: 'column', alignItems: 'flex-start' };

const userBubbleStyle = {
  maxWidth: '80%',
  background: '#238636',
  color: '#fff',
  borderRadius: '16px 16px 4px 16px',
  padding: '10px 14px',
  fontSize: 14,
  lineHeight: 1.5,
};

const assistantBubbleStyle = {
  maxWidth: '80%',
  background: '#21262d',
  color: '#e6edf3',
  border: '1px solid #30363d',
  borderRadius: '16px 16px 16px 4px',
  padding: '10px 14px',
  fontSize: 14,
  lineHeight: 1.5,
};

const timeStyle = {
  fontSize: 10,
  color: '#484f58',
  marginTop: 2,
  padding: '0 4px',
};

const typingStyle = {
  display: 'inline-block',
  marginTop: 6,
  fontSize: 11,
  color: '#8b949e',
  fontStyle: 'italic',
};

const copyButtonStyle = {
  display: 'inline-block',
  marginTop: 6,
  padding: '3px 8px',
  fontSize: 11,
  background: 'transparent',
  color: '#8b949e',
  border: '1px solid #30363d',
  borderRadius: 4,
  cursor: 'pointer',
};

const typingIndicatorStyle = {
  padding: '10px 14px',
  background: '#21262d',
  border: '1px solid #30363d',
  borderRadius: '16px 16px 16px 4px',
  width: 50,
  textAlign: 'center',
  lineHeight: 1,
};

const retryButtonStyle = {
  marginTop: 6,
  padding: '4px 10px',
  fontSize: 11,
  background: '#da363320',
  color: '#f85149',
  border: '1px solid #f8514940',
  borderRadius: 12,
  cursor: 'pointer',
};

const inputContainerStyle = {
  display: 'flex',
  alignItems: 'flex-end',
  gap: 8,
  padding: '10px 14px',
  borderTop: '1px solid #30363d',
  background: '#0d1117',
  flexShrink: 0,
};

const chatInputStyle = {
  flex: 1,
  background: '#161b22',
  color: '#e6edf3',
  border: '1px solid #30363d',
  borderRadius: 8,
  padding: '10px 12px',
  fontSize: 14,
  fontFamily: 'inherit',
  resize: 'none',
  outline: 'none',
  lineHeight: 1.4,
};

const sendButtonStyle = (disabled) => ({
  width: 38,
  height: 38,
  borderRadius: 19,
  background: disabled ? '#21262d' : '#238636',
  border: 'none',
  color: disabled ? '#484f58' : '#fff',
  fontSize: 18,
  cursor: disabled ? 'default' : 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
});

const chatErrorStyle = {
  padding: '8px 14px',
  background: '#da363320',
  color: '#f85149',
  borderTop: '1px solid #f8514940',
  fontSize: 12,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  flexShrink: 0,
};

const thinkingStyle = {
  padding: '6px 14px',
  background: '#161b22',
  borderTop: '1px solid #30363d',
  fontSize: 12,
  display: 'flex',
  alignItems: 'center',
  flexShrink: 0,
};
