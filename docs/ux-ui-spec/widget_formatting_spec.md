# Chat Widget — Message Formatting & Rendering Spec

**Scope:** Flow AI embedded chat widget (`engine/static/widget.js`)
**Status:** Design complete — ready for implementation
**Date:** 2026-05-07
**Supersedes:** n/a (first formatting spec for this component)

---

## 1. Markdown Rendering Approach

### Recommendation: Inline micro-parser (no external library)

Do not load marked.js or any CDN library. Instead, implement a small, self-contained `parseMarkdown(text)` function inside `widget.js` that handles exactly the subset of Markdown the LLM actually produces. The function returns a safe HTML string that gets assigned via `innerHTML` on agent bubbles only (never on user bubbles).

**Why not marked.js or a CDN library?**
- The widget is designed to be a single self-contained `.js` file with no external dependencies. Adding a CDN `<script>` tag introduces a third-party load dependency that can slow widget initialization, fail in restrictive CSPs, and create a supply-chain risk for every client site that embeds the widget.
- The full Markdown spec is far larger than what the LLM actually produces. Loading a 20 KB+ library to handle six syntax patterns is disproportionate.
- A micro-parser that handles only the observed patterns is under 30 lines of code, fully auditable, and zero-dependency.

**Why not instruct the LLM to return plain text?**
- The LLM is shared across channels. The WhatsApp channel already uses Markdown-style formatting (WhatsApp renders `*bold*` natively). Stripping Markdown from the LLM's output format would degrade the WhatsApp experience or require maintaining two separate prompt variants — a fragile solution.
- Plain-text-only responses lose structural clarity for the user. Structured responses with headers and bullets are genuinely easier to read when rendered correctly.

**Why not a hybrid strip-and-linebreak approach?**
- Stripping asterisks and dashes produces malformed output (e.g., "Our Core Service" instead of a bold heading) without delivering any visual benefit. Users see the degraded content without the formatting payoff.

### Patterns the micro-parser must handle

The parser processes agent message text top-to-bottom, applying transformations in this order:

| Pattern | Input | Output HTML |
|---|---|---|
| Bold | `**text**` | `<strong>text</strong>` |
| Italic | `*text*` (not `**`) | `<em>text</em>` |
| Unordered list item | Line starting with `- ` or `* ` | Collected into `<ul><li>...</li></ul>` |
| Numbered list item | Line starting with `1. `, `2. ` etc. | Collected into `<ol><li>...</li></ol>` |
| Blank line | Empty line between paragraphs | Wraps preceding text block in `<p>` |
| Inline line break | Single `\n` within a paragraph | `<br>` |
| Emoji passthrough | Any Unicode emoji | Rendered as-is (no transformation) |

The parser does NOT handle: tables, code blocks, blockquotes, headings (`#`), horizontal rules, links, or images. If the LLM produces those patterns, they fall through as plain text — acceptable given the current prompt output profile.

### XSS safety rule

Before the micro-parser runs, escape the raw text for HTML special characters: replace `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`, `"` → `&quot;`. Apply escaping first, then apply the markdown pattern transformations. This prevents any user-provided content or LLM-injected HTML from executing in the DOM.

The resulting HTML string is set via `innerHTML` on agent message divs only. User message divs continue to use `textContent` — no change needed there.

---

## 2. Message Bubble Design for Structured Responses

### Agent bubble anatomy

Agent bubbles have a light gray background (`#F3F4F6`) and dark text (`#111111`). When a bubble contains structured content (headers, lists), the internal spacing and typography must communicate hierarchy without making the bubble feel like a webpage dropped into a chat.

```
┌──────────────────────────────────────────────────┐
│ Our Core Service:                                │  ← bold inline header
│                                                  │
│ We deploy an AI agent that handles all your      │
│ inbound WhatsApp conversations 24/7...           │
│                                                  │
│ The agent:                                       │
│   • Answers FAQs automatically                   │  ← <ul> list
│   • Qualifies leads with structured questions    │
│   • Books appointments into your calendar        │
│                                                  │
│ Who We Help:                                     │  ← next bold header
│                                                  │
│ We focus on service businesses — HVAC, wellness, │
│ real estate, insurance...                        │
└──────────────────────────────────────────────────┘
```

### Typography inside agent bubbles

