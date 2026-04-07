# PRD-02: AI WhatsApp Chat Agent with CRM Integration

## Product Requirements Document

---

| Field | Value |
|-------|-------|
| **Client** | Aircon Servicing Company (Pilot) |
| **Primary Channel** | WhatsApp Business API |
| **Version** | 1.0 |
| **Date** | April 2026 |
| **Status** | Draft — Pending Review |

---

## 1. Product Overview

The AI WhatsApp Chat Agent is the operational core of the Flow AI platform. It is a conversational AI agent deployed on the client's WhatsApp Business number that autonomously handles customer inquiries, qualifies leads, books appointments, and creates orders — 24 hours a day, 7 days a week, without human intervention for routine interactions.

### Key Differentiator

Unlike a simple chatbot with fixed menu trees, this agent uses context engineering and tool-use to have fluid, natural conversations. It has access to the client's service catalogue, real-time calendar availability, and order records — enabling it to answer questions, check slots, and confirm bookings in a single conversation thread.

### 1.1 Goals

- Automate >70% of inbound WhatsApp inquiries without human handoff
- Reduce booking time from an average of 3–5 messages to under 2 minutes
- Automatically create leads and orders in the CRM upon booking confirmation
- Provide a natural, helpful conversational experience that builds customer trust
- Give admin staff full visibility of every conversation thread in a unified inbox

### 1.2 Agent Capabilities Summary

- Answer FAQs about services, pricing, coverage area, and business hours
- Check real-time calendar availability and propose appointment slots
- Capture customer name, phone number, address, and service details
- Confirm bookings and create order records in the CRM
- Handle rescheduling and cancellation requests
- Escalate to human agent when the conversation exceeds agent scope
- Send booking confirmation summary to the customer

---

## 2. Users & Personas

| Persona | Description | Priority |
|---------|-------------|----------|
| **End Customer** | A Singapore resident or office manager who contacts the business via WhatsApp to enquire about or book aircon servicing. Expects fast, friendly, and accurate responses at any time of day. | Primary |
| **Admin / Staff** | The business owner or admin who monitors the conversation inbox, handles escalations, and manually intervenes when needed. Uses the CRM dashboard to view agent-handled threads. | Primary |
| **Flow AI Operator** | Configures the agent context, sets business rules, updates the service catalogue, and monitors agent performance metrics. | Internal |

---

## 3. Conversation Design

### 3.1 Core Conversation Flows

#### Flow 1: Service Inquiry → Booking

| Step | Action |
|------|--------|
| **Step 1** | Customer sends first message (e.g. 'Hi, I want to service my aircon') |
| **Step 2** | Agent greets, confirms intent, asks for service type if not specified |
| **Step 3** | Agent asks for number of units and address/postal code |
| **Step 4** | Agent checks calendar for the next available slots and presents 2–3 options |
| **Step 5** | Customer selects a slot; agent confirms all details and asks for customer name |
| **Step 6** | Agent confirms booking, creates order in CRM, and sends a summary message |
| **Step 7** | Agent thanks customer and closes with a reminder 24 hours before the appointment |

#### Flow 2: General FAQ

- Customer asks about pricing, service types, or coverage → agent retrieves from service context and responds directly
- Customer asks about warranty or guarantees → agent provides standard policy from context
- Customer asks if service is available in a specific area → agent checks service zone list

#### Flow 3: Rescheduling

- Customer references a booking and requests a new date → agent calls `get_booking_details` to retrieve the active order context
- Agent reads rescheduling policy from context — if a fee applies (e.g. same-day or short-notice change), agent informs the customer of the cost implication before proceeding
- Agent calls `check_availability` and proposes 2–3 alternative slots
- Customer confirms → agent calls `reschedule_booking`; if a fee applies, `generate_invoice` is triggered to amend the order cost (Phase 2)
- Orchestration layer sends booking confirmation message to the customer

#### Flow 4: Human Escalation

- Customer uses keywords like 'urgent', 'problem', 'complaint', or 'speak to someone'
- Agent informs customer a staff member will follow up and tags conversation as 'Escalated' in CRM
- Admin receives a notification in the CRM inbox with full conversation context

### 3.2 Agent Tone & Style Guidelines

- Friendly, professional, and efficient — responds in the same language as the customer (English, with basic Mandarin support if needed)
- Messages should be short (1–4 sentences max) — this is WhatsApp, not email
- Use simple formatting: line breaks, not markdown headers or bold text
- Never fabricate information not present in the context — say 'I'm not sure, let me check' and escalate if needed
- Always confirm bookings with a full summary before closing the conversation

