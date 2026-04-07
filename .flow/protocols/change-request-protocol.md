# Change Request Protocol

## Flow for All Changes

### Standard Change (Client-Specific)
1. Request received by Flow AI Orchestrator
2. Orchestrator issues Task ID, classifies as CLIENT, routes to Client Orchestrator
3. Client Orchestrator routes to Client PM Agent
4. PM Agent updates PRD.md and issues task specs
5. Engineering Agent implements per spec
6. QA Agent validates per QA Brief
7. PM Agent marks task complete, updates changelog
8. Client Orchestrator closes task in log

### Standard Change (Core Platform)
1. Request received by Flow AI Orchestrator
2. Orchestrator issues Task ID, classifies as CORE, routes to Platform PM Agent
3. Platform PM Agent updates core PRD and issues task specs
4. Platform Engineering Agent implements per spec
5. Platform QA Agent validates
6. Platform PM Agent marks task complete, updates changelog
7. Flow AI Orchestrator assesses client impact and notifies affected Client Orchestrators

### Prompt or Persona Change
1. Request received by Client Orchestrator (or Flow AI Orchestrator for base templates)
2. Routes to Client PM Agent
3. PM Agent routes to Prompt/Persona Agent with brief
4. Prompt/Persona Agent produces change with mandatory test dialogue
5. PM Agent reviews and approves
6. If code changes required → Engineering Agent spec issued
7. QA Agent validates
8. PM Agent marks complete, updates changelog

### Knowledge Base Change
1. Request received by Client Orchestrator
2. Routes to Client PM Agent
3. PM Agent routes to Knowledge Agent with brief
4. Knowledge Agent updates/adds entries (source confirmed)
5. If change affects conversation flows → notifies Prompt/Persona Agent
6. PM Agent reviews and approves
7. PM Agent marks complete, updates changelog

## Task ID Format
TASK-[YYYYMMDD]-[NNN]
Example: TASK-20260403-001

## Task States
RECEIVED → CLASSIFIED → IN PROGRESS → IN REVIEW → COMPLETE | BLOCKED

## Document Update Requirements
| Event | PM Must Update |
|-------|---------------|
| Change accepted | PRD.md |
| Task completed | changelog.md |
| New feature | requirements/[feature-name].md |
| Bug fix | changelog.md only (if no PRD change) |
| Persona change | persona.md |
| Knowledge update | Relevant file in knowledge/ |
