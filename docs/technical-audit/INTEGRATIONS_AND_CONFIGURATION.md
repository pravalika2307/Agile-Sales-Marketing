# External Integrations & Environment Configuration Reference

**Platform:** Agile Sales & Marketing  
**Audit Date:** October 2026  
**Auditor Roles:** Senior DevOps Engineer, Cloud Architect, Security Specialist  
**Document Purpose:** Exhaustive operational guide detailing external cloud connectors, SDKs, authorization schemes, webhook signatures, and environment variable references.

---

## 1. External Integration Overview

| Provider | Integration Type | Direction of Flow | Service Files | Primary Purpose | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **AWS SES** | Cloud Email Infrastructure | Outbound | `app/services/outreach/providers/ses.py` | High-volume transactional and sequence email dispatch. | **Verified via local unit & provider tests** |
| **HubSpot CRM v3** | CRM REST API | Inbound (Read-Only) | `app/services/integrations/hubspot/` | Sourcing existing CRM contacts, companies, and deals into local database. | **Verified via API client & sync tests** |
| **Retell AI** | Conversational Voice AI | Bidirectional | `app/services/outreach/voice_followup.py` | Inbound telephony answering and post-call email follow-up automation. | **Verified via webhook signature & logic tests** |
| **Resend** | Alternative Email API | Outbound | `app/services/outreach/providers/resend.py` | Developer-friendly transactional email delivery fallback. | **Code implemented, tested via unit tests** |

---

## 2. Deep Dive: AWS SES Email Integration

* **SDK:** `boto3>=1.34.0`.
* **Adapter Location:** `backend/app/services/outreach/providers/ses.py`.
* **Architecture:**
  * Uses `boto3.client("ses", region_name=...)`.
  * Passes `ConfigurationSetName` (e.g. `sales-marketing-config-set`) for Amazon CloudWatch event tracking.
  * Formats raw UTF-8 MIME multipart messages or structured dictionaries.
  * Returns provider Message ID upon successful handoff.
* **Operational Verification:**
  * Tested using mocked botocore clients in `backend/tests/test_ses_provider.py`.
  * Verified error handling for invalid emails, rate limits (`LimitExceededException`), and template rendering guards.
* **Production Requirements:**
  * AWS IAM User or Role with `ses:SendEmail` and `ses:SendRawEmail` permissions.
  * Domain identity verified in AWS SES Console (DKIM, SPF, DMARC records published).

---

## 3. Deep Dive: HubSpot CRM v3 Integration

* **Client Library:** Custom asynchronous client built with `httpx>=0.27.0`.
* **Service Location:** `backend/app/services/integrations/hubspot/client.py` and `sync.py`.
* **Guarantees:**
  * **Strictly Read-Only:** Never creates, edits, or deletes records in HubSpot CRM.
  * **Cursor Pagination:** Consumes HubSpot v3 pagination (`paging.next.after`) to ingest full datasets.
  * **Tenant Scoping:** All ingested contacts and companies are tagged with the active `organization_id`.
  * **Transparent Permissions:** If a private app token lacks `crm.objects.companies.read`, the engine captures the 403 error in `HubSpotSyncRun.permission_errors` and continues syncing contacts rather than crashing.
* **Required HubSpot Private App Scopes:**
  * `crm.objects.contacts.read`
  * `crm.objects.companies.read`
  * `crm.objects.deals.read`

---

## 4. Deep Dive: Retell AI Voice Webhook Integration

* **Webhook Endpoint:** `POST /api/v1/voice/webhook` (`backend/app/api/v1/voice_webhook.py`).
* **Service Engine:** `backend/app/services/outreach/voice_followup.py` (1,600+ lines).
* **Security & Authentication:**
  * Uses HMAC-SHA256 signature verification comparing `X-Retell-Signature` against `RETELL_API_KEY`.
* **Automated Decision Engine:**
  * Maps call outcomes (`MEETING_REQUESTED`, `QUALIFIED`, `INTERESTED`) to personalized follow-up email templates.
  * Enforces idempotency via `CallRecord.followup_idempotency_key` (constructed from `call_id` + outcome type) to prevent duplicate emails from replay webhooks.
  * Implements a 24-hour contact cooldown window to prevent spamming leads.

---

## 5. Master Environment Variable Reference

The following environment variables configure the backend application.
*(Note: As required by safety standards, only variable names and requirements are documented; actual credentials and secrets are excluded.)*

| Variable Name | Required? | Default Value | Description & Purpose |
| :--- | :--- | :--- | :--- |
| `PROJECT_NAME` | No | `"Agile Sales & Marketing API"` | Human-readable application name for OpenAPI and logs. |
| `VERSION` | No | `"0.1.0"` | Application release version string. |
| `ENVIRONMENT` | No | `"development"` | Runtime stage (`development`, `staging`, `production`). |
| `DEBUG` | No | `false` | Enables verbose logging and SQLAlchemy echo when true. |
| `DATABASE_URL` | **Yes** | `None` | PostgreSQL connection string (`postgresql+psycopg://user:pass@host:5432/dbname`). |
| `SECRET_KEY` | **Yes** | `None` | Cryptographic secret key used to sign and verify JWT tokens (minimum 32 characters). |
| `JWT_ALGORITHM` | No | `"HS256"` | Hashing algorithm for JWT access and refresh tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| No | `30` | Access token lifespan in minutes. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `14` | Refresh token lifespan in days. |
| `EMAIL_PROVIDER_TYPE` | No | `"mock"` | Primary provider adapter: `'ses'`, `'resend'`, or `'mock'`. |
| `EMAIL_FROM_ADDRESS` | **Yes** | `None` | Verified sender email address (e.g. `outreach@agilereceivables.com`). |
| `EMAIL_FROM_NAME` | No | `"Agile Sales & Marketing"` | Friendly sender name displayed in email clients. |
| `AWS_SES_REGION` | If SES | `"us-east-2"` | AWS region where SES identity is verified. |
| `AWS_SES_CONFIGURATION_SET` | If SES | `None` | SES configuration set for event publishing (optional). |
| `AWS_ACCESS_KEY_ID` | If SES | `None` | AWS IAM credentials with SES send permissions. |
| `AWS_SECRET_ACCESS_KEY` | If SES | `None` | AWS IAM secret key. |
| `HUBSPOT_ACCESS_TOKEN` | If HubSpot | `None` | HubSpot Private App Token or Personal Access Key. |
| `HUBSPOT_BASE_URL` | No | `"https://api.hubapi.com"` | HubSpot API v3 base endpoint. |
| `HUBSPOT_TIMEOUT_SECONDS` | No | `10.0` | HTTP request timeout for HubSpot API calls. |
| `RETELL_API_KEY` | If Retell | `None` | Retell AI API key used for webhook signature verification. |
| `RETELL_AGENT_ID` | If Retell | `None` | Outbound SDR agent identifier in Retell console. |
| `RETELL_FROM_NUMBER` | If Retell | `None` | Outbound telephony caller ID phone number in E.164 format. |
| `RESEND_API_KEY` | If Resend | `None` | API key for Resend email provider. |