### 3.3 Out-of-Scope Triggers (Escalation Rules)

- Complaints about past service quality
- Custom service requests not in the catalogue
- Warranty claims or insurance-related queries
- Payment disputes (e.g. customer contests a charge or requests a reversal) — note: routine fee notifications arising from rescheduling or cancellation policy are handled by the agent, not escalated
- Any emotional or sensitive customer situation

---

## 4. Context Engineering

Context engineering is the practice of equipping the AI agent with the right business knowledge so it can respond accurately and helpfully. This is a key differentiator of the Flow AI platform and must be carefully designed and maintained.

### 4.1 Context Components

Context is information the agent *knows* — loaded or injected into the prompt window so the agent can reason from it. It is distinct from tools, which are actions the agent can *take*. The table below defines all context components.

| Component | Description | Type |
|-----------|-------------|------|
| **System Prompt** | Core instructions defining the agent's role, rules, tone, and escalation triggers. Reusable across clients with client-specific fields. | Reusable |
| **Service Catalogue** | Full list of services with names, descriptions, price ranges, and duration estimates. Loaded at session start; updated via CMS or admin panel. | Client-Specific |
| **Business Information** | Name, address, operating hours, WhatsApp number, service zones, and accepted payment methods. | Client-Specific |
| **Business Policies** | Cancellation policy, rescheduling policy (including any applicable fees), refund rules, and out-of-hours handling. Loaded at session start and used by the agent to reason about cost implications, customer commitments, and policy communications — not hardcoded as conditional logic. | Client-Specific |
| **Customer Profile** | Existing customer record retrieved from CRM on phone number match at session start — includes name, address history, and customer tier if applicable. New customers have no profile until one is created via tool. | Dynamic |
| **Booking History** | Past and active orders retrieved from CRM for the matched customer. Gives the agent context on the customer's service history and relationship with the business. | Dynamic |
| **Active Order Context** | The specific order or booking most relevant to the current conversation, injected when the customer references a particular appointment. | Dynamic |
| **Conversation History** | Full WhatsApp thread maintained per session for coherent multi-turn conversations. Older non-critical messages are summarised to manage context window size. | Dynamic |

### 4.2 Context Injection Architecture

- At session start: system prompt + service catalogue + business information + business policies are loaded
- On phone number match: customer profile and booking history are retrieved from CRM and injected
- On booking intent detection: `check_availability` tool is called; the returned slots are injected into context for the agent to present to the customer
- On explicit order reference: active order context is fetched via `get_booking_details` and injected for the relevant appointment
- Context window is managed to prevent overflow — older non-critical conversation turns are summarised rather than dropped

**Modularity Note:** The context layer is the only part of the agent that is client-specific. The agent core (prompt framework, tool definitions, orchestration logic) is fully reusable and shared across all Flow AI clients.

### 4.3 Agent Reasoning Model

The agent must reason from its context — it must not execute hardcoded conditional logic. This distinction is fundamental to the Flow AI design.

**Principle:** The agent reads its business policies and reasons about what to do, rather than following pre-programmed if/then branches.

**Example — Rescheduling Fee:**
The agent does not follow a rule like: *if reschedule is same-day → charge $20 fee*. Instead, the rescheduling policy in its context states the fee conditions. The agent reads this, understands the implication, informs the customer, and triggers the appropriate tool. If the policy changes (e.g. the fee is waived during a promotion), only the policy context needs updating — no code changes required.

**Example — Cancellation:**
The agent does not have a hardcoded cancellation workflow. It reads the cancellation policy, determines whether a fee applies based on the booking timing, communicates this transparently to the customer, and calls `cancel_booking`. If a refund or invoice amendment is needed, the agent reasons from the policy and triggers `generate_invoice` (Phase 2) accordingly.

This approach ensures the agent's behaviour stays aligned with the client's actual policies and can be updated without engineering involvement.

---

## 5. Agent Tools

Tools are actions the agent can *take* — external calls that read live data or write state to external systems. All tool calls are logged for debugging and auditing purposes.

**Note on `send_confirmation`:** Booking confirmation messages are not an agent tool. They are triggered automatically by the orchestration layer upon detecting a confirmed booking state. This prevents the agent from accidentally omitting or prematurely firing a confirmation.

**Note on `get_service_info`:** The service catalogue is loaded as static context at session start (see Section 4.1) and does not require a runtime tool call. Treating it as a tool would add unnecessary latency and a failure point for information that does not change within a session.

