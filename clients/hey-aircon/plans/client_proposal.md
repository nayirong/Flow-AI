# Project Proposal & Pricing — HeyAircon
**Prepared by:** Ryan\
**Prepared for:** HeyAircon\
**Date:** April 2026\
**Version:** 2.0

---

## Overview

This document outlines the scope of work, deliverables, and pricing for the AI-powered WhatsApp booking assistant for HeyAircon.

The project is split into two phases. **Phase 1** delivers a fully functional WhatsApp AI agent that handles customer inquiries and new bookings automatically, with human handover for anything complex. **Phase 2** adds payment handling, reminders, and expanded management features.

---

## Phase 1 — WhatsApp AI Agent + Booking System

### What We're Building

An AI assistant that lives on your WhatsApp Business number and handles customer conversations on your behalf — 24/7, automatically.

### What Your Customers Will Experience

- Message your WhatsApp number with a question about your services
- Get an instant, accurate reply — pricing, services, availability
- Book an appointment directly in the chat, without calling or emailing
- Receive a booking confirmation automatically (if there is no existing booking for the selected timeslot)

### What You Get

| # | Deliverable | Description |
|---|-------------|-------------|
| 1 | **AI Inquiry Handling** | The assistant answers common questions about your services, pricing, and company — automatically, in English |
| 2 | **Automated Booking Flow** | Customers can book a service through WhatsApp. The assistant collects all required details (name, address, service type, preferred date and time) |
| 3 | **Live Availability Check** | Before confirming, the assistant checks your Google Calendar in real time to see if the requested slot is free |
| 4 | **Automatic Booking Confirmation** | If the slot is free, a calendar event is created and a confirmation is sent to the customer — no human needed |
| 5 | **Human Handover** | If a slot is taken, or the customer wants to reschedule or cancel, the assistant notifies your team on WhatsApp and holds the customer until you follow up |
| 6 | **Customer Records (Google Sheets)** | Every booking and customer detail is automatically saved to a shared Google Sheet — your interim CRM |
| 7 | **Conversation Memory** | The assistant remembers the context of each customer's conversation, so customers don't have to repeat themselves |

### What Is Not Included in Phase 1

The following features are scoped for Phase 2 and are **not** part of this delivery:

- Payment collection or deposit handling
- Appointment reminders (24h before)
- Post-service feedback requests
- Managing multiple technician calendars
- Customer-facing booking history lookup
- Out-of-hours auto-reply
- Admin commands (CONFIRM, COMPLETE, RESOLVED)

---

## Phase 2 — Enhanced Automation (Future)

> Phase 2 is not yet scheduled. Pricing will be quoted separately once Phase 1 is live.

| # | Feature |
|---|---------|
| 1 | Deposit and payment flow — send payment instructions, receive confirmation |
| 2 | Pre-appointment reminders — automated WhatsApp message 24 hours before |
| 3 | Post-service follow-up — request feedback and Google review |
| 4 | Multi-technician calendar management |
| 5 | Admin commands — mark jobs as confirmed, completed, or resolved via WhatsApp |
| 6 | Customer booking history lookup |
| 7 | Out-of-hours auto-reply |
| 8 | Reporting dashboard and invoicing |

---

## Pricing

### Phase 1 — Two Ways to Pay

We've structured two payment options so you can choose what makes most sense for where your business is right now.

---

#### Option A — Pay-as-You-Grow (Recommended)

Pay a small amount upfront, then only pay more as real bookings come in through the system.

| Milestone | Amount (SGD) |
|-----------|-------------|
| Project kickoff (upon signing) | **$350** |
| Go-live (when system is live and tested) | **$450** |
| Per booking via WhatsApp | **$8 per completed booking** |
| Per-booking cap | Stops once per-booking total reaches **$800 SGD** |
| Cap period | 12 months from go-live (any uncollected remainder is waived) |
| **Maximum total** | **$1,600 SGD** |

> You only pay more when the system is actively generating bookings for you. The per-booking fee is tracked and invoiced monthly.

---

#### Option B — Flat Rate (Simple)

Prefer a clean, predictable number? One fixed price, split across two milestones.

| Milestone | Amount (SGD) |
|-----------|-------------|
| Project kickoff (upon signing) | **$800 (50%)** |
| Go-live / client sign-off | **$800 (50%)** |
| **Total** | **$1,600 SGD** |

---

> **Any work outside the Phase 1 scope above will be discussed and quoted separately before any work begins.**

---

### Monthly Running Costs — Third-Party Services

