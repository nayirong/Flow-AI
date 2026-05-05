# Flow AI Chat Widget — Client Implementation Guide

> For clients with their own development team or Shopify storefront who want to embed the Flow AI chat widget themselves.

---

## What the widget does

The Flow AI chat widget adds a floating chat button to your website. Visitors can start a conversation with your AI agent directly from any page — no app, no phone number required. Conversations are saved so visitors can continue where they left off if they navigate between pages or come back later.

---

## Before you start

You need the following from your Flow AI account manager before embedding the widget:

| Item | Example | Notes |
|---|---|---|
| Widget script URL | `https://web-production-aca15.up.railway.app/widget/your-client-id.js` | Unique to your account |
| Widget enabled | Confirmed by Flow AI | Must be activated on your account first |

Your script URL is always in this format:
```
https://<flow-ai-engine-url>/widget/<your-client-id>.js
```

---

## Embedding on any website

Add one line of HTML before the closing `</body>` tag on every page:

```html
<script src="https://<flow-ai-engine-url>/widget/<your-client-id>.js" async></script>
```

That's it. The widget is fully self-contained — it injects its own styles and HTML. Do not add any extra CSS or JavaScript.

---

## Platform-specific instructions

### Standard HTML websites

Find your shared layout file (often `base.html`, `layout.html`, or `_layout.html`) and add the script tag before `</body>`:

```html
    <!-- Flow AI Chat Widget -->
    <script src="https://<flow-ai-engine-url>/widget/<your-client-id>.js" async></script>
  </body>
</html>
```

---

### WordPress

**Via theme editor (no plugin needed):**

1. Go to **Appearance → Theme File Editor** (or **Theme Editor**)
2. Open `footer.php`
3. Add the script tag just before `</body>`:

```php
    <!-- Flow AI Chat Widget -->
    <script src="https://<flow-ai-engine-url>/widget/<your-client-id>.js" async></script>

<?php wp_footer(); ?>
</body>
```

**Via plugin (recommended if you don't want to edit theme files):**

Install the free **Insert Headers and Footers** plugin, then paste the script tag into the Footer section.

---

### Shopify

1. Go to **Online Store → Themes → Edit Code**
2. Open `Layout → theme.liquid`
3. Find `</body>` at the bottom of the file and add the script tag just before it:

```liquid
    <!-- Flow AI Chat Widget -->
    <script src="https://<flow-ai-engine-url>/widget/<your-client-id>.js" async></script>
  </body>
</html>
```

4. Click **Save**

The widget will appear on every page of your storefront including product pages, collections, cart, and checkout.

---

### Next.js (App Router)

Add the script to your root layout at `app/layout.tsx`:

```tsx
import Script from 'next/script'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Script
          src="https://<flow-ai-engine-url>/widget/<your-client-id>.js"
          strategy="lazyOnload"
        />
      </body>
    </html>
  )
}
```

---

### Next.js (Pages Router)

Add to `pages/_document.tsx`:

```tsx
import { Html, Head, Main, NextScript } from 'next/document'

export default function Document() {
  return (
    <Html>
      <Head />
      <body>
        <Main />
        <NextScript />
        <script
          src="https://<flow-ai-engine-url>/widget/<your-client-id>.js"
          async
        />
      </body>
    </Html>
  )
}
```

---

### Webflow

1. Go to **Project Settings → Custom Code**
2. Paste the script tag into the **Footer Code** section:

```html
<script src="https://<flow-ai-engine-url>/widget/<your-client-id>.js" async></script>
```

3. Publish your site

---

### Wix

1. Go to **Settings → Custom Code**
2. Click **+ Add Custom Code**
3. Paste the script tag, set placement to **Body — end**, apply to **All Pages**
4. Click **Apply**

---

## Customising the widget

Your widget appearance is controlled from the Flow AI dashboard (or by your Flow AI account manager via the client configuration). No code changes are needed.

| Setting | What it does | Default |
|---|---|---|
| **Primary colour** | Button colour, header background, message bubbles | Flow AI green (`#1B5E3F`) |
| **Agent name** | Name shown in the widget header | `Assistant` |
| **Welcome message** | First message shown when a visitor opens the chat | `Hi! How can I help you today?` |
| **Button icon** | Emoji or symbol on the floating button (max 4 characters) | `💬` |
| **Session timeout** | How long before an inactive session expires (minutes) | `30` |

To change any of these, contact your Flow AI account manager. Changes take effect within 5 minutes — no redeployment of your website required.

---

## How visitor sessions work

- When a visitor opens the widget for the first time, a session is created automatically
- The session ID is saved in the visitor's browser (`localStorage`) so they can continue their conversation if they navigate to another page or close and reopen the widget
- Sessions expire after the configured timeout (default: 30 minutes of inactivity)
- If a visitor provides their phone number in the pre-chat form, their widget conversation is linked to their existing customer record (if one exists from a prior WhatsApp interaction)

---

## Pre-chat form

The widget shows an optional pre-chat form before the conversation starts. Visitors can provide:
- Name (optional)
- Email (optional)
- Phone number (optional)

All fields are optional. Visitors can click **Start Chat** without filling anything in. If a phone number is provided and matches an existing customer record, the agent will have context from previous interactions.

---

## Allowed origins (CORS)

For security, the widget only accepts requests from domains that have been explicitly allowlisted for your account. If you embed the widget on a new domain (including a staging/preview URL), contact your Flow AI account manager to add it to your allowlist.

**Common domains to add:**
- Your production domain (e.g. `https://yourstore.com`)
- Your www subdomain (e.g. `https://www.yourstore.com`)
- Your Shopify `.myshopify.com` URL (e.g. `https://yourstore.myshopify.com`)
- Any Vercel/Netlify preview URLs you use for testing

---

## Troubleshooting

**Widget doesn't appear on the page**
- Check the browser console for errors (F12 → Console)
- Confirm the script tag is placed before `</body>`, not in `<head>`
- Confirm the script URL loads in the browser directly — open it in a new tab. You should see JavaScript starting with `window.FLOWAI_CONFIG`

**Widget appears but chat doesn't work**
- Your domain may not be in the allowlist — check the browser console for a CORS error (a red error message containing "Access-Control-Allow-Origin")
- Contact your Flow AI account manager with the exact domain you're embedding on

**Widget appears but shows wrong colours**
- Configuration updates take up to 5 minutes to propagate. Hard refresh the page (Ctrl+Shift+R / Cmd+Shift+R) to clear the browser cache for the widget JS
- If it still shows the wrong colour after 5 minutes, contact your account manager

**Session doesn't persist between pages**
- Confirm the widget script is loading on every page (not just one)
- Confirm your site doesn't clear `localStorage` between page navigations (some single-page app frameworks do this)

---

## Security notes

- The widget communicates with Flow AI servers over HTTPS only
- No visitor data is stored in the browser except the session ID (in `localStorage`)
- The session ID is a random UUID with no personally identifiable information
- Visitor-provided information (name, email, phone) is stored securely in Flow AI's database and is only accessible to your team

---

## Need help?

Contact your Flow AI account manager or email support with:
1. Your client ID
2. The URL of the page where the widget should appear
3. A screenshot or error message from the browser console
