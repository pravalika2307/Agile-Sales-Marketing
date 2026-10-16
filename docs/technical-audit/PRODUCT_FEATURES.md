# Product Features Inventory & Operational Status Matrix

**Platform:** Agile Sales & Marketing  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Software Architect, Application Auditor  
**Document Purpose:** Complete catalog of all functional capabilities in the platform, documenting frontend components, backend endpoints, database entities, implementation evidence, and operational status.

---

## 1. Feature Status Classification Framework

Every feature is classified into one of six objective categories:
1. **IMPLEMENTED AND VERIFIED:** Code exists, passes automated test suites, and verified in browser workflows.
2. **IMPLEMENTED BUT NOT FULLY VERIFIED:** Backend/frontend code is written and unit-tested, but relies on external live third-party accounts (e.g., live Retell phone numbers or AWS SES production quotas) that have not been triggered in live production.
3. **PARTIALLY IMPLEMENTED:** Core service layer or API exists, but UI integration or automation triggers are incomplete.
4. **CONFIGURATION REQUIRED:** Complete code implementation present, but requires external API credentials or environment configuration to operate.
5. **NOT IMPLEMENTED:** Capability is planned or conceptual, but not present in the code.
6. **BLOCKED OR UNKNOWN:** Implementation is blocked by schema limitations or external dependencies.

---

## 2. Comprehensive Feature Matrix

