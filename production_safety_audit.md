# Agile Sales & Marketing — Production-Readiness & Safety Verification Audit

**Audit Date:** October 12, 2026  
**Audited Systems:** Backend API (FastAPI), Database (PostgreSQL), CRM & Sync (HubSpot v3), Campaigns, Outreach Delivery, Voice Integration (Retell AI), Lead Qualification & Routing  
**Mode:** Strict Read-Only Investigation (No modifications made, no emails sent, no calls placed, no secrets exposed)  
**Deliverable File:** `production_safety_audit.md`

---

## Executive Summary

An exhaustive, read-only production-readiness safety audit of the **Agile Sales & Marketing** platform was conducted across six mandatory domains:
1. **HubSpot Synchronization**
2. **Duplicate Data**
3. **Email and Voice Safety**
4. **Duplicate Assignments and Enrollments**
5. **Data Integrity and Security**
6. **Campaign and Analytics Accuracy**

The audit confirmed that core campaign execution rules, database enrollment constraints, analytics aggregations, and automated test provider isolation are securely designed and safe. However, critical vulnerabilities and defect risks were identified in **tenant authorization for public integration routes**, **webhook fallback tenant resolution**, **suppression check gaps in manual outreach dispatch**, and **the absence of database-level uniqueness constraints on contacts and companies**.

Below is the consolidated audit matrix followed by detailed findings with evidence, actual behavior, business impact, recommended fixes, and safe verification methods.

---

## Consolidated Audit Matrix

| ID | Domain | Subject | Severity | Classification | Status |
|---|---|---|---|---|---|
| **SEC-01** | Data Integrity & Security | Unauthenticated HubSpot Integration Endpoints | **Critical** | Confirmed Defect | Open |
| **SEC-02** | Data Integrity & Security | Webhook Fallback Tenant Resolution (`SELECT ... LIMIT 1`) | **High** | Confirmed Defect | Open |
| **SEC-03** | Data Integrity & Security | Unauthenticated SES Webhook Handler | **Medium** | Confirmed Defect | Open |
| **SAF-01** | Email & Voice Safety | Missing Opt-Out Suppression Guard in `send_outreach()` | **High** | Confirmed Defect | Open |
| **SAF-02** | Email & Voice Safety | Unauthenticated Voice Replay Endpoint in Development | **Medium** | Potential Risk | Open |
| **SAF-03** | Email & Voice Safety | Automated Test Email Provider Isolation | **Low** | Verified Safe Behavior | Passed |
| **DUP-01** | Duplicate Data | Confirmed Duplicate Contact in Database | **Medium** | Confirmed Defect | Open |
| **DUP-02** | Duplicate Data | Missing DB Unique Constraints on Contacts & Companies | **High** | Potential Risk | Open |
| **DUP-03** | Duplicate Data | Shared HubSpot Access Token Causing Cross-Tenant Duplication | **Medium** | Potential Risk | Open |
| **HS-01** | HubSpot Sync | Inbound-Only Synchronization Direction | **Low** | Verified Safe Behavior | Passed |
| **HS-02** | HubSpot Sync | Missing Exponential Backoff on HTTP 429 Rate Limits | **Medium** | Potential Risk | Open |
| **HS-03** | HubSpot Sync | Graceful Missing Scope Handling | **Low** | Verified Safe Behavior | Passed |
| **ENR-01** | Assignments & Enrollments | Database-Enforced Campaign Enrollment Uniqueness | **Low** | Verified Safe Behavior | Passed |
| **ENR-02** | Assignments & Enrollments | Lead Routing Concurrency & Overwrite Protection | **Low** | Verified Safe Behavior | Passed |
| **ACC-01** | Campaign & Analytics | Outreach Drafts Excluded from Sent Counts | **Low** | Verified Safe Behavior | Passed |
| **ACC-02** | Campaign & Analytics | Planned Calls Excluded from Completed Metrics | **Low** | Verified Safe Behavior | Passed |
| **ACC-03** | Campaign & Analytics | Guarded Campaign Completion Transition | **Low** | Verified Safe Behavior | Passed |
| **ACC-04** | Campaign & Analytics | Unsupported Workflow Nodes Execution Prevention | **Low** | Verified Safe Behavior | Passed |

