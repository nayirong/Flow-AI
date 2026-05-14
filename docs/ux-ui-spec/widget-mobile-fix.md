# Chat Widget — Mobile Keyboard / Viewport Fix Spec

**Scope:** `engine/static/widget.js` — CSS and JavaScript changes only  
**Status:** Design complete — ready for implementation  
**Date:** 2026-05-12  
**Bug reference:** On iOS and Android, tapping the message input causes the on-screen keyboard to open and the widget window shifts or is pushed off-screen, making the input bar unreachable.

---

## Root Cause Analysis

The widget window (`#flowai-widget-window`) uses `position: fixed; bottom: 90px`. On desktop this works correctly. On mobile, two distinct platform behaviors break it:

**iOS Safari:** When the on-screen keyboard opens, iOS Safari does not resize the layout viewport. Instead, it visually scrolls the visible region upward. `position: fixed` elements are painted relative to the *layout viewport*, which means a widget anchored to `bottom: 90px` of the layout viewport can end up outside the visible area above the keyboard. The Visual Viewport API (`window.visualViewport`) exposes the *actual visible region* and is the correct mechanism for repositioning the widget in response to keyboard appearance.

**Android Chrome:** Android resizes the browser window when the keyboard opens — `window.innerHeight` shrinks by roughly the keyboard height. Because the widget uses `position: fixed` with a static `height: 500px`, the window overflows the reduced viewport height, causing scroll or clipping.

**Neither platform is handled in the current code.** The widget has no `visualViewport` listener, no `resize` handler, and no dynamic height calculation. The fix requires changes in three areas: CSS layout, a Visual Viewport listener (iOS), and a resize listener (Android).

---

## 1. Viewport Meta Tag

### Current state

`widget.js` does not inject a viewport meta tag. The widget relies entirely on the host page's existing `<meta name="viewport">` declaration.

### Required behavior

The widget must NOT inject its own viewport meta tag. Injecting a viewport meta tag from a third-party script risks overwriting the host page's configuration, which can break the host site's layout irreversibly.

Instead, the implementation must document a client-side requirement: the host page must include the standard viewport meta tag:

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

If `initial-scale=1` is absent or overridden (e.g., `user-scalable=no`), the Visual Viewport API still works but the `visualViewport.scale` value will differ from 1. The widget's JS must not assume `scale === 1` — use `visualViewport.offsetTop` and `visualViewport.height` directly without scale math.

The widget JS must add a one-time console warning during initialization if `window.visualViewport` is unavailable, so developers can diagnose the issue:

```js
if (!window.visualViewport) {
  console.warn('[FlowAI] visualViewport API unavailable — mobile keyboard repositioning disabled. Ensure your page uses a standard viewport meta tag.');
}
```

---

## 2. `position: fixed` — The Core Layout Problem

### Current state

```css
#flowai-widget-window {
  position: fixed;
  bottom: 90px;
  right: 20px;
  width: 360px;
  height: 500px;
}

#flowai-widget-btn {
  position: fixed;
  bottom: 20px;
  right: 20px;
}
```

Both elements use `position: fixed` with static `bottom` values and the window has a hardcoded `height: 500px`.

### Required CSS changes

**On screens wider than 480px (desktop/tablet):** No change. Keep `position: fixed`, `bottom: 90px`, `height: 500px`. The keyboard behavior on large-screen browsers is not a problem.

**On screens 480px wide and below (mobile):** The widget must expand to fill nearly the full viewport height and sit flush against the bottom of the visible area. This eliminates the "widget partially off-screen" failure mode and matches the interaction model users expect from mobile chat apps.

Apply these CSS rules inside a media query:

```css
@media (max-width: 480px) {
  #flowai-widget-window {
    position: fixed;
    bottom: 0;
    right: 0;
    left: 0;
    width: 100%;
    height: 100%;
    max-height: 100%;
    border-radius: 0;
    /* Override desktop border-radius */
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
  }

  #flowai-widget-btn {
    /* Keep the launcher button accessible when the widget is closed */
    bottom: calc(20px + env(safe-area-inset-bottom));
    right: 20px;
  }

  #flowai-input-row {
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
  }
}
```

`env(safe-area-inset-bottom)` handles devices with a home indicator bar (iPhone X and later, most modern Android flagships). On devices without a notch or home bar, `env(safe-area-inset-bottom)` resolves to `0px`, so the padding is unchanged.

The `height: 100%` on mobile is the baseline; it is then overridden dynamically by the Visual Viewport listener described in Section 3.

---

## 3. iOS Keyboard — `visualViewport` API

### Current state

No Visual Viewport listener exists anywhere in `widget.js`.

### Required implementation

Add a `setupViewportListeners()` function called from `init()`. The function must:

