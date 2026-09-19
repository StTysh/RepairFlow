# Fixi UI Specification for Frontend–Backend Integration

## Purpose

This document describes the **complete information architecture, visible data, buttons, tabs, statuses, actions, and navigation represented in the current Fixi UI mockups**.

It is intended to help merge the existing frontend UI with a separately developed backend. The backend implementation should be compared against this document to identify:

- frontend fields that do not yet exist in the backend
- backend data that is not yet displayed in the UI
- missing API endpoints
- missing actions / mutations
- missing workflow states
- missing relationships between tickets, properties, tenants, contractors, messages, appointments, files, costs, and history
- placeholder values that should eventually be replaced with backend data

The current UI focuses on one complete demo flow:

**Maintenance Dashboard → Ticket #1042 Roof Leak → Full Property History**

---

# 1. Global Product Information

## Product name

**Fixi**

## Product subtitle

**Properties, solved.**

## Product purpose

Fixi is a property-maintenance management dashboard for letting agencies / property managers.

The UI is designed around maintenance cases that are managed from initial report through diagnosis, contractor coordination, follow-up, and final resolution.

Core workflow:

**Report → Diagnose → Coordinate → Follow up → Verify → Resolve**

---

# 2. Global Application Navigation

The application includes a persistent left sidebar.

## Sidebar navigation items

1. **Overview**
2. **Maintenance**
3. **Properties**
4. **Contractors**
5. **Tenants**
6. **Insights**
7. **Messages**
8. **Reports**

### Active navigation item in the current mockup

**Maintenance**

The active item is visually highlighted.

---

# 3. Sidebar AI Status Card

Near the bottom of the sidebar there is a small AI status card.

## Visible information

- green status indicator
- **AI agent active**
- **Handling 24 tasks**

## Backend data implied

```json
{
  "agent_status": "active",
  "active_task_count": 24
}
```

Potential backend support:

- AI agent online/offline/paused state
- active task count
- agent health
- optional list of active tasks

---

# 4. Sidebar User / Organisation Section

Visible at the bottom of the sidebar:

- User: **Vlad Shuliar**
- Organisation: **Roche Properties**
- Avatar/initials: **VS**

Possible backend structure:

```json
{
  "user": {
    "id": "...",
    "name": "Vlad Shuliar",
    "avatar_url": null
  },
  "organisation": {
    "id": "...",
    "name": "Roche Properties"
  }
}
```

---

# 5. Screen 1 — Maintenance Dashboard

Suggested route:

`/maintenance`

Purpose: show maintenance workload, KPIs, filters, and all active/recent tickets.

---

# 6. Maintenance Dashboard Header

## Title

**Maintenance**

## Subtitle

**All property issues, from report to resolution.**

## Search field

Placeholder:

**Search tickets, addresses, tenants...**

Expected search targets:

- ticket number
- issue title
- property address
- tenant name
- contractor name
- optionally message content

## Notifications button

Bell icon.

Possible behaviour:

- open notifications panel
- display unread count

## New Ticket button

Label:

**+ New Ticket**

Expected behaviour:

- open create-ticket form/page
- create a maintenance case

Potential backend action:

`POST /tickets`

---

# 7. Dashboard KPI Cards

The dashboard currently displays five KPI cards.

## KPI 1

Value: **24**

Label: **Open tickets**

Suggested backend field: `open_ticket_count`

## KPI 2

Value: **8**

Label: **In progress**

Suggested backend field: `in_progress_ticket_count`

## KPI 3

Value: **12**

Label: **Awaiting response**

Suggested backend field: `awaiting_response_ticket_count`

## KPI 4

Value: **156**

Label: **Resolved (30 days)**

Suggested backend field: `resolved_last_30_days`

## KPI 5

Value: **4.7 days**

Label: **Average time to resolve**

Additional badge: **↓ 32%**

Possible backend fields:

```json
{
  "average_resolution_time_days": 4.7,
  "resolution_time_change_percent": -32
}
```

The backend should define what period the comparison uses, e.g. previous 30 days.

---

# 8. Dashboard Filters

## Status filter buttons

- **All**
- **Open**
- **In progress**
- **Waiting**
- **Resolved**

