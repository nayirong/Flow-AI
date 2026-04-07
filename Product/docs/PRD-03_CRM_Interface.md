# PRD-03: CRM Interface

## Product Requirements Document

---

| Field | Value |
|-------|-------|
| **Client** | Aircon Servicing Company (Pilot) |
| **Users** | Business Admin, Business Owner |
| **Version** | 1.0 |
| **Date** | April 2026 |
| **Status** | Draft — Pending Review |

---

## 1. Product Overview

The CRM Interface is an internal web dashboard used by the client's admin team and business owner to manage all leads, customers, conversations, orders, and deal pipelines. It is modelled on the usability and feature set of tools like HubSpot, but purpose-built for the aircon servicing context and deeply integrated with the AI agent and order management tools.

### Design Principle

The CRM must be operable by a non-technical admin without training. All key actions — viewing a customer record, checking a booking, and responding to a conversation — should be accessible in no more than 2 clicks from the main dashboard.

### 1.1 Goals

- Provide a single source of truth for all customer, lead, and order data
- Give admin full visibility of every AI agent conversation with the ability to take over
- Present a clear deal pipeline so the team always knows the status of each lead
- Associate all orders and interaction history with the correct customer record
- Enable manual lead and order creation for bookings made outside the WhatsApp channel
- Be reusable and extensible for future Flow AI clients in different verticals

### 1.2 Relationship to Other Products

- Receives leads and orders automatically from the AI WhatsApp Agent (Product 2)
- Order records are shared with the Sales & Reporting Tool (Product 4)
- WhatsApp conversation threads are viewable from within the CRM
- Manual orders created here are reflected in the reporting tool

---

## 2. Users & Personas

| Persona | Description | Priority |
|---------|-------------|----------|
| **Business Admin** | Manages day-to-day CRM operations — reviews leads, updates stages, adds notes, views conversations, and handles agent escalations. Uses CRM daily, 1–2 hours per day. | Primary |
| **Business Owner** | Reviews pipeline overview, monitors order volume, and checks customer history. Uses CRM weekly for oversight. | Secondary |
| **Flow AI Operator** | Sets up CRM stages, configures data fields, and manages integrations. Does not use CRM for daily operations. | Internal |

---

## 3. Data Model

### 3.1 Core Entities

| Entity | Description | Creation |
|--------|-------------|----------|
| **Lead** | A potential customer who has made contact but not yet had a confirmed booking. Created automatically by the AI agent or manually by admin. | Auto / Manual |
| **Customer** | A lead who has had at least one confirmed booking. Promoted from Lead automatically upon first order creation. | Promoted |
| **Contact** | Contact details associated with a Lead or Customer — name, phone, email, address. A customer can have multiple contacts (e.g. different unit locations). | Auto / Manual |
| **Order** | A confirmed booking or service job. Linked to a Customer. Contains service type, date, address, unit count, price, and status. | Auto / Manual |
| **Conversation** | A WhatsApp thread linked to a Lead or Customer. Contains all messages and agent actions. | Auto |
| **Activity** | A log entry on a Lead or Customer record — e.g. 'Booking created by agent', 'Admin note added', 'Escalation triggered'. | Auto / Manual |
| **Stage** | The pipeline stage of a Lead or Customer — e.g. New Lead, Contacted, Quoted, Booked, Completed, Recurring. | System |

### 3.2 Lead/Customer Pipeline Stages

| Stage | Description |
|-------|-------------|
| **New Lead** | First contact made — phone number captured, no further details yet |
| **Contacted** | Agent or admin has responded; conversation is active |
| **Quoted** | Service and price shared with the lead |
| **Booked** | Appointment confirmed; order record created |
| **Completed** | Service has been performed; order marked as completed |
| **Invoiced** | Invoice has been generated and sent to the customer |
| **Recurring** | Customer has booked more than once; flagged for retention marketing |
| **Lost** | Lead did not convert; no further follow-up expected |

### 3.3 Order Fields

| Field | Description | Type |
|-------|-------------|------|
| **Order ID** | Unique auto-generated identifier | System |
| **Customer** | Linked customer record | Required |
| **Service Type** | Dropdown from service catalogue | Required |
| **Unit Count** | Number of aircon units | Required |
| **Address** | Service address with postal code | Required |
| **Scheduled Date/Time** | Confirmed appointment slot | Required |
| **Estimated Price** | Calculated from service + unit count | Auto |
| **Actual Price** | Final price after service (may differ) | Manual |
| **Status** | Pending / Confirmed / Completed / Cancelled / Invoiced | Required |
| **Notes** | Free-text field for technician or admin notes | Optional |
| **Created By** | Agent or Admin name/ID | System |
| **Created At** | Timestamp of record creation | System |

