# PRD-04: Sales Reporting & Order Management Tool

## Product Requirements Document

---

| Field | Value |
|-------|-------|
| **Client** | Aircon Servicing Company (Pilot) |
| **Users** | Business Owner, Business Admin |
| **Version** | 1.0 |
| **Date** | April 2026 |
| **Status** | Draft — Pending Review |

---

## 1. Product Overview

The Sales Reporting & Order Management Tool is an internal dashboard for the business owner and admin to manage all confirmed service orders, generate invoices, track payment status, and view financial performance metrics. It functions as the financial backbone of the Flow AI platform — turning every completed service job into a trackable, reportable revenue event.

### Core Value Proposition

Instead of managing orders in WhatsApp, tracking invoices in a spreadsheet, and calculating revenue manually, this tool consolidates everything. Every order confirmed by the AI agent — or manually entered by admin — flows here automatically, where it can be managed, invoiced, and reported on.

### 1.1 Goals

- Give the business owner a clear, real-time view of revenue and order performance
- Enable admin to update order status and generate invoices with one click
- Allow filtering and exporting of order data to Excel for P&L analysis
- Replace the client's current manual spreadsheet-based invoicing workflow
- Surface key business metrics without requiring accounting software knowledge
- Be reusable across all future Flow AI clients in any service vertical

### 1.2 Relationship to Other Products

- Receives orders automatically from the AI WhatsApp Agent (Product 2) via shared database
- Shares order records with the CRM (Product 3) — status updates are bidirectional
- Invoices generated here can be sent to customers via WhatsApp or email
- Report exports feed into the client's accountant or bookkeeping workflow

---

## 2. Users & Personas

| Persona | Description | Priority |
|---------|-------------|----------|
| **Business Owner** | Reviews revenue metrics, monitors order completion rates, and downloads monthly P&L reports. Uses this tool weekly. Not technically savvy — expects a clean, number-forward interface. | Primary |
| **Business Admin** | Updates order status to Completed, generates invoices, filters and exports reports. Uses this tool daily after each service job is completed. | Primary |
| **Flow AI Operator** | Configures invoice templates, tax settings, and report parameters. Does not use the tool for daily operations. | Internal |

---

## 3. Order Management

### 3.1 Order List View

The main view of this tool is a filterable, searchable list of all service orders. This is the admin's daily working view.

#### Columns Displayed

- **Order ID** — unique identifier, clickable to open order detail
- **Customer Name** — linked to CRM customer record
- **Service Type** — e.g. Chemical Wash, General Servicing
- **Unit Count** — number of aircon units serviced
- **Scheduled Date** — confirmed appointment date and time
- **Address** — service location
- **Actual Price (SGD)** — final price charged
- **Status** — Pending / Confirmed / In Progress / Completed / Cancelled
- **Invoice Status** — Not Generated / Generated / Sent / Paid
- **Created By** — Agent or Admin
- **Created At** — timestamp

#### Filters

- **Date Range** — filter by scheduled date or created date
- **Status** — multi-select (Pending, Confirmed, Completed, Cancelled)
- **Invoice Status** — Not Generated, Generated, Sent, Paid
- **Service Type** — dropdown from service catalogue
- **Created By** — Agent or Admin

#### Actions from List View

- **Update Status** — inline dropdown to change order status
- **Generate Invoice** — button that creates a PDF invoice for the selected order
- **Export to Excel** — exports the filtered order list to .xlsx with all visible columns
- **Add New Order** — opens a form to manually create a new order

### 3.2 Order Detail View

Clicking an order opens a full detail panel with all information and available actions.

#### Order Information

| Field | Detail |
|-------|--------|
| **Order ID** | Auto-generated (e.g. ORD-2026-0042) |
| **Customer** | Linked customer name, phone, email |
| **Service Type** | From service catalogue dropdown |
| **Unit Count** | Integer field |
| **Service Address** | Full address with postal code |
| **Scheduled Date/Time** | Date and time picker |
| **Estimated Price** | Auto-calculated from service type and unit count |
| **Actual Price** | Editable — may differ from estimate after service |
| **Status** | Dropdown: Pending / Confirmed / Completed / Cancelled |
| **Notes** | Free-text field for admin or technician notes |
| **Payment Method** | Cash / PayNow / Bank Transfer / Other |
| **Payment Status** | Unpaid / Paid |