| Element | Style |
|---|---|
| Paragraph text | `font-size: 14px`, `line-height: 1.5`, `color: #111111` |
| `<strong>` (bold) | Same 14px, `font-weight: 600`, no size increase |
| `<em>` (italic) | Same 14px, `font-style: italic` |
| `<p>` block | `margin: 0 0 8px 0`; last `<p>` has `margin-bottom: 0` |
| `<ul>` / `<ol>` | `margin: 4px 0 8px 0`, `padding-left: 18px` |
| `<li>` | `margin-bottom: 4px`, `line-height: 1.5` |

Do not increase font size for bold "header" text. The LLM produces inline bold labels (e.g., `**Our Core Service:**`) not Markdown `#` headings. Making them larger would create a jarring typographic jump in a 14px chat bubble. Weight (`font-weight: 600`) is sufficient to establish visual hierarchy at this scale.

### Bubble width

- **Default max-width:** 85% of the message container width (increased from the current 75%).
  - Rationale: The current 75% cap causes structured responses to reflow into very tall, narrow columns. At 360px widget width with 16px padding on each side (328px usable), 75% max-width gives 246px of text width — roughly 35 characters per line, below the comfortable reading minimum of 45. At 85% (279px) the line length reaches approximately 40–42 characters, which is acceptable for a constrained widget environment.
- **User bubbles:** Remain at 75% max-width. User messages are short; the narrower cap keeps them visually distinct as right-aligned, compact replies.
- **Error and notice bubbles:** Remain at 90% max-width, centered — no change.
- **Do not expand the bubble to 100%.** Full-width bubbles lose the visual distinction between a chat interface and a document. Even for long structured responses, the bubble must feel like a message, not a page.

### List marker style

Use the browser default `disc` marker for `<ul>` and `decimal` for `<ol>`. Do not use custom CSS markers or icon replacements — the goal is readable content, not decoration. The default markers render correctly across all browsers with no additional CSS.

---

## 3. Long Message Handling

### Recommendation: Full message always shown, no truncation, scrolling container only at extreme length

**Decision:** Display the full agent message in every case. Do not implement a "Show more / Show less" toggle.

**Reasoning:**

The chat messages container (`#flowai-messages`) already has `overflow-y: auto` and `flex: 1`. When a long agent message is appended, the container scrolls naturally. The user can read the full response by scrolling within the message panel. The current `scrollTop = scrollHeight` call at the end of `appendMessage` already jumps to the bottom after each message is added, so the user arrives at the end of the response and can scroll up to read it — exactly the same pattern as WhatsApp, iMessage, and every major chat UI.

**Why not "Show more" toggle?**
- It creates an interaction cost for content the user asked for. The agent answered a question — hiding part of that answer behind a tap creates friction without benefit.
- It breaks copy-paste. Users who want to share or save the agent's response cannot select truncated content.
- Implementation complexity: tracking expanded/collapsed state per message bubble adds 30–50 lines of stateful JS for no measurable UX gain.

**Why not scroll within the bubble?**
- A scrollable region inside a scrollable region (bubble inside `#flowai-messages`) creates a scroll-trap on touch devices. The user's finger intends to scroll the message list but instead scrolls inside the bubble — a well-documented mobile UX failure.
- Inner scrolling also hides content depth — the user cannot see at a glance how much content is inside the bubble.

**The one exception — enforce a soft cap via the LLM prompt, not the UI:**
The problem of extremely long responses is better solved at the source. The system prompt for the website chat widget should instruct the LLM to keep responses under approximately 200 words and use structured formatting. This is a prompt engineering concern, not a UI concern. The spec notes this recommendation but does not implement UI-side truncation as a substitute.

### Scroll behavior

After every `appendMessage` call, `messagesDiv.scrollTop = messagesDiv.scrollHeight` scrolls to the bottom. This is the correct behavior. No change needed to the scroll logic.

---

## 4. Typing Indicator

### Recommendation: Add a three-dot animated typing indicator

There is currently no typing indicator in the widget. This is a UX gap. When the user sends a message, there is no visual feedback that the request was received and processing is underway. In testing with LLM-backed chat systems, response latency can range from 1–5 seconds. Without a typing indicator, users frequently send duplicate messages or assume the widget is broken.

### Visual design

The typing indicator appears as an agent bubble containing three dots that animate in sequence:

