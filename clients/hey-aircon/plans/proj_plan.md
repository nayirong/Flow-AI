# Project Plan Document

## Customer Journey
The ideal customer journey considering full capabilities of product suites. 

### Customer

**#1 Exposure**\
> User learns about heyaircon through multiple channels such as (1) website, (2) Carousell, (3) word of mouth. 

**#2 Leads contact**\
> Customer reaches out to Heyaircon through whatsapp or contact us page. 

**#3 Customer engagement**
> Customer is greeted by AI agent. AI agent proceeds to understand customer intent through a series of questions or available CTAs such as:
> 1. Book services
> 2. What do we do? 
> 3. What do we charge
> 4. Reschedule my bookings
> 5. Other inquiries

> If customer select other inquiries, customer should provide free text, human language form of their inquiry. It could be inquiring about a completed booking, their next recommended servicing date, asking for invoice, etc. 

>  Customer then can engage the AI agent where AI agent can access tools, information and provide basic level services with the customer. However, if customer is not satisfied, agent will escalate to human. 

**#4 Human escalation**
> Upon human escalation, agent will let customer know a human agent will reach out to customer once they are available. 

> Human agent will pick up from where they left off with access to chat history and address human concern. 

**#5.0 Request for booking**\
> If customer request for booking, the AI agent will ask human for their desired appointment time/date, and a few options as well. AI agent will arrange* the best suited time for the customer that they agree upon. Timings must matched availability of the team(s)** and customer, where AI agent can access availability of the team(s) through calendar tool. 

> _**Note that the timing should be in ranges of X hours, where X is tentatively ~2hr period. So if a worker is available betweeen 10AM - 8PM, timeslots will be from 10AM-12PM, 12PM-2PM, 2PM-4PM, 4PM-6PM, 6PM-8PM. This is to accomodate for time between travelling and other miscellaneous activity._

> _***There can be multiple teams in the organisation and AI agent have visibility and can match based on availability of all the teams_

**#5.1 Booking blocked**
> Once booking is confirmed, AI agent will booked the timeslot for the selected team. If timeslot is already taken by other customers while deliberating, AI agent must inform the customer and propose other timeslots. 

> If all goes smoothly and booking is created by AI agent (with timeblocked), AI agent will inform customer of the confirmation. At this point in time, a work order/booking is created for the team (booking ID is generated)

> Booking will include customer information such as name, adress, contact, type of service required, booking timing, service team (only visible to internal team). 

> At this stage, booking status = blocked; it is pending deposit payment from customer. 

> AI Agent will instruct customer to make payment and send screenshot of payment proof. Payment instruction shall be included in the message. 

> ***Despoit amount?***

***Payment policy? Such as requesting customer to make payment within Xhours to hold booking***

**#5.2 Payment confirmation = Booking confirmation**
> Once customer sends a payment confirmation, AI agent shall do first level verification on payment proof (hard feature, good to have) and let customer know a booking confirmation and invoice will be sent to the user in due time. 

> AI agent should inform team members of payment confirmation; where they need to confirm receipt of payment, then mark booking as confirmed. 

> Only when confirmed, the AI agent will send a confirmation message to customer and send an invoice. 

> AI agent can send some message regarding policy such as cancellation policy, no show policy, rescheduling policy. 

**#5.3 Booking reminder**
> X hours (24hrs tentatively, configurable) before booking confirmation, customer shall receive a reminder message of upcoming booking. 

> _Manual Operation_\
> Service team will request for full payment once job is completed. This is not visible to the system and will assume payment is received at the end of the job. 

**#5.4 Post service**
> AI agent will send a message asking for a feedback and rating of their service:
> 1. rate 1-5 on service provided. 
> 2. If rating is 4/5, send a google link to ask for review. And any other promotion the client wants to include in the link. 

**#6 Upsell/cross-sell**\
> Customer can receive periodic message from agent on new promotion, or reminder to service their air-con. 

**#7 Conversion confirmation**\
> Customer who reached out to the agent but drop-off halfway (did not make a booking), agent can reach out 3 days later where X days is configurable, to prompt if they would still like to make any bookings or if they have found something else. 


Key notes:
1. AI agent interacts with custoemr in 2 primary methods.\
\
1.1 AI Agentic Customer Service - When customer reach out to AI agent for inquiry, bookings services. Agent will respond accordingly based on customer needs or escalate to human agent when needed.\
\
1.2 Orchestration workflow - Client can configure when Agents reach out to customer, such as sending reminder messages for upcoming bookings or upselling opportunities. Any subsequent interaction will be in agentic mode. Or configuring agent actions after certain activity is completed, such as booking confirmation/payment made -> send a confirmation message. 

