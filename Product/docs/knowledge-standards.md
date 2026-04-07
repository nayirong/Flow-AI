# Flow AI — Knowledge Entry Standards

> Owned by: Flow AI Platform Knowledge Agent
> Last Updated: 2026-04-03

---

## Writing Standards for AI-Consumable Knowledge

### Answer Writing Rules
1. **Write for the AI to relay, not for humans to read directly**
   - Good: "Our standard service call takes 1-2 hours depending on the issue."
   - Avoid: "We try to get our techs in and out as fast as we can, usually within a couple of hours."

2. **Be specific and unambiguous**
   - Good: "Operating hours are Monday to Friday, 8am–6pm."
   - Avoid: "We're open most weekdays during business hours."

3. **Avoid speculation language**
   - Never write: "usually", "probably", "we think", "around"
   - If uncertain, mark as TO FILL and escalate

4. **Keep answers atomic**
   - One answer per FAQ entry
   - If a question has multiple valid answers, create multiple entries with different question variants

5. **Customer-facing tone**
   - Write as if the AI is speaking directly to the customer
   - Use "we" for the business, "you" for the customer

### Source Requirements
- Every entry must have a named source (person + role)
- Acceptable sources: business owner, manager, official price list, confirmed email
- Not acceptable: "assumed", "from memory", "probably"

### Review Cadence
| Entry Type | Review Frequency |
|-----------|-----------------|
| Pricing | Monthly, or when changed |
| Operating Hours | Monthly, or before public holidays |
| Services | Quarterly, or when services change |
| FAQs | Quarterly, or when issues recur |
| Policies | When policy changes |

### Conflict Resolution
1. When two entries contradict — freeze both, escalate to PM Agent
2. PM Agent confirms correct version with Hey Aircon stakeholder
3. Correct entry goes live, incorrect entry is deleted (not archived)
4. Log the resolution in changelog.md
