# Agile Sales & Marketing — Duplicate Data Prevention Audit

**Audit Date:** October 12, 2026  
**Audited Subsystems:** CRM Contacts, Companies, Leads, HubSpot Sync Engine, Manual Creation APIs, Lead Conversion, Voice Processing, PostgreSQL Schema & Constraints  
**Mode:** Strict Read-Only Investigation (No modifications executed, no records deleted or merged, no real HubSpot calls, no secrets exposed)  
**Deliverable Document:** `duplicate_prevention_audit.md`

---

## 1. Executive Summary

A comprehensive, read-only data audit was conducted across the live PostgreSQL database and backend application code to investigate duplicate contacts, companies, and leads, analyze all entity creation paths, evaluate existing database constraints, and design safe, multi-tenant duplicate prevention mechanisms.

### Key Audit Findings:
1. **Confirmed Duplicate Contacts:** Exactly **1 duplicate group** (2 contact records) exists within tenant organization `3de43e6b-6cc0-4391-a061-2faba481bcb8` sharing the normalized email `pravalikapalle@agilereceivables.com`, created 37 seconds apart. Neither record possesses a HubSpot ID, campaign enrollment, outreach record, call record, deal, or linked lead.
2. **Missing Database-Level Unique Constraints:** Neither `contacts` nor `companies` has a unique constraint or unique index on `(organization_id, email)` or `(organization_id, domain)`. The `contacts` table has non-unique B-tree indexes `ix_contacts_org_email` and `ix_contacts_org_hubspot_id`. The `companies` table has no index on `(organization_id, domain)` whatsoever.
3. **Application Layer Gaps:**
   - `contact_service.create_contact()` performs **no lookup** for existing email addresses before inserting new records.
   - `company_service.create_company()` performs **no lookup** for existing company domains or names before inserting.
   - `lead_generation.create_lead()` performs **no lookup** for existing lead emails before inserting.
   - `lead_generation.generate_leads()` only deduplicates against `source_external_id`, ignoring existing lead emails and existing CRM contacts.
   - `voice_followup.auto_upsert_contact_or_lead()` performs case-sensitive email lookups and does not link `lead.contact_id` when a lead snapshot is created.
4. **Cross-Tenant Duplication vs Tenant Isolation:** 154 contacts and 128 companies share identical HubSpot IDs across Organization `3de43e6b-...` and Organization `0d85dc9f-...` due to development-stage sync runs using a single global `HUBSPOT_ACCESS_TOKEN`. Within each tenant, HubSpot IDs are unique. Global unique constraints on `hubspot_id` or `email` across the entire database would break multi-tenant isolation; all uniqueness constraints must strictly be organization-scoped.
5. **Pre-Migration Blocker:** The 1 confirmed duplicate contact group in Organization `3de43e6b-...` directly blocks applying `CREATE UNIQUE INDEX uq_contacts_org_lower_email` until administrative resolution is executed.

---

## 2. Phase 1: Read-Only Data Audit Findings

### 2.1 Entity Counts Across Organizations

| Organization ID | Organization Name | Contacts | Companies | Leads | Deals | Call Records | Outreach Records |
|---|---|---|---|---|---|---|---|
| `3de43e6b-6cc0-4391-a061-2faba481bcb8` | Agile Receivables Org | 156 | 0 | 154 | 0 | 1 | 0 |
| `0d85dc9f-1520-4bcb-8af4-8aad025255cb` | Agile Sales & Marketing | 163 | 128 | 157 | 0 | 4 | 7 |
| `781054a3-49b9-40f4-b2bf-ef59e0b1f01c` | Audit Org | 1 | 0 | 0 | 0 | 0 | 0 |
| `244382e6-96fe-4cba-ba58-bf036c209361` | Audit Org 5d8e | 1 | 0 | 0 | 0 | 0 | 0 |
| `f901dda5-d3e7-492b-ab55-4e8229709681` | LiveAuditOrg_1791566755 | 1 | 0 | 0 | 0 | 0 | 0 |
| `5d777a22-b00a-4404-8397-cc45b2e37404` | LiveAuditOrg_1791566782 | 1 | 0 | 0 | 0 | 0 | 1 |
| **Total** | — | **323** | **128** | **311** | **0** | **5** | **8** |

