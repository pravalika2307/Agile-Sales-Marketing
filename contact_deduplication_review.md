# Final Contact Deduplication Review & Hardened Remediation Plan

**Project:** D:\Agile-Sales-Marketing  
**Document:** `contact_deduplication_review.md`  
**Review Date:** October 12, 2026  
**Status:** Hardened Preparation & Code-Review Only (Zero Database Mutations Executed)  
**Target Environment:** Local PostgreSQL (`agile_sales_marketing` on `localhost:5432`)  
**Target Organization:** `3de43e6b-6cc0-4391-a061-2faba481bcb8` (Agile Receivables Org)  

---

## 1. Executive Summary

During the implementation of duplicate prevention across Agile Sales & Marketing, organization-scoped partial unique indexes were safely added for companies (`uq_companies_org_lower_domain`, `uq_companies_org_hubspot_id`), contacts (`uq_contacts_org_hubspot_id`), and leads (`uq_leads_org_lower_email`).

The unique constraint for contact emails (`uq_contacts_org_lower_email`) was **safely halted and skipped** by migration `a1b2c3d4e5f6` because the database contains exactly **one duplicate contact group** (2 records) sharing the normalized email address `pravalikapalle@agilereceivables.com` in organization `3de43e6b-6cc0-4391-a061-2faba481bcb8`.

This document hardens the remediation plan prior to any administrative execution:
- Replaces non-standard SQL statements with a robust, atomic, fail-closed PL/pgSQL block.
- Implements strict snapshot fingerprinting for both the canonical and duplicate rows before proceeding.
- Scans all foreign keys dynamically across the entire database catalog.
- Establishes a durable, append-only backup architecture with batch tracking and retention rules.
- Defines a safe rollback procedure that refuses to overwrite existing records and preserves the unique index.
- Aligns email normalization policy across application services, migrations, and PostgreSQL indexes.
- Provides a comprehensive execution checklist for separately approved maintenance.

---

## 2. Target Record Verification & Snapshot Fingerprints

Direct verification against PostgreSQL confirmed the exact duplicate records. No discrepancies exist between the live database and audit documentation.

### Side-by-Side Record Snapshots

| Field | Canonical Record A | Duplicate Candidate Record B | Separate Tenant Record C |
| :--- | :--- | :--- | :--- |
| **Contact ID** | `aa1b6ce1-d55f-48c5-85aa-52e8e236678a` | `6d6bc3a9-84fd-40e9-8375-0e283f1863fb` | `25591017-f2f1-4a02-a77e-ae578e513135` |
| **Organization ID** | `3de43e6b-6cc0-4391-a061-2faba481bcb8` | `3de43e6b-6cc0-4391-a061-2faba481bcb8` | `0d85dc9f-1520-4bcb-8af4-8aad025255cb` |
| **Organization Name** | Agile Receivables Org | Agile Receivables Org | Agile Sales & Marketing |
| **Email** | `pravalikapalle@agilereceivables.com` | `pravalikapalle@agilereceivables.com` | `pravalikapalle@agilereceivables.com` |
| **First Name** | `Pravalika` | `Pravalika` | `Pravalika` |
| **Last Name** | `Palle` | `Palle` | `Palle` |
| **Job Title** | `Lead` | `Lead` | `Operations Lead` |
| **Phone** | `NULL` | `NULL` | `+15551234567` |
| **Company ID** | `NULL` | `NULL` | `NULL` |
| **HubSpot ID** | `NULL` | `NULL` | `NULL` |
| **Lead Status** | `new` | `new` | `new` |
| **Created At** | `2026-10-07 22:54:26.227430+05:30` | `2026-10-07 22:55:03.676744+05:30` | `2026-10-08 23:07:22.142335+05:30` |
| **Updated At** | `2026-10-07 22:54:26.227433+05:30` | `2026-10-07 22:55:03.676746+05:30` | `2026-10-08 23:07:22.142338+05:30` |
| **Dependent Records** | **0** (all tables) | **0** (all tables) | **8** (2 campaigns, 4 outreach, 2 calls) |

### Canonical Selection Rationale
Record A is selected as canonical because it was created first (37.4 seconds earlier), establishing chronological primacy. Record B is an unreferenced duplicate created by rapid double-submission. Because both records have identical field values and zero child references, selecting Record A retains 100% of business data while preserving original timestamps.

---

## 3. Comprehensive Foreign-Key & Catalog Inspection

An inspection of `information_schema.table_constraints` identified all foreign keys referencing the `contacts` table in PostgreSQL:

