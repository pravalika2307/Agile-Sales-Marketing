# End-to-End Business Workflows & Execution Paths

**Platform:** Agile Sales & Marketing  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Full-Stack Architect, Quality Assurance Lead  
**Document Purpose:** Detailed technical walkthroughs with Mermaid sequence diagrams illustrating exact system behavior across the nine core business workflows.

---

## Workflow 1: Manual Lead Creation & Auto-CRM Association

When an SDR or Sales Manager creates a new lead manually in the UI, the system persists the lead and automatically ensures an associated `CRMContact` is created or reused so the prospect is immediately available for campaign enrollment.

```mermaid
sequenceDiagram
    autonumber
    actor User as Sales Rep (SDR)
    participant UI as Leads Page (/leads)
    participant API as Backend (POST /api/v1/leads)
    participant LeadSvc as Lead Generation Service
    participant DB as PostgreSQL Database

    User->>UI: Fills Add Lead form (Name, Email, Company)
    UI->>API: POST /api/v1/leads
    API->>LeadSvc: create_lead(db, org_id, payload)
    LeadSvc->>DB: Check existing Contact by (org_id, lower(email))
    alt Contact Exists
        DB-->>LeadSvc: Return existing Contact
    else Contact Missing
        LeadSvc->>DB: Create new Contact & Company in tenant org
        DB-->>LeadSvc: Return newly created Contact
    end
    LeadSvc->>DB: Insert Lead record with contact_id and company_id
    DB-->>LeadSvc: Persisted Lead
    LeadSvc-->>API: Lead domain object
    API-->>UI: 201 Created (JSON)
    UI->>UI: Closes modal & refreshes Leads table
    UI->>User: Displays success notification
```

---

## Workflow 2: CSV Bulk Lead Import (Current Status & Gap Analysis)

* **Current Implementation State:** **PARTIALLY IMPLEMENTED (BACKEND PREPARED, UI INCOMPLETE)**
* **Execution Path in Code:**
  * Backend model `Lead` supports bulk persistence and external source tracking (`source="csv_import"`, `source_external_id`).
  * Contact deduplication enforces `ix_contacts_org_lower_email` so repeated emails do not create redundant contacts.
* **Gaps Identified:**
  * Frontend lacks a multi-step CSV file dropzone, column header mapping dialog (mapping `Company` -> `company_name`, `Work Email` -> `email`), and pre-import validation error summary table.
  * Currently, leads are imported individually via API or created manually via the Add Lead modal.

---

## Workflow 3: Campaign Contact Enrollment

SDRs enroll contacts from the central CRM pool into an active outbound campaign.

```mermaid
sequenceDiagram
    autonumber
    actor User as Marketing Manager
    participant UI as Campaign Drawer
    participant API as POST /api/v1/campaigns/{id}/contacts
    participant CampSvc as Campaign Service
    participant DB as PostgreSQL Database

    User->>UI: Opens "Enroll Contacts" modal
    UI->>API: GET /api/v1/contacts (Fetch available audience)
    API-->>UI: List of tenant contacts
    User->>UI: Selects contact checkboxes & clicks "Enroll Selected"
    UI->>API: POST /api/v1/campaigns/{id}/contacts {contact_ids: [...]}
    API->>CampSvc: enroll_contacts(db, org_id, campaign_id, contact_ids)
    loop For each contact_id
        CampSvc->>DB: Check existing CampaignContact(campaign_id, contact_id)
        alt Already Enrolled
            CampSvc->>CampSvc: Add to skipped_ids
        else New Contact
            CampSvc->>DB: Insert CampaignContact(status='queued', step=0)
            CampSvc->>CampSvc: Add to enrolled_ids
        end
    end
    DB-->>CampSvc: Commit batch
    CampSvc-->>API: {enrolled_count: X, skipped_count: Y}
    API-->>UI: 200 OK
    UI->>UI: Increments enrolled audience counter & refreshes list
```

---

## Workflow 4: Email Template Creation & Live Contact Preview

Allows campaign managers to design dynamic templates and preview exactly how an email will look for real enrolled contacts before dispatching.