#### Order Actions

- **Mark as Completed** — updates status to Completed and prompts invoice generation
- **Generate Invoice** — creates and previews a PDF invoice for this order
- **Send Invoice** — sends the invoice to the customer via WhatsApp message or email
- **Mark as Paid** — updates payment status to Paid
- **Cancel Order** — prompts confirmation; sets status to Cancelled
- **Edit Order** — allows modification of editable fields (price, notes, address)

### 3.3 Manual Order Creation

Admin can manually create an order for bookings made outside of WhatsApp (e.g. walk-ins or phone calls).

- Select existing customer or create a new one inline
- Fill in service type, unit count, address, scheduled date/time
- Enter estimated or agreed price
- Order is created with status 'Confirmed' and appears in both this tool and the CRM

---

## 4. Invoice Management

### 4.1 Invoice Generation

Invoices are generated as PDF documents from a pre-designed template. The template includes the client's branding and all required billing information.

#### Invoice Fields

| Field | Detail |
|-------|--------|
| **Invoice Number** | Auto-incremented (e.g. INV-2026-0042) |
| **Issue Date** | Date invoice is generated |
| **Due Date** | Issue Date + configurable payment terms (e.g. 7 days) |
| **Bill To** | Customer name and address |
| **Business Details** | Client company name, address, UEN, contact |
| **Line Items** | Service type, unit count, unit price, subtotal |
| **Subtotal** | Sum of line items |
| **GST (9%)** | Configurable — toggle on/off per client |
| **Total Amount Due** | Subtotal + GST if applicable |
| **Payment Instructions** | Bank account, PayNow QR, or other method |
| **Notes** | Optional additional notes (e.g. 'Thank you for your business!') |

### 4.2 Invoice Actions

- **Preview Invoice** — view the generated PDF in browser before sending
- **Download Invoice** — download PDF to local machine
- **Send via WhatsApp** — sends PDF as a WhatsApp message attachment to the customer's number
- **Send via Email** — sends PDF as an email attachment (requires customer email on record)
- **Mark as Paid** — updates invoice and order payment status

### 4.3 Invoice Template Configuration

- Client logo, company name, address, and UEN configurable in Settings
- Payment terms (e.g. 7 days, 14 days, or due on receipt) configurable per client
- GST toggle — on or off, with rate configurable (default 9% for Singapore)
- Invoice number prefix configurable (e.g. INV- or ACSC-)
- Default payment instructions configurable as free text

#### PDPA & GST Note

For Singapore-based clients, invoices must include the business UEN and, if GST-registered, the GST registration number. The system must make it easy for the client to configure these details accurately.

---

## 5. Sales Dashboard & Reporting

### 5.1 Metrics Dashboard

The top section of the tool displays key business metrics as summary cards and simple charts. This gives the business owner a P&L-oriented view without needing to open a spreadsheet.

#### Summary Metric Cards

| Metric | Definition |
|--------|-----------|
| **Revenue This Month** | Total actual price of all Completed + Paid orders this month (SGD) |
| **Revenue vs Last Month** | Month-on-month revenue change with % delta indicator |
| **Orders This Month** | Total number of orders created this month |
| **Completed Orders** | Count of orders with status Completed |
| **Pending Orders** | Count of orders with status Pending or Confirmed |
| **Outstanding Invoices** | Total value of Generated/Sent invoices that are not yet Paid |
| **Average Order Value** | Total revenue / number of completed orders for the period |
| **Top Service Type** | The service type with the highest order count this month |

#### Charts

- **Revenue Over Time** — bar chart showing daily or weekly revenue for the selected period
- **Orders by Service Type** — pie or bar chart showing order count distribution by service
- **Order Status Breakdown** — stacked bar showing Pending, Completed, Cancelled counts
- **Invoice Status Overview** — pie chart of Not Generated, Generated, Sent, Paid

#### Date Range Filter

- **Presets:** This Week, This Month, Last Month, This Quarter, This Year, Custom Range
- All metrics and charts update dynamically based on selected range

### 5.2 Report Generation & Export

The report export feature allows the business owner or admin to extract filtered order data into an Excel file for use with their accountant or for detailed P&L analysis.

#### Excel Export Columns

