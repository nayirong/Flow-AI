# PRD-01: Client Website with CTA Integration

## Product Requirements Document

---

| Field | Value |
|-------|-------|
| **Client** | Aircon Servicing Company (Pilot) |
| **Primary Channel** | WhatsApp (via CTA redirect) |
| **Version** | 1.0 |
| **Date** | April 2026 |
| **Status** | Draft — Pending Review |

---

## 1. Product Overview

The Client Website is the public-facing digital presence for the aircon servicing company. It serves as the primary marketing and lead-capture surface, designed to convert visitors into customers through clear calls-to-action (CTAs) that route them to the AI-powered WhatsApp agent for immediate engagement.

### Scope Note

For the pilot client, the primary conversion path is WhatsApp. The website must make it frictionless for a visitor — especially on mobile — to tap and open a pre-filled WhatsApp conversation with the business.

### 1.1 Goals

- Establish a professional, trust-building online presence for the client
- Drive high-intent visitors to initiate contact via WhatsApp or a lead capture form
- Communicate the service offering clearly to reduce pre-inquiry friction
- Be fast, mobile-first, and SEO-ready for local search discovery
- Serve as a reusable template for future Flow AI clients in similar verticals

### 1.2 Out of Scope

- Online payment processing
- Customer login portal or self-service booking
- Blog or content management beyond a basic service pages
- Multi-language support (Phase 1)

---

## 2. Users & Personas

| Persona | Description | Priority |
|---------|-------------|----------|
| **Prospective Customer** | A homeowner or office manager in Singapore searching for aircon servicing. Mobile-first, likely found via Google or referral. Needs to quickly understand if this business can help them and how to get in touch. | Primary |
| **Returning Customer** | A past customer looking to rebook or check service info. May visit site directly or via WhatsApp link. | Secondary |
| **Business Admin** | The client's staff or owner reviewing the site for accuracy and making minor content updates. | Internal |

---

## 3. Functional Requirements

### 3.1 Pages & Structure

| Page | Requirements |
|------|--------------|
| **Homepage** | Hero section with headline, sub-headline, and primary WhatsApp CTA button; trust signals (years in service, number of units serviced, testimonials); service summary cards; secondary CTA |
| **Services Page** | Detailed listing of all services with descriptions, indicative pricing, and individual CTAs per service type |
| **About Page** | Company story, team introduction, service areas, certifications or accreditations |
| **Contact Page** | Contact form (name, phone, email, service type, message), WhatsApp button, and Google Maps embed for service area |
| **Thank You Page** | Confirmation page after form submission; prompts user to also connect via WhatsApp |
| **Privacy Policy** | PDPA-compliant privacy policy page (required for form submission) |

### 3.2 WhatsApp CTA Integration

This is the most critical functional requirement on the site. The WhatsApp CTA must appear:

- As a sticky floating button on all pages (bottom-right, mobile and desktop)
- As the primary hero CTA button on the homepage
- Inline within each service card on the Services page
- On the Contact page alongside the contact form

#### CTA Behaviour

- On click/tap, the button must open WhatsApp with a pre-filled message
- **Mobile:** opens the WhatsApp app directly via wa.me deep link
- **Desktop:** opens WhatsApp Web or QR code prompt
- The pre-filled message should be contextual, e.g.: "Hi! I'd like to enquire about aircon servicing."
- When a service-specific CTA is clicked, the pre-filled message should reference that service
- A UTM parameter or source tag must be appended to allow tracking of lead source in the CRM

### 3.3 Contact Form

The contact form is a secondary conversion path for users who prefer not to use WhatsApp.

| Field | Specification |
|-------|--------------|
| **Name** | Required — text input |
| **Phone Number** | Required — phone input with +65 prefix |
| **Email** | Optional — email input |
| **Service Type** | Required — dropdown with service options |
| **Preferred Date** | Optional — date picker |
| **Message** | Optional — textarea |
| **PDPA Consent** | Required — checkbox with link to privacy policy |

On submission, the form data must:

- Be sent to a backend webhook (n8n) which creates a lead in the CRM (Product 3)
- Send a confirmation email to the customer (via SendGrid or similar)
- Notify the client admin via email or WhatsApp notification

### 3.4 Trust & Social Proof Elements

- Customer testimonials section (3–5 testimonials with name and suburb)
- Star rating display (Google Reviews badge or static rating)
- Service count or years-in-business badge
- Brand/partner logos if applicable (e.g., Daikin, Mitsubishi authorised)
- Service area map or list of covered HDB estates and condos

### 3.5 SEO Requirements

- Meta title and description for each page
- Structured data markup (LocalBusiness schema) for Google Search
- Google Business Profile integration (embedded map and NAP consistency)
- Page load time under 3 seconds on mobile (Lighthouse score >80)
- Sitemap.xml and robots.txt configured

---

## 4. Non-Functional Requirements