### Client
**#1 - Dashboard**
> Client can access their dashboard to view analytics, reports, bookings, customers info, PnL records, agents configuration, team settings and calendar settings. 

**#2 - View analytics**
> Client can view key metrics of their business.

**#3 - reports**
> Client can view reports related to their business: bookings, transactions, etc. and download in excel.

**#4 -bookings**
> Client can view all bookings record and status

**#5 - Customers info (CRM)**
> Client can view thier customer details, interaction with agents, past bookings, etc. 

**#6 - PnL records**
> client can view their profit/losses by time period

**#7 - agents configuration**
> This is the orchestration workflow - if we're using n8n, then it is not something client can configure, but have to request Flow AI team to help update. 

**#8 - Team settings**
> This is to add team members, and add availability by team. 

**#9 Calendar settings**
> This is to view all bookings and availability of team. 

## Client needs/wants

Derived from the customer and client journeys above, combined with discovery context. To be validated with client.

### Core Pain Points (what they're struggling with today)
1. **Every inquiry is manual.** The owner or admin is personally responding to every WhatsApp message — pricing questions, availability checks, rescheduling requests. This consumes significant time that could be spent on the job.
2. **Leads fall through the gaps.** Without a system, messages received outside business hours or during a busy job are often missed or answered late, causing drop-offs.
3. **Booking coordination is error-prone.** Scheduling is done mentally or through a basic calendar with no safeguards against double-booking or gaps caused by travel time.
4. **No payment structure.** Deposit collection is informal — there is no consistent process to collect payment upfront, leading to no-shows and last-minute cancellations.
5. **No customer history.** There is no centralised record of past customers, what services they had, or when they are due for their next service. Repeat business relies purely on customers reaching out themselves.
6. **Financial visibility is limited.** Revenue, outstanding payments, and job completion rates are not tracked in real time. The owner has no easy way to see how the business is performing.
7. **No professional digital presence.** The business relies on Carousell and word-of-mouth. A proper website with pricing and booking CTA would improve credibility and conversion.

### What the Client Wants (desired outcomes)
1. **"I don't want to be glued to WhatsApp."** — Automate routine conversations so the team can focus on doing the actual work.
2. **"I want to know every lead is followed up."** — No missed inquiries, no delayed replies. The agent should respond instantly, 24/7.
3. **"Bookings should just happen cleanly."** — Customer picks a time, pays the deposit, gets a confirmation. No back-and-forth needed.
4. **"I want to know what I'm owed and what has been paid."** — Simple visibility into revenue, outstanding deposits, and completed jobs.
5. **"Remind customers before their appointment."** — Reduce no-shows with automated reminders.
6. **"Bring customers back."** — Automatically reach out to past customers when they are due for their next service (typically every 3–6 months).
7. **"Make us look professional."** — A clean, credible website that customers can find and trust before reaching out.
8. **"Keep it simple for my team."** — The admin interface should be easy to use; the team is not technical.

### Prioritised Needs (MoSCoW)
| Priority | Need |
|----------|------|
| Must Have | 24/7 WhatsApp agent for inquiry + booking |
| Must Have | Automated deposit payment collection |
| Must Have | Booking confirmation + reminder messages |
| Must Have | Calendar availability management |
| Must Have | Basic customer record (name, contact, address, service history) |
| Should Have | Invoice generation and delivery via WhatsApp |
| Should Have | Dashboard view of bookings and pipeline |
| Should Have | Client website with WhatsApp CTA |
| Could Have | P&L and revenue reporting dashboard |
| Could Have | Automated re-engagement / upsell campaigns |
| Could Have | Google review prompt after job completion |
| Won't Have (now) | Technician mobile app for field updates |
| Won't Have (now) | Multi-location management |


## Ideal Product

A fully integrated, modular platform that automates the end-to-end workflow of an aircon servicing SME — from first customer contact through to invoice and repeat business — while giving the client real-time visibility into their operations.

### Modules

**Module 1 — AI WhatsApp Agent**
The primary customer-facing interface. Handles all inbound and outbound conversations autonomously, escalating to a human only when needed.
- Inbound: inquiry handling (pricing, availability, services), booking flow, payment instruction, rescheduling, FAQs
- Outbound (orchestrated): booking confirmations, payment confirmations, pre-appointment reminders, post-service feedback requests, re-engagement / upsell messages
- Escalation: human handoff with full chat history
- Tools: calendar availability check, CRM read/write, invoice send, booking create/update
- **Knowledge management:** Agent knowledge (services, pricing, policies) is injected at runtime from Google Sheets (`Config` and `Policies` sheets). Client updates content in Sheets — no code changes needed. Built on context engineering principles: system prompt is lean and behavioural; all business data is externally managed and dynamically assembled before each AI call.

