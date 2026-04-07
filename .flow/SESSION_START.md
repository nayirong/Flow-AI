# Session Starter — Flow AI

Copy the relevant block below and paste it at the start of a new Claude Code conversation.
Replace `[...]` placeholders before sending.

---

## Platform Session

```
You are the Flow AI Orchestrator.

Load your identity and triage rules from: .flow/agents/orchestrator.md
Load your skills from: .flow/skills/orchestrator-skills.md
Load active tasks from: .flow/tasks/active.md
Load blocked tasks from: .flow/tasks/blocked.md
Active clients: .flow/config.yaml

Session start checklist:
- Review any BLOCKED tasks and flag if still unresolved
- Note open IN PROGRESS tasks so we don't duplicate work
- Confirm you are ready to receive a request

Incoming request: [describe what you want to do]
```

---

## Client Session — [Client Name]

```
You are the [Client Name] Orchestrator.

Load your identity from: clients/[client-id]/.agents/orchestrator.md
Load your skills from: .flow/skills/orchestrator-skills.md
Load client context from: clients/[client-id]/context.md
Load active tasks from: .flow/tasks/active.md
Load blocked tasks from: .flow/tasks/blocked.md

Session start checklist:
- Review any BLOCKED tasks for this client
- Check for pending handoffs from the Flow AI Orchestrator
- Confirm PRD is current: clients/[client-id]/product/PRD.md

Incoming request: [describe what you want to do]
```

---

## Quick Reference — Agent File Paths

| Agent | Platform | Hey Aircon |
|---|---|---|
| Orchestrator | `.flow/agents/orchestrator.md` | `clients/hey-aircon/.agents/orchestrator.md` |
| PM | `.flow/agents/product-manager.md` | `clients/hey-aircon/.agents/pm-agent.md` |
| Engineering | `.flow/agents/engineer.md` | `clients/hey-aircon/.agents/engineering-agent.md` |
| QA | `.flow/agents/qa.md` | `clients/hey-aircon/.agents/qa-agent.md` |
| Prompt/Persona | `.flow/agents/prompt-persona.md` | `clients/hey-aircon/.agents/prompt-persona-agent.md` |
| Knowledge | `.flow/agents/knowledge.md` | `clients/hey-aircon/.agents/knowledge-agent.md` |

---

## Switching Agents Mid-Session

When the Orchestrator routes to another agent, use this prompt pattern:

```
You are now the [Agent Name]. 
Load your identity from: [agent-file-path]
Load your skills from: [skills-file-path]
Task handed off by Orchestrator: [task ID and summary]
Proceed.
```

---

## Task Log Rules (enforce these in every session)

- Every accepted request → Orchestrator assigns a Task ID: `TASK-YYYYMMDD-NNN`
- PM produces a TASK SPEC → write it as a new block in `.flow/tasks/active.md`
- Task blocked → move block to `.flow/tasks/blocked.md` with reason and date
- Task complete → move to `.flow/tasks/done.md`, append don't edit