---

## Detailed Findings by Investigation Area

---

### 1. HUBSPOT SYNCHRONIZATION

#### Finding HS-01: Inbound-Only Synchronization Direction
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [sync.py](file:///d:/Agile-Sales-Marketing/backend/app/services/integrations/hubspot/sync.py#L1-L15)
  - [hubspot.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/integrations/hubspot.py#L350-L378)
- **Actual Behavior:** Synchronization is strictly pull-based (HubSpot CRM v3 -> Agile Sales & Marketing PostgreSQL). The `sync_contacts`, `sync_companies`, and `sync_deals` functions perform GET requests against `/crm/v3/objects/*` and upsert local database records. No code path writes, updates, or deletes real records in HubSpot during standard synchronization.
- **Potential Business Impact:** None. Zero risk of corrupting, deleting, or altering HubSpot CRM records during synchronization.
- **Recommended Fix:** None required. Maintain inbound-only policy for Phase 1.
- **Safe Verification Method:** Run `test_hubspot_contacts.py` and inspect HTTP methods; confirm only `GET` requests are issued to HubSpot endpoints.

#### Finding HS-02: Absence of Exponential Backoff on HTTP 429 Rate Limits
- **Severity:** Medium
- **Classification:** Potential Risk
- **Evidence & File Paths:**
  - [client.py](file:///d:/Agile-Sales-Marketing/backend/app/services/integrations/hubspot/client.py#L190-L193)
- **Actual Behavior:** When HubSpot returns HTTP 429 (Rate Limit Exceeded), `HubSpotClient._handle_error_response` raises `HubSpotRateLimitError` immediately. There is no retry loop, jitter, or exponential backoff handling the `Retry-After` header. A rate-limited request will immediately abort the entire sync run.
- **Potential Business Impact:** In high-volume environments or concurrent sync operations, transient rate limits trigger complete sync failure, causing partial synchronization and requiring manual re-triggering.
- **Recommended Fix:** Implement automatic retries with exponential backoff and jitter in `HubSpotClient.request()`, respecting the `Retry-After` response header (up to 3 retries).
- **Safe Verification Method:** Mock an HTTP 429 response in a unit test and assert that client waits and retries rather than immediately raising an exception.

#### Finding HS-03: Graceful Missing Scope Handling Without Data Fabrication
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [sync.py](file:///d:/Agile-Sales-Marketing/backend/app/services/integrations/hubspot/sync.py#L422-L435)
  - [hubspot.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/integrations/hubspot.py#L277-L306)
- **Actual Behavior:** When HubSpot returns HTTP 403 Forbidden due to missing scopes (e.g. `crm.objects.companies.read`), the system catches `HubSpotPermissionError` and returns `ObjectSyncResult(status="missing_scope", error="...")`. It rolls back that entity's transaction, preserves other synced entities, and never synthesizes fake dummy records.
- **Potential Business Impact:** None. Ensures transparent diagnostics for system administrators.
- **Recommended Fix:** None required.

---

### 2. DUPLICATE DATA

#### Finding DUP-01: Confirmed Duplicate Contact in Live Database
- **Severity:** Medium
- **Classification:** Confirmed Defect
- **Evidence & File Paths:**
  - Database Table: `contacts`
  - Record 1: ID `aa1b6ce1-d55f-48c5-85aa-52e8e236678a`, Email `pravalikapalle@agilereceivables.com`, Created `2026-10-07 22:54:26.227430`
  - Record 2: ID `6d6bc3a9-84fd-40e9-8375-0e283f1863fb`, Email `pravalikapalle@agilereceivables.com`, Created `2026-10-07 22:55:03.676744`
  - Tenant Organization: `3de43e6b-6cc0-4391-a061-2faba481bcb8` (Agile Receivables Org)
  - [contact_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/contact_service.py#L20-L40)
- **Actual Behavior:** Two separate rows exist in the `contacts` table for the exact same email address within the same tenant organization, created 37 seconds apart. Neither row has a `hubspot_id`. Neither row is currently enrolled in a campaign or linked to outreach.
- **Potential Business Impact:** Queries using `.first()` resolve an arbitrary contact row. If enrolled into different campaigns, outreach history will be split across two records, complicating tracking and analytics.
- **Recommended Fix:** Perform a non-destructive administrative merge: re-point any future references to the primary contact record, archive the secondary record, and apply a database unique constraint to prevent recurrence.
- **Safe Verification Method:** Query `SELECT organization_id, LOWER(email), COUNT(*) FROM contacts GROUP BY organization_id, LOWER(email) HAVING COUNT(*) > 1;` in PostgreSQL.

#### Finding DUP-02: Missing Database-Level Unique Constraints on Contacts and Companies
- **Severity:** High
- **Classification:** Potential Risk
- **Evidence & File Paths:**
  - [contacts table schema](file:///d:/Agile-Sales-Marketing/backend/app/models/crm.py#L25-L60)
  - [pg_indexes confirmation](file:///d:/Agile-Sales-Marketing/backend/app/models/crm.py)
- **Actual Behavior:** 
  - `contacts` has an index `ix_contacts_org_email` on `(organization_id, email)`, but it is **NOT a UNIQUE index** (`CREATE INDEX ... USING btree (organization_id, email)`).
  - `companies` has an index `ix_companies_org_hubspot_id`, but **no UNIQUE index** on `(organization_id, domain)` or `(organization_id, hubspot_id)`.
  - Application-level `.first()` checks exist, but under concurrent API requests or parallel sync batches, race conditions can insert duplicate records.
- **Potential Business Impact:** Parallel imports, rapid webhook events, or concurrent manual creations can introduce duplicate contacts and companies.
- **Recommended Fix:** Add Alembic migrations creating unique constraints:
  - `CREATE UNIQUE INDEX uq_contacts_org_email ON contacts (organization_id, LOWER(email)) WHERE email IS NOT NULL;`
  - `CREATE UNIQUE INDEX uq_companies_org_domain ON companies (organization_id, LOWER(domain)) WHERE domain IS NOT NULL;`
- **Safe Verification Method:** Inspect `information_schema.table_constraints` for `UNIQUE` constraints on `contacts` and `companies`.

#### Finding DUP-03: Shared Environment Token Producing Cross-Tenant Duplication
- **Severity:** Medium
- **Classification:** Potential Risk
- **Evidence & File Paths:**
  - [config.py](file:///d:/Agile-Sales-Marketing/backend/app/core/config.py#L35-L40)
  - [sync.py](file:///d:/Agile-Sales-Marketing/backend/app/services/integrations/hubspot/sync.py#L120-L135)
  - Database Records: 154 contacts with identical `hubspot_id`s exist in Organization `3de43e6b-6cc0-4391-a061-2faba481bcb8` and Organization `0d85dc9f-1520-4bcb-8af4-8aad025255cb`.
- **Actual Behavior:** The HubSpot client retrieves its access token exclusively from the global `.env` variable `settings.HUBSPOT_ACCESS_TOKEN`. When sync was executed under different tenant sessions during development, the same upstream portal records were ingested into multiple tenants.
- **Potential Business Impact:** In multi-tenant deployments, distinct organizations will sync data from the same HubSpot account, causing cross-tenant data duplication.
- **Recommended Fix:** Store integration credentials (e.g. `HubSpotIntegrationConfig`) per tenant organization in the database (encrypted at rest), rather than using a single global environment variable.
- **Safe Verification Method:** Verify whether `client.py` reads tokens from an organization-specific model or `settings.HUBSPOT_ACCESS_TOKEN`.

---

### 3. EMAIL AND VOICE SAFETY

#### Finding SAF-01: Missing Opt-Out Suppression Guard in Direct `send_outreach()`
- **Severity:** High
- **Classification:** Confirmed Defect
- **Evidence & File Paths:**
  - [service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/outreach/service.py#L322-L370)
  - [rules.py](file:///d:/Agile-Sales-Marketing/backend/app/services/campaign_execution/rules.py#L97-L101)
- **Actual Behavior:** In `backend/app/services/outreach/service.py`, `send_outreach()` validates tenant ownership, campaign state, channel, initial status, empty body, and template placeholders. **However, it does NOT verify whether `outreach.contact.lead_status == 'opted_out'` or check a global suppression list.** While `rules.py` prevents creating initial drafts for opted-out contacts during campaign execution, an already-created draft outreach can still be delivered via `POST /api/v1/outreach/{outreach_id}/send` even if the contact opts out between draft creation and delivery.
- **Potential Business Impact:** Direct violation of CAN-SPAM, GDPR, and sender reputation standards if an unsubscribed prospect receives an email.
- **Recommended Fix:** Add an explicit suppression guard in `send_outreach()`:
  ```python
  if outreach.contact and outreach.contact.lead_status in ("opted_out", "unsubscribed"):
      outreach.status = "cancelled"
      db.commit()
      raise SuppressedRecipientError("Cannot deliver outreach: recipient contact is opted out.")
  ```
- **Safe Verification Method:** Create a mock unit test where a contact's `lead_status` is updated to `'opted_out'` after draft outreach creation, and call `send_outreach()` with `MockEmailProvider`; assert that sending is blocked.

#### Finding SAF-02: Unauthenticated Voice Replay Endpoint in Development Mode
- **Severity:** Medium
- **Classification:** Potential Risk
- **Evidence & File Paths:**
  - [voice_webhook.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/voice_webhook.py#L148-L158)
- **Actual Behavior:** In `POST /api/v1/voice/replay-analyzed-call`:
  ```python
  is_dev = settings.DEBUG or settings.ENVIRONMENT in ("development", "test")
  if not is_dev:
      auth_header = request.headers.get("authorization")
      if not auth_header:
          raise HTTPException(...)
  ```
  In development or test mode, this endpoint requires no authentication. If `EMAIL_PROVIDER_TYPE` is switched to a live provider (`ses` or `resend`), any unauthenticated caller on the network can trigger automated email dispatches via replay payloads.
- **Potential Business Impact:** Unintended email dispatches during development or staging testing.
- **Recommended Fix:** Always require valid authentication or enforce that `replay-analyzed-call` strictly uses `MockEmailProvider()` regardless of environment configuration.
- **Safe Verification Method:** Check the `replay-analyzed-call` endpoint with no headers under `DEBUG=True`; confirm it executes without an `Authorization` header.

#### Finding SAF-03: Automated Test Email Provider Isolation
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [conftest.py](file:///d:/Agile-Sales-Marketing/backend/tests/conftest.py#L66-L72)
  - [providers/__init__.py](file:///d:/Agile-Sales-Marketing/backend/app/services/outreach/providers/__init__.py#L23-L54)
- **Actual Behavior:** Pytest defines an autouse fixture `isolate_test_email_provider` that overrides `settings.EMAIL_PROVIDER_TYPE = "mock"` and `settings.RESEND_API_KEY = ""`. `get_email_provider()` returns `MockEmailProvider()`. Real email providers cannot be reached during automated test runs.
- **Potential Business Impact:** None. Automated test suites are completely isolated from live email services.
- **Recommended Fix:** None required.
- **Safe Verification Method:** Run `pytest tests/test_outreach_*.py` and verify zero network calls are attempted to Resend or SES.

---

### 4. DUPLICATE ASSIGNMENTS AND ENROLLMENTS

#### Finding ENR-01: Database-Enforced Campaign Enrollment Uniqueness
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [campaign_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/campaign_service.py#L366-L394)
  - Database Constraint: `uq_campaign_contact` on `campaign_contacts (campaign_id, contact_id)`
- **Actual Behavior:** Duplicate campaign enrollments are prohibited at two independent layers:
  1. Application layer: `enroll_contact()` queries `CampaignContact` and raises `ContactAlreadyEnrolledError`. `bulk_enroll_contacts()` deduplicates input lists and filters out existing enrollments.
  2. Database engine layer: Unique index `uq_campaign_contact` enforces that no two rows can share the same `(campaign_id, contact_id)` combination.
- **Potential Business Impact:** None. Contacts cannot be double-enrolled in the same campaign.
- **Recommended Fix:** None required.
- **Safe Verification Method:** Attempt inserting duplicate `(campaign_id, contact_id)` row into `campaign_contacts`; verify PostgreSQL raises unique violation `23505`.

#### Finding ENR-02: Lead Routing Concurrency & Overwrite Protection
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [routing_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/lead_qualification/routing_service.py#L308-L327)
- **Actual Behavior:** `route_single_lead()` verifies if `lead.assigned_to_user_id is not None or lead.routing_rule_id is not None`. If already assigned, it aborts assignment and returns `is_routed=False` with an explanation unless `force_reroute=True` is explicitly passed.
- **Potential Business Impact:** Existing lead ownership assignments are preserved and cannot be overwritten by routine batch evaluations.
- **Recommended Fix:** To ensure bulletproof concurrency safety under heavy load, add `with_for_update()` to the lead lookup query in `route_single_lead()`.
- **Safe Verification Method:** Call `route_single_lead` on an already-assigned lead with `force_reroute=False`; verify assignment remains unchanged.

---

### 5. DATA INTEGRITY AND SECURITY

#### Finding SEC-01: Unauthenticated HubSpot Integration Endpoints
- **Severity:** Critical
- **Classification:** Confirmed Defect
- **Evidence & File Paths:**
  - [hubspot.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/integrations/hubspot.py#L381-L407)
  - [hubspot.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/integrations/hubspot.py#L409-L438)
  - [hubspot.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/integrations/hubspot.py#L440-L469)
- **Actual Behavior:** Three API endpoints in `backend/app/api/v1/integrations/hubspot.py` have zero dependency injection for tenant authentication or user authorization:
  1. `GET /api/v1/integrations/hubspot/test`
  2. `GET /api/v1/integrations/hubspot/contacts/{contact_id}`
  3. `GET /api/v1/integrations/hubspot/deals/{deal_id}`
  Any external unauthenticated HTTP client can issue requests to these endpoints, probe API health, and extract contact/deal data directly from the configured HubSpot portal.
- **Potential Business Impact:** Severe security and privacy risk. Unauthenticated data exposure of upstream CRM contacts and deals.
- **Recommended Fix:** Add `current_org: Organization = Depends(get_current_organization)` to all three endpoints and restrict access to authorized administrators.
- **Safe Verification Method:** Issue a `GET` request using `curl` or `httpx` to `http://localhost:8000/api/v1/integrations/hubspot/test` without an `Authorization` header; confirm it returns HTTP 200 rather than HTTP 401/403.

#### Finding SEC-02: Webhook Fallback Tenant Resolution (`SELECT ... LIMIT 1`)
- **Severity:** High
- **Classification:** Confirmed Defect
- **Evidence & File Paths:**
  - [voice_followup.py](file:///d:/Agile-Sales-Marketing/backend/app/services/outreach/voice_followup.py#L676-L699)
- **Actual Behavior:** In `VoiceFollowUpService.resolve_organization()`:
  ```python
  # Fallback to the first organization if only one exists in DB (common in single-tenant/dev)
  first_org = self.db.execute(select(Organization).limit(1)).scalar_one_or_none()
  return first_org
  ```
  If an incoming Retell AI webhook payload lacks `organization_id` in its metadata, the service falls back to selecting an arbitrary organization from the database (`LIMIT 1`). In the audited environment, 6 distinct organizations exist.
- **Potential Business Impact:** In a multi-tenant production environment, untagged voice call records and automated follow-up emails will be arbitrarily attributed to the first tenant in PostgreSQL, leading to cross-tenant data leakage.
- **Recommended Fix:** Remove the `LIMIT 1` fallback. If `organization_id` cannot be determined from call metadata or the agent ID mapping, reject the webhook with an HTTP 422/400 error and log an alert.
- **Safe Verification Method:** Call `VoiceFollowUpService.resolve_organization` with empty metadata on a database containing multiple organizations; verify it selects an arbitrary tenant.

#### Finding SEC-03: Unauthenticated AWS SES Webhook Handler
- **Severity:** Medium
- **Classification:** Confirmed Defect
- **Evidence & File Paths:**
  - [tracking.py](file:///d:/Agile-Sales-Marketing/backend/app/api/v1/tracking.py#L110-L150)
- **Actual Behavior:** `POST /api/v1/outreach/tracking/ses-webhook` processes delivery, bounce, and complaint notifications from AWS SES/SNS. However, it lacks SNS message signature verification (`SigningCertURL`, `Signature`) and does not enforce HMAC/token validation.
- **Potential Business Impact:** An external actor could forge SES bounce or complaint payloads, causing legitimate outreach records to be marked as bounced or failed.
- **Recommended Fix:** Implement AWS SNS signature verification using the official AWS SNS message validator or require a pre-shared webhook secret token query parameter.
- **Safe Verification Method:** Send a synthesized JSON payload to `/api/v1/outreach/tracking/ses-webhook` without an AWS signature; verify it accepts and processes the payload.

---

### 6. CAMPAIGN AND ANALYTICS ACCURACY

#### Finding ACC-01: Outreach Drafts Excluded from Sent Message Metrics
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [analytics_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/analytics_service.py#L103-L120)
  - [analytics_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/analytics_service.py#L175-L187)
- **Actual Behavior:** In `analytics_service.py`, metrics are grouped strictly by `Outreach.status`:
  - `draft_outreach = outreach_status_dict.get("draft", 0)`
  - `sent_outreach = outreach_status_dict.get("sent", 0)`
  Draft outreach records generated by campaign execution are reported under `draft` and never conflated with `sent`.
- **Potential Business Impact:** None. Reporting metrics reflect true operational delivery states.
- **Recommended Fix:** None required.
- **Safe Verification Method:** Inspect database: 8 outreach records exist, draft counts match draft records and sent counts match sent records.

#### Finding ACC-02: Planned Calls Excluded from Completed Metrics
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [analytics_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/analytics_service.py#L197-L205)
- **Actual Behavior:** `completed_calls` is computed using:
  ```python
  (CallRecord.call_status.in_(["ended", "analyzed"])) | (CallRecord.duration_ms > 0)
  ```
  Uncompleted or planned call records with status `scheduled` or duration 0 are excluded from completed call totals.
- **Potential Business Impact:** None. Analytics truthfully report completed calls.
- **Recommended Fix:** None required.
- **Safe Verification Method:** Query `CallRecord` table and verify completed calls count matches `ended` and `analyzed` records.

#### Finding ACC-03: Guarded Campaign Completion Transition
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [campaign_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/campaign_service.py#L296-L327)
- **Actual Behavior:** `complete_campaign()` strictly verifies:
  1. `in_progress_count == 0` (no enrolled contact is in active sequence)
  2. `draft_outreach_count == 0` (no generated outreach messages remain in draft)
  If either count is greater than zero, the transition is rejected with `InvalidCampaignTransitionError` unless `force=True` is explicitly passed by an administrator.
- **Potential Business Impact:** None. Prevents premature campaign termination with abandoned drafts or stranded enrollments.
- **Recommended Fix:** None required.
- **Safe Verification Method:** Attempt to transition a campaign with draft outreach to `completed` without `force=True`; verify HTTP 400 error is returned.

#### Finding ACC-04: Unsupported Workflow Nodes Cannot Execute Silently
- **Severity:** Low
- **Classification:** Verified Safe Behavior
- **Evidence & File Paths:**
  - [workflow_service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/workflow_service.py#L121-L138)
  - [service.py](file:///d:/Agile-Sales-Marketing/backend/app/services/campaign_execution/service.py#L182-L192)
- **Actual Behavior:** 
  1. Visual workflow validation explicitly warns users that SMS steps cannot be executed due to unconfigured SMS gateways, and that condition/wait steps require durable schedulers.
  2. Campaign execution only processes active `CampaignStep` (Step 1 Email) as drafts. There is no background worker that silently runs unconfigured SMS or voice nodes.
- **Potential Business Impact:** None. Zero risk of phantom execution or silent failures.
- **Recommended Fix:** None required.
- **Safe Verification Method:** Validate a workflow with an SMS node; confirm it returns actionable warning stating SMS gateway is unconfigured.

---

## Separation of Verified Facts vs Assumptions

### Verified Facts
1. The database currently contains 6 organizations, 5 users, 128 companies, 323 contacts, 311 leads, 7 campaigns, 4 campaign enrollments, 8 outreach records, and 5 call records.
2. In Organization `3de43e6b-6cc0-4391-a061-2faba481bcb8`, exactly two contact records share the email `pravalikapalle@agilereceivables.com`.
3. In PostgreSQL, `contacts` and `companies` tables lack unique constraints on `(organization_id, email)` and `(organization_id, domain)`.
4. `campaign_contacts` has a database-level unique constraint `uq_campaign_contact` on `(campaign_id, contact_id)`.
5. Direct delivery via `send_outreach()` does not check whether `outreach.contact.lead_status == 'opted_out'`.
6. Endpoints `/api/v1/integrations/hubspot/test`, `/contacts/{contact_id}`, and `/deals/{deal_id}` do not declare tenant authentication dependencies.
7. In `VoiceFollowUpService.resolve_organization()`, missing metadata resolves to `db.execute(select(Organization).limit(1)).scalar_one_or_none()`.
8. The test configuration `tests/conftest.py` automatically forces `EMAIL_PROVIDER_TYPE = "mock"` and `RESEND_API_KEY = ""`.
9. The backend does not run automated background cron or Celery processes that send messages without user or webhook triggers.

### Assumptions & Inferences
1. It is assumed that the duplicate contact `pravalikapalle@agilereceivables.com` was created during manual API testing on October 7, 2026, as both records share identical job titles (`Lead`) and have no `hubspot_id`.
2. It is assumed that both organizations having 154 contacts with the same HubSpot IDs occurred because a single development developer token was shared across tenant test runs.

---

## Areas That Could Not Be Verified

The following areas could not be verified due to the strict safety rules of this audit:
1. **Live HubSpot Rate Limiting (HTTP 429) Response Body:** Could not be verified against live HubSpot because triggering a real rate limit would require flooding the customer's production HubSpot API with hundreds of requests, violating safety rules.
2. **Real Provider Deliverability (SES / Resend):** Live email delivery through Amazon SES or Resend could not be verified because real emails were strictly prohibited. Delivery verification was performed via mock provider inspection and payload contract validation.
3. **Live Retell Telephony Dialing:** Live outbound telephony calls could not be initiated because placing real phone calls was strictly prohibited. Telephony verification was conducted via webhook payload schemas and local replay simulations.
4. **HubSpot Multi-Portal Sync:** Whether the system functions correctly when multiple tenants connect to different HubSpot private apps simultaneously could not be verified because only a single global `HUBSPOT_ACCESS_TOKEN` is currently supported in `.env`.

---

## Action Plan & Remediation Roadmap

When approved to move from audit to remediation, the following targeted fixes should be implemented in priority order:

1. **P0 (Immediate Security):**
   - Add `current_org: Organization = Depends(get_current_organization)` to `/api/v1/integrations/hubspot/test`, `/contacts/{contact_id}`, and `/deals/{deal_id}`.
   - Remove `LIMIT 1` tenant fallback in `VoiceFollowUpService.resolve_organization()`.
   - Add suppression check `if contact.lead_status == 'opted_out': raise ...` in `outreach_service.send_outreach()`.

2. **P1 (Data Integrity):**
   - Add Alembic migration with unique indexes on `contacts (organization_id, LOWER(email))` and `companies (organization_id, LOWER(domain))`.
   - Safely merge or archive duplicate contact `aa1b6ce1-d55f-48c5-85aa-52e8e236678a` / `6d6bc3a9-84fd-40e9-8375-0e283f1863fb`.

3. **P2 (Operational Resilience):**
   - Add exponential backoff retry loop for HTTP 429 in `HubSpotClient.request()`.
   - Add AWS SNS signature verification for `/api/v1/outreach/tracking/ses-webhook`.
   - Transition HubSpot configuration from global `.env` to per-tenant database configuration.

---
*End of Production Safety Audit Report.*