---

## 4. Functional Requirements

### 4.1 Dashboard / Home View

- Summary cards: Total leads this week, bookings today, open escalations, revenue this month
- Pipeline overview: count of leads in each stage, with clickable drill-down
- Recent activity feed: last 10 events across all customers (e.g. 'New lead from WhatsApp — John Tan')
- Upcoming appointments: list of confirmed bookings for today and tomorrow
- Escalation alerts: banner or badge for conversations flagged by the agent for human follow-up

### 4.2 Leads & Customers List View

- Searchable, filterable table of all leads and customers
- Columns: Name, Phone, Stage, Last Activity, Source, Assigned To, Date Created
- Filters: Stage, Source (WhatsApp/Website Form/Manual), Date Range, Assigned To
- Sort by: Date Created, Last Activity, Stage
- Bulk actions: Change stage, Assign to, Export selected to CSV
- Quick-add button to manually create a new lead

### 4.3 Lead / Customer Detail View

#### Contact Information Panel

- Name, phone number, email, address
- Editable fields with save action
- Customer since / First booking date
- Source (WhatsApp / Website / Manual)
- Stage selector (dropdown with stage change history)

#### Order History Panel

- Chronological list of all orders linked to this customer
- Each order shows: Service Type, Date, Status, Price, Invoice status
- Clickable to open the full order detail view
- Quick-add button to manually create a new order for this customer

#### Conversation Panel

- Embedded WhatsApp conversation thread in chronological order
- Visual distinction between customer messages, agent messages, and admin messages
- Admin reply box at the bottom — typing here sends a WhatsApp message from the business number
- 'Take over from agent' toggle — disables AI agent responses for this thread
- Re-enable agent button to hand back to AI after human intervention

#### Activity Timeline

- Auto-generated log of all events on this record
- Admin can add manual notes to the timeline
- Events include: Lead created, Stage changed, Booking created, Escalation triggered, Invoice sent, Admin note added

### 4.4 Pipeline / Kanban View

- Kanban board with a column for each lead stage
- Each card shows: Customer name, service type, last activity date, and assigned admin
- Drag-and-drop to move a card between stages (updates stage in database)
- Filter by date, assigned to, or service type
- Clicking a card opens the full customer detail view

### 4.5 Conversation Inbox

- Unified inbox showing all active WhatsApp conversations
- Tabs: All, Unread, Escalated, Agent-handled, Human-handled
- Each conversation shows: Customer name, last message preview, timestamp, status badge
- Clicking opens the conversation panel with full thread and reply capability
- Notification badge on nav for unread and escalated conversations

### 4.6 Manual Entry: Leads

- Admin can add a new lead by filling in: Name, Phone Number, Source, Initial Service Interest
- New lead is created in 'New Lead' stage and appears in the pipeline

### 4.7 Manual Entry: Orders

- Admin can add a new order for any existing customer
- Required fields: Service Type, Unit Count, Address, Scheduled Date/Time
- Optional fields: Estimated Price, Notes
- Order is created with status 'Confirmed' and linked to the customer record
- New order is also visible in Product 4 (Sales & Reporting Tool)

### 4.8 Search

- Global search bar accessible from all views
- Searches across: Customer name, phone number, order ID, address
- Results grouped by type: Customers, Orders, Conversations

---

## 5. Non-Functional Requirements

| Requirement | Specification | Priority |
|-------------|----------------|----------|
| **Authentication** | Email/password login with role-based access (Admin, Owner, Operator) | Critical |
| **Authorisation** | Admin can view/edit all records; Owner has read-only pipeline and reporting access | Critical |
| **Performance** | List views load in < 2 seconds; detail views < 1 second | High |
| **Real-time Updates** | Conversation inbox and dashboard update in real time without page refresh (WebSocket or SSE) | High |
| **Mobile Responsiveness** | Usable on tablet and mobile for on-the-go access by admin | Medium |
| **Data Export** | All list views can be exported to CSV | High |
| **Audit Log** | All data changes (stage updates, order edits) are logged with user and timestamp | High |
| **Multi-client** | Data is fully isolated per client; no cross-client data access | Critical |

