-- ==============================================================================
-- Hardened Contact Deduplication Remediation Script
-- Organization: 3de43e6b-6cc0-4391-a061-2faba481bcb8 (Agile Receivables Org)
-- Canonical Contact: aa1b6ce1-d55f-48c5-85aa-52e8e236678a
-- Duplicate Candidate: 6d6bc3a9-84fd-40e9-8375-0e283f1863fb
-- Email: pravalikapalle@agilereceivables.com
--
-- STRICT PRECONDITION:
-- - DO NOT EXECUTE WITHOUT EXPLICIT ADMINISTRATIVE APPROVAL.
-- - Table-level lock prevents concurrent inserts, updates, or DDL during transaction.
-- - Fails closed on any unexpected state, foreign keys, or count discrepancies.
-- ==============================================================================

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

    -- 3. Snapshot Fingerprint Assertions: verify exact field values match approved baseline
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