| Feature Area | Specific Capability | Frontend Path | Backend Endpoint / Service | Status | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Leads** | Manual Lead Creation | `frontend/src/app/leads/page.tsx` | `POST /api/v1/leads` (`lead_generation/service.py`) | **IMPLEMENTED AND VERIFIED** | Verified in browser recording & automated tests. Creates Lead & auto-associates CRMContact. |
| **Leads** | Lead Listing & Search | `frontend/src/app/leads/page.tsx` | `GET /api/v1/leads` | **IMPLEMENTED AND VERIFIED** | Verified search by name, email, company, and temperature filter. |
| **Leads** | Lead ICP Scoring & Qual. | `frontend/src/app/leads/page.tsx` | `POST /api/v1/leads/{id}/evaluate` | **IMPLEMENTED AND VERIFIED** | Verified in `test_lead_qualification_and_routing.py`. Generates score (0-100) and qualification status. |
| **Leads** | Lead Routing Rules | `frontend/src/app/api/routing-rules` | `app/api/v1/routing_rules.py` | **IMPLEMENTED AND VERIFIED** | Tenant-scoped routing by firmographics, score, and geography verified in tests. |
| **Leads** | Independent Lead Deletion | `frontend/src/app/leads/page.tsx` | `DELETE /api/v1/leads/{id}` | **IMPLEMENTED AND VERIFIED** | Row-level deletion modal, tenant verification, and preservation of shared CRMContact verified in browser & tests. |
| **CRM** | Contact Management | `frontend/src/services/crmLeadService.ts` | `GET /api/v1/contacts`, `POST /api/v1/contacts` | **IMPLEMENTED AND VERIFIED** | CRUD, tenant isolation, and company link verified in `test_contacts.py`. |
| **CRM** | Contact Deduplication | Schema Migration `b2c3d4e5f6a7` | `app/core/normalization.py` | **IMPLEMENTED AND VERIFIED** | Case-insensitive lower-email unique index verified in `test_duplicate_prevention.py`. |
| **CRM** | Company Management | `frontend/src/app/companies/page.tsx` | `app/api/v1/companies.py` | **IMPLEMENTED AND VERIFIED** | Company listing, creation, and contact grouping verified in `test_companies.py`. |
| **CRM** | Deals & Pipelines | `frontend/src/app/pipeline/page.tsx` | `app/api/v1/pipeline.py`, `deals.py` | **IMPLEMENTED AND VERIFIED** | Stages, probability weights, amounts, and statuses verified in `test_pipelines.py` and `test_deals.py`. |
| **Campaigns** | Campaign CRUD & Listing | `frontend/src/app/campaigns/page.tsx` | `GET/POST /api/v1/campaigns` | **IMPLEMENTED AND VERIFIED** | Types (`sales_outbound`, `marketing_social`, `hybrid`) and statuses (`draft`, `active`, `paused`, `completed`) verified. |
| **Campaigns** | Contact Enrollment | `frontend/src/components/campaigns/campaign-detail-drawer.tsx` | `POST /api/v1/campaigns/{id}/contacts` | **IMPLEMENTED AND VERIFIED** | Modal search, multi-selection, prevention of duplicate enrollment verified end-to-end. |
| **Campaigns** | Remove Contact from Campaign | `frontend/src/components/campaigns/campaign-detail-drawer.tsx` | `DELETE /api/v1/campaigns/{id}/contacts/{contactId}` | **IMPLEMENTED AND VERIFIED** | Removes campaign membership only; preserves CRM contact, lead, other campaigns, and dissociates historical outreach. |
| **Campaigns** | Independent Campaign Deletion | `frontend/src/app/campaigns/page.tsx` | `DELETE /api/v1/campaigns/{id}` | **IMPLEMENTED AND VERIFIED** | Confirmation modal, cancels pending outreach, preserves historical sent outreach, and deletes campaign steps & enrollments cleanly. |
| **Sequences** | Sequence Builder (Steps) | `frontend/src/components/campaigns/campaign-detail-drawer.tsx` | `app/api/v1/campaign_steps.py` | **IMPLEMENTED AND VERIFIED** | Sequential ordering (`step_number`), delay offsets (`delay_days`, `delay_hours`), and template editing verified in `test_campaign_steps.py`. |
| **Sequences** | Template Variable Resolution | `frontend/src/components/campaigns/campaign-detail-drawer.tsx` | `app/services/campaign_steps/template_renderer.py` | **IMPLEMENTED AND VERIFIED** | Resolves `{{contact.first_name}}`, `{{company.name}}`, `{{sender.name}}`, etc. Verified in `test_campaign_template_rendering.py`. |
| **Sequences** | Live Contact Preview | `frontend/src/components/campaigns/campaign-detail-drawer.tsx` | `POST /api/v1/campaigns/{id}/steps/{step_id}/preview` | **IMPLEMENTED AND VERIFIED** | Verified in `test_live_contact_preview.py`. Preview switches dynamically across enrolled contacts. |
| **Outreach** | Execution Dry-Run Preview | `frontend/src/services/campaignService.ts` | `POST /api/v1/campaigns/{id}/execute/preview` | **IMPLEMENTED AND VERIFIED** | Read-only evaluation of eligible contacts and template rendering without DB mutations. Verified in `test_campaign_execution.py`. |
| **Outreach** | Outreach Creation & Scheduling | `frontend/src/app/outreach/page.tsx` | `app/api/v1/outreach.py` | **IMPLEMENTED AND VERIFIED** | Transitions `draft` -> `scheduled`. Strict status machine verified in `test_outreach.py`. |
| **Outreach** | Synchronous Email Dispatch | `frontend/src/services/outreachService.ts` | `POST /api/v1/outreach/{id}/send` | **IMPLEMENTED AND VERIFIED** | Verified with Mock and SES providers in `test_outreach_send.py` and `test_ses_provider.py`. |
| **Outreach** | Suppression & Opt-Out Guard | Service: `app/services/outreach/service.py` | Checked inside `send_outreach()` | **IMPLEMENTED AND VERIFIED** | Fail-closed check: aborts if contact/lead status is `opted_out` or `unsubscribed`. |
| **Outreach** | Unresolved Token Guard | Service: `app/services/outreach/service.py` | Checked inside `send_outreach()` | **IMPLEMENTED AND VERIFIED** | Blocks dispatch if content contains unreplaced template tokens. |
| **Voice AI** | Retell Webhook Handler | Backend: `app/api/v1/voice_webhook.py` | `POST /api/v1/voice/webhook` | **IMPLEMENTED AND VERIFIED (CODE/TESTS)** | Verifies HMAC-SHA256 signature, extracts structured variables, logs `CallRecord`. Verified in `test_retell_inbound_agent.py`. |
| **Voice AI** | Automated Post-Call Follow-Up | Service: `app/services/outreach/voice_followup.py` | Evaluated in webhook handler | **IMPLEMENTED AND VERIFIED (CODE/TESTS)** | Rules engine triggers follow-up email based on outcome (`MEETING_REQUESTED`, `INTERESTED`), enforces idempotency lock. Verified in `test_retell_voice_email_followup.py`. |
| **Voice AI** | Live Outbound Retell Calling | Scripts: `backend/create_retell_sdr_agent.py` | Retell API Client | **CONFIGURATION REQUIRED** | Code and agent creation scripts exist, but operational outbound calling requires active Retell API key and telephony balance. |
| **HubSpot** | Read-Only CRM Sync | Backend: `app/api/v1/integrations/hubspot.py` | `POST /api/v1/integrations/hubspot/sync` | **IMPLEMENTED AND VERIFIED (CODE/TESTS)** | Ingests Contacts, Companies, and Deals with cursor pagination and logs `HubSpotSyncRun`. Verified in `test_hubspot_sync.py`. |
| **HubSpot** | Status & Audit Inspection | `frontend/src/app/integrations/page.tsx` | `GET /api/v1/integrations/hubspot/status` | **IMPLEMENTED AND VERIFIED** | Displays portal ID, last sync time, contact count, and permission errors without throwing crashes. |
| **Analytics** | Real DB KPI Aggregation | `frontend/src/app/page.tsx`, `analytics/page.tsx` | `GET /api/v1/analytics/overview` | **IMPLEMENTED AND VERIFIED** | Computes totals, breakdown by status, call durations, and pipeline value strictly from genuine rows. Fabricated metrics explicitly disabled. |