Expected behaviour: selecting a filter updates the ticket list.

## Priority dropdown

Default: **All priorities**

Possible values:

- High
- Medium
- Low

## Property dropdown

Default: **All properties**

Expected behaviour: filter tickets by property.

---

# 9. Maintenance Ticket Table

Columns:

1. **#**
2. **Issue**
3. **Address**
4. **Priority**
5. **Status**
6. **Assigned to**
7. **Updated**
8. row actions / ellipsis menu

---

# 10. Ticket Table Demo Data

## Ticket #1042

- ID: **1042**
- Issue: **Roof leak**
- Address: **14 King Street, E17**
- Priority: **High**
- Status: **In progress**
- Assigned to: **ABC Roofing**
- Updated: **2h ago**

This is the main clickable demo ticket.

## Ticket #1041

- Issue: **No heating**
- Address: **27 Maple Road, N1**
- Priority: **High**
- Status: **Awaiting tenant**
- Assigned to: **London Heat Ltd**
- Updated: **5h ago**

## Ticket #1040

- Issue: **Leaking pipe**
- Address: **8 Station View, W3**
- Priority: **Medium**
- Status: **Diagnosing**
- Assigned to: none
- Updated: **6h ago**

## Ticket #1039

- Issue: **Broken boiler**
- Address: **12 Oak Avenue, SE3**
- Priority: **High**
- Status: **Contractor booked**
- Assigned to: **HeatRight**
- Updated: **1 day ago**

## Ticket #1038

- Issue: **Electrical issue**
- Address: **90 Riverdale Rd, SW6**
- Priority: **Medium**
- Status: **In progress**
- Assigned to: **PowerFix**
- Updated: **1 day ago**

## Ticket #1037

- Issue: **Mould in bathroom**
- Address: **3 Wellington Close, AL8**
- Priority: **Medium**
- Status: **Awaiting response**
- Assigned to: none
- Updated: **2 days ago**

## Ticket #1036

- Issue: **Window won't close**
- Address: **21 Birch Lane, N8**
- Priority: **Low**
- Status: **Scheduled**
- Assigned to: **HomeFix**
- Updated: **2 days ago**

## Ticket #1035

- Issue: **Water pressure**
- Address: **5 Church Road, E11**
- Priority: **Low**
- Status: **Resolved**
- Assigned to: **FlowTech**
- Updated: **3 days ago**

---

# 11. Ticket Row Actions

Each ticket row includes an ellipsis / more-actions button.

Potential actions:

- Open ticket
- Edit ticket
- Assign contractor
- Change status
- View property
- View tenant
- View contractor
- View full history
- Archive
- Mark resolved
- Cancel

Not all need to be implemented immediately, but the frontend implies an actions menu exists.

---

# 12. Screen 2 — Ticket Detail

Suggested route:

`/maintenance/tickets/1042`

Main example ticket:

**#1042 – Roof leak**

Property:

**14 King Street, Walthamstow, E17 6QX**

This is the key operational screen.

---

# 13. Ticket Detail Header

## Back control

**Back to tickets**

Expected behaviour: return to maintenance dashboard.

## Priority badge

**High**

Possible values:

- High
- Medium
- Low

## Ticket title

**#1042 – Roof leak**

## Property address

**14 King Street, Walthamstow, E17 6QX**

## Ticket status dropdown

Current value: **In progress**

Expected behaviour: allow status change.

Potential backend mutation:

`PATCH /tickets/{id}/status`

---

# 14. Ticket Detail Header Buttons

## Share

Button: **Share**

Possible behaviour:

- copy ticket link
- create shareable link
- share internally
- share with landlord/contractor

## Edit

Button: **Edit**

Expected behaviour: edit ticket details.

## More menu

Ellipsis button.

Possible actions:

- archive
- cancel
- escalate
- reassign
- duplicate
- mark resolved
- delete

---

# 15. Ticket Detail Tabs

Current design uses these top-level tabs:

1. **Overview**
2. **Property**
3. **Files**
4. **Costs**

The earlier mockup included a separate Messages tab, but the revised design moves recent communication into the main Overview screen. A full Messages page can still exist later if useful.