**Module 2 — Booking & Calendar Management**
The operational backbone that manages all appointment logistics.
- Team availability by member, with configurable time-slot windows
- Real-time slot locking to prevent double-booking
- Booking status lifecycle: Pending Deposit → Confirmed → Completed → Invoiced
- Multi-team support with job assignment
- Configurable booking notice period and slot duration

**Module 3 — CRM (Customer Relationship Management)**
Centralised record of all customers and their interactions.
- Customer profiles: contact details, address, unit count, aircon brand(s), service history
- Pipeline view: lead stage from first inquiry through to returning customer
- Booking history per customer
- Chat history linked to customer record
- Per-unit service tracking (good to have)

**Module 4 — Sales & Order Management**
Financial and operational record-keeping for completed and in-progress jobs.
- Order records linked to bookings (auto-created by agent)
- Invoice generation and delivery (via WhatsApp or email)
- Payment tracking: deposit paid, balance outstanding, fully settled
- Revenue reporting: by period, service type, and technician
- P&L summary view for business owner
- Excel export

**Module 5 — Campaign & Automation Engine**
Orchestration layer that proactively reaches out to customers based on triggers and schedules.
- Re-engagement campaign: reach out to customers X months after last service
- Upsell campaigns: promote seasonal deals or new services
- Broadcast messages to customer segments
- Configurable triggers and timing (initially managed by Flow AI team via n8n)

**Module 6 — Client Website**
Marketing and lead generation entry point.
- Landing page with service overview, pricing, and testimonials
- Primary CTA: "Book via WhatsApp" button
- SEO-optimised for Singapore aircon servicing searches
- Contact / inquiry form as secondary CTA

**Module 7 — Client Dashboard & Settings**
The unified interface for the business owner and admin to manage everything.
- Analytics overview (bookings, revenue, agent performance)
- Bookings calendar view
- CRM and customer records
- Team member management and availability settings
- Agent configuration (FAQs, service catalogue, business hours)
- Report downloads

> **Phase 1 agent configuration:** In Phase 1, agent content (services, pricing, policies) is managed directly through Google Sheets (`Config` and `Policies` sheets in `HeyAircon CRM`). The client edits these sheets to update what the agent knows — no n8n or code access required. A proper configuration UI is a Phase 6 productisation item.


## Roadmap

Delivery is structured in phases, each adding a meaningful layer of value. Each phase must be functional and usable before the next begins.

| Phase | Timeline | Theme | Key Deliverables |
|-------|----------|-------|------------------|
| Phase 1 — MVP | Weeks 1–4 | Core booking automation | WhatsApp agent (FAQ + full booking flow + payment), calendar availability, booking confirmation + reminder messages, raw data capture to spreadsheet |
| Phase 2 — CRM & Dashboard | Weeks 5–8 | Operational visibility | CRM interface (customer profiles, pipeline, booking history), bookings management dashboard, team & calendar settings UI. **Also:** migrate interaction logging from Sheets to Postgres (DT-001); migrate policy content from Sheets cells to Google Docs (DT-002). |
| Phase 3 — Finance & Invoicing | Weeks 9–11 | Financial operations | Invoice generation and WhatsApp delivery, order management (status lifecycle), payment tracking, revenue reports and Excel export |
| Phase 4 — Campaigns & Upsell | Weeks 12–14 | Growth automation | Re-engagement campaigns, upsell message sequences, Google review prompt post-service, configurable automation triggers |
| Phase 5 — Website | Weeks 13–15 | Online presence | Client website with service pages, pricing, testimonials, WhatsApp CTA, and SEO setup _(can run in parallel with Phase 4)_ |
| Phase 6 — Productisation | Post-pilot | Multi-client platform | See below |

**Phasing rationale:**
- Phase 1 delivers immediate, visible ROI — the client starts saving admin time on day one.
- Phases 2 and 3 convert the agent's actions into a structured business operating system.
- Phase 4 shifts the platform from reactive to proactive — driving repeat revenue.
- Phase 5 is decoupled from agent delivery and can flex in timeline based on client readiness (content, brand assets).
- Phase 6 is triggered when onboarding a new client becomes the bottleneck, not when the first client is fully delivered.

### Phase 6 — Productisation (Multi-client Scale)

**Trigger:** Approaching client 3–4, where manual per-client setup and the absence of self-serve configuration becomes the bottleneck.

