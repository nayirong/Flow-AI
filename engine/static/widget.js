/**
 * Flow AI Chat Widget — Vanilla JavaScript
 * Self-contained, no dependencies, auto-initializes
 */
(function() {
  'use strict';

  // ── Config ─────────────────────────────────────────────────────────────────
  const _cfg = window.FLOWAI_CONFIG || {};
  const CLIENT_ID = _cfg.clientId || '';
  const SESSION_KEY = 'flowai_session_' + CLIENT_ID;
  const PRIMARY_COLOR = _cfg.primaryColor || '#1B5E3F';
  const BUTTON_ICON = _cfg.buttonIcon || '💬';

  function _darkenColor(hex, pct) {
    const n = parseInt(hex.replace('#', ''), 16);
    const r = Math.max(0, Math.floor((n >> 16) * (1 - pct / 100)));
    const g = Math.max(0, Math.floor(((n >> 8) & 0xff) * (1 - pct / 100)));
    const b = Math.max(0, Math.floor((n & 0xff) * (1 - pct / 100)));
    return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
  }
  const HOVER_COLOR = _darkenColor(PRIMARY_COLOR, 10);

  // Derive base URL from script src
  const _scriptSrc = document.currentScript ? document.currentScript.src : '';
  const BASE_URL = _scriptSrc ? _scriptSrc.replace(/\/widget\/[^/]+\.js.*$/, '') : '';

  let sessionId = null;
  let isOpen = false;

  // ── Styles ─────────────────────────────────────────────────────────────────
  function injectStyles() {
    const style = document.createElement('style');
    style.textContent = `
      #flowai-widget-btn {
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: ${PRIMARY_COLOR};
        color: white;
        font-size: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 9998;
        transition: transform 0.2s;
      }
      #flowai-widget-btn:hover {
        transform: scale(1.05);
      }
      #flowai-widget-window {
        position: fixed;
        bottom: 90px;
        right: 20px;
        width: 360px;
        height: 500px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        z-index: 9999;
        display: flex;
        flex-direction: column;
      }
      #flowai-widget-header {
        background: ${PRIMARY_COLOR};
        color: white;
        padding: 16px;
        border-radius: 12px 12px 0 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      #flowai-widget-title {
        font-weight: 600;
        font-size: 16px;
      }
      #flowai-widget-close {
        background: transparent;
        border: none;
        color: white;
        font-size: 20px;
        cursor: pointer;
        padding: 0;
        width: 24px;
        height: 24px;
      }
      #flowai-widget-close:focus-visible {
        outline: 2px solid white;
        outline-offset: 2px;
      }
      #flowai-prechat-form {
        padding: 24px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      #flowai-prechat-form p {
        margin: 0 0 8px 0;
        font-size: 16px;
        font-weight: 500;
        color: #111;
      }
      #flowai-prechat-form input {
        padding: 10px 12px;
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 14px;
      }
      #flowai-start-chat {
        background: ${PRIMARY_COLOR};
        color: white;
        border: none;
        padding: 12px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        margin-top: 8px;
      }
      #flowai-start-chat:hover {
        background: ${HOVER_COLOR};
      }
      #flowai-start-chat:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      #flowai-chat-body {
        display: flex;
        flex-direction: column;
        flex: 1;
        overflow: hidden;
        min-height: 0;
      }
      #flowai-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        min-height: 0;
        overscroll-behavior: contain;
      }
      .flowai-message {
        max-width: 75%;
        padding: 10px 14px;
        border-radius: 12px;
        font-size: 14px;
        line-height: 1.4;
        word-wrap: break-word;
      }
      .flowai-message-user {
        align-self: flex-end;
        background: ${PRIMARY_COLOR};
        color: white;
      }
      .flowai-message-agent {
        align-self: flex-start;
        background: #F3F4F6;
        color: #111;
        max-width: 85%;
      }
      .flowai-message-agent p {
        margin: 0 0 8px 0;
      }
      .flowai-message-agent p:last-child {
        margin-bottom: 0;
      }
      .flowai-message-agent ul,
      .flowai-message-agent ol {
        margin: 4px 0 8px 0;
        padding-left: 18px;
      }
      .flowai-message-agent li {
        margin-bottom: 4px;
        line-height: 1.5;
      }
      .flowai-message-agent strong {
        font-weight: 600;
      }
      .flowai-message-agent em {
        font-style: italic;
      }
      .flowai-message-error {
        align-self: center;
        background: #FEE;
        color: #C00;
        max-width: 90%;
      }
      .flowai-notice {
        align-self: center;
        background: #FFF3CD;
        color: #856404;
        padding: 10px 14px;
        border-radius: 8px;
        font-size: 13px;
        max-width: 90%;
        text-align: center;
      }
      .flowai-typing-indicator {
        align-self: flex-start;
        background: #F3F4F6;
        color: #111;
        padding: 10px 14px;
        border-radius: 12px;
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .flowai-typing-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #9CA3AF;
        display: inline-block;
      }
      @keyframes flowai-dot-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-4px); }
      }
      @media (prefers-reduced-motion: no-preference) {
        .flowai-typing-dot {
          animation: flowai-dot-bounce 0.6s ease-in-out infinite;
        }
        .flowai-typing-dot:nth-child(2) {
          animation-delay: 0.15s;
        }
        .flowai-typing-dot:nth-child(3) {
          animation-delay: 0.30s;
        }
      }
      #flowai-input-row {
        display: flex;
        gap: 8px;
        padding: 12px;
        border-top: 1px solid #E5E7EB;
      }
      #flowai-message-input {
        flex: 1;
        padding: 10px 12px;
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 14px;
      }
      #flowai-message-input:focus,
      #flowai-prechat-form input:focus {
        outline: 2px solid #1B5E3F;
        outline-offset: 0px;
        border-color: #1B5E3F;
      }
      #flowai-send-btn {
        background: ${PRIMARY_COLOR};
        color: white;
        border: none;
        padding: 10px 16px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
      }
      #flowai-send-btn:hover {
        background: ${HOVER_COLOR};
      }
      #flowai-send-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      @media (max-width: 480px) {
        #flowai-widget-window {
          position: fixed;
          bottom: 0;
          right: 0;
          left: 0;
          top: auto;
          width: 100%;
          height: 100%;
          max-height: 100%;
          border-radius: 0;
          border-top-left-radius: 12px;
          border-top-right-radius: 12px;
          box-sizing: border-box;
        }
        #flowai-widget-btn {
          bottom: calc(20px + env(safe-area-inset-bottom));
          right: 20px;
        }
        #flowai-input-row {
          padding-bottom: calc(12px + env(safe-area-inset-bottom));
        }
        #flowai-message-input,
        #flowai-prechat-form input {
          font-size: 16px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  // ── DOM injection ──────────────────────────────────────────────────────────
  function injectHTML() {
    const container = document.createElement('div');
    container.innerHTML = `
      <div id="flowai-widget-btn" aria-label="Open chat">${BUTTON_ICON}</div>
      <div id="flowai-widget-window" style="display:none">
        <div id="flowai-widget-header">
          <span id="flowai-widget-title">Assistant</span>
          <button id="flowai-widget-close">✕</button>
        </div>
        <div id="flowai-prechat-form">
          <p>How can we help you?</p>
          <input type="text" id="flowai-name" placeholder="Name (optional)" />
          <input type="email" id="flowai-email" placeholder="Email (optional)" />
          <input type="tel" id="flowai-phone" placeholder="Phone (optional)" />
          <button id="flowai-start-chat">Start Chat</button>
        </div>
        <div id="flowai-chat-body" style="display:none">
          <div id="flowai-messages" aria-live="polite" aria-atomic="false"></div>
          <div id="flowai-input-row">
            <input type="text" id="flowai-message-input" placeholder="Type a message..." />
            <button id="flowai-send-btn">Send</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(container);
  }

  // ── Markdown parser ────────────────────────────────────────────────────────
  function parseMarkdown(text) {
    // Step 1: HTML-escape raw input before any transformation
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

    // Step 1.5: Convert inline ✅ section markers into paragraph breaks
    // The LLM uses " ✅ " as a visual section separator on a single line.
    // Splitting here lets the paragraph processor handle each section independently.
    const withSections = escaped.replace(/ ✅ /g, '\n\n✅ ');

    // Step 2: Apply inline formatting transforms to a text segment
    function applyInline(segment) {
      return segment
        // Bold: **text** — must come before italic to avoid partial matches
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // Italic: *text* (single asterisk, not preceded or followed by another asterisk)
        .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    }

    // Step 3: Split on paragraph boundaries (\n\n), then process each paragraph block
    const paragraphBlocks = withSections.split(/\n\n+/);
    const outputParts = [];

    paragraphBlocks.forEach(function(block) {
      if (!block.trim()) return;

      // Split block into individual lines (single \n)
      const lines = block.split('\n');
      const listItems = [];
      const paraLines = [];

      // Helper: flush accumulated paragraph lines as a <p>
      function flushPara() {
        if (paraLines.length === 0) return;
        const content = paraLines.map(applyInline).join('<br>');
        outputParts.push('<p>' + content + '</p>');
        paraLines.length = 0;
      }

      // Helper: flush accumulated list items as a <ul>
      function flushList() {
        if (listItems.length === 0) return;
        const lis = listItems.map(function(item) {
          return '<li>' + applyInline(item.trim()) + '</li>';
        }).join('');
        outputParts.push('<ul>' + lis + '</ul>');
        listItems.length = 0;
      }

      lines.forEach(function(line) {
        // Check for explicit list-item lines (start with "- " or "* ")
        if (/^[-*] /.test(line)) {
          flushPara();
          listItems.push(line.replace(/^[-*] /, ''));
          return;
        }

        // Check for inline bullet segments: line contains " - " but does not start with "- "
        // Split on " - " to extract a leading paragraph segment and trailing list items
        if (line.indexOf(' - ') !== -1) {
          const segments = line.split(' - ');
          // segments[0] is paragraph text; segments[1..n] are list items
          const leadText = segments[0].trim();
          const bulletSegments = segments.slice(1);

          if (leadText) {
            flushList();
            paraLines.push(leadText);
            flushPara();
          }

          bulletSegments.forEach(function(seg) {
            if (seg.trim()) {
              listItems.push(seg.trim());
            }
          });
          return;
        }

        // Plain line — flush any pending list, accumulate as paragraph text
        flushList();
        paraLines.push(line);
      });

      // Flush any remaining accumulated content
      flushList();
      flushPara();
    });

    return outputParts.join('');
  }

  // ── Session management ─────────────────────────────────────────────────────
  async function initSession() {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) {
      const ok = await restoreSession(stored);
      if (!ok) {
        localStorage.removeItem(SESSION_KEY);
        showPrechatForm();
      }
    } else {
      showPrechatForm();
    }
  }

  async function createSession(name, email, phone) {
    const body = {};
    if (name) body.name = name;
    if (email) body.email = email;
    if (phone) body.phone = phone;

    const res = await fetch(`${BASE_URL}/chat/${CLIENT_ID}/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error('Failed to create session');
    return res.json();
  }

  async function restoreSession(sid) {
    try {
      const res = await fetch(`${BASE_URL}/chat/${CLIENT_ID}/history?session_id=${encodeURIComponent(sid)}`, {
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.status === 404 || res.status === 410) return false;
      if (!res.ok) return false;
      const data = await res.json();
      sessionId = sid;
      showChatBody();
      data.messages.forEach(m => appendMessage(m.role === 'user' ? 'user' : 'agent', m.content));
      if (data.escalated) {
        appendNotice('This conversation has been escalated to our team. We\'ll be in touch shortly.');
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  async function sendMessage(text) {
    if (!sessionId || !text.trim()) return;
    appendMessage('user', text);

    const sendBtn = document.getElementById('flowai-send-btn');
    const msgInput = document.getElementById('flowai-message-input');
    sendBtn.disabled = true;
    msgInput.disabled = true;

    showTypingIndicator();

    try {
      const res = await fetch(`${BASE_URL}/chat/${CLIENT_ID}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      if (!res.ok) throw new Error('Request failed');
      const data = await res.json();
      hideTypingIndicator();
      appendMessage('agent', data.reply);
      if (data.escalated) {
        appendNotice('This conversation has been escalated to our team. We\'ll be in touch shortly.');
      }
    } catch (e) {
      hideTypingIndicator();
      appendMessage('error', 'Sorry, something went wrong. Please try again.');
    } finally {
      sendBtn.disabled = false;
      msgInput.disabled = false;
    }
  }

  // ── UI helpers ─────────────────────────────────────────────────────────────
  function appendMessage(role, text) {
    const messagesDiv = document.getElementById('flowai-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'flowai-message flowai-message-' + role;
    if (role === 'agent') {
      msgDiv.innerHTML = parseMarkdown(text);
    } else {
      msgDiv.textContent = text;
    }
    messagesDiv.appendChild(msgDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  function appendNotice(text) {
    const messagesDiv = document.getElementById('flowai-messages');
    const noticeDiv = document.createElement('div');
    noticeDiv.className = 'flowai-notice';
    noticeDiv.textContent = text;
    messagesDiv.appendChild(noticeDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  function showTypingIndicator() {
    const messagesDiv = document.getElementById('flowai-messages');
    const indicator = document.createElement('div');
    indicator.id = 'flowai-typing-indicator';
    indicator.className = 'flowai-typing-indicator';
    indicator.setAttribute('role', 'status');
    indicator.setAttribute('aria-label', 'Agent is typing');
    for (let i = 0; i < 3; i++) {
      const dot = document.createElement('span');
      dot.className = 'flowai-typing-dot';
      indicator.appendChild(dot);
    }
    messagesDiv.appendChild(indicator);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  function hideTypingIndicator() {
    const indicator = document.getElementById('flowai-typing-indicator');
    if (indicator) {
      indicator.parentNode.removeChild(indicator);
    }
  }

  function showPrechatForm() {
    document.getElementById('flowai-prechat-form').style.display = 'flex';
    document.getElementById('flowai-chat-body').style.display = 'none';
  }

  function showChatBody() {
    document.getElementById('flowai-prechat-form').style.display = 'none';
    document.getElementById('flowai-chat-body').style.display = 'flex';
  }

  function toggleWidget() {
    isOpen = !isOpen;
    const widgetWindow = document.getElementById('flowai-widget-window');
    widgetWindow.style.display = isOpen ? 'flex' : 'none';
    const launcherBtn = document.getElementById('flowai-widget-btn');
    launcherBtn.setAttribute('aria-label', isOpen ? 'Close chat' : 'Open chat');
    if (!isOpen) {
      window._flowaiResetViewport && window._flowaiResetViewport();
    }
  }

  // ── Event wiring ───────────────────────────────────────────────────────────
  function wireEvents() {
    document.getElementById('flowai-widget-btn').addEventListener('click', toggleWidget);
    document.getElementById('flowai-widget-close').addEventListener('click', toggleWidget);

    document.getElementById('flowai-start-chat').addEventListener('click', async () => {
      const name = document.getElementById('flowai-name').value;
      const email = document.getElementById('flowai-email').value;
      const phone = document.getElementById('flowai-phone').value;
      const startBtn = document.getElementById('flowai-start-chat');
      const form = document.getElementById('flowai-prechat-form');

      // Clear any previous inline error
      const prevError = form.querySelector('.flowai-prechat-error');
      if (prevError) prevError.parentNode.removeChild(prevError);

      startBtn.disabled = true;
      startBtn.textContent = 'Starting...';

      try {
        const data = await createSession(name, email, phone);
        sessionId = data.session_id;
        localStorage.setItem(SESSION_KEY, sessionId);
        showChatBody();
        if (data.welcome_message) appendMessage('agent', data.welcome_message);
      } catch (e) {
        const errorP = document.createElement('p');
        errorP.className = 'flowai-prechat-error';
        errorP.textContent = 'Something went wrong. Please try again.';
        errorP.style.color = '#C00';
        errorP.style.fontSize = '13px';
        errorP.style.margin = '0';
        form.appendChild(errorP);
      } finally {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Chat';
      }
    });

    document.getElementById('flowai-send-btn').addEventListener('click', () => {
      const input = document.getElementById('flowai-message-input');
      const text = input.value.trim();
      if (text) {
        input.value = '';
        sendMessage(text);
      }
    });

    document.getElementById('flowai-message-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('flowai-send-btn').click();
      }
    });

    preventPageScrollOnFocus(document.getElementById('flowai-message-input'));
    preventPageScrollOnFocus(document.getElementById('flowai-name'));
    preventPageScrollOnFocus(document.getElementById('flowai-email'));
    preventPageScrollOnFocus(document.getElementById('flowai-phone'));
  }

  // ── Focus scroll helper ────────────────────────────────────────────────────
  function preventPageScrollOnFocus(inputElement) {
    if (!inputElement) return;
    inputElement.addEventListener('focus', function(e) {
      // scrollIntoView with block:'nearest' performs zero movement when the element
      // is already visible — the visualViewport listener handles actual repositioning.
      e.target.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
    }, { passive: true });
  }

  // ── Mobile viewport listeners ──────────────────────────────────────────────
  function setupViewportListeners() {
    if (!window.visualViewport) {
      console.warn('[FlowAI] visualViewport API unavailable — mobile keyboard repositioning disabled. Ensure your page uses a standard viewport meta tag.');
    }

    const widgetWindow = document.getElementById('flowai-widget-window');
    if (!widgetWindow) return;

    function isMobile() {
      return window.innerWidth <= 480;
    }

    function onVisualViewportChange() {
      if (!isOpen || !isMobile()) return;
      const vv = window.visualViewport;
      // vv.height = visible height above the keyboard
      // vv.offsetTop = distance from layout viewport top to visual viewport top
      widgetWindow.style.height = vv.height + 'px';
      widgetWindow.style.top = vv.offsetTop + 'px';
      widgetWindow.style.bottom = 'auto';
    }

    function resetWidgetPosition() {
      if (!isMobile()) return;
      // Clear inline overrides — CSS media query takes over
      widgetWindow.style.height = '';
      widgetWindow.style.top = '';
      widgetWindow.style.bottom = '';
    }

    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', onVisualViewportChange);
      window.visualViewport.addEventListener('scroll', onVisualViewportChange);
    } else {
      // Android fallback: window.resize fires when keyboard changes window.innerHeight
      // Only activate when visualViewport is absent to prevent double-handling on modern Android
      var lastInnerHeight = window.innerHeight;
      window.addEventListener('resize', function() {
        if (!isOpen || !isMobile()) return;
        var newHeight = window.innerHeight;
        if (newHeight === lastInnerHeight) return;
        lastInnerHeight = newHeight;
        var ww = document.getElementById('flowai-widget-window');
        if (!ww) return;
        ww.style.height = newHeight + 'px';
        ww.style.top = '0px';
        ww.style.bottom = 'auto';
      });
    }

    // Expose reset so toggleWidget() can clear inline styles on close
    window._flowaiResetViewport = resetWidgetPosition;
  }

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  function init() {
    injectStyles();
    injectHTML();
    wireEvents();
    setupViewportListeners();
    initSession();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
