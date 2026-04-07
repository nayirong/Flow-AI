# Flow AI — Knowledge Base Schema

> Owned by: Flow AI Platform Knowledge Agent
> Last Updated: 2026-04-03

---

## Purpose
Defines the required structure for all client knowledge bases. Every client knowledge base must conform to this schema.

## Required Directory Structure
```
product/knowledge/
├── faqs/               # FAQ entries (one file per category, or one per entry)
├── services/           # Service catalogue entries
├── pricing.md          # Pricing structure
├── hours.md            # Operating hours
└── policies/           # Policy documents (returns, cancellations, etc.)
```

## FAQ Entry Schema
```
FAQ ENTRY
ID: FAQ-[NNN]
Category: [string]
Question Variants:
  - [string]
  - [string]
Answer: [string — written for AI relay to customer]
Last Updated: [YYYY-MM-DD]
Source: [name/role of person who confirmed]
Expiry: [YYYY-MM-DD or "ongoing"]
```

## Service Catalogue Entry Schema
```
SERVICE ENTRY
ID: SVC-[NNN]
Service Name: [string]
Description: [one sentence, customer-facing]
Duration: [string — e.g. "1-2 hours"]
Price: [string or reference to pricing.md]
Availability: [string — constraints]
Prerequisites: [string or "None"]
Last Updated: [YYYY-MM-DD]
```

## Knowledge Gap Schema
```
KNOWLEDGE GAP
ID: GAP-[NNN]
Identified By: [agent or session ID]
Date: [YYYY-MM-DD]
Query That Failed: [string]
Why It Failed: [missing | contradiction | outdated]
Impact: [HIGH | MEDIUM | LOW]
Recommended Action: [string]
Status: OPEN | IN PROGRESS | RESOLVED
```

## Validation Rules
- Every entry must have an ID, Last Updated date, and Source
- Pricing and policy entries must have an Expiry date
- No two entries may have the same ID within the same category
- Contradictory entries must be resolved before either is marked active
