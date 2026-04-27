# Flow AI — Frequently Asked Questions

> Agent answers these questions directly. Escalate to founder if the question falls outside this file.

---

## About the Product

**Q: What exactly does Flow AI do?**
Flow AI automates your WhatsApp customer conversations. The agent handles inbound inquiries 24/7 — answering FAQs, qualifying leads, taking bookings — so your team only deals with what genuinely needs a human.

**Q: Is this a chatbot?**
Not in the traditional sense. A chatbot follows rigid scripts. Our agents understand natural language and context — a customer can ask the same question 10 different ways and get the right answer each time. The booking flow is structured, but everything else adapts to the conversation.

**Q: What WhatsApp number do I use?**
Your existing WhatsApp Business number, or we can help you set up a new one. We connect directly to Meta's Cloud API — no middlemen, no extra BSP fees.

**Q: Will my customers know they're talking to an AI?**
The agent doesn't volunteer that it's an AI, but it won't deny it if asked directly. Most clients prefer it this way — the agent introduces itself by name (e.g., "Hi, I'm Kai from [Business]") without specifying it's an AI.

**Q: What happens if a customer asks something the agent doesn't know?**
The agent has a hard escalation gate — if it can't confidently answer or the situation needs human judgment, it sends an alert to your team's WhatsApp and holds the customer with a polite holding message.

---

## Setup & Implementation

**Q: How long does it take to go live?**
4 weeks from signed agreement to live WhatsApp number. That includes: knowledge base build, agent configuration, testing, and handoff.

**Q: What do I need to provide?**
- Access to your WhatsApp Business account (Meta Business Manager)
- Your business knowledge: services, pricing, hours, policies
- A phone number on your team for escalation alerts

**Q: Do I need a developer?**
No. We handle the full technical setup. You just review and approve the knowledge base content.

**Q: Can I update the agent's knowledge later?**
Yes, anytime. You update content in a shared Supabase table — no code changes, no redeployment. Changes go live immediately.

---

## Integration & Data

**Q: Does it integrate with my existing CRM?**
In Phase 1, all data is stored in a dedicated Supabase database (your client-isolated CRM). We can export or sync data to external CRMs — that's a Phase 2 roadmap item. Ask the founder for current integration status.

**Q: Where is my customer data stored?**
In an isolated Supabase (Postgres) database, one per client. Your data is never mixed with another client's. Hosted in Singapore/Southeast Asia region.

**Q: Is my data secure?**
All data is encrypted at rest and in transit. Each client has dedicated API keys and database credentials. We never share data between clients.

---

## Pricing & Commercial

**Q: How much does it cost?**
[See pricing.md — quote the Starter/Growth tiers and offer to connect with founder for custom quotes.]

**Q: Is there a free trial?**
We don't offer a free trial, but we do offer a paid pilot — 30 days at a reduced rate for new clients. Ask the founder for current pilot terms.

**Q: Can I cancel anytime?**
30-day written notice required to cancel. No long-term lock-in beyond that.

---

## Objection Handling

**"We already have someone managing WhatsApp."**
That person's time is expensive. Our agents handle 80–90% of routine inquiries automatically — your team member focuses on the conversations that actually need judgment. Most clients find their team member's time freed up for higher-value work.

**"Our customers prefer talking to a human."**
They prefer fast, accurate responses — and humans aren't always available. The agent handles the routine 80%, and humans stay in the loop for everything that matters. Customers can reach a human anytime via escalation.

**"We're not tech-savvy enough."**
You don't touch any code. You review the knowledge base, approve the content, and we handle everything else. Your only ongoing task is updating your services or pricing in a simple table — like editing a spreadsheet.

**"We tried a chatbot before and it didn't work."**
Flow AI is not a rule-based chatbot. It's an LLM-powered agent that understands context and adapts to natural conversation. The difference is meaningful — ask us to show you a demo of how it handles edge cases.
