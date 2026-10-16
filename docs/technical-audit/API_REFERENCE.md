# Complete REST API Reference Manual

**Platform:** Agile Sales & Marketing  
**Base URL:** `http://localhost:8000/api/v1` (Backend) / `http://localhost:3000/api` (Frontend Proxy)  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Backend Architect, API Integration Engineer  

---

## 1. Authentication & Security Headers

All protected endpoints require HTTP Bearer token authentication:
```http
Authorization: Bearer <jwt_access_token>
```
* **Tenant Isolation:** The backend extracts the user's `organization_id` directly from the validated token.
* **Missing Credentials:** Returns `401 Unauthorized`.
* **Cross-Tenant Access:** Returns `404 Not Found` (to avoid leaking resource existence across tenants).

---

## 2. API Endpoints by Module

### 2.1. Authentication (`/auth`)

#### `POST /auth/register`
* **Purpose:** Register a new user and organization account.
* **Body:**
  ```json
  {
    "email": "user@example.com",
    "password": "StrongPassword123!",
    "full_name": "Jane Doe",
    "organization_name": "Acme Corp"
  }
  ```
* **Responses:** `201 Created` with `UserResponse`, `400 Bad Request` (duplicate email).

#### `POST /auth/login`
* **Purpose:** Authenticate and obtain JWT access and refresh tokens.
* **Body:** `OAuth2PasswordRequestForm` (`username` = email, `password`).
* **Response:** `200 OK`:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1Ni...",
    "refresh_token": "eyJhbGciOiJIUzI1Ni...",
    "token_type": "bearer"
  }
  ```

#### `GET /auth/me`
* **Purpose:** Retrieve the authenticated user's profile and organization details.
* **Response:** `200 OK` with `UserResponse`.

---

### 2.2. Leads Management (`/leads`)

#### `GET /leads`
* **Purpose:** List leads belonging to the tenant organization.
* **Query Params:** `skip` (int, default 0), `limit` (int, default 50), `query` (string), `temperature` (`cold`/`warm`/`hot`), `status` (string), `exclude_test` (bool, default false).
* **Response:** `200 OK`:
  ```json
  {
    "items": [
      {
        "id": "c1f7b028-...",
        "company_name": "Apex Global",
        "email": "contact@apex.com",
        "lead_score": 85,
        "qualification_status": "qualified",
        "lead_temperature": "hot",
        "status": "new",
        "created_at": "2026-10-14T01:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 50
  }
  ```

#### `POST /leads`
* **Purpose:** Manually create a new lead and automatically associate or create a matching `CRMContact`.
* **Body:**
  ```json
  {
    "company_name": "Apex Global",
    "first_name": "Jane",
    "last_name": "Doe",
    "email": "jane@apex.com",
    "phone": "+15551234567",
    "job_title": "VP Finance",
    "industry": "Fintech",
    "lead_temperature": "warm"
  }
  ```
* **Response:** `201 Created` with created Lead details.

#### `DELETE /leads/{lead_id}`
* **Purpose:** Organization-scoped deletion of an individual lead. Preserves shared CRMContact and historical records.
* **Responses:** `204 No Content` (success), `404 Not Found` (missing or cross-tenant).

#### `POST /leads/{lead_id}/evaluate`
* **Purpose:** Evaluate and score a lead against the tenant's Ideal Customer Profile (ICP).
* **Response:** `200 OK` with updated `lead_score`, `qualification_status`, and `qualification_reason`.

---

### 2.3. Campaigns & Enrollments (`/campaigns`)

#### `GET /campaigns`
* **Purpose:** List campaigns with enrolled contact counts and step counts.
* **Response:** `200 OK` with array of Campaign objects.

#### `POST /campaigns`
* **Purpose:** Create a new campaign.
* **Body:**
  ```json
  {
    "name": "Q4 Debt Recovery Outreach",
    "type": "sales_outbound",
    "status": "draft",
    "description": "Multi-step email cadence targeting financial controllers."
  }
  ```
* **Response:** `201 Created` with Campaign object.

#### `DELETE /campaigns/{campaign_id}`
* **Purpose:** Organization-scoped deletion of a campaign. Cancels pending outreach, dissociates historical sent outreach, deletes steps and enrollments.
* **Responses:** `204 No Content`, `404 Not Found`.

#### `POST /campaigns/{campaign_id}/contacts`
* **Purpose:** Enroll contacts into a campaign.
* **Body:**
  ```json
  {
    "contact_ids": ["f8b2d1c0-..."]
  }
  ```
* **Response:** `200 OK` with enrolled count and skipped count (prevents duplicate enrollments).

#### `DELETE /campaigns/{campaign_id}/contacts/{contact_id}`
* **Purpose:** Remove an individual contact from a specific campaign. Dissociates historical outreach, cancels pending outreach, preserves contact in CRM and other campaigns.
* **Responses:** `200 OK`, `404 Not Found`.

---

### 2.4. Campaign Steps & Sequence Builder (`/campaigns/{id}/steps`)

#### `GET /campaigns/{id}/steps`
* **Purpose:** List sequence steps ordered by `step_number`.
* **Response:** `200 OK` with list of `CampaignStepResponse`.

#### `POST /campaigns/{id}/steps`
* **Purpose:** Add a sequence step.
* **Body:**
  ```json
  {
    "step_number": 1,
    "step_type": "email",
    "subject_template": "Quick question regarding {{company.name}}",
    "body_template": "Hi {{contact.first_name}},\n\nWanted to reach out...\n\nBest,\n{{sender.name}}",
    "delay_days": 0,
    "delay_hours": 0
  }
  ```
* **Response:** `201 Created`.

#### `POST /campaigns/{id}/steps/{step_id}/preview`
* **Purpose:** Live contact preview of rendered email templates for a selected contact.
* **Body:**
  ```json
  {
    "contact_id": "f8b2d1c0-..."
  }
  ```
* **Response:** `200 OK`:
  ```json
  {
    "rendered_subject": "Quick question regarding Apex Global",
    "rendered_body": "Hi Jane,\n\nWanted to reach out...\n\nBest,\nAgile SDR",
    "unresolved_placeholders": []
  }
  ```

---

### 2.5. Campaign Execution & Outreach (`/campaigns/{id}/execute`, `/outreach`)

#### `POST /campaigns/{id}/execute/preview`
* **Purpose:** Read-only dry-run evaluating eligible contacts without mutating database state.
* **Response:** `200 OK` with `eligible_count`, `skipped_count`, `rejected_count`, and rendered preview items.

#### `POST /campaigns/{id}/execute`
* **Purpose:** Execute campaign Step 1: creates draft `Outreach` records, transitions enrolled contacts to `in_progress`, and sets `current_step = 1`.
* **Response:** `200 OK` with `created_count` and created outreach IDs.

#### `POST /outreach/{id}/send`
* **Purpose:** Trigger immediate delivery of an outreach message via the configured provider (AWS SES).
* **Guards:** Fail-closed suppression guard (checks opted-out), unresolved placeholder guard.
* **Responses:** `200 OK` (status updated to `sent`), `400 Bad Request` (suppressed or unresolved tokens), `502 Bad Gateway` (provider delivery error).

#### `POST /outreach/{id}/retry`
* **Purpose:** Retry delivery for a `failed` outreach message.
* **Responses:** `200 OK`, `400 Bad Request` (if status is not `failed`).

#### `POST /outreach/{id}/cancel`
* **Purpose:** Cancel a `draft` or `scheduled` outreach message.
* **Responses:** `200 OK` (status updated to `cancelled`).

---

### 2.6. Voice Webhook (`/voice/webhook`)

#### `POST /voice/webhook`
* **Purpose:** Ingest Retell AI call completion events, verify HMAC signature, log `CallRecord`, and trigger automated follow-up emails.
* **Headers:** `X-Retell-Signature: <hex_signature>`.
* **Body:** Retell webhook JSON payload (containing `call_id`, `call_status`, `call_analysis`, `transcript`).
* **Responses:** `200 OK`, `401 Unauthorized` (invalid signature), `422 Unprocessable Entity` (malformed payload).

---

### 2.7. HubSpot Integration (`/integrations/hubspot`)

#### `GET /integrations/hubspot/status`
* **Purpose:** Check connection status, portal ID, and last sync timestamp.
* **Response:** `200 OK` with configuration and sync status.

#### `POST /integrations/hubspot/sync`
* **Purpose:** Trigger read-only synchronization of Contacts, Companies, and Deals from HubSpot CRM v3.
* **Response:** `200 OK` with `HubSpotSyncSummary`.

---

### 2.8. Health & System Status (`/`, `/health`)

#### `GET /`
* **Purpose:** Simple service ping.
* **Response:** `200 OK` (`{"status": "online"}`).

#### `GET /health`
* **Purpose:** Comprehensive health probe verifying DB and configuration.
* **Response:** `200 OK` (`{"status": "ok", "hubspot_configured": true}`).
