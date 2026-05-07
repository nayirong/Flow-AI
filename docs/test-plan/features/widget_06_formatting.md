# Test Plan: Widget 06 — Message Formatting & Rendering

**Feature:** Chat widget Markdown rendering, typing indicator, accessibility fixes
**Worktree:** `.worktree/widget-06-formatting`
**Branch:** `widget-06-formatting`
**Spec:** `docs/ux-ui-spec/widget_formatting_spec.md`
**File under test:** `engine/static/widget.js` (single file, vanilla JS, no build step)
**Status:** READY FOR IMPLEMENTATION
**Date:** 2026-05-07

---

## 1. Scope

This test plan covers 7 implementation items defined in the UX spec:

1. `parseMarkdown()` micro-parser (XSS-safe, inline, no external libs)
2. Agent bubble max-width 85%, CSS for `p/ul/ol/li/strong/em`
3. Typing indicator (3-dot bounce, reduced-motion, aria, lifecycle)
4. Send button + input disabled during in-flight requests
5. Focus rings on all inputs and close button
6. Launcher `aria-label` toggling with open/close state
7. `aria-live="polite"` on `#flowai-messages`, inline error replacing `alert()`

Regression scope: session restore, prechat form, error handling, existing message rendering.

---

## 2. Test Environment

- Browser: Chrome (primary), Firefox, Safari (secondary)
- Viewport: 360px width (minimum), 768px (desktop)
- Load `widget.js` from a local HTML file or a running dev instance at `http://localhost:8000`
- No build step required — `widget.js` is self-contained

**Setup:**
```bash
# From the worktree
cd .worktree/widget-06-formatting
python -m http.server 8000
# Open a test HTML that embeds widget.js, or use the existing demo page
```

---

## 3. Item 1 — `parseMarkdown()` Parser

### 3.1 Correctness: Spec sample response

**Input:** The raw LLM output from spec Appendix (single-line, space-delimited sections with `**Header:**` markers and `- ` list items).

**Expected output HTML (exact semantic structure):**
```html
<p>Great question! Flow AI is a WhatsApp automation platform built for service businesses in Southeast Asia. Here's what we do: <strong>Our Core Service:</strong> We deploy an AI agent that handles all your inbound WhatsApp conversations 24/7 — directly through your existing WhatsApp Business number. The agent:</p>
<ul>
  <li>Answers FAQs automatically</li>
  <li>Qualifies leads with structured discovery questions</li>
  <li>Books appointments directly into your calendar</li>
  <li>Escalates complex issues to your team with full conversation context</li>
  <li>Logs everything in your CRM for follow-up</li>
</ul>
<p><strong>Who We Help:</strong> We focus on service businesses — HVAC and home services, aesthetics and wellness, real estate, insurance, and similar verticals where WhatsApp is how customers reach you.</p>
<p><strong>The Win:</strong> Instead of your team drowning in repetitive WhatsApp messages, our agent handles the routine stuff 24/7, routes hot leads to you, and frees your team to focus on closing deals and delivering service.</p>
<p><strong>Implementation:</strong> It's typically up and running within days — not months. We handle the setup, training, and ongoing support. Does this sound relevant to what your business is dealing with? Happy to dig deeper into how it could work for you. 😊</p>
```

**Pass criteria:** Inspect the DOM via DevTools. The agent bubble's `innerHTML` must match the above structure. Text content of each `<li>` must be exact. No `**` literal characters visible in rendered output.

### 3.2 Pattern coverage

| Pattern | Input | Expected DOM | Pass |
|---|---|---|---|
| Bold | `**text**` | `<strong>text</strong>` | [ ] |
| Italic | `*text*` | `<em>text</em>` | [ ] |
| Unordered list | Line starting `- item` | `<ul><li>item</li></ul>` | [ ] |
| Numbered list | Line starting `1. item` | `<ol><li>item</li></ol>` | [ ] |
| Paragraph break | Double newline `\n\n` | `<p>...</p><p>...</p>` | [ ] |
| Inline line break | Single `\n` within text | `<br>` | [ ] |
| Emoji passthrough | `😊` anywhere in text | Rendered as-is, no transformation | [ ] |

