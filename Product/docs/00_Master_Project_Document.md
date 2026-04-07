# FLOW AI
## Agentic AI Platform for SMEs

### MASTER PROJECT DOCUMENT

---

**Pilot Client:** Aircon Servicing Company  
**Primary Channel:** WhatsApp  
**Version:** 1.0 | April 2026

---

## 1. Executive Summary

Flow AI is a technology company that provides agentic AI solutions to Small and Medium Enterprises (SMEs), enabling them to automate key business workflows — including customer engagement, appointment booking, CRM management, and financial reporting — without the need to hire additional staff.

### Pilot Client Focus
This document covers the initial product build scoped to a Singapore-based aircon servicing company. All customer interactions will be conducted via WhatsApp, making it the primary channel for AI agent engagement.

The Flow AI platform is composed of four modular products delivered to each client:

- **Product 1** — Client Website with CTA Integration
- **Product 2** — AI WhatsApp Chat Agent with CRM Integration
- **Product 3** — CRM Interface
- **Product 4** — Sales Reporting & Order Management Tool

This master document defines the overall system architecture, product philosophy, technical direction, and cross-product dependencies to guide the engineering and product teams through the delivery of the platform.

---

## 2. Company & Product Vision

### 2.1 Mission
2.1 Mission
To empower SMEs with enterprise-grade AI automation tools that are affordable, easy to deploy, and deeply integrated into their day-to-day operations.

### 2.2 Problem Statement

SMEs in service industries such as aircon servicing face a common set of operational challenges:

- High volume of repetitive inbound inquiries (pricing, availability, service types)
- Manual and error-prone booking coordination across phone calls, WhatsApp, and email
- No centralised system to track leads, customers, and order history
- Invoicing handled manually via spreadsheets, leading to delayed payments
- No real-time visibility into revenue, pipeline, or P&L performance

Hiring dedicated staff to manage these tasks is costly and does not scale. Flow AI solves this by deploying a suite of AI-powered tools that automate and manage these workflows autonomously.

### 2.3 Solution Overview
Flow AI delivers a fully integrated, modular platform consisting of a marketing website, an AI-powered WhatsApp agent, a CRM system, and a financial reporting tool — all connected through a shared data layer and unified around the client's business context.

### 2.4 Design Philosophy: Modularity First

The platform is intentionally designed to be modular. This is critical because:

- Core components (AI agent engine, CRM data model, reporting engine) are reusable across all future clients
- Client-specific customisations (service catalogue, pricing, brand identity) are isolated in configuration layers
- Individual products can be updated or replaced independently without breaking the full stack
- New verticals (e.g. cleaning, plumbing, tutoring) can be onboarded by swapping out the context and configuration layer

---

## 3. System Architecture Overview

### 3.1 High-Level Module Map

| Product | Module | Description |
|---------|--------|-------------|
| Product 1 | Client Website | Static/CMS site with CTA widgets directing visitors to WhatsApp or lead form |
| Product 2 | AI WhatsApp Agent | Conversational AI agent handling inquiries, bookings, and order creation via WhatsApp |
| Product 3 | CRM Interface | Web dashboard for managing leads, customers, contacts, and deal pipelines |
| Product 4 | Sales & Reporting | Order management, invoice generation, revenue reporting, and P&L dashboard |

### 3.2 Data Flow Overview
All four products share a unified data layer. The flow of information follows this path:

1. A customer visits the website (Product 1) and initiates contact via WhatsApp or a contact form
2. The WhatsApp AI Agent (Product 2) picks up the conversation, qualifies the lead, captures details, checks calendar availability, and confirms a booking
3. Upon booking confirmation, the customer and order are automatically created in the CRM (Product 3)
4. Once the service is completed, the order is updated and an invoice is generated via the Sales & Reporting tool (Product 4)
5. Revenue data flows into the reporting dashboard for P&L analysis

### 3.3 Modularity & Reusability Matrix

| Component | Type | Notes |
|-----------|------|-------|
| AI Agent Core | Reusable | Prompt framework, tool definitions, context injection — reused for all clients |
| Context Layer | Client-Specific | Services, pricing, FAQs, business hours — configured per client |
| CRM Data Schema | Reusable | Lead, contact, order, and stage models — shared across all clients |
| CRM UI | Reusable | Dashboard interface — reused with minor branding changes |
| Reporting Engine | Reusable | Core reporting logic — shared, with client-specific KPIs configurable |
| Website Template | Semi-Reusable | Base template reused; content, branding, and CTAs are client-specific |
| WhatsApp Channel | Client-Specific | Each client has their own WhatsApp Business account and number |

### 3.4 Technology Stack Recommendations

| Layer | Technology |
|-------|-----------|
| Frontend (Website) | Next.js or Webflow for rapid deployment |
| CRM & Reporting UI | Next.js + React with Tailwind CSS |
| AI Agent Framework | LangChain or custom agent loop with Claude or GPT-4o as base model |
| WhatsApp Integration | WhatsApp Business API via 360dialog or Meta Cloud API |
| Workflow Automation | n8n (self-hosted) for agent tool orchestration and CRM webhooks |
| Database | PostgreSQL (primary), Redis for session state |
| Calendar Integration | Google Calendar API / Calendly API |
| Authentication | Clerk or Supabase Auth for staff dashboard access |
| Hosting | Vercel (frontend), Railway or Render (backend), Supabase (DB) |
| Invoice Generation | PDF generation via Puppeteer or React-PDF |

