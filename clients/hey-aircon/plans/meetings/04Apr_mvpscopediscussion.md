# MVP Scope discussion
1. Book-keeping module keep on hold first (out of MVP scope)
2. MVP scope to focus only on whatsapp agent basic functions and basic CRM function


### WhatsApp basic functions:
#### 1. Answer inquiry
WhatsApp agent can answer basic inquiry for:
- Services related information
- Pricing related information
- about the company
- Past booking information (out of scope)
- upcoming booking information (out of scope)

#### 2. Handle basic booking
Whatsapp agent will have the following flow when handling customer booking:
1. Let customer know the bookings are by 4 hour window: 9am-1pm, 1pm-6pm and ask for date, preferred timeslot, address, type of servicing required. 
2. Customer share required information
3. AI agent checks if all information are shared. If all are shared, proceed to next step, if not AI agent will ask for missing information. 
4. (a) CASE: If no bookings are made by other customer for the time slot - AI agent will proceed to help schedule the booking and send confirmation to the customer. AI agent will then proceed to schedule a timeslot on google calendar.\
(b) CASE: If there are atleast 1 booking made by other customer for the time slot - AI agent will let customer know a human agent will out to arrange and confirm the booking. AI Agent will then notify human of booking request. 
5. Customer request for booking reschedule/cancellation: Agent share rescheduling/cancellation policy related information and let customer know a human agent will reach out for further confirmation or next steps.  


**Note:**
1. Need to confirm notification approach. Tentative send whatsapp message to human agent and/or mark the chat with color
2. Agent will only add to google calendar and not remove/update. Since booking updates or cancellation is handled by human, google calendar event removal/update have to be handled by human as well
3. Agent only support English language

### CRM
1. Store all customer information record where available
2. Store all bookings information 
3. Unique identier for customer by phone number

### Escalation Scenarios:
1. When customer ask something that is not within the context provided to agent
2. When customer send a preferred booking timeslot that is already taken by atleast one other customer for the selected date
3. When customer request to make booking changes (cancel booking, change timeslot/date) - escalate to human incase of penalties

## Follow up
### Required policy/docs
1. Rescheduling policy
2. Cancellation policy
3. Pricing docs
4. Service docs
5. Terms and Conditions (?)
6. Privacy policy (?)

### Required information:
1. Business opening hours
2. Business timeslot (12-1, 2-6PM)?
3. Days of operation (Mon-Sun?)
4. Operate on public holidays? 
5. Information needed for booking confirmation
6. How much notice is typically needed to schedule a job? 