---

# 16. Overview Tab Structure

The Overview tab contains:

1. ticket progress tracker
2. case overview column
3. agent timeline column
4. latest messages column
5. property history preview
6. link to full property history

---

# 17. Ticket Progress / Workflow Tracker

A horizontal tracker appears near the top.

## Stage 1 — Reported

Timestamp: **12 Sep, 10:24**

State: completed

## Stage 2 — Diagnosing

Timestamp: **12 Sep, 11:02**

State: completed

## Stage 3 — Contractor on site

State: current

## Stage 4 — Follow up

State: upcoming

## Stage 5 — Resolved

State: upcoming

Possible backend structure:

```json
{
  "workflow": [
    {"stage": "reported", "status": "completed", "timestamp": "2026-09-12T10:24:00"},
    {"stage": "diagnosing", "status": "completed", "timestamp": "2026-09-12T11:02:00"},
    {"stage": "contractor_on_site", "status": "current", "timestamp": null},
    {"stage": "follow_up", "status": "pending", "timestamp": null},
    {"stage": "resolved", "status": "pending", "timestamp": null}
  ]
}
```

---

# 18. Ticket Overview — Three-Column Layout

Below the progress tracker, the detail view uses three columns:

1. **Case overview**
2. **Agent timeline**
3. **Latest messages**

This is a core UI requirement.

---

# 19. Column 1 — Case Overview

## Section title

**Case overview**

## Current case summary

Current demo text:

> Tenant reports water coming through the ceiling in the bedroom after heavy rain. Similar issue reported 4 months ago. Contractor on site inspecting the roof. Next step depends on findings (possible scaffolding required).

This should eventually be generated from current backend state.

Suggested field: `case_summary`

The summary should answer:

- what happened
- what is happening now
- what was previously attempted
- who is responsible now
- what is blocking progress
- what likely happens next

---

# 20. Issue Photos / Attachments

The overview displays image thumbnails.

Examples:

- ceiling water damage
- roof exterior
- additional photos

A final thumbnail may display **+2**, indicating more attachments.

Possible attachment model:

```json
{
  "id": "...",
  "ticket_id": "...",
  "type": "image",
  "url": "...",
  "uploaded_by_type": "tenant",
  "uploaded_by_id": "...",
  "created_at": "..."
}
```

Supported future attachment types:

- image
- video
- PDF
- contractor report
- invoice
- audio

---

# 21. Tenant Information

Section label: **Tenant**

Visible example:

- Name: **James Doe**
- Phone: **+44 7700 123456**

Action icons/buttons:

- message
- email
- phone/call

Possible backend structure:

```json
{
  "tenant": {
    "id": "...",
    "name": "James Doe",
    "phone": "+44 7700 123456",
    "email": "...",
    "preferred_language": "en"
  }
}
```

---

# 22. Assigned Contractor

Section label: **Assigned contractor**

Visible example:

- Company: **ABC Roofing**
- Specialisation: **Roofing Specialist**
- Phone: **+44 20 7946 0011**

Button: **View profile**

Expected behaviour: open contractor profile.

Possible route:

`/contractors/{id}`

---

# 23. Next Appointment

Section label: **Next appointment**

Visible:

- **Tomorrow, 14 Sep 2026**
- **15:00 – 17:00**

Button: **Reschedule**

Expected behaviour:

- change appointment time
- preserve appointment history
- ideally account for tenant and contractor availability

Possible model:

```json
{
  "appointment": {
    "id": "...",
    "ticket_id": "...",
    "contractor_id": "...",
    "tenant_id": "...",
    "start_at": "...",
    "end_at": "...",
    "status": "scheduled"
  }
}
```

---

# 24. Property History Preview in Ticket View

The ticket detail screen includes a compact preview of previous work on the same property.

Visible example rows:

### May 2026

- Issue: **Roof leak**
- Status: **Resolved**
- Outcome: **Flashing replaced by ABC Roofing**

### Nov 2025

- Issue: **Gutter blockage**
- Status: **Resolved**
- Outcome: **Gutters cleared**

### Feb 2025

- Issue: **Damp in bedroom**
- Status: **Resolved**
- Outcome: **No further issues**

