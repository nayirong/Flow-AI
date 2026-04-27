# Flow AI — Product Capabilities

> Source of truth for what Flow AI can and cannot do. Agent answers product questions from this file.

---

## What Flow AI Is

Flow AI is an AI agent platform that automates WhatsApp customer conversations for service SMEs in Southeast Asia. The agent handles inbound inquiries 24/7, qualifies leads, takes bookings, and escalates to humans when needed — all through the customer's existing WhatsApp Business number.

---

## Core Capabilities

### 1. 24/7 WhatsApp Automation
- Responds instantly to every inbound message, any time of day
- Handles FAQs, pricing questions, availability checks, and service information
- Maintains conversation context across multiple messages in the same thread

### 2. Lead Qualification
- Asks structured discovery questions to understand customer needs
- Scores leads and routes high-fit prospects to human agents
- Captures low-fit leads in CRM for nurture sequences

### 3. Appointment Booking
- Checks calendar availability and presents open slots to customers
- Writes confirmed bookings directly to the client's system
- Sends booking confirmation via WhatsApp

### 4. Human Escalation
- Hard programmatic gate — agent recognises when to hand off (no LLM decision)
- Sends escalation alert to the human agent's WhatsApp with full context
- Holds the customer with a polite holding message until the human responds
- Human resets the escalation with a simple reply ("done", "resolved")

### 5. CRM Integration
- Every conversation logged as structured data (customer profile, interaction history)
- New customers auto-created; returning customers recognised by phone number
- Booking records written with full details (service, date, time, address)

### 6. Context-Aware Responses
- Business knowledge (services, pricing, policies, hours) stored in database — not hardcoded
- Client can update content directly in Supabase without any code changes
- Agent pulls current knowledge before every response

---

## What Flow AI Is Not (Phase 1)

| Not supported | Why |
|---------------|-----|
| SMS, email, or other channels | WhatsApp-first — Meta Cloud API only |
| Outbound campaigns / broadcast messages | Inbound-only in Phase 1 |
| Voice or video | Text only |
| Custom CRM integrations (Salesforce, HubSpot) | Supabase is the system of record; export/sync is a Phase 2 roadmap item |
| Payment processing | Not in scope |
| Multi-language (non-English) | English primary; basic Singlish understood; full multilingual is roadmap |

---

## Implementation

- **Onboarding timeline:** 4 weeks from signed agreement to live WhatsApp number
- **What the client provides:** WhatsApp Business number + Meta Business account access, business knowledge (services, pricing, hours, policies), human agent's phone number for escalations
- **What Flow AI provides:** Agent setup, knowledge base population, Supabase provisioning, Railway deployment, webhook configuration, testing, handoff training

---

## Technology (what to say if asked)

Flow AI is built on a proprietary Python orchestration engine. The agent uses large language models for natural conversation, with a rules-based layer for booking flows, escalation logic, and safety guardrails. All customer data is stored in isolated, per-client databases. The platform is hosted on Railway with 99.9% uptime SLA.

Do not name the underlying model provider.