1. Check for `window.visualViewport` availability. If not present, exit silently (the widget still works on desktop and Android `resize` handles Android separately).
2. Attach a `resize` handler to `window.visualViewport`.
3. In the handler, reposition and resize `#flowai-widget-window` to match the visual viewport exactly.

The Visual Viewport `resize` event fires on both iOS and Android Chrome when the keyboard appears or disappears. The `resize` on `window.visualViewport` is distinct from `window.resize` (which Android also fires) — using both gives correct behavior on both platforms.

**Exact implementation pattern:**

```js
function setupViewportListeners() {
  const widgetWindow = document.getElementById('flowai-widget-window');
  if (!widgetWindow) return;

  // Only activate on mobile widths
  function isMobile() {
    return window.innerWidth <= 480;
  }

  function onVisualViewportChange() {
    if (!isOpen || !isMobile()) return;

    const vv = window.visualViewport;
    // vv.height = visible height above keyboard
    // vv.offsetTop = how far the visual viewport is scrolled from the layout viewport top
    // vv.offsetLeft = horizontal offset (usually 0)

    widgetWindow.style.height = vv.height + 'px';
    widgetWindow.style.top = vv.offsetTop + 'px';
    widgetWindow.style.bottom = 'auto';
    // Reset bottom to 'auto' so top + height controls position exclusively
  }

  function resetWidgetPosition() {
    if (!isMobile()) return;
    // Remove inline overrides — let CSS media query take over
    widgetWindow.style.height = '';
    widgetWindow.style.top = '';
    widgetWindow.style.bottom = '';
  }

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', onVisualViewportChange);
    window.visualViewport.addEventListener('scroll', onVisualViewportChange);
    // scroll fires when the user scrolls inside the keyboard-open state on iOS
  } else {
    console.warn('[FlowAI] visualViewport API unavailable — mobile keyboard repositioning disabled.');
  }

  // Also expose resetWidgetPosition so toggleWidget() can call it on close
  window._flowaiResetViewport = resetWidgetPosition;
}
```

Call `setupViewportListeners()` inside `init()`, after `wireEvents()`.

In `toggleWidget()`, when the widget is closed (`isOpen` becomes `false`), call `window._flowaiResetViewport && window._flowaiResetViewport()` to clean up any inline styles left by the viewport listener.

**Why `visualViewport.scroll` in addition to `resize`:**  
On iOS, when the keyboard is already open and the user scrolls the page behind the widget, `scroll` fires but `resize` does not. Listening to both keeps the widget anchored to the visible area in all scroll/keyboard states.

---

## 4. Android Keyboard — `window.resize`

### Current state

No `window` resize handler exists in `widget.js`.

### Required implementation

Android Chrome does not implement the Visual Viewport API as reliably as iOS Safari (support varies by Android version and browser). The reliable signal on Android is `window.resize` — the browser shrinks `window.innerHeight` when the keyboard opens.

The `visualViewport` `resize` handler above also fires on modern Android Chrome, so devices with the API are covered by Section 3. The `window.resize` fallback handles older Android browsers that lack `window.visualViewport`.

Add this inside `setupViewportListeners()`, after the `visualViewport` block:

```js
// Android fallback: resize window when keyboard changes window.innerHeight
// Only apply if visualViewport is not available (prevents double-handling on modern Android)
if (!window.visualViewport) {
  let lastInnerHeight = window.innerHeight;

  window.addEventListener('resize', function() {
    if (!isOpen || !isMobile()) return;

    const newHeight = window.innerHeight;
    if (newHeight === lastInnerHeight) return;
    lastInnerHeight = newHeight;

    const widgetWindow = document.getElementById('flowai-widget-window');
    if (!widgetWindow) return;

    // Set widget height to match the new (keyboard-reduced) window height
    widgetWindow.style.height = newHeight + 'px';
    widgetWindow.style.top = '0px';
    widgetWindow.style.bottom = 'auto';
  });
}
```

**Why check `!window.visualViewport` before adding the window resize listener:**  
On modern Android Chrome, both `window.visualViewport.resize` and `window.resize` fire when the keyboard opens. If both handlers run, they may conflict (e.g., one sets `top: vv.offsetTop`, the other sets `top: 0`). The guard ensures only one code path runs per device.

---

## 5. Input Focus Scroll Behavior

### Current state

The message input (`#flowai-message-input`) has no `focus` event handler. When the user taps it, the browser's default focus behavior runs — which on some Android devices includes `scrollIntoView`, causing the page behind the widget to scroll unexpectedly.

### Required behavior

Add a `focus` event handler to `#flowai-message-input` and to each prechat form input:

```js
function preventPageScrollOnFocus(inputElement) {
  inputElement.addEventListener('focus', function(e) {
    // preventScroll: true stops the browser from scrolling the host page
    // to bring the input into view — the widget handles positioning itself
    // via the visualViewport listener instead.
    e.target.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
  }, { passive: true });
}
```