| Source Table | Foreign Key Column | Constraint Name | Record A Count | Record B Count |
| :--- | :--- | :--- | :---: | :---: |
| `campaign_contacts` | `contact_id` | `fk_campaign_contacts_contact_id_contacts` | 0 | 0 |
| `outreach` | `contact_id` | `fk_outreach_contact_id_contacts` | 0 | 0 |
| `call_records` | `contact_id` | `call_records_contact_id_fkey` | 0 | 0 |
| `leads` | `contact_id` | `leads_contact_id_fkey` | 0 | 0 |
| `deals` | `contact_id` | `fk_deals_contact_id_contacts` | 0 | 0 |

No other tables in the database schema reference `contacts.id`. The remediation transaction includes a dynamic PL/pgSQL validation loop that queries all foreign-key constraints registered in PostgreSQL, guaranteeing that even newly added tables are checked.

---

## 4. Hardened Remediation Transaction (Task 1)

The remediation transaction is structured as a single atomic, fail-closed `DO $$ ... $$ LANGUAGE plpgsql;` block inside an explicit `BEGIN ... COMMIT` block. Standalone `PERFORM` statements have been replaced with valid PL/pgSQL execution.

```sql
\set ON_ERROR_STOP on

BEGIN;

-- 0. Acquire table-level lock to prevent concurrent contact creation, modifications, or DDL
LOCK TABLE contacts IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    c_org_id      CONSTANT UUID := '3de43e6b-6cc0-4391-a061-2faba481bcb8';
    c_email       CONSTANT VARCHAR := 'pravalikapalle@agilereceivables.com';
    c_canon_id    CONSTANT UUID := 'aa1b6ce1-d55f-48c5-85aa-52e8e236678a';
    c_dup_id      CONSTANT UUID := '6d6bc3a9-84fd-40e9-8375-0e283f1863fb';
    
    v_canon_row   contacts%ROWTYPE;
    v_dup_row     contacts%ROWTYPE;
    
    v_batch_id    UUID := gen_random_uuid();
    v_fk_rec      RECORD;
    v_ref_count   BIGINT := 0;
    v_total_dupes BIGINT := 0;
    v_ins_count   INT := 0;
    v_del_count   INT := 0;
BEGIN
    -- Explicitly verify table-level lock is held
    LOCK TABLE contacts IN SHARE ROW EXCLUSIVE MODE;

    -- 1. Ensure durable backup table exists with compatible schema
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'contacts_deduplication_quarantine_backup'
    ) THEN
        -- Verify that all 16 required columns and data types exist
        IF (
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'contacts_deduplication_quarantine_backup'
              AND (
                  (column_name = 'backup_id' AND data_type = 'bigint') OR
                  (column_name = 'execution_batch_id' AND data_type = 'uuid' AND is_nullable = 'NO') OR
                  (column_name = 'quarantined_at' AND data_type = 'timestamp with time zone' AND is_nullable = 'NO') OR
                  (column_name = 'reason' AND data_type = 'text' AND is_nullable = 'NO') OR
                  (column_name = 'id' AND data_type = 'uuid' AND is_nullable = 'NO') OR
                  (column_name = 'organization_id' AND data_type = 'uuid' AND is_nullable = 'NO') OR
                  (column_name = 'company_id' AND data_type = 'uuid') OR
                  (column_name = 'email' AND data_type = 'character varying' AND is_nullable = 'NO') OR
                  (column_name = 'first_name' AND data_type = 'character varying' AND is_nullable = 'NO') OR
                  (column_name = 'last_name' AND data_type = 'character varying' AND is_nullable = 'NO') OR
                  (column_name = 'phone' AND data_type = 'character varying') OR
                  (column_name = 'job_title' AND data_type = 'character varying') OR
                  (column_name = 'lead_status' AND data_type = 'character varying' AND is_nullable = 'NO') OR
                  (column_name = 'created_at' AND data_type = 'timestamp with time zone' AND is_nullable = 'NO') OR
                  (column_name = 'updated_at' AND data_type = 'timestamp with time zone' AND is_nullable = 'NO') OR
                  (column_name = 'hubspot_id' AND data_type = 'character varying')
              )
        ) != 16 THEN
            RAISE EXCEPTION 'Precondition Failed: Existing contacts_deduplication_quarantine_backup table has incompatible column schema or data types';
        END IF;

        -- Verify required unique constraint on (execution_batch_id, id)
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE tablename = 'contacts_deduplication_quarantine_backup'
              AND indexname = 'uq_quarantine_backup_batch_id'
        ) THEN
            RAISE EXCEPTION 'Precondition Failed: Existing contacts_deduplication_quarantine_backup missing unique index uq_quarantine_backup_batch_id';
        END IF;
    ELSE
        CREATE TABLE contacts_deduplication_quarantine_backup (
            backup_id          BIGSERIAL PRIMARY KEY,
            execution_batch_id UUID NOT NULL,
            quarantined_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reason             TEXT NOT NULL,
            id                 UUID NOT NULL,
            organization_id    UUID NOT NULL,
            company_id         UUID,
            email              VARCHAR(255) NOT NULL,
            first_name         VARCHAR(100) NOT NULL,
            last_name          VARCHAR(100) NOT NULL,
            phone              VARCHAR(50),
            job_title          VARCHAR(150),
            lead_status        VARCHAR NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL,
            updated_at         TIMESTAMPTZ NOT NULL,
            hubspot_id         VARCHAR(100)
        );

        CREATE UNIQUE INDEX uq_quarantine_backup_batch_id
        ON contacts_deduplication_quarantine_backup (execution_batch_id, id);
    END IF;

    -- 2. Lock both target rows with explicit row locking
    SELECT * INTO v_canon_row
    FROM contacts
    WHERE id = c_canon_id AND organization_id = c_org_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Precondition Failed: Canonical row % not found in org %', c_canon_id, c_org_id;
    END IF;

    SELECT * INTO v_dup_row
    FROM contacts
    WHERE id = c_dup_id AND organization_id = c_org_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Precondition Failed: Duplicate candidate % not found in org %', c_dup_id, c_org_id;
    END IF;

    -- 3. Snapshot Fingerprint Assertions: verify exact field values match approved state
    IF LOWER(TRIM(v_canon_row.email)) != c_email OR
       v_canon_row.first_name != 'Pravalika' OR
       v_canon_row.last_name != 'Palle' OR
       v_canon_row.lead_status != 'new' OR
       v_canon_row.company_id IS NOT NULL OR
       v_canon_row.phone IS NOT NULL OR
       v_canon_row.hubspot_id IS NOT NULL THEN
        RAISE EXCEPTION 'Precondition Failed: Canonical row snapshot does not match approved baseline';
    END IF;

    IF LOWER(TRIM(v_dup_row.email)) != c_email OR
       v_dup_row.first_name != 'Pravalika' OR
       v_dup_row.last_name != 'Palle' OR
       v_dup_row.lead_status != 'new' OR
       v_dup_row.company_id IS NOT NULL OR
       v_dup_row.phone IS NOT NULL OR
       v_dup_row.hubspot_id IS NOT NULL THEN
        RAISE EXCEPTION 'Precondition Failed: Duplicate candidate snapshot does not match approved baseline';
    END IF;

    -- 4. Dynamic Foreign-Key Scan: verify ZERO references across all foreign keys pointing to contacts
    FOR v_fk_rec IN (
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'contacts'
    ) LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I WHERE %I = $1', v_fk_rec.table_name, v_fk_rec.column_name)
        INTO v_ref_count
        USING c_dup_id;

        IF v_ref_count > 0 THEN
            RAISE EXCEPTION 'Precondition Failed: Duplicate record % has % active foreign keys in %.%',
                c_dup_id, v_ref_count, v_fk_rec.table_name, v_fk_rec.column_name;
        END IF;
    END LOOP;

    -- 5. Scope Assertion: verify exactly 1 duplicate group exists in the entire database
    SELECT COUNT(*) INTO v_total_dupes FROM (
        SELECT organization_id, LOWER(TRIM(email))
        FROM contacts
        WHERE email IS NOT NULL AND TRIM(email) != ''
        GROUP BY organization_id, LOWER(TRIM(email))
        HAVING COUNT(*) > 1
    ) t;

    IF v_total_dupes != 1 THEN
        RAISE EXCEPTION 'Precondition Failed: Expected exactly 1 duplicate group, found %', v_total_dupes;
    END IF;

    -- 6. Insert into durable quarantine backup table
    INSERT INTO contacts_deduplication_quarantine_backup (
        execution_batch_id, reason, id, organization_id, company_id,
        email, first_name, last_name, phone, job_title,
        lead_status, created_at, updated_at, hubspot_id
    ) VALUES (
        v_batch_id,
        'Duplicate resolution: consolidated into canonical contact ' || c_canon_id::text,
        v_dup_row.id, v_dup_row.organization_id, v_dup_row.company_id,
        v_dup_row.email, v_dup_row.first_name, v_dup_row.last_name, v_dup_row.phone, v_dup_row.job_title,
        v_dup_row.lead_status, v_dup_row.created_at, v_dup_row.updated_at, v_dup_row.hubspot_id
    );

    GET DIAGNOSTICS v_ins_count = ROW_COUNT;
    IF v_ins_count != 1 THEN
        RAISE EXCEPTION 'Integrity Failure: Expected exactly 1 backup row inserted, got %', v_ins_count;
    END IF;

    -- Verify that the backup row for this exact execution batch ID and contact ID exists
    IF NOT EXISTS (
        SELECT 1 FROM contacts_deduplication_quarantine_backup
        WHERE execution_batch_id = v_batch_id AND id = c_dup_id
    ) THEN
        RAISE EXCEPTION 'Integrity Failure: Backup verification failed for current batch % and contact %', v_batch_id, c_dup_id;
    END IF;

    -- 7. Narrow, targeted delete of duplicate record
    DELETE FROM contacts
    WHERE id = c_dup_id
      AND organization_id = c_org_id
      AND email = c_email;

    GET DIAGNOSTICS v_del_count = ROW_COUNT;
    IF v_del_count != 1 THEN
        RAISE EXCEPTION 'Integrity Failure: Expected exactly 1 row deleted, got %', v_del_count;
    END IF;

    RAISE NOTICE 'Deduplication completed successfully. Batch ID: %', v_batch_id;
END $$;

COMMIT;
```

