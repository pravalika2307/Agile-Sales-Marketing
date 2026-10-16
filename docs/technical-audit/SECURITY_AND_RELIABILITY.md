# Security, Reliability, & Data Safety Assessment

**Platform:** Agile Sales & Marketing  
**Audit Date:** October 2026  
**Auditor Roles:** Senior Application Security Architect, Infrastructure Auditor  
**Document Purpose:** Detailed technical evaluation of authorization, tenant isolation, cryptographic hygiene, data integrity safeguards, and identified vulnerability risks.

---

## 1. Security Architecture & Controls

### 1.1. Tenant Isolation
* **Architecture:** Shared database, shared schema with logical row-level tenant boundaries.
* **Mechanism:**
  * Every tenant model references `organizations.id` via non-nullable foreign keys.
  * Tenant identity is extracted from validated JWT token claims in `deps.py` (`get_current_organization`) and cannot be overridden by client query parameters.
  * Service layer queries strictly enforce `filter(Model.organization_id == current_org.id)`. Cross-tenant lookup attempts return HTTP 404.

### 1.2. Cryptographic Storage & Authentication
* **Password Hashing:**
  * Uses **Argon2id** via `argon2-cffi>=23.1.0` in `backend/app/core/security.py`.
  * Protects against GPU-accelerated brute-force attacks.
* **Token Authentication:**
  * Uses RFC 7519 JSON Web Tokens (PyJWT 2.8) signed with `HS256` and a configurable `SECRET_KEY`.
  * Separate `access` (30 min) and `refresh` (14 days) tokens with `type` claim validation.

### 1.3. SQL Injection & Parameter Safety
* **ORM Safety:**
  * Uses SQLAlchemy 2.0 type-hinted mapped queries.
  * All SQL queries utilize parameterized statements; zero raw unescaped string concatenations exist in production API paths.

### 1.4. Sensitive Data & Log Sanitization
* **Credential Hygiene:**
  * `HubSpotClient.__repr__` explicitly masks access tokens:
    ```python
    def __repr__(self) -> str:
        return f"<HubSpotClient base_url='{self.base_url}' configured={self.is_configured} timeout={self.timeout}>"
    ```
  * Password hashes, external API keys, and secret values are excluded from Pydantic response models (`UserResponse`, `OutreachResponse`).

### 1.5. Fail-Closed Recipient Suppression Guard
* **Compliance Safeguard:**
  * Before any email is dispatched in `send_outreach()` (`outreach/service.py`), the service verifies:
    1. If `Contact.lead_status` is `'opted_out'` or `'unsubscribed'`, dispatch is **strictly blocked**.
    2. If an associated `Lead` record in the tenant organization is `'opted_out'` or `'rejected'`, dispatch is **strictly blocked**.
  * The outreach record status transitions to `'cancelled'` with an audit event, raising `SuppressedRecipientError`.

### 1.6. Fail-Safe Unresolved Placeholder Blocker
* **Brand Protection:**
  * If a template contains `{{company.name}}` or `{{contact.job_title}}` and the recipient record has null values without a fallback, the system intercepts the error before reaching AWS SES and blocks dispatch (`UnresolvedTemplatePlaceholderError`).

### 1.7. Webhook HMAC-SHA256 Signature Verification
* **Retell Webhook Security:**
  * `VoiceFollowUpService.verify_webhook_signature()` calculates an HMAC-SHA256 hash over the raw webhook body using `RETELL_API_KEY` and performs a constant-time comparison against `X-Retell-Signature` using `hmac.compare_digest()`.
  * Prevents replay attacks and unauthorized payload injection.

---

## 2. Risk Log & Technical Findings

| ID | Finding | Severity | File Path | Potential Impact | Status / Remediation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Wildcard CORS Configuration (`allow_origins=["*"]`) | **Medium** | `backend/app/main.py:29` | In production, any origin could make browser-based API calls if credentials/cookies were enabled. | **Pending Production Remediation:** Restrict `allow_origins` to explicit frontend domain (e.g. `https://sales.agilereceivables.com`). |
| **SEC-02** | Absence of Rate Limiting Middleware | **Medium** | `backend/app/main.py` | API endpoints (`/leads`, `/outreach/{id}/send`) lack per-IP or per-tenant rate limiting (e.g. slowapi). | **Recommended (P1):** Introduce Redis-backed token bucket rate limiting on public and heavy endpoints. |
| **SEC-03** | Frontend Missing Direct JWT Authentication State | **Medium** | `frontend/src/app/api/` | Frontend route handlers proxy calls with a default organization context rather than user login tokens. | **Recommended (P1):** Implement client login form and store JWT in HTTP-only secure cookie. |
| **SEC-04** | Missing Asynchronous SNS Bounce Webhook Handler | **Low** | `backend/app/api/v1/tracking.py` | If an email bounces asynchronously in SES, contact lead status is not automatically updated to `opted_out`. | **Recommended (P1):** Wire AWS SNS HTTP webhook endpoint to process Bounce and Complaint notifications. |
| **SEC-05** | Case-Insensitive Duplicate Contacts Vulnerability | **Resolved** | Migration `b2c3d4e5f6a7` | Previously, contacts with different casing (`user@ex.com` vs `USER@EX.COM`) could coexist. | **Remediated:** Unique index `ix_contacts_org_lower_email` added; passes `test_duplicate_prevention.py`. |
| **SEC-06** | Accidental Shared Contact Deletion on Lead Delete | **Resolved** | `app/services/lead_generation/service.py` | Deleting a lead might have cascaded to shared CRM contacts used by other campaigns. | **Remediated:** Lead deletion removes `leads` row only, leaving `contacts` and `campaign_contacts` intact. |
