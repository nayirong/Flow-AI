# Handoff Protocol

## Purpose
Defines how work is transferred between agents to prevent loss of context.

## Rules
1. Every handoff must include a Task ID (issued by Orchestrator)
2. The sending agent must confirm the receiving agent has acknowledged before closing their involvement
3. Context must be passed explicitly — agents do not assume shared memory
4. Handoffs are logged in the task's requirement file

## Handoff Payload Structure
```
HANDOFF
From: [agent name]
To: [agent name]
Task ID: [ID]
Summary: [what has been done so far]
What Is Needed: [specific ask for receiving agent]
Attachments: [links to relevant docs]
Deadline: [if applicable]
```

## Client → Core Escalation
When a Client PM Agent identifies a core platform concern:
1. Client PM Agent → notifies Client Orchestrator
2. Client Orchestrator → sends handoff to Flow AI Orchestrator
3. Flow AI Orchestrator → re-classifies and routes to Platform PM Agent
4. Platform PM Agent → communicates resolution back through same chain

## Core → Client Communication
When Flow AI platform makes a change that affects clients:
1. Flow AI Orchestrator → assesses which clients are impacted
2. Flow AI Orchestrator → sends handoff to each affected Client Orchestrator
3. Client Orchestrator → routes to Client PM Agent
4. Client PM Agent → updates client PRD/changelog and routes implementation