### Concurrency Race Analysis & Table/Row-Level Locking
- **SHARE ROW EXCLUSIVE Table Lock:** The transaction immediately executes `LOCK TABLE contacts IN SHARE ROW EXCLUSIVE MODE;` as its first operation.
  - In PostgreSQL, `SHARE ROW EXCLUSIVE` conflicts with `ROW EXCLUSIVE` (acquired by `INSERT`, `UPDATE`, `DELETE`), `SHARE UPDATE EXCLUSIVE` (concurrent indexing / vacuuming), and `ACCESS EXCLUSIVE` (DDL alterations).
  - This mathematically guarantees that no concurrent process can insert new duplicate contacts, modify the target rows, or execute schema alterations during the entire remediation window.
  - Concurrent `SELECT` queries (which acquire `ACCESS SHARE`) are completely unblocked and run normally.
  - The table lock is acquired before target row snapshot verification, foreign-key catalog scans, duplicate group counting, backup insertion, and deletion, and is held continuously until transaction `COMMIT` or `ROLLBACK`.
- **Foreign-Key Reference Race Prevention:** In PostgreSQL, inserting a foreign-key child row requires the database engine to acquire a `FOR KEY SHARE` lock on the referenced parent row in `contacts`.
- **Lock Interaction:** Because the remediation transaction holds both a `SHARE ROW EXCLUSIVE` table lock and an explicit `FOR UPDATE` lock on `v_dup_row` (`c_dup_id`), any concurrent transaction attempting to insert a new dependent record (in `campaign_contacts`, `outreach`, `leads`, `deals`, or `call_records`) will block waiting for the remediation transaction. Once the remediation transaction commits the `DELETE`, the concurrent insert's foreign-key check immediately fails with `foreign_key_violation`.
- **Pre-Lock Race Detection:** If a concurrent insert committed *before* the remediation transaction locked `v_dup_row`, the dynamic foreign-key scan in step 4 will observe `v_ref_count > 0` and raise an exception, rolling back the entire transaction (`FAIL CLOSED`).