**The scalability gap with the MVP architecture:**
Phases 1–5 are built on n8n workflows with client-specific configuration hardcoded in system prompts and workflow nodes. This works for a single client but does not scale:
- Each new client requires a new n8n instance, Railway project, Sheets template, and 360dialog account — all set up manually by the Flow AI team
- Clients cannot self-serve changes to their agent (business hours, pricing, FAQs) without Flow AI team editing workflows
- No central observability across clients (errors, conversation logs, booking metrics are siloed per instance)
- The client dashboard (Module 7) cannot be built on top of n8n — it requires a proper web application

**What Phase 6 builds:**

| Component | Description |
|-----------|-------------|
| Shared multi-tenant backend | PostgreSQL with `client_id` scoping across all data models (bookings, customers, sessions, config). Replaces per-client Google Sheets as the data layer. |
| Client configuration API | Service catalogue, business hours, FAQs, payment details, and agent persona stored in DB per client. System prompt is generated dynamically from config — not hardcoded. |
| Agent runtime migration | The n8n AI Agent + tool pattern is preserved but tools now call the shared backend API instead of per-client Sheets. Session memory migrates from per-instance Postgres to the shared DB. |
| Client onboarding automation | A new client is onboarded by creating a config record in the DB and pointing a new 360dialog webhook to the shared agent runtime — no new n8n instance or Railway project required. |
| Client dashboard (web app) | A lightweight Next.js web app giving each client self-serve access to: agent configuration, bookings view, CRM, and reports. This is the productised version of what n8n workflow editing currently provides. |
| Central observability | Unified logging and error tracking across all clients; Flow AI team can monitor agent performance, conversation quality, and booking health across the entire platform. |

**What stays the same:**
The core agent design pattern — Layer 1 hard-coded pre-checks + Layer 2 AI Agent with tool calling + separate scheduled workflows — is the right architecture and carries forward unchanged. The transition is about where configuration lives (DB instead of hardcoded) and where workflows run (shared runtime instead of per-client n8n instance). Nothing built in Phases 1–5 is thrown away.


### Known Technical Debt (logged during Phase 1 build)

> These are not blockers for Phase 1 but must be addressed in Phase 2. Full details in `mvp_scope.md` → Deferred Technical Items.

| ID | Problem | Impact | Target phase |
|----|---------|--------|-------------|
| DT-001 | Interactions Log is append-only in Google Sheets — will hit storage and performance limits at scale | Sheet becomes slow/unqueryable; 10M cell limit hit within months at moderate volume | Phase 2 — migrate to Postgres |
| DT-002 | Policy content (booking, escalation, cancellation policies) stored in Google Sheets cells — poor editing UX for client | Client editing experience degrades; no version history; limited text length | Phase 2 — migrate to Google Docs |

---

### MVP Scope (Phase 1)

> Full MVP scope, build plan, component breakdown, sprint plan, and pre-build checklist are in [`mvp_scope.md`](mvp_scope.md).

**In Scope (summary)**

| # | Feature | Notes |
|---|---------|-------|
| 1 | WhatsApp AI agent — inbound inquiry handling | Responds to FAQ (pricing, services, availability questions) |
| 2 | WhatsApp AI agent — booking flow | Collects customer details, checks calendar availability, proposes timeslots, confirms appointment |
| 3 | Calendar availability check | Agent queries team calendar in real time to propose accurate timeslots; blocks confirmed slots |
| 4 | Deposit payment instruction | Agent sends payment details after booking is confirmed; waits for screenshot of proof |
| 5 | Basic payment verification | Agent acknowledges payment receipt and notifies admin to confirm (manual admin confirmation for Phase 1) |
| 6 | Booking confirmation message | Confirmation + booking summary sent to customer upon admin sign-off |
| 7 | Pre-appointment reminder | Automated WhatsApp reminder sent 24 hours before appointment (configurable) |
| 8 | Post-service feedback request | Agent sends rating request after job is marked complete; surfaces Google review link for 4–5 star ratings |
| 9 | Human escalation | Agent hands off to human agent when customer requests it or when intent is unresolved; passes full chat history |
| 10 | Out-of-hours handling | Agent acknowledges message, states business hours, and confirms follow-up next working day. Configurable hours and can be turned on/off |
| 11 | Raw data capture | All bookings, customer details, and interactions captured to a structured spreadsheet (Google Sheets) as interim CRM |

**Out of Scope for MVP**
- CRM web interface (spreadsheet is the interim solution)
- Invoice generation (manual for Phase 1)
- Sales reporting dashboard
- Campaign / upsell automation
- Client website
- Technician-facing views

**MVP Success Criteria**
| Metric | Target |
|--------|--------|
| Agent responds to new inquiry | < 10 seconds |
| Booking completed without human touch | > 70% of bookings |
| Inquiry correctly handled without escalation | > 80% |
| No-show rate reduction (vs. baseline) | Measurable reduction with reminders active |
| Admin time saved per week | > 10 hours |