### Oct 2024

- Issue: **Roof leak**
- Status: **Resolved**
- Outcome: **Minor repair**

Button/link at bottom:

**View full property history**

---

# 25. Column 2 — Agent Timeline

## Section title

**Agent timeline**

## Subtitle

**What the AI agent has done and what's next.**

This is a chronological operational log of AI actions, decisions, and pending next steps.

---

# 26. Agent Timeline Example Events

## Event 1 — Analysed issue

Description:

**Identified as likely roof leak based on tenant description and photos.**

Timestamp: **12 Sep, 10:26**

State: completed

## Event 2 — Checked property history

Description:

**Found similar issue in May 2026. Previous repair may not have fully resolved the underlying cause.**

Timestamp: **12 Sep, 10:27**

State: completed

## Event 3 — Selected contractor

Description:

**Chose ABC Roofing (highest rating, available this week).**

Timestamp: **12 Sep, 10:31**

State: completed

## Event 4 — Contacted tenant

Description:

**Confirmed access for inspection.**

Timestamp: **12 Sep, 10:34**

State: completed

## Event 5 — Contractor on site

Description:

**ABC Roofing has arrived and is inspecting the roof.**

Timestamp: **12 Sep, 12:05**

State: current

## Event 6 — Waiting for contractor update

Description:

**Contractor will provide findings and next steps.**

State: pending/current

## Event 7 — Plan next steps

Description:

**May require scaffolding or further investigation.**

State: upcoming

---

# 27. Agent Timeline Backend Requirements

Recommended event model fields:

- event ID
- ticket ID
- event type
- title
- description
- actor type
- actor ID if applicable
- event state
- timestamp
- metadata

Suggested event types:

- issue_received
- issue_analysed
- history_checked
- contractor_selected
- contractor_contacted
- tenant_contacted
- appointment_scheduled
- appointment_rescheduled
- contractor_arrived
- contractor_update_received
- follow_up_requested
- quote_requested
- quote_approved
- repair_completed
- tenant_confirmation_requested
- resolution_verified
- escalation_required
- human_intervention_requested
- case_closed

Example:

```json
{
  "id": "...",
  "ticket_id": "1042",
  "type": "contractor_selected",
  "title": "Selected contractor",
  "description": "Chose ABC Roofing...",
  "actor_type": "ai_agent",
  "status": "completed",
  "created_at": "..."
}
```

---

# 28. Column 3 — Latest Messages

## Section title

**Latest incoming messages**

## Subtitle

**Messages, calls and updates from all parties.**

This panel displays the latest communication associated with the case.

The feed should normally show the newest updates first.

---

# 29. Possible Message Sources

- Tenant
- Contractor
- AI Agent
- Property manager
- Landlord
- System
- Phone call transcript
- Email
- SMS
- WhatsApp
- Web chat

---

# 30. Latest Messages Demo Content

## Message 1

Sender: **Contractor (ABC Roofing)**

Time: **12:05**

> On site now. Initial inspection shows possible flashing issue. Need to check under tiles. Will update shortly.

## Message 2

Sender: **AI Agent**

Time: **12:06**

> Thanks. Please take photos of the flashing and let me know if scaffolding is required.

## Message 3

Sender: **Tenant (James Doe)**

Time: **11:48**

> That's great. I'm at work today — please use the back entrance if needed.

## Message 4

Sender: **AI Agent**

Time: **11:49**

> Noted. I've informed the contractor about access. I'll keep you updated.

## Message 5

Sender: **Tenant**

Time: **10:28**

> Here are some more photos of the ceiling. The leak seems worse after last night's rain.

This message includes image attachments.

---

# 31. Latest Messages Controls

Potential controls shown/implied by the UI:

- **View all**
- open message
- open image/file attachment
- contact sender
- view call transcript
- reply

The current prototype can initially make only **View all** / attachments functional if time is limited.

---

# 32. Unified Communication Backend Model

Recommended conceptual shape:

```json
{
  "id": "...",
  "ticket_id": "1042",
  "sender_type": "tenant",
  "sender_id": "...",
  "recipient_type": "ai_agent",
  "channel": "phone",
  "direction": "incoming",
  "content": "...",
  "transcript": "...",
  "attachments": [],
  "created_at": "..."
}
```

