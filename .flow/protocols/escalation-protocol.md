# Escalation Protocol

## When To Escalate
| Situation | Escalate To |
|-----------|-------------|
| Classification confidence < 70% | Flow AI Orchestrator → Human Operator |
| Task blocked for > 1 session | Human Operator |
| Conflicting requirements from two agents | Human Operator |
| Client change found to affect core platform | Flow AI Platform PM |
| QA finds systemic regression | Flow AI Orchestrator |
| Prompt change poses safety risk | PM Agent → Human Operator |
| Knowledge entry has no confirmable source | PM Agent |

## Escalation Format
```
ESCALATION
Task ID: [ID]
Raised By: [agent]
Situation: [description]
Attempted Resolution: [what was tried]
Decision Needed: [specific question for human or escalation target]
Urgency: HIGH | MEDIUM | LOW
```

## Resolution SLA (guideline)
- HIGH: resolve before next agent session
- MEDIUM: resolve within 2 sessions
- LOW: log and address in next planning cycle