---

## 5. Safe Backup & Rollback Architecture (Task 2)

### Backup Table Design & Governance
- **Table Name:** `contacts_deduplication_quarantine_backup`
- **Durable Storage:** Stored directly inside PostgreSQL. Survived across server restarts and connection resets.
- **Batch Isolation:** Each execution assigns a unique `execution_batch_id UUID`. A unique index on `(execution_batch_id, id)` prevents duplicate or stale backup reuse.
- **Retention & Access:** Minimum retention period of 90 days. Read-only permissions granted to application service role; insert/delete restricted to migration scripts.

### Rollback Procedures & Unique Index Safeguards
Routine rollback must **never** automatically drop `uq_contacts_org_lower_email`, as dropping a production index breaks tenant isolation and creates concurrency windows for other organizations.

#### Distinguishing Exact Rollback vs. Audit-Alias Restoration:
1. **Original Email Preserved in Durable Backup:** The backup table `contacts_deduplication_quarantine_backup` stores the exact original email (`pravalikapalle@agilereceivables.com`), UUID, and timestamps.
2. **Exact Rollback:** When the unique index is not active (or if an approved maintenance rollback downgrades the migration), Record B is restored with its exact original email and all 12 original column values.
3. **Audit-Alias Restoration:** If `uq_contacts_org_lower_email` is already active in production and canonical Record A still exists, inserting Record B with the identical email violates the unique constraint (`SQLSTATE 23505`). To restore the row for legal/audit purposes without dropping the index, it is restored with a non-colliding audit alias email (`pravalikapalle+restored_audit_6d6bc3a9@agilereceivables.com`).
4. **Exact Restoration with Active Unique Index:** To restore the exact original email while the index is active without silent index dropping, an administrator must execute a formal, recorded Alembic downgrade (`alembic downgrade -1`) in an approved maintenance window, which safely drops the index via DDL before performing the exact rollback.

