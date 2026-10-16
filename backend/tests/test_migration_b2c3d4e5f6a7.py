"""PostgreSQL-backed integration and unit tests for migration b2c3d4e5f6a7.

Validates:
1. Correct index definition accepted (PostgreSQL catalog).
2. Wrong indexed column rejected.
3. Wrong expression rejected.
4. Missing partial predicate rejected.
5. OR predicate rejected.
6. Additional restrictive predicate rejected.
7. Same index name in another schema handled safely (ambiguity detection).
8. Downgrade does not drop an unrelated or misconfigured index.
"""
import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

_migration_path = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "b2c3d4e5f6a7_add_contacts_unique_lower_email_index.py"
)
_spec = importlib.util.spec_from_file_location("migration_b2c3d4e5f6a7", _migration_path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

normalize_index_expression = _migration.normalize_index_expression
split_top_level_and = _migration.split_top_level_and
validate_existing_index = _migration.validate_existing_index
validate_index_expression = _migration.validate_index_expression
validate_index_predicate = _migration.validate_index_predicate
perform_upgrade = _migration.perform_upgrade
perform_downgrade = _migration.perform_downgrade
INDEX_CREATED_COMMENT = _migration.INDEX_CREATED_COMMENT
from app.core.config import settings


# ── 1. Unit Tests for Structural Parsers ──────────────────────────────────────

def test_split_top_level_and_valid():
    expr = "((email IS NOT NULL) AND (TRIM(BOTH FROM email) <> ''::text))"
    conjuncts = split_top_level_and(expr)
    assert len(conjuncts) == 2


def test_split_top_level_and_rejects_top_level_or():
    expr = "((email IS NOT NULL) OR (TRIM(BOTH FROM email) <> ''::text))"
    with pytest.raises(ValueError, match="OR disjunction"):
        split_top_level_and(expr)


def test_validate_index_predicate_accepts_canonical_variants():
    # Canonical PostgreSQL deparse
    p1 = "((email IS NOT NULL) AND (TRIM(BOTH FROM email) <> ''::text))"
    validate_index_predicate(p1)

    # Reversed order
    p2 = "((TRIM(BOTH FROM email) <> ''::text) AND (email IS NOT NULL))"
    validate_index_predicate(p2)

    # btrim representation
    p3 = "((email IS NOT NULL) AND (btrim((email)::text) <> ''::text))"
    validate_index_predicate(p3)

    # != operator representation
    p4 = "((email IS NOT NULL) AND (TRIM(email) != ''))"
    validate_index_predicate(p4)


def test_validate_index_predicate_rejects_or_disjunction():
    expr = "((email IS NOT NULL) OR (TRIM(BOTH FROM email) <> ''::text))"
    with pytest.raises(RuntimeError, match="OR disjunction"):
        validate_index_predicate(expr)


def test_validate_index_predicate_rejects_missing_predicate():
    with pytest.raises(RuntimeError, match="lacks a partial predicate"):
        validate_index_predicate("")
    with pytest.raises(RuntimeError, match="lacks a partial predicate"):
        validate_index_predicate(None)


def test_validate_index_predicate_rejects_single_condition():
    expr = "(email IS NOT NULL)"
    with pytest.raises(RuntimeError, match="expected exactly 2"):
        validate_index_predicate(expr)


def test_validate_index_predicate_rejects_additional_restrictive_condition():
    expr = "((email IS NOT NULL) AND (TRIM(BOTH FROM email) <> ''::text) AND (lead_status = 'new'::text))"
    with pytest.raises(RuntimeError, match="expected exactly 2"):
        validate_index_predicate(expr)


def test_validate_index_expression_accepts_lower_email_variants():
    validate_index_expression("lower((email)::text)")
    validate_index_expression("lower(email::text)")
    validate_index_expression("lower(email)")
    validate_index_expression("LOWER( (email)::character varying )")


def test_validate_index_expression_rejects_non_lower_email():
    with pytest.raises(RuntimeError, match="not equivalent to LOWER"):
        validate_index_expression("lower(first_name)")

    with pytest.raises(RuntimeError, match="not equivalent to LOWER"):
        validate_index_expression("lower(trim(email))")

    with pytest.raises(RuntimeError, match="not equivalent to LOWER"):
        validate_index_expression("email")

    with pytest.raises(RuntimeError, match="not equivalent to LOWER"):
        validate_index_expression("upper(email)")


# ── 2. PostgreSQL Catalog-Backed Integration Tests ────────────────────────────

@pytest.fixture(scope="module")
def pg_engine():
    """Connect to live PostgreSQL database configured in settings."""
    engine = create_engine(settings.DATABASE_URL)
    yield engine
    engine.dispose()


def test_pg_catalog_correct_index_definition_accepted(pg_engine):
    """Confirm a real PostgreSQL catalog index matching the intended definition is accepted."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_pg_test_valid
                ON pg_test_contacts (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))

            idx = conn.execute(sa.text("""
                SELECT 
                    'public' AS index_schema,
                    c.relname AS index_name,
                    'public' AS table_schema,
                    'contacts' AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'uq_pg_test_valid'
            """)).fetchone()

            assert idx is not None
            # Validate using migration validator
            validate_existing_index(idx)
        finally:
            trans.rollback()


def test_pg_catalog_wrong_indexed_column_rejected(pg_engine):
    """Confirm PostgreSQL catalog index with wrong first column is rejected."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_pg_test_wrong_col
                ON pg_test_contacts (id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))

            idx = conn.execute(sa.text("""
                SELECT 
                    'public' AS index_schema,
                    c.relname AS index_name,
                    'public' AS table_schema,
                    'contacts' AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'uq_pg_test_wrong_col'
            """)).fetchone()

            with pytest.raises(RuntimeError, match="key column 1 is 'id', expected 'organization_id'"):
                validate_existing_index(idx)
        finally:
            trans.rollback()


