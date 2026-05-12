# Test Plan — Widget 07: Mobile Keyboard / Viewport Fix

**Feature:** `engine/static/widget.js` — CSS and JS mobile keyboard/viewport fix  
**Branch:** `widget-07-mobile-keyboard-fix`  
**Spec:** `docs/ux-ui-spec/widget-mobile-fix.md`  
**Date:** 2026-05-12  
**Status:** Active

---

## Success Condition

The chat widget input bar remains visible and accessible when the on-screen keyboard opens on iOS Safari and Android Chrome. The widget does not shift off-screen, clip, or require the user to scroll to reach the input.

**Proof metric:** On a physical iOS device (Safari), tap the message input — the widget repositions upward, the input bar is fully visible above the keyboard, and the message list occupies the remaining space. No host page scroll occurs.

**Proxy metrics (support debugging, do not prove the outcome alone):**
- `setupViewportListeners()` is present in widget.js
- `@media (max-width: 480px)` block is present in `injectStyles()`
- `preventPageScrollOnFocus` is called for all four inputs
- `toggleWidget()` calls `_flowaiResetViewport` on close
- Unit tests pass green

Physical device testing (Section 7 of spec) is required for proof. Unit tests here verify code structure and correctness; they are proxy metrics.

---

## Automated Test Scenarios

### T1 — `@media (max-width: 480px)` block present in widget source

**File:** `engine/tests/unit/test_widget_js.py`  
**Method:** Read `engine/static/widget.js` as text, assert substrings.

| Assertion | Expected |
|---|---|
| `@media (max-width: 480px)` exists | True |
| `bottom: 0` inside media query | True |
| `width: 100%` inside media query | True |
| `height: 100%` inside media query | True |
| `border-radius: 0` inside media query | True |
| `border-top-left-radius: 12px` inside media query | True |
| `env(safe-area-inset-bottom)` used in input-row padding | True |
| `env(safe-area-inset-bottom)` used in launcher btn bottom | True |

### T2 — `min-height: 0` and `overscroll-behavior: contain` added

| Assertion | Expected |
|---|---|
| `min-height: 0` present (at least twice — for `#flowai-messages` and `#flowai-chat-body`) | Count >= 2 |
| `overscroll-behavior: contain` present in widget source | True |

### T3 — `setupViewportListeners` function present

| Assertion | Expected |
|---|---|
| `setupViewportListeners` defined as a function | True |
| `window.visualViewport` existence check present | True |
| `console.warn` with `[FlowAI]` present | True |
| `window._flowaiResetViewport` assignment present | True |
| Android fallback `window.addEventListener('resize'` present | True |
| Guard `!window.visualViewport` before Android fallback | True |

### T4 — `setupViewportListeners()` called from `init()`

| Assertion | Expected |
|---|---|
| `init()` function body contains call to `setupViewportListeners()` | True |

### T5 — `toggleWidget()` calls `_flowaiResetViewport` on close

| Assertion | Expected |
|---|---|
| `_flowaiResetViewport` referenced in `toggleWidget` or near `isOpen` toggle logic | True |

### T6 — `preventPageScrollOnFocus` present and wired

| Assertion | Expected |
|---|---|
| `preventPageScrollOnFocus` function defined | True |
| `scrollIntoView` called inside `preventPageScrollOnFocus` | True |
| `block: 'nearest'` used in `scrollIntoView` call | True |
| `preventPageScrollOnFocus` called for `flowai-message-input` | True |
| `preventPageScrollOnFocus` called for `flowai-name` | True |
| `preventPageScrollOnFocus` called for `flowai-email` | True |
| `preventPageScrollOnFocus` called for `flowai-phone` | True |

### T7 — Desktop layout is unaffected (regression guard)

| Assertion | Expected |
|---|---|
| `width: 360px` still present in desktop styles (outside media query) | True |
| `height: 500px` still present in desktop styles (outside media query) | True |
| `bottom: 90px` still present in desktop `#flowai-widget-window` rule | True |
| `right: 20px` on `#flowai-widget-btn` still present | True |

### T8 — No hardcoded client data introduced

| Assertion | Expected |
|---|---|
| `hey-aircon` not present in `widget.js` | True |
| `HeyAircon` not present in `widget.js` | True |

### T9 — Existing widget JS endpoint tests still pass

All tests in `test_widget_js.py` that existed before this slice must continue to pass without modification.

---

## Manual / Physical Device Checklist

These items cannot be automated. They are required before marking the PR ready to merge.

- [ ] iOS Safari (iPhone, iOS 16+): keyboard opens → widget repositions upward, input visible
- [ ] iOS Safari: keyboard dismisses → widget returns to full-screen
- [ ] iOS Safari: scrolling message list does not cause host page to bounce
- [ ] iOS Safari: home indicator spacing visible below input bar (notched device)
- [ ] iOS Safari: prechat form inputs (Name, Email, Phone) behave same as message input
- [ ] iOS Safari: close widget while keyboard open → reopen → no stale inline styles
- [ ] Android Chrome: keyboard opens → widget height adjusts, input visible
- [ ] Android Chrome: keyboard dismisses → widget returns to full height
- [ ] Desktop Chrome 1280px: widget appears at 360px × 500px, bottom-right, unchanged
- [ ] Browser resize to 480px: widget transitions to full-width mobile layout
- [ ] Browser resize back above 480px: widget returns to desktop layout

---

## Out of Scope

- Python engine files (`api/`, `core/`, `integrations/`) — no changes
- `widget_routes.py` — no changes
- Any other widget slice's behavior — regression tests cover the boundary
