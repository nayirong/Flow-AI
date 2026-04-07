# Client Discovery Document
## Flow AI — Product Scoping & Analysis Template

> **Purpose**
> Use this document during client discovery conversations. By the time every section is filled, you should be able to: (1) write the agent's system prompt, (2) define the CRM data model, (3) scope the MVP, and (4) sequence the delivery phases.
>
> 🔴 Not Started · 🟡 In Progress · 🟢 Confirmed | `_____` = needs client input

---

**Client Name:** _____
**Vertical:** _____
**Discovery Date(s):** _____
**Document Owner:** _____
**Status:** 🔴 Not Started

---

## Part A — Business Context
*Just enough to configure the products. Keep this brief.*

> *Status: 🔴 Not Started*

**What does this business do, in one or two sentences?**
_____

**Primary service channel(s):** _(how customers reach them today)_
_____

| Field | Answer |
|-------|--------|
| Operating hours | _____ |
| Days of operation | _____ |
| Public holiday availability | _____ |
| Geographic service area | _____ |
| Average jobs per week | _____ |
| Average job duration (on-site) | _____ |
| Number of staff who will use Flow AI | _____ |

**Service & Pricing Catalogue** _(needed to configure the AI agent context layer)_

| Service / Product | Brief Description | Price or Range | On-site Duration | Notes |
|-------------------|-------------------|---------------|-----------------|-------|
| _____ | _____ | _____ | _____ | _____ |
| _____ | _____ | _____ | _____ | _____ |
| _____ | _____ | _____ | _____ | _____ |

**Does pricing vary by any of the following?**

| Factor | Yes / No | Detail |
|--------|----------|--------|
| Quantity / unit count | _____ | _____ |
| Urgency / same-day | _____ | _____ |
| One-off vs contract | _____ | _____ |
| Other | _____ | _____ |

**Cancellation & rescheduling policy:** _(agent will enforce this in conversation)_
_____

**Languages customers use to communicate:**
_____

---

## Part B — Current Workflow & Pain Points
*This is the most important section. Understand what is broken before deciding what to build.*

> *Status: 🔴 Not Started*

### B1 · As-Is Booking Process
Walk through every step from first customer contact to job completion — including all manual steps.

| Step | What Happens | Who Does It | Tool / Channel Used | Time Taken |
|------|-------------|-------------|--------------------|-----------:|
| 1 | _____ | _____ | _____ | _____ |
| 2 | _____ | _____ | _____ | _____ |
| 3 | _____ | _____ | _____ | _____ |
| 4 | _____ | _____ | _____ | _____ |
| 5 | _____ | _____ | _____ | _____ |
| 6 | _____ | _____ | _____ | _____ |

**Estimated hours per week spent on admin / coordination:**
_____

**Where does the process break down most often?**
_____

**What happens when the business is closed and a customer messages?**
_____

### B2 · Existing Tools
| Category | Tool Currently Used | Keep / Replace / Integrate |
|----------|--------------------|-----------------------------|
| WhatsApp | Personal App / Business App? | _____ |
| Scheduling / calendar | _____ | _____ |
| Customer tracking | _____ | _____ |
| Invoicing | _____ | _____ |
| Payment collection | _____ | _____ |
| Internal comms | _____ | _____ |
| Website (if any) | _____ | _____ |

**Any tools with existing data that needs to migrate?**
_____

### B3 · Key Pain Points
> Rate each pain point: 🔴 Critical · 🟡 Significant · 🟢 Minor

| Pain Point | Severity | Notes |
|------------|----------|-------|
| Slow response to new inquiries | _____ | _____ |
| Manual booking coordination | _____ | _____ |
| No centralised customer records | _____ | _____ |
| Invoicing is slow or manual | _____ | _____ |
| No visibility into revenue / pipeline | _____ | _____ |
| Leads falling through the cracks | _____ | _____ |
| _____ | _____ | _____ |

**In the owner's own words — what is the single biggest problem they want solved?**
_____

---

## Part C — Users & Access
*Drives UX complexity, access model, and which products need to ship on Day 1.*

> *Status: 🔴 Not Started*