```
┌─────────────────┐
│  •  •  •        │   ← three dots, pulsing in sequence
└─────────────────┘
```

- Container: same styling as `.flowai-message-agent` — gray background (`#F3F4F6`), 12px border-radius, `padding: 10px 14px`, `align-self: flex-start`
- The three dots are `<span>` elements, each 7px × 7px, `border-radius: 50%`, background `#9CA3AF` (medium gray, not the primary green — the indicator is a system state, not content)
- Dots are arranged with `display: inline-flex`, `gap: 4px`, `align-items: center`
- Animation: CSS keyframe `@keyframes flowai-dot-bounce` — each dot translates upward 4px and back, duration 0.6s ease-in-out, infinite. Dot 2 starts with `animation-delay: 0.15s`, dot 3 with `animation-delay: 0.30s`. This produces the classic sequential bounce effect.
- The indicator uses `aria-label="Agent is typing"` and `role="status"` for screen reader announcement.

### Lifecycle

1. User clicks Send (or presses Enter).
2. Before the `fetch` call begins, call `showTypingIndicator()` — appends the typing bubble with a fixed `id="flowai-typing-indicator"` to `#flowai-messages` and scrolls to bottom.
3. When the `fetch` resolves (success or error), call `hideTypingIndicator()` — removes the element by ID.
4. `appendMessage('agent', ...)` or `appendMessage('error', ...)` is called after hiding the indicator.

This means the indicator is always removed before the real message appears — no overlap.

### Reduced motion

Wrap the animation keyframes in a `@media (prefers-reduced-motion: no-preference)` block. When reduced motion is preferred, the dots are shown statically (no animation) but remain visible so the user still knows processing is underway.

```
@media (prefers-reduced-motion: no-preference) {
  .flowai-typing-dot {
    animation: flowai-dot-bounce 0.6s ease-in-out infinite;
  }
}
```

---

## 5. Additional UX Gaps Identified

The following issues were observed during code review. They are outside the direct scope of the markdown rendering fix but should be addressed in the same implementation pass.

### 5.1 Send button has no disabled state during request

**Current behavior:** The Send button and the input field remain active while a fetch is in-flight. The user can click Send multiple times, queuing multiple identical requests.

**Required behavior:** When `sendMessage` is called:
1. Set `document.getElementById('flowai-send-btn').disabled = true`
2. Set `document.getElementById('flowai-message-input').disabled = true`
3. On fetch resolution (success or error), re-enable both.

**Visual state for disabled Send button:** `opacity: 0.5`, `cursor: not-allowed`. Add this to the CSS for `#flowai-send-btn:disabled`.

### 5.2 Input field has no focus state

**Current behavior:** The message input and prechat form inputs have `border: 1px solid #ddd` in all states. There is no visual difference when the input is focused. This fails WCAG 2.1 SC 1.4.11 (Non-text Contrast) — focus indicators must meet 3:1 contrast against adjacent colors.

**Required behavior:** Add focus styles for `#flowai-message-input:focus` and `#flowai-prechat-form input:focus`:
- `outline: 2px solid #1B5E3F`
- `outline-offset: 0px`
- `border-color: #1B5E3F`

This matches the brand primary and meets contrast requirements (the green `#1B5E3F` against white background is 7.8:1).

### 5.3 Close button has no visible focus indicator

**Current behavior:** `#flowai-widget-close` is a `<button>` styled with `background: transparent` and no outline or focus ring specified. When keyboard-navigated, the focus state is invisible.

**Required behavior:** Add `#flowai-widget-close:focus-visible` with `outline: 2px solid white` and `outline-offset: 2px`. White outline is appropriate here because the button sits on the dark green header background.

### 5.4 Widget launcher button has no accessible label

**Current behavior:** The launcher button (`#flowai-widget-btn`) contains only the emoji `💬` as its content. There is no `aria-label`. Screen readers will announce the emoji character name, not the button's purpose.

**Required behavior:** Add `aria-label="Open chat"` to the launcher button element. When the widget is open, update to `aria-label="Close chat"` via JavaScript in `toggleWidget()`. This provides a meaningful label regardless of the emoji character used.

### 5.5 No aria-live region for new messages

**Current behavior:** When a new agent message appears, there is no programmatic announcement to screen reader users. The user has no way to know a response arrived without manually navigating to the message list.