---

## 4. Pilot Client Context — Aircon Servicing Company

### 4.1 Business Overview
The pilot client is a Singapore-based SME providing residential and commercial aircon services. Their customer base primarily consists of HDB and condo residents, as well as small office tenants. WhatsApp is the dominant communication channel for their customers.

### 4.2 Service Catalogue (Illustrative)

| Service | Description | Price Range (SGD) |
|---------|-------------|-------------------|
| Chemical Wash | Deep cleaning of aircon unit with chemicals | $80 – $120 per unit |
| General Servicing | Filter cleaning, coil inspection, drainage check | $50 – $80 per unit |
| Gas Top-Up | Refrigerant recharge for cooling performance | $80 – $150 per unit |
| Installation | New aircon unit installation | $200 – $400 per unit |
| Repair | Diagnosis and repair of faults | $80 – $250 depending on fault |
| Maintenance Contract | Quarterly servicing package | $300 – $600 per year per unit |

### 4.3 Customer Journey

- Customer sees an ad or visits website → clicks WhatsApp CTA
- AI agent greets customer, asks for service type, unit count, and location
- Agent checks calendar for available slots and proposes appointment times
- Customer confirms slot → booking is created in CRM
- Technician completes the service → admin updates order to 'Completed'
- Invoice is generated and sent to customer via WhatsApp or email
- Customer is moved to 'Returning Customer' stage in CRM

### 4.4 Key Stakeholders

| Role | Responsibilities |
|------|-----------------|
| Business Owner | Reviews reports, approves invoices, monitors pipeline |
| Admin Staff | Manages CRM, updates order status, handles exceptions |
| Technician | Receives job details; status updates may be mobile-facing in future |
| End Customer | Interacts exclusively via WhatsApp for bookings and inquiries |

---

## 5. Cross-Product Dependencies
The four products are independent UIs but share data and events. The following dependencies must be clearly managed:

| Dependency | Description |
|-----------|-------------|
| Product 1 → 2 | Website CTA links customer directly to WhatsApp; lead source is tagged |
| Product 2 → 3 | Agent creates/updates leads and orders in CRM upon booking confirmation |
| Product 2 → 4 | Confirmed bookings generate draft orders in the order management tool |
| Product 3 ↔ 4 | Order records are shared; status updates in Product 4 reflect in Product 3 |
| Product 4 → Client | Invoices generated here are sent to customers; reports exported to Excel |

---

## 6. Phased Delivery Plan

| Phase | Timeline | Deliverables |
|-------|----------|--------------|
| Phase 1 | Weeks 1–3 | Product 1 (Website) + WhatsApp channel setup + basic AI agent (FAQ + lead capture) |
| Phase 2 | Weeks 4–6 | Product 2 full build: booking agent, calendar integration, n8n orchestration |
| Phase 3 | Weeks 7–9 | Product 3: CRM interface with lead pipeline and order history |
| Phase 4 | Weeks 10–12 | Product 4: Order management, invoice generation, sales reporting dashboard |
| Phase 5 | Weeks 13–14 | Integration testing, UAT with client, bug fixes, go-live |

---

## 7. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| WhatsApp API approval delay | HIGH | Apply for Meta Business API access in Week 1; use 360dialog as BSP for faster approval |
| AI agent hallucination | MEDIUM | Strict context engineering; agent only uses provided service catalogue and tools |
| Calendar double-booking | MEDIUM | Real-time availability check before confirming; slot locking mechanism |
| Client adoption resistance | MEDIUM | Hands-on onboarding, simple UI, and WhatsApp-native UX reduces learning curve |
| Data privacy compliance | LOW | All customer data stored in Singapore-region servers; PDPA-compliant data handling |

---

## 8. Success Metrics

| Metric | Definition & Target |
|--------|-------------------|
| Booking Automation Rate | % of bookings completed without human intervention — Target: >70% |
| Lead Response Time | Time from first WhatsApp message to agent response — Target: <10 seconds |
| Agent Accuracy | % of inquiries correctly resolved by agent without escalation — Target: >85% |
| Invoice Generation Time | Time from order completion to invoice sent — Target: <5 minutes |
| Admin Time Saved | Estimated weekly hours saved for the client — Target: >15 hours/week |
| CRM Data Completeness | % of orders with complete customer and order data — Target: >95% |

---

## 9. Document Index

This master document is accompanied by four Product Requirements Documents (PRDs), one per product:

| Document | Title |
|----------|-------|
| PRD-01 | Client Website with CTA Integration |
| PRD-02 | AI WhatsApp Chat Agent with CRM Integration |
| PRD-03 | CRM Interface |
| PRD-04 | Sales Reporting & Order Management Tool |

Each PRD contains: Product Overview, Goals & Success Metrics, User Stories, Functional Requirements, Non-Functional Requirements, UI/UX Considerations, and Technical Specifications.