The system runs on a small set of third-party services (hosting, WhatsApp messaging, AI model usage). Here is how these costs are handled across the project lifecycle:

#### During Build & Stabilisation (Months 1–3)

Flow AI will cover or manage all third-party service accounts during the build and the first 2 months post-launch. This gives the system time to stabilise and ensures a smooth handover without rushing.

| Item | Estimated Monthly Cost (SGD) |
|------|------------------------------|
| Server hosting (Railway) | ~$10–15 |
| WhatsApp messaging fees (Meta) | ~$0–20 (pay-per-conversation, volume dependent) |
| AI model usage (LLM API) | ~$5–15 (usage dependent) |
| **Estimated total** | **~$15–50/month** |

#### After Stabilisation (Month 3 Onwards)

> ⚠️ From Month 3 post-launch, all third-party service accounts and their associated costs will be transferred to and billed directly under HeyAircon's own accounts.

This includes:
- **Railway** — server hosting (~$10–15/month)
- **Meta** — WhatsApp Business messaging fees (~$0–20/month)
- **OpenAI / Anthropic** — AI model API usage (~$5–15/month)

Flow AI will assist with account setup, credentialing, and handover as part of the project delivery. Once transferred, these costs are owned entirely by HeyAircon and are not passed through Flow AI.

> Note: AI API costs can increase with higher conversation volume. We will flag this proactively if usage trends in that direction before the handover.

---

### Optional: Monthly Support Retainer (Post-Launch)

| Tier | Price (SGD/month) | Includes |
|------|------------------|----------|
| Basic | $200 | Monitoring, minor prompt updates, up to 2hrs support |
| Standard | $400 | Monitoring, content updates (pricing/services docs), up to 5hrs support, priority response |

---

## Delivery Timeline

| Week | What Happens |
|------|-------------|
| **Week 1** | System setup, WhatsApp connection, basic message flow live, AI assistant live — answers FAQ, handles inquiries |
| **Week 2** | Booking flow live — checks availability, creates appointments, saves records; Human handover flow live — escalation, notifications; full end-to-end testing |
| **Week 3** | UAT and testing |
| **Week 4 (Buffer)** | Client UAT — you test as a customer; final adjustments |

**Target go-live: 4 weeks from project start.**

> Note: Timeline assumes WhatsApp Business API approval within Week 1. Delays on Meta's end may shift the schedule — this is outside our control but we will manage it proactively.

---

## What We Need From You

To keep the project on schedule, we'll need the following from HeyAircon:

| Item | When Needed | Status |
|------|------------|--------|
| Your final service list and descriptions | Before Week 2 | Pending |
| Your pricing list | Before Week 2 | Pending |
| Your rescheduling and cancellation policy | Before Week 2 | Pending |
| Your business hours and days of operation | Before Week 2 | Pending |
| Access to your Google account (for Calendar + Sheets) | Before Week 3 | Required |
| Your WhatsApp Business number details | Before go-live | Required |
| WhatsApp number for receiving escalation alerts | Before go-live | Required |

> We will begin building with placeholder content immediately and swap in your real content as it is provided. The only hard blockers are your Google account access (needed for Week 3) and your WhatsApp Business number (needed for go-live).

---

## Post-Launch Support

We stand behind what we build. After go-live, the following support is included at no additional charge:

**Duration:** 2 months from the date of go-live sign-off

**What's covered (free of charge):**
- Bug fixes — any system errors or broken functionality that arise after launch
- Missed requirements — anything that was agreed in scope but not delivered correctly
- Feedback-based adjustments — minor tweaks to how the assistant responds, based on real usage (e.g. tone, wording, handling of a specific question type)

**What's not covered under free support:**
- New features or capabilities not in the original Phase 1 scope
- Changes to business information (pricing, services, policies) — these are content updates; billable at hourly rate if required

After the 2-month support period, ongoing help is available via the optional monthly retainer above.

---

## Summary

| | |
|--|--|
| **Option A (Pay-as-you-grow)** | $350 kickoff + $450 go-live + $8/booking (max $1,600 SGD total) |
| **Option B (Flat rate)** | $1,600 SGD (50% on start, 50% on go-live) |
| **Third-party running costs** | Covered by Flow AI during build + first 2 months post-launch; transferred to HeyAircon from Month 3 (~$15–50/month) |
| **Optional monthly retainer** | $200–400/month |
| **Post-launch support** | 2 months free (bug fixes + missed requirements) |
| **Delivery timeline** | 4 weeks from project start |
| **Payment terms** | Any work outside Phase 1 scope quoted separately before proceeding |