| Column | Description |
|--------|-------------|
| **Order ID** | Unique identifier |
| **Invoice Number** | Associated invoice number |
| **Customer Name** | Full name |
| **Customer Phone** | Contact number |
| **Service Type** | Type of service performed |
| **Unit Count** | Number of units |
| **Service Address** | Full address |
| **Scheduled Date** | Appointment date and time |
| **Completed Date** | Date order was marked Completed |
| **Estimated Price (SGD)** | Original estimate |
| **Actual Price (SGD)** | Final price charged |
| **Payment Method** | Cash / PayNow / Bank Transfer |
| **Payment Status** | Unpaid / Paid |
| **Invoice Status** | Not Generated / Generated / Sent / Paid |
| **Created By** | Agent or Admin |
| **Notes** | Admin or technician notes |

#### Export Filters Applied

- All active filters (date range, status, service type) carry over into the export
- Admin can preview row count before exporting
- Export generates an .xlsx file with formatting: header row bold, column widths auto-fitted, currency columns right-aligned

### 5.3 Basic P&L Summary

A simplified P&L summary view, distinct from the main dashboard, that aggregates revenue by month in a table format — suitable for sharing with an accountant.

| Column | Definition |
|--------|-----------|
| **Period** | Month and year |
| **Total Orders** | Count of all orders in that period |
| **Gross Revenue** | Sum of all Actual Prices for Completed orders |
| **Invoiced Amount** | Sum of all invoices generated |
| **Collected Amount** | Sum of invoices marked as Paid |
| **Outstanding Amount** | Invoiced Amount minus Collected Amount |
| **Cancelled Orders** | Count of cancelled orders in period |

This table can be exported to Excel and is date-range selectable (e.g. Jan 2026 – Apr 2026).

---

## 6. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR-R-01** | All orders confirmed by the AI agent must appear in this tool within 60 seconds | Critical |
| **FR-R-02** | Admin can update order status via dropdown in both list and detail views | Critical |
| **FR-R-03** | Invoice PDF can be generated for any order with status Completed | Critical |
| **FR-R-04** | Invoice can be sent to customer via WhatsApp directly from this tool | Critical |
| **FR-R-05** | Order list can be filtered by date range, status, service type, and invoice status | Critical |
| **FR-R-06** | Filtered order list can be exported to a formatted Excel file | Critical |
| **FR-R-07** | Dashboard metrics update in real time when order status changes | High |
| **FR-R-08** | P&L summary table can be generated for any configurable date range | High |
| **FR-R-09** | Admin can manually create a new order with all required fields | High |
| **FR-R-10** | Invoice template is configurable with client branding and GST settings | High |
| **FR-R-11** | Payment status can be marked as Paid; this updates the invoice status accordingly | High |
| **FR-R-12** | Charts on the dashboard are interactive (hover for values, click to filter) | Medium |

---

## 7. Non-Functional Requirements

| Requirement | Specification | Priority |
|-------------|----------------|----------|
| **Performance** | Dashboard metrics load in < 3 seconds; Excel export completes in < 10 seconds for up to 5,000 rows | High |
| **Data Accuracy** | All revenue figures must be accurate to 2 decimal places; no rounding errors in totals | Critical |
| **PDF Quality** | Generated invoices must be print-ready at A4 size with client branding | High |
| **Authentication** | Same role-based auth as CRM; Owner has read-only access to reporting | Critical |
| **Audit Trail** | All status changes and invoice actions logged with user and timestamp | High |
| **Data Isolation** | Financial data is strictly isolated per client | Critical |
| **Export Format** | Excel exports must open correctly in Microsoft Excel and Google Sheets | High |

---

## 8. User Stories

| ID | User Story |
|----|-----------|
| **US-R-01** | As an admin, I want to update an order status to Completed so that the system knows the job is done and I can generate the invoice. |
| **US-R-02** | As an admin, I want to generate an invoice with one click and send it to the customer via WhatsApp so that I don't have to create it manually. |
| **US-R-03** | As a business owner, I want to see this month's revenue at a glance on the dashboard so that I know how the business is performing. |
| **US-R-04** | As a business owner, I want to filter orders by month and export them to Excel so that I can share them with my accountant. |
| **US-R-05** | As an admin, I want to mark an invoice as paid so that I can track which customers have settled their bills. |
| **US-R-06** | As a business owner, I want to see a breakdown of revenue by service type so that I know which services are most profitable. |
| **US-R-07** | As an admin, I want to manually create an order for a customer who booked by phone so that the job is tracked in the system. |
| **US-R-08** | As a business owner, I want to see outstanding (unpaid) invoice amounts so that I can follow up on collections. |
| **US-R-09** | As an admin, I want the exported Excel file to be pre-formatted so that I don't have to clean it up before sharing. |