---

## 3. Page-by-Page Breakdown (Frontend)

### 3.1. Dashboard (`/`)
* **Purpose:** Executive command center displaying revenue KPIs, lead pipeline health, outreach status breakdown, and call analytics.
* **Components:** `KpiCard`, `ChartCard`, `BarChart`, `LineChart`, `AppShell`.
* **APIs Called:** `GET /api/v1/analytics/overview`, `GET /api/v1/leads?exclude_test=true`.
* **Data Integrity Feature:** Displays neutral zero/empty states if no outreach has been sent. Trend lines and fabricated conversion percentages are never displayed without real underlying event data.

### 3.2. Leads Management (`/leads`)
* **Purpose:** Sourcing, viewing, searching, qualifying, and managing prospect leads.
* **Components:** `LeadsTable`, `AddLeadModal`, `LeadDetailDrawer`, `DeleteLeadConfirmationModal`.
* **User Actions:** Add Lead (creates lead + auto-associates CRM contact), Search by name/email/company, Filter by temperature (Cold, Warm, Hot), Open Lead Detail Drawer, Delete Individual Lead.
* **APIs Called:** `GET /api/v1/leads`, `POST /api/v1/leads`, `DELETE /api/v1/leads/{id}`, `POST /api/v1/leads/{id}/evaluate`.

### 3.3. Campaigns Management (`/campaigns`)
* **Purpose:** Multi-channel outbound marketing campaign orchestration.
* **Components:** `CampaignsTable`, `CampaignDetailDrawer`, `EnrollContactsModal`, `DeleteCampaignConfirmationModal`.
* **User Actions:** Create Campaign, View Sequence Steps, Add/Edit Sequence Step (email subject, body, delay), Live Contact Preview (switches contact tokens in real time), Enroll Contacts, Remove Enrolled Contact, Delete Campaign.
* **APIs Called:** `GET /api/v1/campaigns`, `POST /api/v1/campaigns`, `DELETE /api/v1/campaigns/{id}`, `GET /api/v1/campaigns/{id}/contacts`, `POST /api/v1/campaigns/{id}/contacts`, `DELETE /api/v1/campaigns/{id}/contacts/{contact_id}`, `GET /api/v1/campaigns/{id}/steps`, `POST /api/v1/campaigns/{id}/steps`.

### 3.4. Companies (`/companies`)
* **Purpose:** Target account repository for B2B accounts.
* **Components:** `CompaniesTable`, `CompanyDetailDrawer`, `AddCompanyModal`.
* **APIs Called:** `GET /api/v1/companies`, `POST /api/v1/companies`, `GET /api/v1/companies/{id}`.

### 3.5. Pipeline & Deals (`/pipeline`)
* **Purpose:** Sales pipeline tracking across stages (Prospecting, Qualification, Demo, Proposal, Closed Won, Closed Lost).
* **Components:** `PipelineBoard`, `DealCard`, `AddDealModal`.
* **APIs Called:** `GET /api/v1/pipelines`, `GET /api/v1/deals`, `POST /api/v1/deals`, `PATCH /api/v1/deals/{id}`.

### 3.6. Outreach & Delivery (`/outreach`)
* **Purpose:** Real-time visibility into generated messages, delivery statuses (`draft`, `scheduled`, `sending`, `sent`, `failed`, `cancelled`), and retry actions.
* **Components:** `OutreachTable`, `OutreachDetailDrawer`.
* **APIs Called:** `GET /api/v1/outreach`, `POST /api/v1/outreach/{id}/send`, `POST /api/v1/outreach/{id}/retry`, `POST /api/v1/outreach/{id}/cancel`.

### 3.7. Integrations (`/integrations`)
* **Purpose:** Manage connected CRM, email, and voice service providers.
* **Components:** `IntegrationCard`, `HubSpotSyncModal`, `ProviderStatusBadge`.
* **APIs Called:** `GET /api/v1/integrations/hubspot/status`, `POST /api/v1/integrations/hubspot/sync`.