Useful channel values:

- phone
- SMS
- email
- WhatsApp
- web
- internal_ai
- contractor_portal

---

# 33. Call / Voice Transcript Support

Because the product is intended to support AI calls, a communication may originate from a voice conversation.

Useful backend fields:

- call ID
- caller
- recipient
- start time
- end time
- duration
- status
- audio recording URL if retained
- original transcript
- translated transcript
- detected/original language
- AI-generated summary
- extracted action items

Example:

```json
{
  "channel": "phone",
  "original_language": "uk",
  "transcript_original": "...",
  "transcript_english": "...",
  "summary": "...",
  "action_items": []
}
```

---

# 34. Full History CTA

At the bottom of the latest-messages panel there is a CTA card.

## Heading

**Need the full history?**

## Description

**See all previous issues, repairs and documents for this property.**

## Button

**View full history**

Expected behaviour: open full property history screen.

---

# 35. Screen 3 — Full Property History

Suggested route:

`/properties/{property_id}/history`

Example:

`/properties/14-king-street/history`

This can be a dedicated page, modal, or side sheet. For the prototype, a dedicated page is acceptable.

---

# 36. Property History Header

Title:

**Property history**

Address:

**14 King Street, Walthamstow, E17 6QX**

Optional property photo displayed in header.

Close/back control should return to the ticket detail page.

---

# 37. Property History Summary Cards

## Card 1

Value: **3**

Label: **Active tickets**

## Card 2

Value: **8**

Label: **Total tickets**

## Card 3

Value: **2**

Label: **Repeat issues**

## Card 4

Value: **2021**

Label: **Built**

---

# 38. Property History Tabs

Tabs:

1. **Maintenance history**
2. **Property details**
3. **Documents**
4. **Notes**

Default active tab:

**Maintenance history**

---

# 39. Maintenance History Table

Columns:

1. **Date**
2. **Issue**
3. **State**
4. **Outcome**
5. **Contractor**
6. **Cost**
7. **View**

---

# 40. Full Property History Demo Records

## May 2026

- Issue: **Roof leak**
- State: **Resolved**
- Outcome: **Flashing replaced**
- Contractor: **ABC Roofing**
- Cost: **£620**

## Nov 2025

- Issue: **Gutter blockage**
- State: **Resolved**
- Outcome: **Gutters cleared**
- Contractor: **City Gutters**
- Cost: **£180**

## Feb 2025

- Issue: **Damp in bedroom**
- State: **Resolved**
- Outcome: **No further issues**
- Contractor: **HomeFix**
- Cost: **£350**

## Oct 2024

- Issue: **Roof leak**
- State: **Resolved**
- Outcome: **Minor repair**
- Contractor: **ABC Roofing**
- Cost: **£240**

## Jun 2024

- Issue: **Broken tile**
- State: **Resolved**
- Outcome: **Tile replaced**
- Contractor: **Local Builders**
- Cost: **£120**

## Jan 2024

- Issue: **Boiler service**
- State: **Resolved**
- Outcome: **Annual service**
- Contractor: **HeatRight**
- Cost: **£90**

## Aug 2023

- Issue: **Leak under sink**
- State: **Resolved**
- Outcome: **Pipe replaced**
- Contractor: **PlumbPro**
- Cost: **£210**

## Mar 2023

- Issue: **Electrical issue**
- State: **Resolved**
- Outcome: **Socket replaced**
- Contractor: **PowerFix**
- Cost: **£160**

## Sep 2022

- Issue: **Damp in hallway**
- State: **Resolved**
- Outcome: **Ventilation improved**
- Contractor: **HomeFix**
- Cost: **£300**

## Apr 2022

- Issue: **Roof inspection**
- State: **Resolved**
- Outcome: **No issues found**
- Contractor: **ABC Roofing**
- Cost: **£80**

## Nov 2021

- Issue: **Heating issue**
- State: **Resolved**
- Outcome: **Thermostat replaced**
- Contractor: **HeatRight**
- Cost: **£180**

---