### 3.3 XSS safety

**Test:** Simulate an LLM response containing HTML injection attempts. Verify the parser escapes these before pattern matching.

| XSS attempt | Expected output |
|---|---|
| `<script>alert(1)</script>` | Renders as literal text `&lt;script&gt;alert(1)&lt;/script&gt;` |
| `"><img src=x onerror=alert(1)>` | Rendered as escaped literal characters |
| `**<b>bold</b>**` | `<strong>&lt;b&gt;bold&lt;/b&gt;</strong>` — inner HTML escaped |
| `&amp;lt;` entity chain | Rendered as literal `&amp;lt;` — no double-decoding |

**Pass criteria:** In all cases, no JavaScript executes. No DOM element is injected. DevTools shows escaped text nodes inside the agent bubble.

### 3.4 User and error bubbles unchanged

- Send a user message. Inspect the DOM — the user bubble must use `textContent` (not `innerHTML`). No Markdown processing applied.
- Trigger an error state. The error bubble must display raw text without HTML parsing.

**Pass criteria:** User bubble `div.innerHTML` equals the raw string with any `<` characters escaped. Error bubble same.

---

## 4. Item 2 — Agent Bubble Width and Typography CSS

### 4.1 Max-width

- Open the widget at 360px viewport width.
- Trigger an agent response with the sample long response.
- Inspect `.flowai-message-agent` in DevTools.

**Pass criteria:**
- `max-width` computed value equals 85% of the container width.
- User bubble computed `max-width` remains at 75%.
- No horizontal overflow (no scrollbar on x-axis, no text clipping).

### 4.2 Typography styles inside agent bubble

Inspect computed styles on elements inside a rendered agent bubble:

| Element | Property | Expected value |
|---|---|---|
| `p` | `margin-bottom` | `8px` (last `<p>` may be `0`) |
| `ul` / `ol` | `padding-left` | `18px` |
| `ul` / `ol` | `margin` | `4px 0 8px 0` |
| `li` | `margin-bottom` | `4px` |
| `li` | `line-height` | `1.5` |
| `strong` | `font-weight` | `600` |
| `strong` | `font-size` | `14px` (same as body — no size increase) |
| `em` | `font-style` | `italic` |

**Pass criteria:** All values match. No style bleeds outside `.flowai-message-agent` (test by placing a `<ul>` outside the agent bubble in the page and confirming its style is unchanged).

---

## 5. Item 3 — Typing Indicator

### 5.1 Lifecycle

1. Click Send with a non-empty message.
2. Immediately inspect `#flowai-messages` — before the response arrives.

**Pass criteria:**
- An element with `id="flowai-typing-indicator"` is present in the DOM.
- It contains three child `<span>` elements with class `flowai-typing-dot`.
- The element has `role="status"` and `aria-label="Agent is typing"`.

3. Wait for the response to arrive.

**Pass criteria:**
- `#flowai-typing-indicator` is removed from the DOM BEFORE the agent message is appended.
- No typing indicator visible alongside the agent response.

### 5.2 Styling

Inspect the typing indicator bubble:

| Property | Expected |
|---|---|
| Background | `#F3F4F6` (same as agent bubble) |
| `border-radius` | `12px` |
| Dot size | `7px × 7px` |
| Dot shape | `border-radius: 50%` |
| Dot color | `#9CA3AF` |
| Gap between dots | `4px` |
| Alignment | `display: inline-flex; align-items: center` |
| Animation | CSS keyframe `flowai-dot-bounce`, sequential delay 0s / 0.15s / 0.30s |

### 5.3 Reduced motion

- Open browser DevTools → Rendering tab → enable "Emulate CSS prefers-reduced-motion: reduce".
- Send a message and observe the typing indicator.