Call `preventPageScrollOnFocus` for each input in `wireEvents()`:

```js
preventPageScrollOnFocus(document.getElementById('flowai-message-input'));
preventPageScrollOnFocus(document.getElementById('flowai-name'));
preventPageScrollOnFocus(document.getElementById('flowai-email'));
preventPageScrollOnFocus(document.getElementById('flowai-phone'));
```

**Why `block: 'nearest'` instead of `block: 'center'` or `block: 'start'`:**  
`nearest` scrolls the minimum distance needed to make the element visible. Because the widget repositions itself via `visualViewport`, the input is already visible — `nearest` performs a zero-scroll (no movement), which is the correct outcome.

**Do not use `preventScroll: true` on `.focus()` calls.** `preventScroll: true` is a `focus()` option, not a `scrollIntoView()` option. It prevents scrolling when `.focus()` is called programmatically. For the tap-triggered focus case (the bug scenario), `preventScroll` has no effect because the user, not JS, triggered the focus. The `visualViewport` listener is what prevents the visual displacement.

**`scroll-behavior` CSS property:** Do not set `scroll-behavior: smooth` on `#flowai-messages` or the widget container. Smooth scrolling creates a delay between keyboard appearance and widget repositioning, making the viewport handler feel laggy. Keep the default `scroll-behavior: auto` (or omit the property).

---

## 6. Complete CSS and Layout Change Summary

All changes are additions or targeted overrides. No existing desktop CSS rules are removed.

### 6.1 `#flowai-widget-window` — mobile override

Add inside the `@media (max-width: 480px)` block:

```css
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
```

When the Visual Viewport JS listener fires, it overrides `height` and `top` inline. `bottom: auto` is also set inline by the JS handler. When the widget is closed and the listener resets, these inline values are cleared and the CSS rules above take over again.

### 6.2 `#flowai-messages` — mobile height

The message list uses `flex: 1` inside a flex column. When the widget height is constrained by the visual viewport height, `flex: 1` automatically gives the message list the remaining space after the header and input bar. No additional CSS is required for `#flowai-messages`.

However, add `min-height: 0` to `#flowai-messages` to prevent a common flexbox overflow bug where flex children refuse to shrink below their content size:

```css
#flowai-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0; /* ADD THIS — prevents flex overflow on short viewports */
}
```

Also add `min-height: 0` to `#flowai-chat-body` for the same reason:

```css
#flowai-chat-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  min-height: 0; /* ADD THIS */
}
```

### 6.3 `#flowai-input-row` — safe area inset

```css
@media (max-width: 480px) {
  #flowai-input-row {
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
  }
}
```

This ensures the input bar clears the home indicator bar on notched iPhones and similar devices. When the keyboard is open, the home indicator is hidden and `env(safe-area-inset-bottom)` resolves to 0 — so the extra padding only applies in the closed-keyboard state, which is the correct behavior.

### 6.4 `#flowai-widget-btn` — safe area inset

```css
@media (max-width: 480px) {
  #flowai-widget-btn {
    bottom: calc(20px + env(safe-area-inset-bottom));
  }
}
```

### 6.5 `-webkit-overflow-scrolling` — NOT required

Do not add `-webkit-overflow-scrolling: touch` to `#flowai-messages`. This was a performance hint for momentum scrolling on old iOS (pre-iOS 13). As of iOS 13+, momentum scrolling is the default and the property is a no-op. Adding it introduces dead code.

### 6.6 `overscroll-behavior` on the message list

Add to `#flowai-messages`:

```css
#flowai-messages {
  overscroll-behavior: contain;
}
```

`overscroll-behavior: contain` prevents the rubber-band overscroll from propagating to the host page when the user reaches the top or bottom of the message list. Without this, over-scrolling inside `#flowai-messages` on iOS causes the host page to bounce, which feels broken.

---

## 7. Test Matrix

All tests must be performed on physical devices, not browser DevTools device simulation. DevTools simulates the viewport dimensions but does not replicate the real keyboard appearance behavior.

### 7.1 iOS Safari (iPhone, iOS 16+)

| Test | Steps | Pass criteria |
|---|---|---|
| Widget opens correctly | Tap launcher button | Widget window fills full screen, no horizontal overflow |
| Keyboard appearance | Tap message input | Widget repositions upward; input bar is visible above keyboard; message list shrinks to fill remaining space; no content clipped |
| Keyboard dismissal | Tap "Done" or swipe down keyboard | Widget returns to full-screen position; input bar returns to bottom |
| Message scroll with keyboard open | Send a message; scroll through message history | Scrolling `#flowai-messages` does not cause host page to bounce or scroll |
| Home indicator spacing | Open widget with keyboard closed | Input bar bottom edge has visible clearance above the home indicator bar |
| Prechat form inputs | Tap Name, Email, Phone inputs | Same keyboard appearance behavior as message input; no page scroll |
| Close and reopen | Close widget while keyboard is open; reopen | Widget reopens correctly; no stale inline `top`/`height` styles from previous session |