---

## 9. Technical Specifications

| Component | Technology |
|-----------|-----------|
| **Frontend** | Next.js + React + Tailwind CSS + Recharts for dashboard charts |
| **PDF Generation** | React-PDF or Puppeteer for server-side PDF rendering |
| **Excel Export** | SheetJS (xlsx library) for .xlsx file generation with formatting |
| **Backend** | FastAPI or Node.js API connected to shared PostgreSQL database |
| **Real-time Metrics** | Server-Sent Events or periodic polling (every 30s) for dashboard refresh |
| **Invoice Storage** | Generated PDFs stored in S3-compatible object storage; URL linked to order record |
| **WhatsApp Send** | Calls WhatsApp Business API to send invoice PDF as a document message |
| **Email Send** | SendGrid or AWS SES for invoice email delivery |
| **Auth** | Same auth layer as CRM (Clerk or Supabase Auth) |

---

## 10. Invoice Template Specification

The following defines the PDF invoice layout requirements:

| Element | Specification |
|---------|----------------|
| **Paper Size** | A4 (210 × 297mm), portrait orientation |
| **Header** | Client logo (top-left), 'TAX INVOICE' label (top-right), company name and UEN below logo |
| **Invoice Meta** | Invoice Number, Issue Date, Due Date — aligned right |
| **Bill To** | Customer name and address block — left-aligned below header |
| **Line Items Table** | Description, Qty, Unit Price, Amount — bordered table with header row |
| **Subtotal Block** | Subtotal, GST (if applicable), Total Due — right-aligned |
| **Payment Section** | Payment instructions and PayNow QR code (if enabled) |
| **Footer** | Thank you message, company contact details, PDPA statement |

---

## 11. Acceptance Criteria

| ID | Criterion | Type |
|----|-----------|------|
| **AC-R-01** | An order confirmed by the agent appears in the order list within 60 seconds | Pass/Fail |
| **AC-R-02** | Admin can mark an order as Completed and generate a PDF invoice in < 30 seconds end-to-end | Timed |
| **AC-R-03** | Invoice PDF renders correctly with client branding, line items, and correct totals | Pass/Fail |
| **AC-R-04** | Invoice is sent to customer WhatsApp within 60 seconds of clicking Send | Pass/Fail |
| **AC-R-05** | Excel export for 100 orders completes in < 5 seconds and opens in Microsoft Excel | Timed + Pass/Fail |
| **AC-R-06** | Dashboard revenue metric matches the sum of all Completed order Actual Prices for the selected period | Data Accuracy |
| **AC-R-07** | Filtering by date range and service type correctly reduces the order list | Pass/Fail |
| **AC-R-08** | P&L summary table for a 3-month range is correct and exportable | Pass/Fail |
| **AC-R-09** | Owner login can view dashboard and export reports but cannot edit orders or generate invoices | Pass/Fail |

---

## 12. Open Questions

| ID | Question | Owner |
|----|----------|-------|
| **OQ-R-01** | Is the client GST-registered? This affects whether GST should be applied to invoices. | Client to confirm |
| **OQ-R-02** | What payment terms should be set as default (e.g. due on receipt, 7 days, 14 days)? | Client to confirm |
| **OQ-R-03** | Should invoices be sent automatically upon order completion, or only when admin clicks Send? | Product decision |
| **OQ-R-04** | Should the tool support multiple service line items per order (e.g. servicing + gas top-up in one visit)? | Product decision |
| **OQ-R-05** | Is PayNow QR code generation required on invoices in Phase 1? | Client to confirm |
| **OQ-R-06** | Should revenue reports be accessible to technicians, or is it restricted to Owner and Admin? | Client to confirm |
| **OQ-R-07** | Will the client require integration with accounting software (e.g. Xero, QuickBooks) in future phases? | Future planning |