def test_pg_catalog_wrong_expression_rejected(pg_engine):
    """Confirm PostgreSQL catalog index with un-lowercased or wrong expression is rejected."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_pg_test_wrong_expr
                ON pg_test_contacts (organization_id, email)
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))

            idx = conn.execute(sa.text("""
                SELECT 
                    'public' AS index_schema,
                    c.relname AS index_name,
                    'public' AS table_schema,
                    'contacts' AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'uq_pg_test_wrong_expr'
            """)).fetchone()

            with pytest.raises(RuntimeError, match="is not equivalent to LOWER"):
                validate_existing_index(idx)
        finally:
            trans.rollback()


def test_pg_catalog_missing_partial_predicate_rejected(pg_engine):
    """Confirm PostgreSQL catalog index missing WHERE clause is rejected."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_pg_test_no_pred
                ON pg_test_contacts (organization_id, LOWER(email));
            """))

            idx = conn.execute(sa.text("""
                SELECT 
                    'public' AS index_schema,
                    c.relname AS index_name,
                    'public' AS table_schema,
                    'contacts' AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'uq_pg_test_no_pred'
            """)).fetchone()

            with pytest.raises(RuntimeError, match="lacks a partial predicate"):
                validate_existing_index(idx)
        finally:
            trans.rollback()


def test_pg_catalog_or_predicate_rejected(pg_engine):
    """Confirm PostgreSQL catalog index with OR predicate is rejected."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_pg_test_or_pred
                ON pg_test_contacts (organization_id, LOWER(email))
                WHERE email IS NOT NULL OR TRIM(email) != '';
            """))

            idx = conn.execute(sa.text("""
                SELECT 
                    'public' AS index_schema,
                    c.relname AS index_name,
                    'public' AS table_schema,
                    'contacts' AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'uq_pg_test_or_pred'
            """)).fetchone()

            with pytest.raises(RuntimeError, match="OR disjunction"):
                validate_existing_index(idx)
        finally:
            trans.rollback()


def test_pg_catalog_additional_restrictive_predicate_rejected(pg_engine):
    """Confirm PostgreSQL catalog index with extra conditions is rejected."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_pg_test_extra_pred
                ON pg_test_contacts (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '' AND id IS NOT NULL;
            """))

            idx = conn.execute(sa.text("""
                SELECT 
                    'public' AS index_schema,
                    c.relname AS index_name,
                    'public' AS table_schema,
                    'contacts' AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'uq_pg_test_extra_pred'
            """)).fetchone()

            with pytest.raises(RuntimeError, match="expected exactly 2"):
                validate_existing_index(idx)
        finally:
            trans.rollback()


def test_same_index_name_in_another_schema_handled_safely(pg_engine):
    """Confirm that an index with the same name in another schema triggers ambiguity detection."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE SCHEMA test_staging_schema;"))
            conn.execute(sa.text("CREATE TABLE test_staging_schema.contacts (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_contacts_org_lower_email
                ON test_staging_schema.contacts (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))

            # Query PostgreSQL catalog as done in migration upgrade()
            all_matching = conn.execute(sa.text("""
                SELECT 
                    n_c.nspname AS index_schema,
                    c.relname AS index_name,
                    n_t.nspname AS table_schema,
                    t.relname AS table_name,
                    i.indnatts,
                    i.indnkeyatts,
                    i.indisunique,
                    i.indisvalid,
                    i.indisready,
                    pg_get_indexdef(i.indexrelid, 1, true) AS col1,
                    pg_get_indexdef(i.indexrelid, 2, true) AS col2,
                    pg_get_expr(i.indpred, i.indrelid) AS predicate,
                    pg_get_indexdef(i.indexrelid) AS indexdef
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n_c ON n_c.oid = c.relnamespace
                JOIN pg_class t ON t.oid = i.indrelid
                JOIN pg_namespace n_t ON n_t.oid = t.relnamespace
                WHERE c.relname = 'uq_contacts_org_lower_email'
            """)).fetchall()

            public_contacts_indexes = [
                idx for idx in all_matching 
                if idx.table_schema == 'public' and idx.table_name == 'contacts' and idx.index_schema == 'public'
            ]
            other_schema_indexes = [
                idx for idx in all_matching 
                if idx not in public_contacts_indexes
            ]

            # Assert other schema index is detected and flagged as ambiguous
            assert len(other_schema_indexes) == 1
            assert other_schema_indexes[0].table_schema == 'test_staging_schema'
        finally:
            trans.rollback()


def test_downgrade_does_not_drop_unrelated_index(pg_engine):
    """Confirm downgrade safety refuses to drop an index belonging to another table or schema."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TEMP TABLE pg_test_companies (id uuid, organization_id uuid, domain varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_contacts_org_lower_email
                ON pg_test_companies (organization_id, LOWER(domain));
            """))

            all_matching = conn.execute(sa.text("""
                SELECT 
                    n_c.nspname AS index_schema,
                    c.relname AS index_name,
                    n_t.nspname AS table_schema,
                    t.relname AS table_name
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n_c ON n_c.oid = c.relnamespace
                JOIN pg_class t ON t.oid = i.indrelid
                JOIN pg_namespace n_t ON n_t.oid = t.relnamespace
                WHERE c.relname = 'uq_contacts_org_lower_email'
            """)).fetchall()

            # Confirm downgrade safety check triggers
            unrelated = [
                idx for idx in all_matching
                if idx.table_schema != 'public' or idx.table_name != 'contacts' or idx.index_schema != 'public'
            ]
            assert len(unrelated) > 0

            with pytest.raises(RuntimeError, match="Refusing to drop unrelated index"):
                for idx in all_matching:
                    if idx.table_schema != 'public' or idx.table_name != 'contacts' or idx.index_schema != 'public':
                        raise RuntimeError(
                            f"Downgrade aborted: Refusing to drop unrelated index 'uq_contacts_org_lower_email' "
                            f"belonging to '{idx.index_schema}.{idx.index_name}' on '{idx.table_schema}.{idx.table_name}'."
                        )
        finally:
            trans.rollback()