| Tool Name | Description | Category |
|-----------|-------------|----------|
| **check_availability** | Queries the calendar system for available time slots given a date range and service duration. Results are injected into context for the agent to present to the customer. | Booking |
| **create_booking** | Creates a new calendar event and a corresponding order record in the CRM. Called after the customer confirms a slot and all required details are captured. | Booking |
| **reschedule_booking** | Moves an existing booking to a new date/time. Distinct from cancellation — agent reasons from rescheduling policy context about any applicable fees before calling this tool. | Booking |
| **cancel_booking** | Cancels an existing booking and marks the order accordingly. Agent reasons from cancellation policy context about fees or refunds before calling this tool. | Booking |
| **get_booking_details** | Fetches the full details of a specific booking from the booking management system — includes scheduled date/time, service type, address, unit count, and current status. Used when a customer references a specific appointment. | Booking |
| **get_customer** | Retrieves an existing customer record from the CRM by phone number. | CRM |
| **create_customer** | Creates a new customer or lead record in the CRM when a first-time customer is detected. | CRM |
| **get_order** | Fetches the financial order record from the CRM for a given booking — includes pricing, invoice status, and payment details. | CRM |
| **generate_invoice** | Generates or amends an invoice for an order. Used when a booking change affects cost (e.g. rescheduling fee, cancellation fee, scope change). *(Phase 2)* | Billing |
| **escalate_to_human** | Flags the conversation for human follow-up, notifies the admin team, and tags the conversation as 'Escalated' in the CRM inbox. | Operations |

---

## 6. WhatsApp Integration

### 6.1 Channel Setup

- WhatsApp Business API via Meta Cloud API or BSP (360dialog recommended for Singapore)
- Client must have a verified WhatsApp Business Account and a dedicated business phone number
- A Meta Business Manager account with the WhatsApp Business App connected
- Webhook URL configured to route all incoming messages to the Flow AI agent orchestrator

### 6.2 Message Types

| Type | Handling |
|------|----------|
| **Free-form Text** | Standard customer messages — handled by AI agent in real time |
| **WhatsApp Templates** | Pre-approved message templates used for booking confirmations and reminders (required for business-initiated messages after 24-hour window) |
| **Media (Images)** | Customer may send photos of aircon units — agent should acknowledge and escalate if diagnosis is needed |
| **Voice Notes** | Out of scope for Phase 1; agent should prompt customer to type their request |
| **Buttons / Quick Replies** | Optional — can be used for common responses like 'Check availability' or 'Talk to someone' |

### 6.3 Session & Rate Limits

- WhatsApp enforces a 24-hour session window for free-form messaging
- After 24 hours, only approved message templates can be sent
- Rate limits: the agent must not send more than 3 messages per response to avoid spam flagging
- A business account can handle up to 1,000 unique users per day on a standard tier

---

## 7. CRM Integration

### 7.1 Data Created by Agent

| Record Type | Details |
|-------------|---------|
| **Lead Record** | Created when a customer's phone number is first seen — captures name, number, source (WhatsApp), and initial enquiry type |
| **Customer Record** | Promoted from Lead after first booking is confirmed |
| **Order Record** | Created upon booking confirmation — includes service type, address, scheduled date/time, unit count, and estimated price |
| **Conversation Log** | Full WhatsApp conversation thread linked to the customer record in CRM |
| **Activity Timeline** | Each agent action (booking created, escalation triggered) is logged as an activity on the customer record |

### 7.2 Integration Approach

- n8n workflows orchestrate communication between the WhatsApp webhook, AI agent, and CRM database
- Alternatively, a custom FastAPI backend can serve as the orchestrator with direct database writes
- All CRM writes are idempotent — duplicate webhook deliveries will not create duplicate records

---

## 8. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR-A-01** | Agent must respond to any incoming WhatsApp message within 10 seconds | Critical |
| **FR-A-02** | Agent must correctly identify service intent from free-form text with >85% accuracy | Critical |
| **FR-A-03** | Agent must check real-time calendar availability before confirming any booking | Critical |
| **FR-A-04** | Agent must create a CRM order record for every confirmed booking | Critical |
| **FR-A-05** | Agent must send a booking confirmation message including date, time, address, and service type | Critical |
| **FR-A-06** | Agent must escalate conversations that match escalation trigger keywords within 1 exchange | High |
| **FR-A-07** | Agent must handle rescheduling and cancellation requests end-to-end | High |
| **FR-A-08** | Agent must never fabricate service prices or availability not present in its context or tools | Critical |
| **FR-A-09** | Admin staff must be able to view and take over any conversation from the CRM inbox | High |
| **FR-A-10** | All tool calls and agent decisions must be logged in an audit trail | High |
| **FR-A-11** | Agent must support English; Mandarin support is a Phase 2 consideration | Medium |
| **FR-A-12** | Agent must handle multiple concurrent conversations without degradation | High |

