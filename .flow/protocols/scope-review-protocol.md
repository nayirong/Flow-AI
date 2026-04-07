# Scope Review Protocol

## Purpose
Defines how agents assess, evaluate, and provide structured feedback on a scope document (e.g. MVP scope, feature scope, sprint scope) before any implementation begins.

A scope review is **assessment only** — it does not trigger PRD updates, task specs, or engineering work. Those only begin once the scope is approved and a change request is issued.

---

## When to Use This Protocol
- Reviewing an MVP scope before committing to build
- Assessing a new feature request before adding it to the PRD
- Evaluating a proposed change for feasibility and completeness
- Validating that a scope has clear, testable acceptance criteria

---

## Trigger Format

Issue this brief to the relevant Orchestrator (Flow AI or Client level):

```
REVIEW REQUEST
Task ID: [TASK-YYYYMMDD-NNN]
Type: SCOPE REVIEW
Document: [path to scope document]
Requested By: [name]
Review Focus:
  - [specific question 1 — e.g. "Is this feasible for MVP?"]
  - [specific question 2 — e.g. "What knowledge base gaps exist?"]
Agents To Involve: [list — PM is always required; others as relevant]
Output Required: Consolidated Review Report from PM Agent
```

---

## Orchestration Flow

```
Orchestrator receives REVIEW REQUEST
         │
         ▼
Routes to PM Agent (always the first and last agent in a review)
         │
PM Agent distributes to relevant agents with per-agent brief
         │
         ├──▶ Engineering Agent   (if scope includes technical work)
         ├──▶ QA Agent            (if scope includes testable features)
         ├──▶ Prompt/Persona Agent (if scope includes conversation flows)
         └──▶ Knowledge Agent     (if scope implies knowledge base content)
                   │
         Each returns a REVIEW FINDING to PM Agent
                   │
         PM Agent consolidates into SCOPE REVIEW REPORT
                   │
         PM Agent returns report to Orchestrator
                   │
         Orchestrator routes report back to human
```

---

## Agent Involvement Guide

Only involve agents whose domain is touched by the scope. Do not default to involving all agents.

| Include This Agent | When the Scope Contains |
|---|---|
| **Engineering Agent** | New features, integrations, system changes, infrastructure |
| **QA Agent** | Any item that needs to be verified or tested |
| **Prompt/Persona Agent** | Conversation flows, escalation logic, agent tone/behaviour |
| **Knowledge Agent** | FAQs, services, pricing, policies, or knowledge base changes |

---

## Per-Agent Review Brief (PM Agent issues this)

```
REVIEW BRIEF
Task ID: [from Review Request]
Type: SCOPE REVIEW
Document: [path]
Your Lens: [Engineering feasibility | QA testability | Conversation coverage | Knowledge requirements]
Specific Questions:
  - [tailored question for this agent]
Return To: PM Agent
Deadline: [session or date]
```

---

## Review Finding Format (each agent returns this)

```
REVIEW FINDING
Task ID: [ID]
Reviewer: [agent name]
Lens: [their review area]
Status: APPROVED | APPROVED WITH CONCERNS | NEEDS REVISION

Findings:
  - [BLOCKER | CONCERN | ADVISORY] [description]
    Scope Item: [which item this refers to]
    Detail: [explanation of the issue or risk]

Gaps Identified:
  - [anything implied by the scope but not explicitly covered]

Recommendation: PROCEED | REVISE ITEM(S) | DESCOPE ITEM(S)
```

### Finding Severity Definitions
| Level | Meaning |
|---|---|
| **BLOCKER** | Must be resolved before scope can be approved — fundamental issue |
| **CONCERN** | Should be resolved — risk to delivery or quality if ignored |
| **ADVISORY** | Noted for awareness — low priority, does not block approval |

---

## Scope Review Report Format (PM Agent produces this)

```
SCOPE REVIEW REPORT
Task ID: [ID]
Document Reviewed: [path]
Date: [YYYY-MM-DD]
Agents Consulted: [list]
Overall Status: APPROVED | APPROVED WITH REVISIONS | NEEDS REWORK

Summary:
  [2-3 sentence overview of the scope and the review outcome]

Blockers (must resolve before proceeding):
  - [item] — raised by [agent] — [description]

Concerns (should resolve):
  - [item] — raised by [agent] — [description]

Advisories (noted, low priority):
  - [item] — raised by [agent] — [description]

Gaps (not in scope, but should be considered):
  - [item] — raised by [agent] — [description]

Recommendation:
  PROCEED | REVISE AND RE-REVIEW | REWORK SCOPE

Next Step (if PROCEED):
  Issue change request referencing Task ID [ID] to begin PRD update and implementation.
```

---

## Revision Loop

If the report status is **APPROVED WITH REVISIONS** or **NEEDS REWORK**:

1. Human or PM Agent updates the scope document
2. PM Agent re-issues review briefs **only to agents with open BLOCKERs or CONCERNs**
3. Those agents return updated REVIEW FINDINGs
4. PM Agent updates the Review Report
5. Loop repeats until status is **APPROVED**

Do not re-run the full review for every revision — only involve agents affected by the changes.

---

## Transition to Implementation

Once the Review Report status is **APPROVED**:

1. PM Agent updates `PRD.md` to reflect the approved scope
2. PM Agent issues task specs to Engineering, QA, and other relevant agents
3. Standard change request protocol applies from this point forward

See: [change-request-protocol.md](change-request-protocol.md)

---

## Rules
- Scope review never produces code or configuration changes — assessment only
- PM Agent is always involved — they own the review process and its output
- Every BLOCKER must be resolved before a scope is approved
- The Review Report must be stored alongside the scope document or linked from the PRD