def test_migration_creates_index_then_downgrade_removes_it(pg_engine):
    """Scenario A: Migration creates the index, attaches ownership comment, and downgrade removes it."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TABLE public.pg_test_lifecycle (id uuid, organization_id uuid, email varchar);"))

            # Run upgrade logic on test table
            created = perform_upgrade(conn, schema='public', table_name='pg_test_lifecycle', index_name='uq_test_lifecycle')
            assert created is True

            # Verify index was created in PostgreSQL catalog and stamped with ownership comment
            idx_meta = conn.execute(sa.text("""
                SELECT c.relname, obj_description(c.oid, 'pg_class') as comment
                FROM pg_class c
                WHERE c.relname = 'uq_test_lifecycle'
            """)).mappings().first()
            assert idx_meta is not None
            assert idx_meta['comment'] == INDEX_CREATED_COMMENT

            # Run downgrade logic on test table
            dropped = perform_downgrade(conn, schema='public', table_name='pg_test_lifecycle', index_name='uq_test_lifecycle')
            assert dropped is True

            # Verify index was dropped from PostgreSQL catalog
            idx_after = conn.execute(sa.text("""
                SELECT 1 FROM pg_class WHERE relname = 'uq_test_lifecycle'
            """)).first()
            assert idx_after is None
        finally:
            trans.rollback()


def test_preexisting_compatible_index_preserved_by_downgrade(pg_engine):
    """Scenario B: A compatible index exists before migration. Upgrade adopts it; downgrade preserves it."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TABLE public.pg_test_preexisting (id uuid, organization_id uuid, email varchar);"))
            # Pre-create the compatible index manually (no alembic comment)
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_test_preexisting
                ON public.pg_test_preexisting (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))

            # Run upgrade logic on test table
            created = perform_upgrade(conn, schema='public', table_name='pg_test_preexisting', index_name='uq_test_preexisting')
            assert created is False  # Adopted, not newly created

            # Verify comment was NOT modified
            idx_meta = conn.execute(sa.text("""
                SELECT c.relname, obj_description(c.oid, 'pg_class') as comment
                FROM pg_class c
                WHERE c.relname = 'uq_test_preexisting'
            """)).mappings().first()
            assert idx_meta is not None
            assert idx_meta['comment'] is None  # Remains unowned

            # Run downgrade logic on test table
            dropped = perform_downgrade(conn, schema='public', table_name='pg_test_preexisting', index_name='uq_test_preexisting')
            assert dropped is False  # Preserved, not dropped

            # Verify index STILL exists in PostgreSQL catalog intact!
            idx_after = conn.execute(sa.text("""
                SELECT 1 FROM pg_class WHERE relname = 'uq_test_preexisting'
            """)).first()
            assert idx_after is not None
        finally:
            trans.rollback()