# 41. History Row View Action

Each row includes a right-arrow / view action.

Expected behaviour:

- open historic ticket details
- show repair details
- show contractor report
- show attachments/messages if available

Possible route:

`/maintenance/tickets/{historic_ticket_id}`

---

# 42. Property Details Tab

Potential information:

- full address
- postcode
- property type
- year built
- number of bedrooms
- number of bathrooms
- landlord
- current tenant(s)
- access instructions
- alarm / entry notes
- emergency contacts
- warranties
- appliances
- insurer information
- approved/preferred contractors
- spending approval threshold
- landlord maintenance preferences

---

# 43. Documents Tab

Potential document categories:

- inspection reports
- invoices
- quotes
- contractor reports
- warranties
- tenancy documents
- compliance documents
- property certificates
- photos
- videos

Possible controls:

- preview
- download
- upload
- delete
- link to ticket

---

# 44. Notes Tab

Potential content:

- internal property-manager notes
- landlord preferences
- tenant preferences
- access notes
- known recurring problems
- contractor notes
- AI-generated insights

---

# 45. Status / Badge System

Current UI implies the following ticket/workflow states:

- Open
- Diagnosing
- In progress
- Awaiting tenant
- Awaiting response
- Contractor booked
- Scheduled
- Contractor on site
- Follow up
- Resolved

Recommended backend enum may include:

```text
OPEN
DIAGNOSING
AWAITING_TENANT
AWAITING_CONTRACTOR
AWAITING_RESPONSE
CONTRACTOR_SELECTED
CONTRACTOR_BOOKED
SCHEDULED
CONTRACTOR_ON_SITE
IN_PROGRESS
FOLLOW_UP
AWAITING_CONFIRMATION
RESOLVED
CLOSED
ESCALATED
CANCELLED
```

---

# 46. Priority System

Current visible values:

- High
- Medium
- Low

Possible backend enum:

```text
HIGH
MEDIUM
LOW
```

Future optional value:

- Emergency / Critical

---

# 47. Core Data Entities Implied by the UI

The frontend implies these backend entities or concepts:

## User

Logged-in property-management user.

## Organisation / Agency

Company using Fixi.

## Property

Managed residence/building/unit.

## Tenant

Resident associated with a property.

## Landlord

Property owner. Not prominent in the current UI, but likely required operationally.

## Ticket / Maintenance Case

Primary repair case.

## Contractor

Company/person doing repair work.

## Appointment

Scheduled visit involving property, tenant and/or contractor.

## Communication / Message

Calls, email, SMS, WhatsApp, AI messages, web messages, etc.

## Attachment

Photo, video, report, invoice, document, recording.

## Agent Timeline Event

AI action, system action, decision, or workflow state change.

## Cost / Quote / Invoice

Financial information linked to repair work.

## Notification

Alerts for the user.

## Property History

Can be generated from historical ticket records rather than requiring a separate entity.

---

# 48. Suggested Core Ticket Response Shape

A ticket endpoint should expose enough data to render the complete detail screen.

Conceptual example:

```json
{
  "id": "1042",
  "ticket_number": 1042,
  "title": "Roof leak",
  "description": "Tenant reports water coming through ceiling...",
  "summary": "...",
  "priority": "high",
  "status": "in_progress",
  "created_at": "...",
  "updated_at": "...",
  "property": {},
  "tenant": {},
  "landlord": {},
  "assigned_contractor": {},
  "attachments": [],
  "appointments": [],
  "timeline": [],
  "messages": [],
  "costs": [],
  "workflow": [],
  "related_history": []
}
```

---

# 49. Backend Functions Required by the Current UI

## Dashboard

- get KPI counts
- list tickets
- search tickets
- filter tickets
- filter by property
- filter by priority
- sort ticket list
- create ticket

## Ticket detail

- get ticket
- update ticket
- change status
- change priority
- share ticket
- assign contractor
- view related property
- view tenant
- view contractor

## Scheduling

- create appointment
- reschedule appointment
- cancel appointment
- confirm appointment
- get contractor availability
- get tenant availability

## Messages / communication