**Pass criteria:**
- Three dots are visible (indicator still shows — it does not disappear).
- Dots are static — no bounce animation playing.
- No JavaScript errors in console.

### 5.4 No duplicate indicators

- Network throttle to "Slow 3G" to keep the request in-flight longer.
- Click Send once. Confirm indicator appears.
- Click Send again (button should be disabled — covered in Item 4). Confirm only one `#flowai-typing-indicator` element exists.

---

## 6. Item 4 — Send Button and Input Disabled State

### 6.1 Disabled during fetch

1. Network throttle to "Slow 3G".
2. Type a message and click Send.
3. While the request is in-flight:

**Pass criteria:**
- `document.getElementById('flowai-send-btn').disabled === true`
- `document.getElementById('flowai-message-input').disabled === true`
- Send button shows `opacity: 0.5` and `cursor: not-allowed` (inspect computed style).

4. Request resolves.

**Pass criteria:**
- Both controls re-enabled immediately after response (or error).
- User can type and send again without refreshing.

### 6.2 No duplicate request

- While request is in-flight, attempt to press Enter in the input field.
- **Pass criteria:** No second request is sent (check Network tab — only one request).

---

## 7. Item 5 — Focus Rings

### 7.1 Message input focus ring

- Click inside `#flowai-message-input`.
- **Pass criteria:** `outline: 2px solid #1B5E3F`, `border-color: #1B5E3F` visible. No browser default focus ring.

### 7.2 Prechat form input focus ring

- Open the widget before session exists (prechat form visible).
- Tab into each prechat form input.
- **Pass criteria:** Same `outline: 2px solid #1B5E3F` visible on each input.

### 7.3 Close button focus ring

- Open the widget.
- Tab to the `#flowai-widget-close` button (keyboard nav).
- **Pass criteria:** `outline: 2px solid white`, `outline-offset: 2px`. Focus indicator clearly visible against the dark green header.

---

## 8. Item 6 — Launcher `aria-label` Toggle

### 8.1 Closed state

- Widget is closed (launcher button visible).
- Inspect `#flowai-widget-btn`.
- **Pass criteria:** `aria-label="Open chat"`.

### 8.2 Open state

- Click the launcher to open the widget.
- Inspect `#flowai-widget-btn`.
- **Pass criteria:** `aria-label="Close chat"`.

### 8.3 Toggle back

- Close the widget by clicking the launcher again.
- **Pass criteria:** `aria-label` reverts to `"Open chat"`.

### 8.4 Close via X button

- Open widget, click `#flowai-widget-close` (the X button inside the widget).
- **Pass criteria:** `#flowai-widget-btn` `aria-label` updates to `"Open chat"`. Both close paths update the label.

---

## 9. Item 7 — `aria-live` Region and Inline Error

### 9.1 `aria-live` on messages container

- Inspect `#flowai-messages` in the DOM before interaction.
- **Pass criteria:** `aria-live="polite"` and `aria-atomic="false"` attributes present.

### 9.2 Screen reader announcement (manual)

- Use VoiceOver (macOS) or NVDA (Windows).
- Send a message and wait for agent response.
- **Pass criteria:** Screen reader announces the new agent message without the user navigating to it manually. Announcement does not interrupt currently reading content (polite, not assertive).

### 9.3 Inline session error replaces `alert()`

- Simulate a session creation failure (disconnect network or point API URL to invalid endpoint).
- Click "Start Chat" in the prechat form.
- **Pass criteria:**
  - No browser `alert()` dialog appears.
  - An inline `<p class="flowai-prechat-error">` appears inside `#flowai-prechat-form` with text `"Something went wrong. Please try again."`.
  - Text color is `#CC0000` (or `#C00`), `font-size: 13px`.
  - Clicking "Start Chat" again removes the old error and shows a fresh one (no accumulation).

---

## 10. Edge Cases

### 10.1 Empty message