```mermaid
sequenceDiagram
    autonumber
    actor User as Campaign Designer
    participant UI as Sequence Builder Drawer
    participant API as POST /api/v1/campaigns/{id}/steps/{step_id}/preview
    participant Renderer as Template Renderer Engine
    participant DB as PostgreSQL Database

    User->>UI: Enters Subject: "Update for {{company.name}}"<br/>Body: "Hi {{contact.first_name}}..."
    User->>UI: Selects "Maya Sen" from Live Preview dropdown
    UI->>API: POST /steps/{step_id}/preview {contact_id: "..."}
    API->>DB: Query Contact, Company, and CampaignStep
    DB-->>API: Domain records
    API->>Renderer: render_template(subject, body, contact, company)
    Renderer->>Renderer: Substitute contact and company variables
    Renderer->>Renderer: find_unresolved_placeholders()
    Renderer-->>API: {rendered_subject, rendered_body, unresolved: []}
    API-->>UI: 200 OK
    UI->>User: Displays rendered email card in real-time preview
```

---

## Workflow 5: Campaign Outreach Execution & Email Delivery

The campaign execution engine evaluates eligible audience members, generates outreach drafts, checks suppression, and delivers emails via AWS SES.

```mermaid
sequenceDiagram
    autonumber
    actor User as User or Worker
    participant API as POST /api/v1/outreach/{id}/send
    participant OutreachSvc as Outreach Service
    participant DB as PostgreSQL Database
    participant SES as AWS SES Provider (boto3)

    User->>API: POST /api/v1/outreach/{id}/send
    API->>OutreachSvc: send_outreach(db, org_id, outreach_id)
    OutreachSvc->>DB: Lock Outreach row (FOR UPDATE)
    
    alt Contact is opted_out or unsubscribed
        OutreachSvc->>DB: Update status='cancelled', write OutreachEvent
        OutreachSvc-->>API: Raise SuppressedRecipientError (Fail-closed)
    end

    alt Content has unresolved {{tokens}}
        OutreachSvc-->>API: Raise UnresolvedTemplatePlaceholderError
    end

    OutreachSvc->>DB: Update status='sending', write OutreachEvent
    DB-->>OutreachSvc: Committed
    OutreachSvc->>SES: client.send_email(Source, Destination, Message)
    
    alt AWS SES Accepts Message
        SES-->>OutreachSvc: 200 OK (MessageId="0100018f...")
        OutreachSvc->>DB: Update status='sent', sent_at=NOW(), set provider_message_id
        OutreachSvc->>DB: Write OutreachEvent(event_type='sent')
    else AWS SES Rejects (Bounce / Quota)
        SES-->>OutreachSvc: Error (MessageRejected)
        OutreachSvc->>DB: Update status='failed', write OutreachEvent(event_type='failed')
    end
    DB-->>OutreachSvc: Commit
    OutreachSvc-->>API: Outreach domain response
    API-->>User: 200 OK / Error
```

---

## Workflow 6: Retell Voice Call Webhook & Follow-Up Automation

When a prospect completes a call with the AI SDR voice agent, Retell dispatches an asynchronous webhook that triggers variable extraction and automated email follow-ups.

```mermaid
sequenceDiagram
    autonumber
    participant Retell as Retell AI Cloud
    participant Webhook as POST /api/v1/voice/webhook
    participant FollowUpSvc as Voice Follow-Up Engine
    participant DB as PostgreSQL Database
    participant Email as Email Provider (SES/Resend)

    Retell->>Webhook: Webhook Event (call_ended / call_analyzed)<br/>Header: X-Retell-Signature
    Webhook->>FollowUpSvc: verify_webhook_signature(body, secret)
    FollowUpSvc-->>Webhook: Signature Validated
    Webhook->>FollowUpSvc: process_call_event(payload)
    FollowUpSvc->>DB: Insert or Update CallRecord (summary, transcript, outcome)
    
    FollowUpSvc->>FollowUpSvc: Evaluate Decision Rules Engine
    alt Outcome in [MEETING_REQUESTED, INTERESTED, QUALIFIED]
        FollowUpSvc->>DB: Check idempotency key (call_id + followup_type)
        alt Key Exists
            FollowUpSvc->>FollowUpSvc: Skip (Prevent duplicate email)
        else Key New
            FollowUpSvc->>DB: Create Outreach(channel='email', status='sending')
            FollowUpSvc->>Email: Deliver personalized follow-up email
            Email-->>FollowUpSvc: Sent (MessageId)
            FollowUpSvc->>DB: Update CallRecord.followup_status = 'sent'
        end
    else Outcome is NOT_INTERESTED or DO_NOT_CONTACT
        FollowUpSvc->>DB: Mark Contact.lead_status = 'opted_out'
    end
    DB-->>FollowUpSvc: Commit transaction
    FollowUpSvc-->>Webhook: Processed
    Webhook-->>Retell: 200 OK
```