#### Rollback Script (Refuses Overwrite)
```sql
\set ON_ERROR_STOP on

BEGIN;

-- Acquire table lock to prevent concurrent contact creation or modifications during rollback
LOCK TABLE contacts IN SHARE ROW EXCLUSIVE MODE;

DO $$
DECLARE
    c_target_id    CONSTANT UUID := '6d6bc3a9-84fd-40e9-8375-0e283f1863fb';
    c_allow_alias  CONSTANT BOOLEAN := FALSE; -- Safe default: refuse to silently modify original email
    v_backup_row   contacts_deduplication_quarantine_backup%ROWTYPE;
    v_canon_exists BOOLEAN := FALSE;
    v_index_exists BOOLEAN := FALSE;
    v_ins_count    INT := 0;
BEGIN
    -- 1. Fetch latest backup record
    SELECT * INTO v_backup_row
    FROM contacts_deduplication_quarantine_backup
    WHERE id = c_target_id
    ORDER BY quarantined_at DESC, backup_id DESC
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Rollback Failed: No backup record found for ID %', c_target_id;
    END IF;

    -- 2. Refuse to overwrite existing UUID
    IF EXISTS (SELECT 1 FROM contacts WHERE id = c_target_id) THEN
        RAISE EXCEPTION 'Rollback Refused: Contact ID % already exists in contacts table', c_target_id;
    END IF;

    -- 3. Check whether unique index is active
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'contacts' AND indexname = 'uq_contacts_org_lower_email'
    ) INTO v_index_exists;

    -- 4. Check whether canonical record exists with same email in org
    SELECT EXISTS (
        SELECT 1 FROM contacts 
        WHERE organization_id = v_backup_row.organization_id 
          AND LOWER(TRIM(email)) = LOWER(TRIM(v_backup_row.email))
    ) INTO v_canon_exists;

    -- 5. Execution branch
    IF v_index_exists AND v_canon_exists THEN
        -- Unique index is active and canonical record exists.
        -- Refuse to silently alter email or drop index unless explicitly allowed.
        IF NOT c_allow_alias THEN
            RAISE EXCEPTION 'Rollback Refused: Unique index uq_contacts_org_lower_email is active and canonical contact % exists. Restoring original email (%) would violate the unique constraint. To restore the exact original record, downgrade migration first via alembic downgrade -1. Rollback refuses to silently modify original email or drop the index.',
                v_backup_row.id, v_backup_row.email;
        END IF;

        -- Explicitly allowed audit alias restoration:
        INSERT INTO contacts (
            id, organization_id, company_id, email,
            first_name, last_name, phone, job_title,
            lead_status, created_at, updated_at, hubspot_id
        ) VALUES (
            v_backup_row.id, v_backup_row.organization_id, v_backup_row.company_id,
            'pravalikapalle+restored_audit_6d6bc3a9@agilereceivables.com',
            v_backup_row.first_name, v_backup_row.last_name, v_backup_row.phone, v_backup_row.job_title,
            v_backup_row.lead_status, v_backup_row.created_at, v_backup_row.updated_at, v_backup_row.hubspot_id
        );
        RAISE NOTICE 'Restored record % with quarantined audit email to preserve unique index.', c_target_id;
    ELSE
        -- Either index is absent or canonical record was removed: restore exact original email
        INSERT INTO contacts (
            id, organization_id, company_id, email,
            first_name, last_name, phone, job_title,
            lead_status, created_at, updated_at, hubspot_id
        ) VALUES (
            v_backup_row.id, v_backup_row.organization_id, v_backup_row.company_id,
            v_backup_row.email,
            v_backup_row.first_name, v_backup_row.last_name, v_backup_row.phone, v_backup_row.job_title,
            v_backup_row.lead_status, v_backup_row.created_at, v_backup_row.updated_at, v_backup_row.hubspot_id
        );
        RAISE NOTICE 'Restored record % with original email address.', c_target_id;
    END IF;

    GET DIAGNOSTICS v_ins_count = ROW_COUNT;
    IF v_ins_count != 1 THEN
        RAISE EXCEPTION 'Rollback Failed: Expected 1 row restored, got %', v_ins_count;
    END IF;
END $$;

COMMIT;
```

---

## 6. Normalization Alignment Findings (Task 3)

### Comparison Across System Layers

| Layer | Implementation | Trimming Behavior | Casing Behavior | Null / Blank Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **`normalize_email()`** | `email.strip().lower() if email else None` | Strips whitespace | Lowercase | Returns `None` for null or blank |
| **Application Services** | `func.lower(Contact.email) == norm_email` | Operates on trimmed input | Case-insensitive | `if norm_email:` check guards lookup |
| **Leads Index (`a1b2c3d4e5f6`)** | `(organization_id, LOWER(email))` | Database B-tree | Lowercase | Filtered: `WHERE email IS NOT NULL AND TRIM(email) != ''` |
| **Proposed Contacts Index** | `(organization_id, LOWER(email))` | Database B-tree | Lowercase | Filtered: `WHERE email IS NOT NULL AND TRIM(email) != ''` |