---

## 6. User Stories

| ID | User Story |
|----|-----------|
| **US-C-01** | As an admin, I want to see all new leads in one view so that I can prioritise who to follow up with. |
| **US-C-02** | As an admin, I want to receive an alert when the agent escalates a conversation so that I can respond before the customer waits too long. |
| **US-C-03** | As an admin, I want to view the full WhatsApp conversation thread from within the CRM so that I have full context before replying. |
| **US-C-04** | As an admin, I want to reply to a WhatsApp message directly from the CRM without switching apps. |
| **US-C-05** | As an admin, I want to manually create an order for a customer who called in by phone so that the order is captured in the system. |
| **US-C-06** | As a business owner, I want to see the pipeline Kanban view so that I can see how many leads are at each stage at a glance. |
| **US-C-07** | As an admin, I want to search for a customer by phone number so that I can find their record quickly. |
| **US-C-08** | As an admin, I want to add a note to a customer record so that I can capture context from a phone call. |
| **US-C-09** | As an admin, I want to see all orders for a customer in one place so that I understand their service history before a new appointment. |

---

## 7. UI/UX Considerations

### 7.1 Navigation Structure

| Nav Item | Content |
|----------|---------|
| **Dashboard** | Overview, metrics, alerts, upcoming bookings |
| **Contacts** | Combined leads and customers list view |
| **Pipeline** | Kanban board view of all deals by stage |
| **Inbox** | Conversation inbox — all WhatsApp threads |
| **Orders** | All orders across all customers (also accessible from Product 4) |
| **Settings** | Stage configuration, user management, integrations |

### 7.2 Design Direction

- Clean, data-dense interface — similar to HubSpot or Pipedrive
- Left-side navigation; main content area with contextual right panel for details
- Colour-coded stage badges for quick visual scanning
- Conversation panel uses WhatsApp-like bubble design for familiarity
- Dark mode support as a future enhancement (not Phase 1)

---

## 8. Technical Specifications

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js + React + Tailwind CSS |
| **State Management** | React Query for server state; Zustand for UI state |
| **Real-time** | WebSocket (Socket.IO) or Server-Sent Events for inbox updates |
| **Backend API** | REST API (FastAPI or Node.js); GraphQL considered for v2 |
| **Database** | PostgreSQL with row-level security for multi-tenancy |
| **Auth** | Clerk or Supabase Auth with JWT role claims |
| **WhatsApp Send** | Calls the same WhatsApp Business API used by the agent |
| **Hosting** | Vercel (frontend), Railway/Render (backend) |
| **File Storage** | S3-compatible storage for conversation media attachments |

---

## 9. Acceptance Criteria

| ID | Criterion | Type |
|----|-----------|------|
| **AC-C-01** | New WhatsApp lead appears in CRM within 60 seconds of first message | Pass/Fail |
| **AC-C-02** | Admin can view a full conversation thread and reply from the CRM inbox | Pass/Fail |
| **AC-C-03** | Dragging a card on the Kanban board updates the stage in the database | Pass/Fail |
| **AC-C-04** | Admin can manually create a lead and an order from the CRM | Pass/Fail |
| **AC-C-05** | A manually created order is visible in the Sales Reporting Tool (Product 4) | Pass/Fail |
| **AC-C-06** | Global search returns results by name and phone number within 2 seconds | Pass/Fail |
| **AC-C-07** | Escalated conversations appear with a notification badge and alert banner | Pass/Fail |
| **AC-C-08** | Admin can add a note to a customer record and it appears in the activity timeline | Pass/Fail |
| **AC-C-09** | Owner login can view but not edit pipeline and customer data | Pass/Fail |

---

## 10. Open Questions

| ID | Question | Owner |
|----|----------|-------|
| **OQ-C-01** | Should the CRM support multiple admin users, or is it single-user for the pilot? | Client to confirm |
| **OQ-C-02** | Should stages be fully configurable by the client, or is a fixed set sufficient for Phase 1? | Product decision |
| **OQ-C-03** | Does the owner need a mobile-optimised view for on-the-go pipeline checks? | Client to confirm |
| **OQ-C-04** | Should the CRM support tagging or labelling of customers beyond pipeline stages? | Product decision |
| **OQ-C-05** | Is email integration (Gmail) needed in Phase 1 for customers who contact via email? | Client to confirm |