- Click Send with an empty `#flowai-message-input`.
- **Pass criteria:** No request is sent. No typing indicator appears. Input remains enabled.

### 10.2 Very long unbroken string

- Send a message with a 200-character word (no spaces).
- **Pass criteria:** User bubble does not overflow the widget width. `overflow-wrap: break-word` or equivalent applies.

### 10.3 Mixed Markdown and plain text

- Trigger an agent response like: `Here is info. **Bold label:** some text. - item one - item two`
- **Pass criteria:** Bold renders, list renders, surrounding plain text wraps in `<p>` tags. No raw `**` or `-` visible.

### 10.4 Parser with no Markdown

- Trigger an agent response that is plain text only (no `**`, no `-`, no `\n`).
- **Pass criteria:** Response renders as a single `<p>` tag. No corruption of the text.

### 10.5 Parser with nested-ish patterns

- Trigger a response with `**bold _and italic_**`.
- **Pass criteria:** Parser produces correct `<strong>bold _and italic_</strong>` — it does NOT need to handle nested italic inside bold (not in spec scope). No crash. Text readable.

### 10.6 Rapid consecutive messages

- Send three messages quickly (while the previous response is still arriving, if possible).
- **Pass criteria:** Each request handled in sequence. No UI state corruption. Typing indicator lifecycle correct for each.

---

## 11. Regression Tests

These behaviors must continue to work after the change.

| Scenario | Verification |
|---|---|
| Session restore on page reload | Reload the page with an existing session cookie. Chat history loads. No errors. |
| Prechat form renders on first visit | Clear cookies. Reload. Prechat form appears before chat UI. |
| Prechat form submits successfully | Fill name/phone, click "Start Chat". Session created. Chat UI appears. |
| User message renders correctly | User messages show as plain text, right-aligned, 75% max-width. |
| Error message for failed agent call | Kill the server mid-conversation. Error message appears inline in chat. No `alert()`. No crash. |
| Widget open/close toggle | Launcher button opens and closes the widget panel. State persists correctly. |
| Session TTL expiry | Let session expire (or manually clear session in Supabase). Widget handles gracefully without infinite loop. |

---

## 12. Verification Sign-off Checklist

Complete this checklist before approving merge. Each item maps to the spec's Section 6 checklist.

- [ ] `appendMessage` for `'agent'` uses `innerHTML` + `parseMarkdown()` output
- [ ] `appendMessage` for `'user'` and `'error'` uses `textContent` — unchanged
- [ ] `parseMarkdown` escapes `&`, `<`, `>`, `"` before pattern transformations
- [ ] Sample response from Appendix renders to expected HTML (verified in DOM)
- [ ] Agent bubble `max-width` is 85%
- [ ] CSS present and correct for `p`, `ul`, `ol`, `li`, `strong`, `em` inside `.flowai-message-agent`
- [ ] Typing indicator appears immediately on Send
- [ ] Typing indicator disappears before agent message renders (no overlap)
- [ ] Typing indicator respects `prefers-reduced-motion` (static dots when reduced motion enabled)
- [ ] Send button disabled during in-flight request; re-enabled on resolve
- [ ] Input field disabled during in-flight request; re-enabled on resolve
- [ ] Focus ring visible on `#flowai-message-input` (green outline, `#1B5E3F`)
- [ ] Focus ring visible on prechat form inputs (green outline, `#1B5E3F`)
- [ ] Focus ring visible on `#flowai-widget-close` (white outline on green header)
- [ ] `#flowai-widget-btn` has `aria-label="Open chat"` when widget is closed
- [ ] `#flowai-widget-btn` has `aria-label="Close chat"` when widget is open
- [ ] `#flowai-messages` has `aria-live="polite"` and `aria-atomic="false"`
- [ ] Session start error uses inline `<p class="flowai-prechat-error">`, not `alert()`
- [ ] Widget renders correctly at 360px viewport width — no horizontal overflow
- [ ] All regression scenarios pass