### Database Verification:
1. Checked for untrimmed emails in `contacts`:
   ```sql
   SELECT COUNT(*) FROM contacts WHERE email != TRIM(email);
   ```
   **Result:** `0` rows with whitespace anomalies.
2. Evaluated `LOWER(TRIM(email))` vs. `LOWER(email)`:
   Because `normalize_email()` trims all incoming data before persistence, `LOWER(email)` and `LOWER(TRIM(email))` evaluate identically on existing database data.
3. **Recommended Normalization Policy:**
   - Application layer: Continue enforcing `normalize_email()` (`strip().lower()`).
   - Database index expression: Use `(organization_id, LOWER(email)) WHERE email IS NOT NULL AND TRIM(email) != ''`. This guarantees exact parity with `uq_leads_org_lower_email` on the `leads` table and correctly handles missing and empty values.

---

## 7. Migration Safety Findings (Task 4)

### Inspection of Existing Migration `a1b2c3d4e5f6`
- **Migration File:** [`backend/alembic/versions/a1b2c3d4e5f6_add_duplicate_prevention_unique_constraints.py`](file:///d:/Agile-Sales-Marketing/backend/alembic/versions/a1b2c3d4e5f6_add_duplicate_prevention_unique_constraints.py)
- **Pre-check Logic:** Lines 48–65 query `contacts` for duplicate `(organization_id, LOWER(email))`. Finding 1 duplicate group in Org `3de43e6b-...`, the script logged a notice and skipped creating the index.
- **Current PostgreSQL Index State:** Checked `pg_indexes WHERE tablename = 'contacts'`:
  - `pk_contacts` (Unique PK on `id`)
  - `ix_contacts_organization_id`
  - `ix_contacts_company_id`
  - `ix_contacts_email`
  - `ix_contacts_org_email`
  - `ix_contacts_hubspot_id`
  - `ix_contacts_org_hubspot_id`
  - `uq_contacts_org_hubspot_id` (Unique on `organization_id, hubspot_id`)
  - **`uq_contacts_org_lower_email` is COMPLETELY ABSENT.** No invalid, broken, or partial index was created.

### Followup Migration Design (`b2c3d4e5f6a7`)
A new Alembic migration script will add the index safely:
- **Down Revision:** `a1b2c3d4e5f6`
- **Precondition Assertion:** Fails closed if duplicate count > 0.
- **Idempotency:** Uses `CREATE UNIQUE INDEX IF NOT EXISTS`.

```python
"""add_contacts_unique_lower_email_index

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-12 22:00:00.000000
"""
import re
from typing import Optional, Sequence, Union
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

def strip_enclosing_parens(s: str) -> str:
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        matched = False
        for i, ch in enumerate(s):
            if ch == "(": depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    matched = (i == len(s) - 1)
                    break
        if matched: s = s[1:-1].strip()
        else: break
    return s

def split_top_level_and(expr: str) -> list[str]:
    expr = strip_enclosing_parens(expr)
    conjuncts = []
    depth = 0
    current = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == "(": depth += 1; current.append(ch); i += 1
        elif ch == ")": depth -= 1; current.append(ch); i += 1
        elif depth == 0 and expr[i:i+4].lower() == " or ":
            raise ValueError(f"Predicate contains top-level OR disjunction: '{expr}'")
        elif depth == 0 and expr[i:i+5].lower() == " and ":
            conjuncts.append("".join(current).strip())
            current = []
            i += 5
        else: current.append(ch); i += 1
    if current: conjuncts.append("".join(current).strip())
    return conjuncts

def normalize_index_expression(col2_def: Optional[str]) -> str:
    if not col2_def: raise RuntimeError("Existing index column 2 expression is missing.")
    s = col2_def.strip().lower()
    s = re.sub(r'::\s*(text|character varying|varchar)', '', s)
    m = re.match(r'^lower\s*\((.+)\)$', s)
    if not m: return s
    arg = strip_enclosing_parens(m.group(1).strip())
    return f"lower({arg})"

def validate_index_expression(col2_def: Optional[str]) -> None:
    norm = normalize_index_expression(col2_def)
    if norm != "lower(email)":
        raise RuntimeError(f"Index column 2 '{col2_def}' (normalized '{norm}') is not equivalent to LOWER(email).")

def validate_index_predicate(predicate_str: Optional[str]) -> None:
    if not predicate_str or not predicate_str.strip():
        raise RuntimeError("Existing index lacks a partial predicate (full index).")
    conjuncts = split_top_level_and(predicate_str)
    if len(conjuncts) != 2:
        raise RuntimeError(f"Predicate has {len(conjuncts)} conditions, expected exactly 2: '{predicate_str}'")
    has_not_null = False
    has_trim_not_empty = False
    for conj in conjuncts:
        inner = strip_enclosing_parens(conj)
        clean_inner = re.sub(r'::\s*(text|character varying|varchar)', '', inner).lower()
        clean_inner = strip_enclosing_parens(clean_inner)
        m_nn = re.match(r'^\(?([a-zA-Z0-9_]+)\)?\s+is\s+not\s+null$', clean_inner)
        if m_nn and m_nn.group(1) == "email":
            if has_not_null: raise RuntimeError("Duplicate NOT NULL condition.")
            has_not_null = True
            continue
        match_op = None
        for op_sym in ["<>", "!="]:
            if op_sym in clean_inner: match_op = op_sym; break
        if match_op:
            left_part, right_part = [strip_enclosing_parens(p.strip()) for p in clean_inner.split(match_op, 1)]
            if right_part in ("''", "''''"):
                m_trim = re.match(r'^(?:btrim|trim)\s*\(\s*(?:both\s+from\s+)?\(?\s*([a-zA-Z0-9_]+)\s*\)?\s*\)$', left_part)
                if m_trim and m_trim.group(1) == "email":
                    if has_trim_not_empty: raise RuntimeError("Duplicate TRIM condition.")
                    has_trim_not_empty = True
                    continue
        raise RuntimeError(f"Incompatible predicate condition: '{conj}'")
    if not (has_not_null and has_trim_not_empty):
        raise RuntimeError(f"Missing required conditions in predicate: '{predicate_str}'")

def validate_existing_index(existing_idx) -> None:
    if existing_idx.table_schema != 'public' or existing_idx.table_name != 'contacts':
        raise RuntimeError(f"Index attached to '{existing_idx.table_schema}.{existing_idx.table_name}', expected 'public.contacts'.")
    if existing_idx.index_schema != 'public':
        raise RuntimeError(f"Index in schema '{existing_idx.index_schema}', expected 'public'.")
    if not existing_idx.indisunique: raise RuntimeError("Index is NOT unique.")
    if not existing_idx.indisvalid or not existing_idx.indisready: raise RuntimeError("Index is not valid/ready.")
    if existing_idx.indnatts != 2 or existing_idx.indnkeyatts != 2: raise RuntimeError("Expected exactly 2 key attributes.")
    if (existing_idx.col1 or "").strip().lower() != 'organization_id': raise RuntimeError("Expected col 1 to be organization_id.")
    validate_index_expression(existing_idx.col2)
    validate_index_predicate(existing_idx.predicate)

INDEX_CREATED_COMMENT = "created_by_alembic:b2c3d4e5f6a7"

def upgrade() -> None:
    conn = op.get_bind()
    dupes = conn.execute(sa.text("""
        SELECT organization_id, LOWER(TRIM(email)) AS normalized_email, COUNT(*) AS cnt
        FROM public.contacts WHERE email IS NOT NULL AND TRIM(email) != ''
        GROUP BY organization_id, LOWER(TRIM(email)) HAVING COUNT(*) > 1
    """)).fetchall()
    if dupes:
        raise RuntimeError(f"Migration aborted: {len(dupes)} duplicate contact group(s) exist.")

    all_matching = conn.execute(sa.text("""
        SELECT n_c.nspname AS index_schema, c.relname AS index_name,
               n_t.nspname AS table_schema, t.relname AS table_name,
               i.indnatts, i.indnkeyatts, i.indisunique, i.indisvalid, i.indisready,
               pg_get_indexdef(i.indexrelid, 1, true) AS col1,
               pg_get_indexdef(i.indexrelid, 2, true) AS col2,
               pg_get_expr(i.indpred, i.indrelid) AS predicate,
               pg_get_indexdef(i.indexrelid) AS indexdef,
               obj_description(i.indexrelid, 'pg_class') AS index_comment
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n_c ON n_c.oid = c.relnamespace
        JOIN pg_class t ON t.oid = i.indrelid JOIN pg_namespace n_t ON n_t.oid = t.relnamespace
        WHERE c.relname = 'uq_contacts_org_lower_email'
    """)).fetchall()

    public_contacts = [idx for idx in all_matching if idx.table_schema == 'public' and idx.table_name == 'contacts' and idx.index_schema == 'public']
    other_indexes = [idx for idx in all_matching if idx not in public_contacts]
    if other_indexes:
        raise RuntimeError(f"Ambiguity detected: Index exists in other schema/table: {other_indexes}")
    if public_contacts:
        if len(public_contacts) > 1: raise RuntimeError("Multiple matching indexes in public.contacts.")
        validate_existing_index(public_contacts[0])
    else:
        op.execute("""
            CREATE UNIQUE INDEX uq_contacts_org_lower_email
            ON public.contacts (organization_id, LOWER(email))
            WHERE email IS NOT NULL AND TRIM(email) != '';
            COMMENT ON INDEX public.uq_contacts_org_lower_email IS 'created_by_alembic:b2c3d4e5f6a7';
        """)

def downgrade() -> None:
    conn = op.get_bind()
    all_matching = conn.execute(sa.text("""
        SELECT n_c.nspname AS index_schema, c.relname AS index_name,
               n_t.nspname AS table_schema, t.relname AS table_name,
               i.indnatts, i.indnkeyatts, i.indisunique, i.indisvalid, i.indisready,
               pg_get_indexdef(i.indexrelid, 1, true) AS col1,
               pg_get_indexdef(i.indexrelid, 2, true) AS col2,
               pg_get_expr(i.indpred, i.indrelid) AS predicate,
               pg_get_indexdef(i.indexrelid) AS indexdef,
               obj_description(i.indexrelid, 'pg_class') AS index_comment
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n_c ON n_c.oid = c.relnamespace
        JOIN pg_class t ON t.oid = i.indrelid JOIN pg_namespace n_t ON n_t.oid = t.relnamespace
        WHERE c.relname = 'uq_contacts_org_lower_email'
    """)).fetchall()
    if not all_matching: return
    for idx in all_matching:
        if idx.table_schema != 'public' or idx.table_name != 'contacts' or idx.index_schema != 'public':
            raise RuntimeError(f"Refusing to drop unrelated index: {idx.index_schema}.{idx.index_name}")
        validate_existing_index(idx)
    target_idx = all_matching[0]
    if target_idx.index_comment == INDEX_CREATED_COMMENT:
        op.execute("DROP INDEX public.uq_contacts_org_lower_email;")
    else:
        pass # Pre-existing index preserved!
```

---

## 8. Final Execution Checklist

For when administrative approval is granted to perform the deduplication:

### Phase 1: Pre-Execution Gate
- [ ] Confirm no concurrent deployments or batch imports are running.
- [ ] Run Precondition Verification Queries (Part A below) and confirm expected row counts:
  - Canonical Record A count: `1`
  - Duplicate Record B count: `1`
  - Record B foreign-key reference count: `0`
  - Total database duplicate group count: `1`

### Phase 2: Execution Gate
- [ ] Execute the Hardened Remediation Transaction (Section 4) inside `psql` or database client.
- [ ] Verify transaction logs: `Deduplication completed successfully. Batch ID: <UUID>`.
- [ ] Confirm `contacts_deduplication_quarantine_backup` contains exactly 1 row for `6d6bc3a9-84fd-40e9-8375-0e283f1863fb`.

### Phase 3: Post-Remediation Verification Gate
- [ ] Run duplicate group query; assert `0` duplicate groups returned.
- [ ] Assert Canonical Record A remains active in `3de43e6b-...`.
- [ ] Assert Separate Tenant Record C remains active in `0d85dc9f-...`.

### Phase 4: Migration Gate
- [ ] Execute `alembic upgrade head` to run migration `b2c3d4e5f6a7`.
- [ ] Query `pg_indexes` and verify `uq_contacts_org_lower_email` exists with `indexdef` matching specification.

### Phase 5: Regression Gate
- [ ] Run backend test suite (`python -m pytest tests/test_duplicate_prevention.py -v`).
- [ ] Run full regression suite (`python -m pytest -q`).

---

## 9. Verification Queries & Expected Results

### Pre-Remediation Query
```sql
SELECT organization_id, LOWER(email) AS lower_email, COUNT(*) AS count
FROM contacts
WHERE email IS NOT NULL AND TRIM(email) != ''
GROUP BY organization_id, LOWER(email)
HAVING COUNT(*) > 1;
```
**Expected Pre-Remediation Result:**
```
           organization_id            |              lower_email              | count 
--------------------------------------+---------------------------------------+-------
 3de43e6b-6cc0-4391-a061-2faba481bcb8 | pravalikapalle@agilereceivables.com   |     2
(1 row)
```

### Post-Remediation Query
```sql
SELECT organization_id, LOWER(email) AS lower_email, COUNT(*) AS count
FROM contacts
WHERE email IS NOT NULL AND TRIM(email) != ''
GROUP BY organization_id, LOWER(email)
HAVING COUNT(*) > 1;
```
**Expected Post-Remediation Result:**
```
 organization_id | lower_email | count 
-----------------+-------------+-------
(0 rows)
```

### Index Existence Query
```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'contacts' AND indexname = 'uq_contacts_org_lower_email';
```
**Expected Post-Migration Result:**
```
          indexname            |                                                              indexdef                                                               
-------------------------------+-------------------------------------------------------------------------------------------------------------------------------------
 uq_contacts_org_lower_email   | CREATE UNIQUE INDEX uq_contacts_org_lower_email ON public.contacts USING btree (organization_id, lower((email)::text)) WHERE ((email IS NOT NULL) AND (TRIM(BOTH FROM email) <> ''::text))
(1 row)
```