| Requirement | Specification | Priority |
|-------------|----------------|----------|
| **Performance** | Page load < 3s on 4G mobile | Critical |
| **Mobile Responsiveness** | Fully responsive; WhatsApp CTA must be thumb-reachable | Critical |
| **Accessibility** | WCAG 2.1 AA compliance for key elements | High |
| **Analytics** | Google Analytics 4 with conversion event tracking on WhatsApp CTA and form submit | High |
| **Browser Support** | Chrome, Safari, Firefox (latest 2 versions); Samsung Internet | High |
| **Hosting & Uptime** | 99.9% uptime; CDN-served for Singapore latency | High |
| **Security** | HTTPS enforced; form spam protection via reCAPTCHA or Cloudflare Turnstile | High |
| **CMS** | Client can update text, images, pricing without developer access | Medium |

---

## 5. User Stories

### 5.1 Prospective Customer Stories

| ID | User Story |
|----|-----------|
| **US-W-01** | As a customer searching for aircon servicing, I want to quickly find the WhatsApp button so that I can get a quote without filling out a form. |
| **US-W-02** | As a mobile user, I want the WhatsApp button to open the app directly so that I don't have to copy-paste a number. |
| **US-W-03** | As a customer interested in a chemical wash, I want to see the price range and click a service-specific CTA so that my enquiry is pre-contextualised. |
| **US-W-04** | As a customer who prefers email, I want to submit a contact form so that I can be contacted during business hours. |
| **US-W-05** | As a first-time visitor, I want to see reviews and service history so that I can trust this company before reaching out. |

### 5.2 Admin Stories

| ID | User Story |
|----|-----------|
| **US-W-06** | As a business admin, I want to update service descriptions and prices via a CMS so that I don't need to contact a developer for every change. |
| **US-W-07** | As a business owner, I want form submissions to be logged in the CRM automatically so that no lead is missed. |

---

## 6. Design & UX Considerations

### 6.1 Visual Direction

- Clean, professional, and trustworthy aesthetic — light background, strong CTA contrast
- WhatsApp green (#25D366) used for CTA buttons to leverage brand recognition
- Aircon/cooling imagery (e.g. clean units, cool interiors, technicians at work)
- Mobile-first design: all key actions accessible without scrolling on mobile viewport

### 6.2 WhatsApp CTA Design Spec

- **Floating button:** 56px diameter circle, WhatsApp icon, fixed bottom-right, z-index top
- **Pulse animation on load** to draw attention (once, on first visit)
- **On hover/tap:** expands with label text 'Chat with us on WhatsApp'
- **Colour:** #25D366 background with white icon

### 6.3 Content Tone

- Friendly and professional — not corporate or cold
- Local Singapore dialect cues where appropriate (e.g. 'Book a slot lah' as a playful CTA variant)
- Short, scannable copy — most customers are mobile users in a hurry

---

## 7. Technical Specifications

| Component | Specification |
|-----------|----------------|
| **Framework** | Next.js (React) or Webflow for no-code maintenance |
| **Hosting** | Vercel or Netlify with CDN |
| **CMS** | Sanity.io or Contentful for client-editable content |
| **Forms Backend** | n8n webhook receiving form submissions |
| **Analytics** | Google Analytics 4 + Google Tag Manager |
| **WhatsApp Link** | `wa.me/{number}?text={encoded_message}` |
| **UTM Tracking** | Source tags appended to all WhatsApp links for CRM attribution |
| **DNS/Domain** | Client-owned domain; SSL via Let's Encrypt or Vercel |
| **Spam Protection** | Cloudflare Turnstile on contact form |

---

## 8. Acceptance Criteria

| ID | Criterion | Type |
|----|-----------|------|
| **AC-W-01** | WhatsApp CTA visible on all pages without scrolling on 375px viewport | Pass/Fail |
| **AC-W-02** | Tapping WhatsApp CTA on mobile opens WhatsApp app with pre-filled message | Pass/Fail |
| **AC-W-03** | Contact form submits and creates a lead in the CRM within 30 seconds | Pass/Fail |
| **AC-W-04** | Google Lighthouse Performance score >= 80 on mobile | Score |
| **AC-W-05** | All 6 pages are accessible and render correctly on Chrome, Safari, Firefox | Pass/Fail |
| **AC-W-06** | Form submission triggers confirmation email to the customer | Pass/Fail |
| **AC-W-07** | Client admin can update service name and price via CMS without dev access | Pass/Fail |
| **AC-W-08** | PDPA consent checkbox is present and form cannot submit without it | Pass/Fail |

---

## 9. Open Questions

| ID | Question | Owner |
|----|----------|-------|
| **OQ-W-01** | Will the client provide professional photography, or do we source stock images? | Client to confirm |
| **OQ-W-02** | Does the client have an existing domain and hosting, or do we provision? | Client to confirm |
| **OQ-W-03** | Should the site support a blog/news section for future SEO content? | Product decision |
| **OQ-W-04** | What is the exact WhatsApp Business number to use in CTAs? | Client to confirm |
| **OQ-W-05** | Should the contact form submissions notify the client via WhatsApp or email? | Client to confirm |