---

## Workflow 7: HubSpot CRM Read-Only Synchronization

Ingests contacts, companies, and deals from HubSpot CRM v3 into the local database without ever mutating external customer records.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Admin User
    participant UI as Integrations Page
    participant API as POST /api/v1/integrations/hubspot/sync
    participant SyncEngine as HubSpot Sync Engine
    participant HubSpot as HubSpot CRM API v3
    participant DB as PostgreSQL Database

    Admin->>UI: Clicks "Run HubSpot Sync"
    UI->>API: POST /api/v1/integrations/hubspot/sync
    API->>SyncEngine: sync_all(db, org_id)
    SyncEngine->>DB: Create HubSpotSyncRun(status='in_progress')
    
    SyncEngine->>HubSpot: GET /crm/v3/objects/contacts (with cursor after)
    HubSpot-->>SyncEngine: Contacts batch JSON
    SyncEngine->>DB: Upsert Contacts matching (org_id, lower(email))
    
    SyncEngine->>HubSpot: GET /crm/v3/objects/companies (with cursor after)
    HubSpot-->>SyncEngine: Companies batch JSON
    SyncEngine->>DB: Upsert Companies matching (org_id, domain)

    SyncEngine->>HubSpot: GET /crm/v3/objects/deals (with cursor after)
    HubSpot-->>SyncEngine: Deals batch JSON
    SyncEngine->>DB: Upsert Deals matching (org_id, hubspot_id)

    SyncEngine->>DB: Update HubSpotSyncRun(status='completed', counts)
    DB-->>SyncEngine: Commit
    SyncEngine-->>API: Summary JSON
    API-->>UI: 200 OK
    UI->>Admin: Displays sync summary badge
```

---

## Workflow 8: Independent Lifecycle Deletions (Lead, Contact, Campaign)

Guarantees safe deletion boundaries where each operation remains completely independent:

```mermaid
graph TD
    subgraph OpA ["Operation A: Delete Lead"]
        DelLead["DELETE /api/v1/leads/{id}"]
        DelLead --> SafeLead["Deletes row from 'leads' table only"]
        SafeLead -.-> PresCRM["Preserves shared CRM Contact"]
        SafeLead -.-> PresCamp["Preserves other campaign memberships"]
    end

    subgraph OpB ["Operation B: Remove Contact from Campaign"]
        RemCont["DELETE /campaigns/{id}/contacts/{contact_id}"]
        RemCont --> DissocOut["Dissociates Outreach (campaign_contact_id = NULL)"]
        DissocOut --> CancDraft["Cancels pending draft/scheduled outreaches"]
        CancDraft --> DelJoin["Deletes CampaignContact join row only"]
        DelJoin -.-> ContIntact["Contact remains in CRM and other campaigns"]
    end

    subgraph OpC ["Operation C: Delete Campaign"]
        DelCamp["DELETE /api/v1/campaigns/{id}"]
        DelCamp --> DissocAllOut["Dissociates all Outreach (campaign_id = NULL)"]
        DissocAllOut --> CancAllDraft["Cancels all pending draft outreaches"]
        CancAllDraft --> DelSteps["Deletes CampaignSteps & CampaignContacts"]
        DelSteps --> DelCampRow["Deletes Campaign row"]
        DelCampRow -.-> HistPres["Historical sent emails & SES message IDs preserved"]
        DelCampRow -.-> ContLeadSafe["Zero contacts or leads deleted globally"]
    end
```