- list ticket communications
- send message
- store incoming tenant message
- store incoming contractor message
- store AI outgoing message
- store call transcript
- store translation
- attach files
- mark message read

## Agent timeline

- list workflow events
- create event
- update event state
- identify current event
- identify next step

## Property history

- list all property tickets
- calculate active ticket count
- calculate total ticket count
- identify repeat issues
- display historic outcomes
- display contractor
- display cost
- open historic case

## Files

- upload file
- list files
- preview file
- attach file to ticket/message

## Costs

- add estimate
- add quote
- approve quote
- add invoice
- calculate final cost

---

# 50. AI-Specific Backend Capabilities Implied by the Product

The complete product concept may require backend support for:

- issue classification
- urgency detection
- structured diagnosis
- follow-up question generation
- property-history analysis
- repeat-issue detection
- cross-ticket pattern detection
- contractor selection
- appointment coordination
- tenant communication
- contractor communication
- multilingual interaction
- speech-to-text / transcription
- translation
- message summarisation
- case summary generation
- next-step reasoning
- automatic follow-up
- human escalation
- resolution verification

---

# 51. Resolution Verification Requirement

A contractor marking work as completed should **not automatically mean the case is resolved**.

The product concept requires separate states such as:

1. contractor work completed
2. follow-up due
3. awaiting tenant confirmation
4. outcome verified
5. resolved

Possible backend fields:

```json
{
  "contractor_marked_complete": true,
  "tenant_confirmed_resolved": false,
  "resolution_verified": false
}
```

This is important because Fixi is intended to manage **outcomes**, not merely work-order completion.

---

# 52. Repeat Issue Detection

The property history intentionally shows repeated roof-related issues.

Examples:

- Oct 2024 — Roof leak
- May 2026 — Roof leak
- Sep 2026 — current roof leak

The backend should ideally support:

- repeat issue flag
- related historic tickets
- similarity/confidence score if AI-generated
- explanation of relationship

Example:

```json
{
  "is_repeat_issue": true,
  "related_ticket_ids": ["...", "..."]
}
```

---

# 53. AI Case Summary Requirement

The summary shown in the Case Overview should ideally be generated from live state, including:

- original report
- latest messages
- contractor findings
- appointments
- previous repairs
- current workflow state
- AI decisions

The summary should be concise and answer:

- What happened?
- What is happening now?
- What has already been tried?
- Is this a repeat issue?
- Who is responsible for the next action?
- What is the blocker?
- What is the next expected step?

---

# 54. Current Hardcoded / Mock Information

Unless already represented in the backend, treat the following as demo data:

- 24 open tickets
- 8 in progress
- 12 awaiting response
- 156 resolved in 30 days
- 4.7 day average resolution time
- 32% improvement
- ticket #1042 and all example ticket rows
- James Doe
- ABC Roofing
- example phone numbers
- appointment date/time
- current case summary
- all timeline events
- all message text
- property history
- historical costs
- build year
- repeat issue count

During integration, replace these with backend values where available.

---

# 55. Frontend–Backend Comparison Checklist

## Dashboard

- [ ] Open ticket count
- [ ] In-progress count
- [ ] Awaiting-response count
- [ ] Resolved-last-30-days count
- [ ] Average resolution time
- [ ] Resolution-time trend
- [ ] Ticket search
- [ ] Status filter
- [ ] Property filter
- [ ] Priority filter

## Ticket

- [ ] Ticket ID
- [ ] Ticket number
- [ ] Title
- [ ] Description
- [ ] Current summary
- [ ] Priority
- [ ] Status
- [ ] Created timestamp
- [ ] Updated timestamp

## Property

- [ ] Property ID
- [ ] Address
- [ ] Postcode
- [ ] Property image
- [ ] Year built
- [ ] Maintenance history
- [ ] Active ticket count
- [ ] Total ticket count
- [ ] Repeat issue count

## Tenant

- [ ] Tenant ID
- [ ] Name
- [ ] Phone
- [ ] Email
- [ ] Preferred language
- [ ] Preferred communication channel

## Contractor

- [ ] Contractor ID
- [ ] Company/name
- [ ] Phone
- [ ] Speciality
- [ ] Availability
- [ ] Assigned ticket

