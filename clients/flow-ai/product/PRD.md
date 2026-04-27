# Flow AI WhatsApp Agent — PRD

**Client:** Flow AI (internal — platform as its own client)
**Phase:** 1 — Lead Qualification Agent
**Status:** Draft

---

## 1. Problem Statement

Flow AI's website has a WhatsApp "Contact Us" button. Inbound inquiries arrive from SME owners and operators interested in the platform. Currently these go unanswered or require founder manual response. This creates response latency, unqualified discovery calls, and lost leads outside business hours.

The agent must handle initial qualification autonomously, freeing the founder to focus on high-fit prospects only.

## 2. Goals

| Goal | Metric |
|------|--------|
| Respond to every inbound inquiry within 60 seconds, 24/7 | 100% of inbound messages receive a reply |
| Qualify leads before routing to founder | Every escalated lead has answered 4 qualification questions |
| Capture all leads in CRM | 100% of conversations logged to `flow-ai-crm` Supabase |
| Reduce founder pre-call prep time | Founder receives structured lead summary at escalation |

## 3. Out of Scope (Phase 1)

- Discovery call scheduling (send Calendly link; no native calendar integration)
- Booking system (Flow AI has no bookable service slots in Phase 1)
- Google Sheets sync (internal team, no external CRM needed)
- Proactive follow-up sequences (add in Phase 2)

## 4. Agent Flows

### Flow A — Standard Inquiry

```
Customer: "Hi, I saw your website. Can you tell me more?"
Agent: [brief intro] → [qualification Q1: What industry is your business?]
Customer: [answers]
Agent: [Q2: How many WhatsApp inquiries do you receive per week?]
Customer: [answers]
Agent: [Q3: What's your biggest pain point with current WhatsApp handling?]
Customer: [answers]
Agent: [Q4: How large is your team?]
Customer: [answers]
Agent: [lead score internally] → [if high-fit: route to founder] / [if low-fit: capture + nurture message]
```

### Flow B — Direct Question (FAQ)

```
Customer: "How much does it cost?"
Agent: [answer from knowledge base] → [pivot to qualification if not yet complete]
```

### Flow C — Escalation

```
Customer: [frustrated / requests live demo / specific technical integration question]
Agent: [acknowledge] → [escalate to founder with lead summary]
```

## 5. Qualification Questions

Asked in order, but agent may adapt order based on conversation context:

| # | Question | Purpose |
|---|----------|---------|
| Q1 | What industry is your business in? | Vertical fit check |
| Q2 | How many WhatsApp messages does your team handle per week? | Volume signal |
| Q3 | What's your biggest frustration with how you handle WhatsApp today? | Pain qualification |
| Q4 | How many people are on your team? | Deal size signal |

## 6. Lead Routing Logic

| Signal | Action |
|--------|--------|
| Service SME in target vertical (aircon, aesthetics, real estate, insurance) + 50+ msg/week | Escalate to founder with summary |
| Any industry + 100+ msg/week | Escalate to founder with summary |
| Outside target vertical + < 50 msg/week | Capture in CRM, send nurture message with case study |
| Unresponsive after 2 turns | Capture contact, offer to send info via WhatsApp |

## 7. Escalation Message Format

When escalating, send to founder's WhatsApp (`human_agent_number`):

```
🚨 New qualified lead — Flow AI WhatsApp

Name: {customer_name}
Number: {phone_number}
Industry: {Q1 answer}
Volume: {Q2 answer}
Pain point: {Q3 answer}
Team size: {Q4 answer}
Conversation started: {timestamp}
```

## 8. Data Model (flow-ai-crm Supabase)

See `clients/flow-ai/plans/architecture.md` for full schema.

Key tables: `customers` (leads), `interactions_log` (conversation history), `config` (agent knowledge), `policies` (routing rules, qualification thresholds).

No `bookings` table — Flow AI agent does not take bookings in Phase 1.

## 9. Acceptance Criteria

- [ ] Agent responds within 60 seconds to any inbound message on Flow AI's WhatsApp number
- [ ] Agent completes qualification flow (4 questions) before routing or capturing any lead
- [ ] Escalation message delivered to founder's WhatsApp with full lead summary
- [ ] All conversations logged to `interactions_log` in `flow-ai-crm`
- [ ] Agent never reveals underlying model or technical implementation details
- [ ] Agent handles off-topic messages (non-business) gracefully without breaking flow
