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
      #flowai-chat-body {
        display: flex;
        flex-direction: column;
        flex: 1;
        overflow: hidden;
      }
      #flowai-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
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
    `;
    document.head.appendChild(style);
  }
  
  // ── DOM injection ──────────────────────────────────────────────────────────
  function injectHTML() {
    const container = document.createElement('div');
    container.innerHTML = `
      <div id="flowai-widget-btn">${BUTTON_ICON}</div>
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
          <div id="flowai-messages"></div>
          <div id="flowai-input-row">
            <input type="text" id="flowai-message-input" placeholder="Type a message..." />
            <button id="flowai-send-btn">Send</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(container);
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
    
    try {
      const res = await fetch(`${BASE_URL}/chat/${CLIENT_ID}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
      });
      if (!res.ok) throw new Error('Request failed');
      const data = await res.json();
      appendMessage('agent', data.reply);
      if (data.escalated) {
        appendNotice('This conversation has been escalated to our team. We\'ll be in touch shortly.');
      }
    } catch (e) {
      appendMessage('error', 'Sorry, something went wrong. Please try again.');
    }
  }
  
  // ── UI helpers ─────────────────────────────────────────────────────────────
  function appendMessage(role, text) {
    const messagesDiv = document.getElementById('flowai-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'flowai-message flowai-message-' + role;
    msgDiv.textContent = text;
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
    const window = document.getElementById('flowai-widget-window');
    window.style.display = isOpen ? 'flex' : 'none';
  }
  
  // ── Event wiring ───────────────────────────────────────────────────────────
  function wireEvents() {
    document.getElementById('flowai-widget-btn').addEventListener('click', toggleWidget);
    document.getElementById('flowai-widget-close').addEventListener('click', toggleWidget);
    
    document.getElementById('flowai-start-chat').addEventListener('click', async () => {
      const name = document.getElementById('flowai-name').value;
      const email = document.getElementById('flowai-email').value;
      const phone = document.getElementById('flowai-phone').value;
      try {
        const data = await createSession(name, email, phone);
        sessionId = data.session_id;
        localStorage.setItem(SESSION_KEY, sessionId);
        showChatBody();
        if (data.welcome_message) appendMessage('agent', data.welcome_message);
      } catch (e) {
        alert('Failed to start chat. Please try again.');
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
  }
  
  // ── Bootstrap ──────────────────────────────────────────────────────────────
  function init() {
    injectStyles();
    injectHTML();
    wireEvents();
    initSession();
  }
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  
})();