---

### 2.2 Finding Classification & Detailed Inventory

#### Audit Item 1: Duplicate Contact Emails Within Organization
- **Status:** **Confirmed Duplicate (1 group, 2 records)**
- **Classification:** Confirmed Duplicate
- **Tenant:** `3de43e6b-6cc0-4391-a061-2faba481bcb8` (Agile Receivables Org)
- **Sanitized Evidence:**
  - Record A ID: `aa1b6ce1-d55f-48c5-85aa-52e8e236678a`
    - Email: `pravalikapalle@agilereceivables.com`
    - First/Last Name: `Pravalika Palle`
    - Job Title: `Lead`
    - Company ID: `None`
    - HubSpot ID: `None`
    - Created At: `2026-10-07 22:54:26.227430+05:30`
    - References: 0 campaign enrollments, 0 outreach records, 0 call records, 0 leads, 0 deals.
  - Record B ID: `6d6bc3a9-84fd-40e9-8375-0e283f1863fb`
    - Email: `pravalikapalle@agilereceivables.com`
    - First/Last Name: `Pravalika Palle`
    - Job Title: `Lead`
    - Company ID: `None`
    - HubSpot ID: `None`
    - Created At: `2026-10-07 22:55:03.676744+05:30` (37.4 seconds later)
    - References: 0 campaign enrollments, 0 outreach records, 0 call records, 0 leads, 0 deals.
- **Root Cause:** Double-submission via `POST /api/v1/contacts` on October 7, 2026. Because `contact_service.create_contact()` lacks an existing email check and `contacts` lacks a database unique constraint, both inserts succeeded.
- **Impact:** Any query using `filter(Contact.organization_id == org_id, Contact.email == email).first()` resolves arbitrarily depending on query plan ordering. Prevents applying a unique index constraint.

#### Audit Item 2: Duplicate HubSpot Contact IDs
- **Within-Tenant:** **0 duplicate HubSpot contact IDs** across all 6 organizations. Every HubSpot ID is strictly unique within its organization.
- **Across-Tenants:** **154 shared HubSpot contact IDs** between Organization `3de43e6b-...` and Organization `0d85dc9f-...`.
- **Classification:** Legitimate Separate Tenant Records (produced by shared development environment token).
- **Evidence:** HubSpot Contact IDs (e.g., `293958591213`, `294016954103`, `308373850845`) exist independently in both tenant schemas. Each tenant holds separate campaign enrollments and outreach histories. These records must NOT be merged or linked across organizations.

#### Audit Item 3: Duplicate Company Domains After Safe Normalization
- **Total Companies:** 128 (all in Organization `0d85dc9f-1520-4bcb-8af4-8aad025255cb`).
- **Normalized Domain Duplicates:** **0 duplicate domain groups**.
- **Normalization Methodology:** `LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(domain, '^https?://', ''), '^www\.', '')))` split at `/`, `?`, and `#`.
- **Classification:** Clean / No Duplicates. All 128 companies possess clean, distinct domains.

#### Audit Item 4: Potential Duplicate Company Names
- **Classification:** Clean / No Duplicates.
- **Inspection Methodology:** Normalized name matching stripping punctuation, whitespace collapse, and common legal suffixes (`Inc`, `LLC`, `Corp`, `Co`, `Ltd`).
- **Result:** **0 duplicate normalized name groups** within any organization. All company names in the database correspond to distinct entities.

#### Audit Item 5: Duplicate Lead Emails
- **Classification:** Clean / No Duplicates.
- **Result:** **0 duplicate lead emails** within any organization. Across 311 lead records, every lead email is unique within its tenant.

