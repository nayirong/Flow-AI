# Hey Aircon — Client Context

## Business
- Industry: HVAC services (air conditioning installation, maintenance, repair)
- Primary users: Customers booking via WhatsApp AI agent
- Internal users: Field technicians, service coordinators

## AI Agent Purpose
- Handle inbound customer queries via WhatsApp
- Book, reschedule, and cancel service appointments
- Provide quotes and service information
- Escalate complex issues to human coordinators

## Key Constraints
- Operating hours must be respected in all booking flows
- Technician availability is managed externally — do not hardcode schedules
- All customer data is subject to local privacy regulations
- Never commit to specific technician names or exact arrival times

## Integration Points
- CRM: [to be defined]
- Booking system: [to be defined]
- WhatsApp: via n8n

## Product Documents
- PRD: product/PRD.md
- Changelog: product/changelog.md
- Persona: product/persona.md
- Knowledge Base: product/knowledge/