**Required behavior:** Add `aria-live="polite"` and `aria-atomic="false"` to the `#flowai-messages` div. This tells screen readers to announce new content appended to the container without interrupting what the user is currently hearing. Use `polite` (not `assertive`) — the agent response is important but not an urgent alert.

### 5.6 Prechat form "Start Chat" shows no loading state

**Current behavior:** Clicking "Start Chat" triggers an async `createSession` call. If the server is slow, the button gives no feedback and the user may click it multiple times, creating duplicate sessions.

**Required behavior:** On click:
1. Disable the button immediately (`button.disabled = true`)
2. Change button text to `"Starting..."` 
3. On success or error, re-enable and restore text.

**Visual state:** Same disabled treatment as Send button — `opacity: 0.5`, `cursor: not-allowed`.

### 5.7 Error message for session start uses `alert()`

**Current behavior:** Session creation failure triggers `alert('Failed to start chat. Please try again.')` — a browser-native blocking dialog. This breaks the widget's visual containment, looks unprofessional, and cannot be styled.

**Required behavior:** Replace the `alert()` call with an inline error message rendered inside `#flowai-prechat-form`. Append a `<p>` element with class `flowai-prechat-error` styled as: `color: #C00`, `font-size: 13px`, `margin: 0`. Remove and re-add this element on each attempt (don't accumulate multiple error paragraphs). The error text should read: `"Something went wrong. Please try again."` — consistent with the error message already used in the chat body.

---

## 6. Implementation Checklist

Before marking this work complete, verify:

- [ ] `appendMessage` for role `'agent'` uses `innerHTML` with the output of `parseMarkdown(text)`, not `textContent`
- [ ] `appendMessage` for role `'user'` and `'error'` still uses `textContent` — no change
- [ ] `parseMarkdown` escapes `&`, `<`, `>`, `"` before applying pattern transformations
- [ ] Bold (`**`), unordered lists (`-`), and paragraph breaks render correctly for the sample response in the problem statement
- [ ] Agent bubble max-width updated to 85%
- [ ] CSS added for `p`, `ul`, `ol`, `li`, `strong`, `em` inside `.flowai-message-agent`
- [ ] Typing indicator appears immediately on Send, disappears before agent message renders
- [ ] Typing indicator respects `prefers-reduced-motion`
- [ ] Send button and input are disabled during in-flight requests
- [ ] Focus rings visible on all inputs and the close button
- [ ] Launcher button has `aria-label` that toggles with open/close state
- [ ] `#flowai-messages` has `aria-live="polite"` and `aria-atomic="false"`
- [ ] Session start error uses inline message, not `alert()`
- [ ] Widget tested at 360px viewport width with the sample long response — no horizontal overflow

---

## Appendix: Sample Response Rendering Verification

Use this input to verify the parser implementation produces the correct output:

**Raw LLM output:**
```
Great question! Flow AI is a WhatsApp automation platform built for service businesses in Southeast Asia. Here's what we do: **Our Core Service:** We deploy an AI agent that handles all your inbound WhatsApp conversations 24/7 — directly through your existing WhatsApp Business number. The agent: - Answers FAQs automatically - Qualifies leads with structured discovery questions - Books appointments directly into your calendar - Escalates complex issues to your team with full conversation context - Logs everything in your CRM for follow-up **Who We Help:** We focus on service businesses — HVAC and home services, aesthetics and wellness, real estate, insurance, and similar verticals where WhatsApp is how customers reach you. **The Win:** Instead of your team drowning in repetitive WhatsApp messages, our agent handles the routine stuff 24/7, routes hot leads to you, and frees your team to focus on closing deals and delivering service. **Implementation:** It's typically up and running within days — not months. We handle the setup, training, and ongoing support. Does this sound relevant to what your business is dealing with? Happy to dig deeper into how it could work for you. 😊
```

**Expected rendered output (semantic HTML):**

The parser should produce output equivalent to:

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

Note: The LLM produced this response as a single line with space-separated sections rather than newline-separated paragraphs. The parser must handle both `\n`-delimited and inline `**Header:**` transitions. The recommended approach is to split on `**...**` boundaries as paragraph markers when no newline separator exists — or (preferably) the LLM prompt should be updated to produce `\n\n` between sections, which makes parsing unambiguous and robust.