### 7.2 iOS Chrome (iPhone, iOS 16+)

iOS Chrome uses the same WebKit rendering engine as iOS Safari (Apple App Store requirement). The Visual Viewport behavior is identical to Safari. Run the same test cases as 7.1. The primary difference to check is whether Chrome's additional UI chrome (address bar, tab bar) affects `visualViewport.height` calculations — it should resolve correctly because `visualViewport.height` already accounts for browser chrome.

### 7.3 Android Chrome (Android 10+)

| Test | Steps | Pass criteria |
|---|---|---|
| Widget opens correctly | Tap launcher button | Widget window fills full screen; rounded top corners visible |
| Keyboard appearance | Tap message input | Widget height adjusts; input bar stays visible above keyboard; no content pushed off-screen |
| Keyboard dismissal | Use back button or tap outside keyboard | Widget returns to full viewport height |
| Soft keyboard height variability | Test with GBoard, Samsung Keyboard | Widget repositions correctly regardless of keyboard height (the handler is dynamic, not hardcoded) |
| Home gesture bar | Open widget on phones with gesture navigation | Input bar clears the gesture bar at the bottom |

### 7.4 Android Firefox (secondary — nice to have)

Firefox on Android has its own Gecko engine and does not fire `window.visualViewport.resize` identically to Chrome. Run the keyboard appearance test — if the widget misbehaves, the Android `window.resize` fallback should activate. Verify that the fallback fires and corrects the position.

### 7.5 Regression — Desktop browsers

| Test | Steps | Pass criteria |
|---|---|---|
| Widget at full desktop width | Open in Chrome/Safari desktop at 1280px width | Widget shows at 360px × 500px, bottom-right corner, unchanged from pre-fix behavior |
| Media query boundary | Resize browser to exactly 480px | Widget transitions to full-width mobile layout |
| Resize below 480px | Drag browser window narrower than 480px | Widget switches to mobile layout; no visual artifacts |
| Resize back above 480px | Drag browser window back to 800px+ | Widget returns to 360px × 500px desktop layout |

---

## 8. Files Changed

All changes are confined to `engine/static/widget.js`:

1. `injectStyles()` — add `@media (max-width: 480px)` block with mobile CSS overrides (Sections 2, 6.1, 6.3, 6.4); add `min-height: 0` to `#flowai-messages` and `#flowai-chat-body` (Section 6.2); add `overscroll-behavior: contain` to `#flowai-messages` (Section 6.6)
2. New function `setupViewportListeners()` — Visual Viewport handler (Section 3) + Android fallback (Section 4) + exposes `window._flowaiResetViewport`
3. `wireEvents()` — add `preventPageScrollOnFocus()` calls for all four inputs (Section 5)
4. `init()` — add `setupViewportListeners()` call after `wireEvents()`
5. `toggleWidget()` — call `window._flowaiResetViewport && window._flowaiResetViewport()` when closing

No changes to `api/widget_routes.py`, `api/chat_routes.py`, or any Python file. This is a pure frontend change.

---

## 9. Implementation Checklist

Before marking this work complete, verify every item on the test matrix (Section 7) plus the following code-level checks:

- [ ] `@media (max-width: 480px)` block added to `injectStyles()` with all five property groups (window, input-row, launcher btn)
- [ ] `min-height: 0` added to `#flowai-messages` and `#flowai-chat-body`
- [ ] `overscroll-behavior: contain` added to `#flowai-messages`
- [ ] `env(safe-area-inset-bottom)` used in `#flowai-input-row` and `#flowai-widget-btn` padding/bottom
- [ ] `setupViewportListeners()` added and called from `init()`
- [ ] `window.visualViewport` existence check present before attaching listener
- [ ] Console warning present when `visualViewport` is unavailable
- [ ] Visual Viewport handler sets `height`, `top`, and `bottom: auto` via inline style on `#flowai-widget-window`
- [ ] Android `window.resize` fallback only activates when `!window.visualViewport`
- [ ] `preventPageScrollOnFocus()` called for all four inputs in `wireEvents()`
- [ ] `toggleWidget()` calls `_flowaiResetViewport` on close
- [ ] Widget closes cleanly (no stale inline styles) after keyboard was open
- [ ] Desktop layout (viewport > 480px) is visually unchanged from pre-fix state
- [ ] Tested on physical iOS device (Safari), physical Android device (Chrome)
- [ ] `overscroll-behavior: contain` confirmed — host page does not bounce when scrolling to top/bottom of message list