| Name | Role | Daily / Occasional | Products They Will Use | Tech Comfort (1–5) |
|------|------|--------------------|------------------------|-------------------|
| _____ | Business Owner | _____ | Reporting (P4), CRM read | _____ |
| _____ | Admin / Operations | _____ | WhatsApp inbox (P2), CRM (P3) | _____ |
| _____ | Technician | _____ | Job view only (future) | _____ |

**Who is the primary daily user of the system?**
_____

**What device will the admin user primarily use?** _(Mobile / Desktop / Both)_
_____

> ⚠️ **Product decision note:** If the admin user is primarily on mobile, all CRM and inbox views must be fully responsive at MVP.

---

## Part D — AI WhatsApp Agent Scope (Product 2)
*The most complex product. This section defines the agent's capabilities, boundaries, and context.*

> *Status: 🔴 Not Started*

### D1 · WhatsApp Channel Setup
| Field | Answer |
|-------|--------|
| Existing WhatsApp Business number? | _____ |
| Number (if existing) | _____ |
| Registered with Meta Business Manager? | _____ |
| Meta Business Suite account exists? | _____ |

> ⚠️ **Action:** Meta API + 360dialog BSP application must be submitted in Week 1. Confirm status immediately.

### D2 · Agent Persona
| Field | Answer |
|-------|--------|
| Agent name | _____ |
| Tone of voice | _____ _(e.g. friendly and direct, professional, conversational)_ |
| Languages to support | _____ |
| Sign-off / closing style | _____ |

### D3 · Conversation Scope
*Define what the agent handles autonomously vs. what escalates to a human. This directly determines MVP complexity.*

| Conversation Type | Handle Autonomously? | Notes / Edge Cases |
|-------------------|---------------------|-------------------|
| Service pricing inquiry | _____ | _____ |
| Availability check | _____ | _____ |
| New booking (full flow) | _____ | _____ |
| Rescheduling existing booking | _____ | _____ |
| Cancellation | _____ | _____ |
| Complaint handling | _____ | _____ |
| Custom / ad-hoc quote | _____ | _____ |
| Repeat customer recognition | _____ | _____ |
| Post-service follow-up | _____ | _____ |
| _____ | _____ | _____ |

**What triggers a handoff to a human?**
_____