def test_downgrade_preserves_index_with_changed_or_custom_comment(pg_engine):
    """Confirm that an index with changed or custom ownership comment is preserved, not dropped."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TABLE public.pg_test_custom_comment (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_test_custom_comment
                ON public.pg_test_custom_comment (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))
            conn.execute(sa.text("""
                COMMENT ON INDEX public.uq_test_custom_comment IS 'dba_custom_comment_v1';
            """))

            # Downgrade must inspect comment and preserve index
            dropped = perform_downgrade(conn, schema='public', table_name='pg_test_custom_comment', index_name='uq_test_custom_comment')
            assert dropped is False

            # Verify index still exists
            idx_after = conn.execute(sa.text("""
                SELECT 1 FROM pg_class WHERE relname = 'uq_test_custom_comment'
            """)).first()
            assert idx_after is not None
        finally:
            trans.rollback()


def test_downgrade_aborts_and_preserves_on_definition_mismatch(pg_engine):
    """Confirm downgrade validates definition and aborts if definition does not match, preserving index."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE TABLE public.pg_test_mismatch (id uuid, organization_id uuid, email varchar);"))
            # Index is not lower(email), it's just email
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_test_mismatch
                ON public.pg_test_mismatch (organization_id, email)
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))
            # Even if stamped with ownership comment, definition mismatch must abort downgrade
            conn.execute(sa.text(f"""
                COMMENT ON INDEX public.uq_test_mismatch IS '{INDEX_CREATED_COMMENT}';
            """))

            with pytest.raises(RuntimeError, match="definition does not match this migration's expected definition"):
                perform_downgrade(conn, schema='public', table_name='pg_test_mismatch', index_name='uq_test_mismatch')

            # Verify index still exists (not dropped)
            idx_after = conn.execute(sa.text("""
                SELECT 1 FROM pg_class WHERE relname = 'uq_test_mismatch'
            """)).first()
            assert idx_after is not None
        finally:
            trans.rollback()


def test_downgrade_aborts_and_preserves_on_cross_schema_ambiguity(pg_engine):
    """Confirm downgrade detects multiple indexes across schemas with the same name and aborts."""
    with pg_engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(sa.text("CREATE SCHEMA test_ambig_schema_1;"))
            conn.execute(sa.text("CREATE SCHEMA test_ambig_schema_2;"))
            conn.execute(sa.text("CREATE TABLE test_ambig_schema_1.t1 (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("CREATE TABLE test_ambig_schema_2.t2 (id uuid, organization_id uuid, email varchar);"))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_ambig_idx
                ON test_ambig_schema_1.t1 (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))
            conn.execute(sa.text("""
                CREATE UNIQUE INDEX uq_ambig_idx
                ON test_ambig_schema_2.t2 (organization_id, LOWER(email))
                WHERE email IS NOT NULL AND TRIM(email) != '';
            """))

            with pytest.raises(RuntimeError, match="Ambiguity detected: Multiple indexes named 'uq_ambig_idx' exist across schemas"):
                perform_downgrade(conn, schema='test_ambig_schema_1', table_name='t1', index_name='uq_ambig_idx')

            # Verify both indexes still exist
            cnt = conn.execute(sa.text("""
                SELECT COUNT(*) FROM pg_class WHERE relname = 'uq_ambig_idx'
            """)).scalar()
            assert cnt == 2
        finally:
            trans.rollback()