#### Audit Item 6: Leads Associated with the Same Contact
- **Classification:** Clean / No Duplicates.
- **Result:** **0 multiple leads pointing to the same contact ID**. All 308 linked leads maintain a strict 1-to-1 relationship with their corresponding `Contact` record.

#### Audit Item 7: Lead / Contact Records Representing Potentially Same Person
- **Classification:** Potential Duplicate / Unlinked Records (2 unlinked pairs).
- **Overview:**
  - Total overlapping email pairs between `leads` and `contacts` in the same tenant: **310 pairs**.
  - Explicitly linked (`lead.contact_id == contact.id`): **308 pairs** (properly converted/synced).
  - Unlinked (`lead.contact_id IS NULL` despite identical email in same tenant): **2 pairs**.
- **Sanitized Unlinked Evidence:**
  1. Pair 1 (Org `0d85dc9f-...`):
     - Lead ID: `5fe6f2b0-a287-46a3-b88f-2763742dbf7e` | Email: `pravalikapalle@agilereceivables.com` | Source: `retell_voice_call` | Status: `new` | `contact_id`: `NULL`
     - Contact ID: `25591017-f2f1-4a02-a77e-ae578e513135` | Email: `pravalikapalle@agilereceivables.com` | Lead Status: `new` | Enrolled in 2 campaigns, 5 outreach records.
  2. Pair 2 (Org `0d85dc9f-...`):
     - Lead ID: `be5bafe0-e705-449a-813a-52f3ef3edf41` | Email: `test@example.com` | Source: `retell_voice_call` | Status: `new` | `contact_id`: `NULL`
     - Contact ID: `90be03bd-93ff-40b7-84db-2c7f87a93525` | Email: `test@example.com` | Lead Status: `new` | 0 campaigns.
  3. Single Standalone Lead (Org `0d85dc9f-...`):
     - Lead ID: `3f772103-5d2c-4b3c-860b-165adb639fc8` | Email: `pravalikareddy722@gmail.com` | Source: `manual` | Status: `new` | `contact_id`: `NULL` (No contact exists for this email).
- **Root Cause:** In `voice_followup.auto_upsert_contact_or_lead()`, when a call creates a new `Lead` snapshot from call analysis, it fails to populate `lead.contact_id = contact.id` when the corresponding contact exists or is created.

#### Audit Item 8: Repeated HubSpot Imports or Conversions
- **Sync Runs Inspected:** 9 sync runs recorded in `hubspot_sync_runs` table.
- **Behavior:**
  - `sync_contacts` performs upsert matching on `(Contact.hubspot_id == hs_id) | (Contact.email == raw_email)`.
  - `sync_companies` performs upsert matching on `(Company.hubspot_id == hs_id) | (Company.domain == domain)`.
  - Re-running synchronization is **idempotent in single-threaded execution**: existing rows are updated and counters report `updated_count += 1` rather than inserting duplicates.
  - However, in concurrent sync executions, lack of database locks or unique constraints would allow race-condition duplicate inserts.

#### Audit Item 9: Existing References Across Campaigns, Outreach, and Voice Records
- **Campaign Enrollments:** 4 total enrollments in `campaign_contacts`.
  - Contact `25591017-f2f1-4a02-a77e-ae578e513135`: Enrolled in Campaign `01fb4ace-...` and Campaign `33e60218-...`.
  - Contact `7ed2781d-c155-481b-93c0-bac3e7ca5b09`: Enrolled in Campaign `01fb4ace-...`.
  - Contact `142e7462-fd17-4515-abf9-5683a26ac115`: Enrolled in Campaign `d8b7de4a-...`.
- **Outreach Records:** 8 total records.
  - 5 records linked to Contact `25591017-f2f1-4a02-a77e-ae578e513135`.
  - 2 records linked to Contact `a4591acf-9dc4-4ad1-a0b3-29c2945fff3a`.
  - 1 record linked to Contact `142e7462-fd17-4515-abf9-5683a26ac115`.