---

## 9. Non-Functional Requirements

| Requirement | Specification | Priority |
|-------------|----------------|----------|
| **Response Latency** | < 10 seconds end-to-end from message receipt to agent reply | Critical |
| **Availability** | 99.5% uptime; agent must be available 24/7 | Critical |
| **Scalability** | Must support up to 500 concurrent sessions per client instance | High |
| **Data Residency** | Customer conversation data stored in Singapore-region servers (PDPA) | Critical |
| **Hallucination Prevention** | Agent must only use tools or provided context; no fabricated facts | Critical |
| **Auditability** | All agent decisions and tool calls logged with timestamps | High |
| **Failsafe** | If AI agent fails, incoming messages must trigger a fallback reply and escalation | High |

---

## 10. User Stories

| ID | User Story |
|----|-----------|
| **US-A-01** | As a customer, I want to type a message in plain English and receive a helpful response so that I don't have to navigate a menu. |
| **US-A-02** | As a customer, I want to see available time slots proposed to me so that I can pick one without back-and-forth. |
| **US-A-03** | As a customer, I want to receive a booking confirmation summary on WhatsApp so that I have a record of my appointment. |
| **US-A-04** | As a customer, I want to reschedule my appointment via WhatsApp so that I don't have to call in. |
| **US-A-05** | As an admin, I want to see all active WhatsApp conversations in one dashboard so that I can monitor the agent and step in if needed. |
| **US-A-06** | As an admin, I want to receive an alert when the agent escalates a conversation so that I can follow up promptly. |
| **US-A-07** | As the Flow AI operator, I want to update the service catalogue in one place so that the agent always has the latest pricing and service information. |

---

## 11. Technical Specifications

| Component | Technology |
|-----------|-----------|
| **AI Model** | Claude 3.5 Sonnet or GPT-4o (configurable) |
| **Agent Framework** | LangChain agents or custom async Python agent loop |
| **Orchestration** | n8n (self-hosted) for webhook routing and tool orchestration |
| **WhatsApp API** | Meta Cloud API or 360dialog BSP |
| **Backend** | FastAPI (Python) or Node.js Express |
| **Session State** | Redis for conversation state and context window management |
| **Database** | PostgreSQL for CRM records and audit logs |
| **Calendar** | Google Calendar API (OAuth2 service account) |
| **Hosting** | Railway or Render for backend; same region as DB |
| **Monitoring** | Langfuse or Langsmith for agent trace monitoring and cost tracking |

---

## 12. Acceptance Criteria

| ID | Criterion | Type |
|----|-----------|------|
| **AC-A-01** | Agent responds to a new WhatsApp message within 10 seconds | Pass/Fail |
| **AC-A-02** | Booking flow completes end-to-end (intent → slot → confirm → CRM order created) | Pass/Fail |
| **AC-A-03** | Agent correctly handles 10 scripted test conversations with >85% accuracy | Score |
| **AC-A-04** | Escalation is triggered correctly for 5 escalation keyword scenarios | Pass/Fail |
| **AC-A-05** | CRM order record is created within 30 seconds of booking confirmation | Pass/Fail |
| **AC-A-06** | Agent does not fabricate service prices when tested with unknown service queries | Pass/Fail |
| **AC-A-07** | Admin can view and reply to a conversation from the CRM inbox | Pass/Fail |
| **AC-A-08** | Rescheduling flow completes and CRM order is updated correctly | Pass/Fail |
| **AC-A-09** | Agent correctly communicates rescheduling or cancellation fee to customer based on policy context before calling the relevant tool | Pass/Fail |
| **AC-A-10** | Agent does not follow hardcoded logic — changing the policy context (e.g. fee amount) results in updated agent behaviour without code changes | Pass/Fail |

---

## 13. Open Questions

| ID | Question | Owner |
|----|----------|-------|
| **OQ-A-01** | Will the client use an existing WhatsApp Business number or provision a new one? | Client to confirm |
| **OQ-A-02** | Should the agent support image input (photos of aircon units) in Phase 1? | Product decision |
| **OQ-A-03** | What is the client's policy for handling bookings outside business hours? | Client to confirm |
| **OQ-A-04** | Should the agent send a reminder message 24 hours before each appointment? | Client to confirm |
| **OQ-A-05** | Will the client manage the Google Calendar directly, or should we build an availability management UI? | Product decision |
| **OQ-A-06** | Is Mandarin language support required for Phase 1 or Phase 2? | Client to confirm |