## Appointment

- [ ] Appointment ID
- [ ] Start time
- [ ] End time
- [ ] Tenant
- [ ] Contractor
- [ ] Status
- [ ] Reschedule action

## Timeline

- [ ] Event ID
- [ ] Type
- [ ] Title
- [ ] Description
- [ ] Timestamp
- [ ] Actor
- [ ] Status

## Messages

- [ ] Sender
- [ ] Recipient
- [ ] Channel
- [ ] Direction
- [ ] Timestamp
- [ ] Body
- [ ] Attachments
- [ ] Call transcript
- [ ] Language
- [ ] Translation

## History

- [ ] Date
- [ ] Issue
- [ ] State/status
- [ ] Outcome
- [ ] Contractor
- [ ] Cost
- [ ] Historic ticket link

## Attachments

- [ ] Type
- [ ] URL/file reference
- [ ] Uploaded by
- [ ] Uploaded at
- [ ] Ticket/message relationship

## Costs

- [ ] Estimate
- [ ] Quote
- [ ] Approved amount
- [ ] Invoice
- [ ] Final cost

---

# 56. Recommended Behaviour When Backend Data Is Missing

If the UI expects data that the backend does not currently expose:

1. do not automatically remove the UI element
2. determine whether the field is core to the product flow
3. if core, add the missing backend model/field/endpoint
4. if prototype-only, keep a temporary placeholder
5. map equivalent fields instead of creating duplicates
6. standardise frontend/backend names where practical

---

# 57. Recommended Integration Priority

## Priority 1 — Working demo flow

Implement/connect first:

1. Maintenance dashboard
2. Ticket list
3. Click ticket #1042
4. Ticket detail data
5. Workflow progress state
6. Case summary
7. Tenant details
8. Contractor details
9. Appointment
10. Agent timeline
11. Latest messages
12. Full property history

## Priority 2 — Interactive actions

Then:

1. status changes
2. reschedule appointment
3. contractor profile
4. file/image viewing
5. ticket editing
6. message sending
7. new ticket creation

## Priority 3 — AI automation

Then:

1. generated summaries
2. automatic timeline events
3. contractor selection
4. tenant/contractor communication
5. multilingual calls/messages
6. automatic follow-up
7. repeat issue detection
8. resolution verification

---

# 58. Complete Intended UI Flow

```text
Maintenance Dashboard
    ↓
Click #1042 Roof Leak
    ↓
Ticket Detail
    ├── Progress / workflow tracker
    ├── Case overview
    │     ├── Current summary
    │     ├── Photos / attachments
    │     ├── Tenant
    │     ├── Contractor
    │     ├── Next appointment
    │     └── Property history preview
    ├── Agent timeline
    └── Latest messages
          ↓
      View full history
          ↓
Property History
    ├── Maintenance history
    ├── Property details
    ├── Documents
    └── Notes
```

---

# 59. Key Product Principle

The UI is built around the principle:

> **Existing systems manage tickets. Fixi manages outcomes.**

The backend should therefore track more than whether a contractor completed a job. It should support:

- original problem state
- diagnosis
- repair attempts
- communications
- appointments
- contractor findings
- previous failures
- recurring issues
- follow-ups
- tenant confirmation
- resolution verification
- chronological AI actions
- complete property history

The final **Resolved** state should represent a genuinely verified resolution rather than simply a contractor marking a work order complete.

---

# 60. Final Instructions for the Merge

When comparing the UI against the existing backend, categorise every mismatch into one of these groups:

### A. Backend already supports it
Connect the frontend to the existing field/endpoint.

### B. Backend supports equivalent data under a different name
Map or rename it instead of duplicating it.

### C. UI requires data/functionality that the backend does not support yet
Add the necessary model, field, endpoint, workflow, event, or service.

### D. Backend contains useful data not currently represented in the UI
Decide whether it should be exposed in the frontend.

### E. UI data is prototype-only
Keep it mocked until it is needed.

The goal is not to force the backend to mirror the frontend literally. The goal is to make sure the final application has enough data, relationships, endpoints, workflow state, and actions to support **every visible UI element and every intended user interaction** in the Fixi prototype.