**How should escalations be routed?** _(e.g. ping owner's phone, flag in CRM inbox, take a message)_
_____

**Out-of-hours behaviour:**
_____

**Topics or phrasing the agent must never use:**
_____

### D4 · FAQ Bank _(minimum 10 — must be confirmed and worded by client)_

| # | Customer Question | Approved Answer |
|---|-------------------|----------------|
| 1 | _____ | _____ |
| 2 | _____ | _____ |
| 3 | _____ | _____ |
| 4 | _____ | _____ |
| 5 | _____ | _____ |
| 6 | _____ | _____ |
| 7 | _____ | _____ |
| 8 | _____ | _____ |
| 9 | _____ | _____ |
| 10 | _____ | _____ |

### D5 · Booking Confirmation Flow
**What information must be collected before a booking is confirmed?**
_____

**What should the booking confirmation message say?** _(draft or describe)_
_____

**Should a reminder be sent before the appointment? If so, how far in advance?**
_____

---

## Part E — CRM Data Model (Product 3)
*Decisions made here affect the database schema, agent tool definitions, and reporting.*

> *Status: 🔴 Not Started*

### E1 · Pipeline Stages
Define the stages an order moves through from first contact to payment collected.

| Stage # | Stage Name | Who Moves It | Triggered By |
|---------|-----------|-------------|-------------|
| 1 | _____ | _____ | _____ |
| 2 | _____ | _____ | _____ |
| 3 | _____ | _____ | _____ |
| 4 | _____ | _____ | _____ |
| 5 | _____ | _____ | _____ |

### E2 · Data Model Decisions

| Question | Answer | Product Impact |
|----------|--------|---------------|
| Do customers have multiple service addresses? | _____ | Affects Contact schema |
| Do you track individual units (e.g. per aircon unit)? | _____ | Affects Order / Asset schema |
| Can one booking contain multiple services? | _____ | Affects Order line item model |
| Do repeat customers need service history visible to the agent? | _____ | Affects agent tool: `get_customer_history` |
| Are contracts / maintenance packages tracked differently from one-off jobs? | _____ | Affects Order type model |

**Customer record — required fields:**
_____  _(e.g. name, WhatsApp number, email, address, unit count, notes)_

**Order record — required fields:**
_____  _(e.g. service type, date/time, technician assigned, price, status, address)_

### E3 · Access & Notifications
| Role | CRM Access Level | Should they receive notifications? |
|------|-----------------|-------------------------------------|
| Business Owner | Admin / View-only | _____ |
| Admin Staff | Edit | _____ |
| Technician | View job details only | _____ (Day 1 or later phase?) |

---

## Part F — Website Scope (Product 1)
*Typically the fastest product to ship. Define scope to avoid scope creep.*

> *Status: 🔴 Not Started*

### F1 · Assets & Brand
| Field | Answer |
|-------|--------|
| Existing domain? | _____ |
| Domain name (if yes) | _____ |
| Logo available? | _____ |
| Brand colours | _____ |
| Reference websites client likes | _____ |

**Content the client will supply:** _(photos, testimonials, service descriptions — get a deadline)_
_____

### F2 · Page Scope
Mark each page: **In** = build now · **Out** = not needed · **Later** = post-MVP

| Page | Scope | Notes |
|------|-------|-------|
| Home / Landing | _____ | Primary WhatsApp CTA |
| Services & Pricing | _____ | _____ |
| About Us | _____ | _____ |
| FAQ | _____ | _____ |
| Gallery / Before & After | _____ | Requires client photos |
| Testimonials | _____ | _____ |
| Blog / Articles | _____ | _____ |
| Contact / Book Now | _____ | _____ |

**Primary CTA on every page:**
_____  _(expected: "Book via WhatsApp")_

**Does the client want SEO from Day 1, or is it a later concern?**
_____

---

## Part G — Reporting & Invoicing Scope (Product 4)
*Defines the financial data model and what the reporting dashboard must show.*

> *Status: 🔴 Not Started*

### G1 · Invoicing
| Field | Answer | Product Impact |
|-------|--------|---------------|
| GST-registered? | _____ | GST line on invoice template |
| GST number (if yes) | _____ | _____ |
| Invoice delivery method | WhatsApp / Email / Both | _____ |
| Payment methods accepted | _____ | Agent communicates this to customers |
| Payment terms | _____ _(e.g. on-site, 7 days)_ | Invoice due date logic |
| Needs accounting export? | _____ _(Xero / QuickBooks / CSV)_ | Integration requirement |

### G2 · Reports Required
Mark each: **Day 1** · **Nice to Have** · **Not Needed**

| Report | Priority | Notes |
|--------|----------|-------|
| Revenue by day / week / month | _____ | _____ |
| Jobs booked vs completed | _____ | _____ |
| Outstanding / unpaid invoices | _____ | _____ |
| Revenue by service type | _____ | _____ |
| Revenue by technician | _____ | _____ |
| New vs returning customer count | _____ | _____ |
| _____ | _____ | _____ |

**How often does the owner check reports?** _(daily / weekly / monthly)_
_____

---

## Part H — MVP Scope Definition
*Complete this at the end of the discovery conversation. This becomes the source of truth for Phase 1.*

> *Status: 🔴 Not Started*

### H1 · Feature Scope Table
For each feature, assign: **P1** = MVP · **P2** = Phase 2 · **P3** = Future · **Out** = Not building

| Product | Feature | Phase | Rationale |
|---------|---------|-------|-----------|
| **P1 · Website** | Landing page with WhatsApp CTA | _____ | _____ |
| **P1 · Website** | Services & Pricing page | _____ | _____ |
| **P1 · Website** | FAQ page | _____ | _____ |
| **P1 · Website** | Portfolio / Gallery | _____ | _____ |
| **P1 · Website** | SEO setup | _____ | _____ |
| **P2 · WhatsApp Agent** | FAQ + service inquiry responses | _____ | _____ |
| **P2 · WhatsApp Agent** | Full booking flow (availability check → confirm) | _____ | _____ |
| **P2 · WhatsApp Agent** | Rescheduling flow | _____ | _____ |
| **P2 · WhatsApp Agent** | Cancellation flow | _____ | _____ |
| **P2 · WhatsApp Agent** | Repeat customer recognition | _____ | _____ |
| **P2 · WhatsApp Agent** | Post-service follow-up message | _____ | _____ |
| **P2 · WhatsApp Agent** | Human handoff / escalation | _____ | _____ |
| **P3 · CRM** | Lead & order pipeline view | _____ | _____ |
| **P3 · CRM** | Customer profile with history | _____ | _____ |
| **P3 · CRM** | Agent conversation inbox | _____ | _____ |
| **P3 · CRM** | Technician job view | _____ | _____ |
| **P4 · Reporting** | Invoice generation & delivery | _____ | _____ |
| **P4 · Reporting** | Revenue dashboard | _____ | _____ |
| **P4 · Reporting** | Outstanding invoices view | _____ | _____ |
| **P4 · Reporting** | Accounting export | _____ | _____ |

### H2 · MVP Summary Statement
*In plain language, describe what Phase 1 delivers and what success looks like.*

**Phase 1 delivers:**
_____

**Phase 1 is complete when:**
_____

**What is explicitly out of scope for Phase 1:**
_____

---

## Part I — Phase Sequencing
*Translate the scope table into a concrete delivery order.*

> *Status: 🔴 Not Started*

| Phase | Products in Scope | Key Deliverables | Target Duration | Dependencies |
|-------|------------------|-----------------|-----------------|--------------|
| Phase 1 | _____ | _____ | Weeks _____ | _____ |
| Phase 2 | _____ | _____ | Weeks _____ | _____ |
| Phase 3 | _____ | _____ | Weeks _____ | _____ |
| Phase 4 | _____ | _____ | Weeks _____ | _____ |
| Phase 5 (UAT + Go-live) | All | Integration testing, client UAT, bug fixes | Weeks _____ | All phases complete |

**Hard go-live deadline (if any):**
_____

**Peak periods or events that should influence the timeline:**
_____

---

## Part J — Open Questions & Decisions Log
*Log unresolved points here. Each item should be closed before the relevant build phase starts.*

| # | Question | Blocks Which Phase | Owner | Due | Status |
|---|----------|--------------------|-------|-----|--------|
| 1 | _____ | _____ | _____ | _____ | Open |
| 2 | _____ | _____ | _____ | _____ | Open |
| 3 | _____ | _____ | _____ | _____ | Open |

---

## Pre-Build Checklist
*Every item must be ✅ before the corresponding phase begins.*

### Phase 1 Gate (Website + Basic Agent)
- 🔲 Service catalogue with confirmed pricing completed
- 🔲 Operating hours and service area confirmed
- 🔲 Logo, brand colours, and any client content received
- 🔲 Website page scope agreed
- 🔲 WhatsApp Business number confirmed
- 🔲 Meta Business Manager account confirmed — 360dialog application submitted
- 🔲 Agent persona, name, and tone approved by client
- 🔲 FAQ bank (minimum 10) confirmed and client-approved
- 🔲 Escalation and out-of-hours behaviour defined

### Phase 2 Gate (Full Booking Agent)
- 🔲 Booking confirmation flow and required fields agreed
- 🔲 Rescheduling / cancellation policy confirmed and worded for agent
- 🔲 Calendar tool confirmed and API access granted
- 🔲 Appointment reminder behaviour agreed (timing, message content)
- 🔲 Repeat customer handling decision confirmed

### Phase 3 Gate (CRM)
- 🔲 Pipeline stages finalised with exact labels
- 🔲 Customer and order data model fields confirmed
- 🔲 Per-unit / per-address tracking decision made
- 🔲 CRM user roles and access levels defined
- 🔲 Admin user's primary device confirmed (mobile vs desktop)

### Phase 4 Gate (Reporting & Invoicing)
- 🔲 GST registration status confirmed
- 🔲 Invoice template requirements agreed
- 🔲 Payment methods confirmed
- 🔲 Required reports agreed and prioritised
- 🔲 Accounting export requirement confirmed (or ruled out)

### Go-Live Gate
- 🔲 UAT sign-off from client
- 🔲 All open questions resolved
- 🔲 Contract / commercial agreement signed