- **Call Records:** 5 total records.
  - 2 records linked to Contact `25591017-f2f1-4a02-a77e-ae578e513135` and Lead `5fe6f2b0-a287-46a3-b88f-2763742dbf7e`.
  - 2 records linked to Contact `a4591acf-9dc4-4ad1-a0b3-29c2945fff3a`.
  - 1 unlinked call record (`bea6d498-...`).
- **Critical Reference Rule:** The duplicate contact in Org `3de43e6b-...` (`aa1b6ce1-...` and `6d6bc3a9-...`) has **zero foreign key references** in any table. The contact in Org `0d85dc9f-...` (`25591017-...`) has **active campaign enrollments, outreach events, and voice call logs that must remain completely untouched**.

---

## 3. Phase 2: Trace Creation Paths

| Path | File / Function | Existing Pre-Check Behavior | Concurrency Safety | Duplicate Risk |
|---|---|---|---|---|
| **1. HubSpot Contact Sync** | [`sync.py:169-250`](file:///d:/Agile-Sales-Marketing/backend/app/services/integrations/hubspot/sync.py#L169-L250) | Queries `db.query(Contact).filter(org_id, (hubspot_id == hs_id) \| (email == raw_email)).first()`. If found, updates; otherwise inserts. | **Unsafe** under concurrent sync runs (no row lock or unique index). | **Low** sequentially; **High** if parallel syncs trigger simultaneously. |
| **2. HubSpot Company Sync** | [`sync.py:355-390`](file:///d:/Agile-Sales-Marketing/backend/app/services/integrations/hubspot/sync.py#L355-L390) | Queries `db.query(Company).filter(org_id, (hubspot_id == hs_id) \| (domain == domain)).first()`. If found, updates; otherwise inserts. | **Unsafe** under concurrent sync runs. | **Low** sequentially; **High** under parallel sync runs. |
| **3. Manual CRM Contact Creation** | [`contact_service.py:41-65`](file:///d:/Agile-Sales-Marketing/backend/app/services/contact_service.py#L41-L65) (`POST /api/v1/contacts`) | **None.** Validates company reference, but performs zero query for existing email in the organization before `db.add(contact)`. | **Unsafe.** | **Critical.** Direct cause of confirmed duplicate DUP-01. |
| **4. Manual CRM Company Creation** | [`company_service.py:17-36`](file:///d:/Agile-Sales-Marketing/backend/app/services/company_service.py#L17-L36) (`POST /api/v1/companies`) | **None.** Directly instantiates `Company` and executes `db.add(company)` without checking domain or name. | **Unsafe.** | **High.** Clicking "Create Company" twice creates duplicate companies. |
| **5. Manual Lead Creation** | [`lead_generation/service.py:205-235`](file:///d:/Agile-Sales-Marketing/backend/app/services/lead_generation/service.py#L205-L235) (`POST /api/v1/leads`) | **None.** Directly instantiates `Lead` and executes `db.add(lead)` without checking existing email in the organization. | **Unsafe.** | **High.** Multiple manual leads with the same email can be added. |
| **6. Lead Generation / Discovery** | [`lead_generation/service.py:78-91`](file:///d:/Agile-Sales-Marketing/backend/app/services/lead_generation/service.py#L78-L91) (`POST /api/v1/leads/generate`) | Checks `source_external_id` if present. Does **not** check lead email or CRM contact email. | **Unsafe.** | **Medium.** Re-running discovery can insert leads with duplicate emails if external ID is omitted. |
| **7. Lead-to-CRM Conversion** | [`lead_generation/service.py:378-436`](file:///d:/Agile-Sales-Marketing/backend/app/services/lead_generation/service.py#L378-L436) (`POST /api/v1/leads/{id}/convert`) | Checks `Company.domain.ilike()` and `Company.name.ilike()`. Checks `Contact.email.ilike()`. Reuses existing entities if found. | **Unsafe** under rapid concurrent requests (no `SELECT FOR UPDATE` or DB unique constraint). | **Medium** due to potential race conditions or company name false-positive matching. |
| **8. Voice Call Follow-Up Webhook** | [`voice_followup.py:800-875`](file:///d:/Agile-Sales-Marketing/backend/app/services/outreach/voice_followup.py#L800-L875) (`retell-webhook`) | Checks `Contact` by `phone` or `email`. Checks `Lead` by `email`. If missing, creates minimal record. Does not normalize email casing. Does not set `lead.contact_id` on new lead. | **Unsafe** under concurrent webhook deliveries. | **Medium.** Can cause casing mismatches or unlinked lead/contact pairs. |
| **9. CSV Imports** | N/A | **Not implemented.** Backend contains no CSV import routes. | N/A | None currently. Must include deduplication when designed. |

---

## 4. Analysis of Missing Duplicate Protections

### 4.1 Missing Database-Level Protections
1. **`contacts` Table:**
   - Missing: `UNIQUE (organization_id, LOWER(email))`
   - Missing: `UNIQUE (organization_id, hubspot_id) WHERE hubspot_id IS NOT NULL`
   - Current State: Only non-unique index `ix_contacts_org_email` on `(organization_id, email)` (case-sensitive, permits duplicates).
2. **`companies` Table:**
   - Missing: `UNIQUE (organization_id, LOWER(domain)) WHERE domain IS NOT NULL`
   - Missing: `UNIQUE (organization_id, hubspot_id) WHERE hubspot_id IS NOT NULL`
   - Current State: No index on `domain`; non-unique index `ix_companies_org_hubspot_id`.
3. **`leads` Table:**
   - Missing: `UNIQUE (organization_id, LOWER(email)) WHERE email IS NOT NULL`
   - Current State: Unique constraint `uq_leads_org_source_ext` on `(organization_id, source, source_external_id)`. In PostgreSQL, standard unique constraints treat `NULL` as distinct, permitting unlimited duplicate leads where `source_external_id IS NULL`.

### 4.2 Missing Application-Level Protections
1. **Inconsistent Email Normalization:** Some code paths use `.strip().lower()`, while others (`voice_followup.py`) query `Contact.email == data.email` without lowercase normalization.
2. **Domain Normalization Missing:** `Company.domain` is stored as provided without stripping `https://`, `http://`, `www.`, or path suffixes. `acme.com` and `www.acme.com` would currently bypass equality checks.
3. **Absence of Concurrency Locks:** Sync upserts, conversions, and webhook processors do not utilize `SELECT ... FOR UPDATE` row locks or database-level `ON CONFLICT DO UPDATE` / `ON CONFLICT DO NOTHING` statements.
4. **Company Matching by Name Alone:** In `convert_lead_to_crm()`, if domain is absent, it falls back to `Company.name.ilike(lead.company_name)`. For generic names (e.g. "Acme", "Consulting", "Unknown"), this causes false-positive company merges.

---

## 5. Phase 3: Safe Duplicate Prevention Design

### 5.1 Normalization Specifications

#### Email Normalization Standard:
All email inputs across manual creation, sync, voice webhooks, and lead discovery must pass through a single normalization function:
```python
def normalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned if cleaned else None
```

#### Company Domain Normalization Standard:
Company domains must be normalized to clean apex / hostnames:
```python
import re

def normalize_domain(domain: Optional[str]) -> Optional[str]:
    if not domain:
        return None
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0].strip()
    return d if d else None
```

#### Company Name Matching Safety Rule:
- Company name alone must **never** be used as authoritative proof of identity across distinct sources.
- Company deduplication must prioritize:
  1. Primary Key (`company_id`)
  2. Upstream Integration ID (`hubspot_id`) within the organization.
  3. Authoritative Normalized Domain (`domain`) within the organization.
  4. If only company name is available and domain is null, match only if the name is an exact normalized match and employee count / city / country matches, or create a distinct company to avoid accidental cross-entity merging.

---

### 5.2 Proposed Database Constraints (Alembic Migration Specification)

All proposed constraints are strictly **organization-scoped** and use PostgreSQL **partial indexes** where columns can be nullable:

```sql
-- 1. Contacts: Enforce unique email per tenant (case-insensitive)
CREATE UNIQUE INDEX uq_contacts_org_lower_email 
ON contacts (organization_id, LOWER(email)) 
WHERE email IS NOT NULL AND TRIM(email) != '';

-- 2. Contacts: Enforce unique HubSpot Contact ID per tenant
CREATE UNIQUE INDEX uq_contacts_org_hubspot_id 
ON contacts (organization_id, hubspot_id) 
WHERE hubspot_id IS NOT NULL AND TRIM(hubspot_id) != '';

-- 3. Companies: Enforce unique company domain per tenant (case-insensitive)
CREATE UNIQUE INDEX uq_companies_org_lower_domain 
ON companies (organization_id, LOWER(domain)) 
WHERE domain IS NOT NULL AND TRIM(domain) != '';

-- 4. Companies: Enforce unique HubSpot Company ID per tenant
CREATE UNIQUE INDEX uq_companies_org_hubspot_id 
ON companies (organization_id, hubspot_id) 
WHERE hubspot_id IS NOT NULL AND TRIM(hubspot_id) != '';

-- 5. Leads: Enforce unique lead email per tenant (case-insensitive)
CREATE UNIQUE INDEX uq_leads_org_lower_email 
ON leads (organization_id, LOWER(email)) 
WHERE email IS NOT NULL AND TRIM(email) != '';
```

---

### 5.3 Required Pre-Migration Checks

Applying the proposed unique indexes immediately would **fail** due to the confirmed duplicate in `contacts`:

| Proposed Index | Pre-Migration Status | Compatibility Check Result | Action Required Before Migration |
|---|---|---|---|
| `uq_contacts_org_lower_email` | **BLOCKED** | **1 duplicate group found:** Org `3de43e6b-...`, email `pravalikapalle@agilereceivables.com` (IDs `aa1b6ce1-...` and `6d6bc3a9-...`). | Must execute administrative resolution of Record B before applying migration. |
| `uq_contacts_org_hubspot_id` | **PASSED** | 0 duplicates found within any organization. | Ready to apply. |
| `uq_companies_org_lower_domain`| **PASSED** | 0 duplicate normalized domains found across all 128 companies. | Ready to apply. |
| `uq_companies_org_hubspot_id` | **PASSED** | 0 duplicate HubSpot IDs found within any organization. | Ready to apply. |
| `uq_leads_org_lower_email` | **PASSED** | 0 duplicate lead emails found across all 311 leads. | Ready to apply. |

#### Pre-Migration Verification Query:
Before running `alembic upgrade head`, the deployment pipeline must run:
```sql
SELECT organization_id, LOWER(email), COUNT(*) 
FROM contacts 
WHERE email IS NOT NULL 
GROUP BY organization_id, LOWER(email) 
HAVING COUNT(*) > 1;
```
If the query returns any rows, the migration must halt and raise an alert.

---

### 5.4 Safe Remediation Plan for Existing Duplicates

To resolve the pre-migration blocker safely without data loss, violation of safety rules, or accidental side-effects:

#### Remediation Protocol for Contact `aa1b6ce1-...` and `6d6bc3a9-...`:
1. **Verification of Absence of Dependencies:**
   - Both rows have 0 `campaign_contacts`, 0 `outreach`, 0 `call_records`, 0 `deals`, 0 `leads`, and no `hubspot_id`.
   - Record A (`aa1b6ce1-d55f-48c5-85aa-52e8e236678a`) was created at `22:54:26`.
   - Record B (`6d6bc3a9-84fd-40e9-8375-0e283f1863fb`) was created at `22:55:03`.
2. **Administrative Resolution Option (Recommended):**
   - Retain Record A as the primary authoritative record.
   - For Record B, rather than a hard SQL `DELETE`, perform an administrative deprecation:
     - Update Record B email to a quarantined tombstone address: `pravalikapalle+duplicate_archive_6d6bc3a9@agilereceivables.com`.
     - Or set an `is_archived = True` flag (if soft-delete column is introduced).
     - Alternatively, perform a strict administrative `DELETE FROM contacts WHERE id = '6d6bc3a9-84fd-40e9-8375-0e283f1863fb'` within a transaction that first verifies `SELECT COUNT(*) FROM campaign_contacts WHERE contact_id = '6d6bc3a9-...' == 0` and logs an audit record.
3. **Preservation of Cross-Tenant Record:**
   - Contact `25591017-f2f1-4a02-a77e-ae578e513135` in Organization `0d85dc9f-...` has 2 active campaign enrollments, 5 outreach items, and 2 call records. It belongs to a different organization and must **never** be merged or altered.

#### Remediation Protocol for Unlinked Lead/Contact Pairs:
1. For Lead `5fe6f2b0-a287-46a3-b88f-2763742dbf7e` and Contact `25591017-f2f1-4a02-a77e-ae578e513135`:
   - Both exist in Org `0d85dc9f-...` with email `pravalikapalle@agilereceivables.com`.
   - Run a safe data backfill update:
     ```sql
     UPDATE leads l
     SET contact_id = c.id
     FROM contacts c
     WHERE l.organization_id = c.organization_id
       AND LOWER(l.email) = LOWER(c.email)
       AND l.contact_id IS NULL;
     ```
   - This idempotently links the 2 voice-generated leads to their corresponding pre-existing contacts without modifying any contact or outreach data.

---

### 5.5 Tests Required for Repeated and Concurrent Operations

Prior to and following future implementation, the following automated tests must be executed:

1. **Manual Contact Creation Deduplication Test:**
   - Attempt creating contact with email `test@acme.com` twice sequentially in the same org.
   - Assert: Second call returns existing contact or HTTP 409 Conflict, rather than inserting duplicate.
2. **Manual Company Creation Deduplication Test:**
   - Attempt creating company with domain `https://www.acme.com/` and `acme.com` in the same org.
   - Assert: Normalized domain matches and returns existing company.
3. **Concurrent Contact Creation Race Condition Test:**
   - Dispatch 10 parallel HTTP requests (`asyncio.gather`) to `POST /api/v1/contacts` with the exact same email under the same tenant token.
   - Assert: Exactly 1 contact row is inserted in PostgreSQL; database unique constraint prevents duplicates.
4. **Repeated HubSpot Sync Idempotency Test:**
   - Run `HubSpotSyncEngine.run_sync()` 3 times consecutively on the same mock data payload.
   - Assert: Initial run imports records (`imported_count == N`). Subsequent runs report `imported_count == 0`, `updated_count == N`. Database total row count remains strictly constant.
5. **Cross-Tenant Isolation Test:**
   - Tenant A and Tenant B both create a contact with email `ceo@enterprise.com`.
   - Assert: Both succeed independently; neither tenant can read, modify, or overwrite the other's contact.
6. **Lead Conversion Idempotency Test:**
   - Call `convert_lead_to_crm()` twice on the same lead.
   - Assert: First call creates Company and Contact. Second call reuses existing entities and returns `company_created=False, contact_created=False`.

---

## 6. Unverified Areas & Unresolved Risks

1. **HubSpot Upstream Merges:** If two contacts or companies are merged inside HubSpot CRM, HubSpot retains the primary ID and aliases the merged ID. The local database currently maps only a single `hubspot_id` per entity. Handling HubSpot merged IDs requires subscribing to HubSpot webhook `contact.merged` events.
2. **Multi-Tenant Credentials Architecture:** The platform currently relies on a single `HUBSPOT_ACCESS_TOKEN` in `.env`. Until tenant-scoped encrypted credential storage is added (Finding DUP-03), any tenant executing HubSpot sync will ingest data from the same shared HubSpot portal.
3. **Batch External Import Ingestion:** CSV or webhook bulk ingestion is not yet implemented. Any future bulk import feature must enforce the normalization and database constraints designed in this audit before deployment.

---

*End of Duplicate Prevention Audit Report.*
