-- ==============================================================================
-- Contact Deduplication Rollback Script (Refuses Overwrite)
-- Duplicate Contact ID: 6d6bc3a9-84fd-40e9-8375-0e283f1863fb
--
-- STRICT PRECONDITION:
-- - DO NOT EXECUTE WITHOUT EXPLICIT ADMINISTRATIVE APPROVAL.
-- - Table-level lock prevents concurrent modifications during rollback.
-- - Refuses to overwrite if contact UUID already exists in contacts table.
-- - Preserves unique index: if uq_contacts_org_lower_email is active and
--   canonical contact exists, restores using non-colliding audit alias.
--   If index is not active, restores exact original email.
-- ==============================================================================

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
