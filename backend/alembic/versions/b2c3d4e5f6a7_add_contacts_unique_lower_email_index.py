"""add_contacts_unique_lower_email_index

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-12 22:00:00.000000

"""
import re
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_CREATED_COMMENT: str = "created_by_alembic:b2c3d4e5f6a7"


def strip_enclosing_parens(s: str) -> str:
    """Repeatedly strip balanced outer parentheses from an expression."""
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        matched = False
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    matched = (i == len(s) - 1)
                    break
        if matched:
            s = s[1:-1].strip()
        else:
            break
    return s


def split_top_level_and(expr: str) -> list[str]:
    """Split a boolean expression into its top-level AND conjuncts.
    
    Raises ValueError if a top-level OR disjunction is detected.
    """
    expr = strip_enclosing_parens(expr)
    conjuncts = []
    depth = 0
    current = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch == "(":
            depth += 1
            current.append(ch)
            i += 1
        elif ch == ")":
            depth -= 1
            current.append(ch)
            i += 1
        elif depth == 0 and expr[i:i+4].lower() == " or ":
            raise ValueError(f"Predicate contains top-level OR disjunction: '{expr}'")
        elif depth == 0 and expr[i:i+5].lower() == " and ":
            conjuncts.append("".join(current).strip())
            current = []
            i += 5
        else:
            current.append(ch)
            i += 1
    if current:
        conjuncts.append("".join(current).strip())
    return conjuncts


def normalize_index_expression(col2_def: Optional[str]) -> str:
    """Normalize the second index expression by stripping typecasts and redundant parens."""
    if not col2_def:
        raise RuntimeError("Existing index column 2 expression is missing.")
    s = col2_def.strip().lower()
    # Remove PostgreSQL typecasts: ::text, ::character varying, etc.
    s = re.sub(r'::\s*(text|character varying|varchar)', '', s)
    # Match lower(...)
    m = re.match(r'^lower\s*\((.+)\)$', s)
    if not m:
        return s
    arg = m.group(1).strip()
    arg = strip_enclosing_parens(arg)
    return f"lower({arg})"


def validate_index_expression(col2_def: Optional[str]) -> None:
    """Confirm the second indexed column is strictly equivalent to LOWER(email)."""
    norm = normalize_index_expression(col2_def)
    if norm != "lower(email)":
        raise RuntimeError(
            f"Existing index key column 2 expression '{col2_def}' (normalized '{norm}') "
            "is not equivalent to LOWER(email)."
        )


def validate_index_predicate(predicate_str: Optional[str]) -> None:
    """Confirm the partial predicate is equivalent to: email IS NOT NULL AND TRIM(email) != ''.
    
    Rejects:
    - Missing predicate
    - OR disjunctions
    - Extraneous / restrictive conditions
    - Non-trim or non-email conditions
    """
    if not predicate_str or not predicate_str.strip():
        raise RuntimeError("Existing index lacks a partial predicate (full index).")

    try:
        conjuncts = split_top_level_and(predicate_str)
    except ValueError as e:
        raise RuntimeError(f"Invalid predicate structure: {e}") from e

    if len(conjuncts) != 2:
        raise RuntimeError(
            f"Existing index predicate has {len(conjuncts)} conditions, expected exactly 2. "
            f"Predicate: '{predicate_str}'"
        )

    has_not_null = False
    has_trim_not_empty = False

    for conj in conjuncts:
        # Check for nested OR in each conjunct outside quotes
        inner = strip_enclosing_parens(conj)
        depth = 0
        in_str = False
        for i, ch in enumerate(inner):
            if ch == "'":
                in_str = not in_str
            elif not in_str:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                elif depth == 0 and inner[i:i+4].lower() == " or ":
                    raise RuntimeError(f"Predicate conjunct contains OR disjunction: '{conj}'")

        # Strip typecasts from inner expression
        clean_inner = re.sub(r'::\s*(text|character varying|varchar)', '', inner).lower()
        clean_inner = strip_enclosing_parens(clean_inner)

        # 1. Check if this is the email IS NOT NULL condition
        m_nn = re.match(r'^\(?([a-zA-Z0-9_]+)\)?\s+is\s+not\s+null$', clean_inner)
        if m_nn and m_nn.group(1) == "email":
            if has_not_null:
                raise RuntimeError(f"Duplicate NOT NULL condition in predicate: '{predicate_str}'")
            has_not_null = True
            continue

        # 2. Check if this is the TRIM(email) != '' condition
        match_op = None
        for op_sym in ["<>", "!="]:
            if op_sym in clean_inner:
                match_op = op_sym
                break

        if match_op:
            left_part, right_part = [strip_enclosing_parens(p.strip()) for p in clean_inner.split(match_op, 1)]
            if right_part in ("''", "''''"):
                # Left side must be a trim function on email:
                m_trim = re.match(
                    r'^(?:btrim|trim)\s*\(\s*(?:both\s+from\s+)?\(?\s*([a-zA-Z0-9_]+)\s*\)?\s*\)$',
                    left_part
                )
                if m_trim and m_trim.group(1) == "email":
                    if has_trim_not_empty:
                        raise RuntimeError(f"Duplicate TRIM condition in predicate: '{predicate_str}'")
                    has_trim_not_empty = True
                    continue

        raise RuntimeError(
            f"Unrecognized or incompatible predicate condition: '{conj}' in '{predicate_str}'"
        )

    if not (has_not_null and has_trim_not_empty):
        raise RuntimeError(
            f"Predicate is missing required conditions: '{predicate_str}'. "
            "Expected email IS NOT NULL AND TRIM(email) != ''."
        )


def validate_existing_index(existing_idx, expected_schema: str = 'public', expected_table: str = 'contacts') -> None:
    """Full structural validation of an existing index against required definition."""
    if existing_idx.table_schema != expected_schema or existing_idx.table_name != expected_table:
        raise RuntimeError(
            f"Existing index {existing_idx.index_name} is attached to '{existing_idx.table_schema}.{existing_idx.table_name}', expected '{expected_schema}.{expected_table}'."
        )
    if existing_idx.index_schema != expected_schema:
        raise RuntimeError(
            f"Existing index {existing_idx.index_name} is in schema '{existing_idx.index_schema}', expected '{expected_schema}'."
        )
    if not existing_idx.indisunique:
        raise RuntimeError(
            f"Existing index {existing_idx.index_name} is NOT unique. Definition: {existing_idx.indexdef}"
        )
    if not existing_idx.indisvalid or not existing_idx.indisready:
        raise RuntimeError(
            f"Existing index {existing_idx.index_name} is marked invalid or not ready in PostgreSQL catalog."
        )
    if existing_idx.indnatts != 2 or existing_idx.indnkeyatts != 2:
        raise RuntimeError(
            f"Existing index {existing_idx.index_name} has {existing_idx.indnkeyatts} key attributes, expected exactly 2."
        )
    col1_norm = (existing_idx.col1 or "").strip().lower()
    if col1_norm != 'organization_id':
        raise RuntimeError(
            f"Existing index {existing_idx.index_name} key column 1 is '{existing_idx.col1}', expected 'organization_id'."
        )
    validate_index_expression(existing_idx.col2)
    validate_index_predicate(existing_idx.predicate)


def perform_upgrade(conn, schema: str = 'public', table_name: str = 'contacts', index_name: str = 'uq_contacts_org_lower_email') -> bool:
    """Core upgrade logic with pre-checks, ambiguity detection, validation, and creation tracking.
    
    Returns True if a new index was created, False if an existing compatible index was preserved.
    """
    # Pre-check: Ensure zero duplicate groups exist before attempting unique index
    dupes = conn.execute(sa.text(f"""
        SELECT organization_id, LOWER(TRIM(email)) AS normalized_email, COUNT(*) AS cnt
        FROM {schema}.{table_name}
        WHERE email IS NOT NULL AND TRIM(email) != ''
        GROUP BY organization_id, LOWER(TRIM(email))
        HAVING COUNT(*) > 1
    """)).fetchall()

    if dupes:
        raise RuntimeError(
            f"Migration aborted: {len(dupes)} duplicate contact group(s) exist in the database. "
            f"Resolve duplicates before applying {index_name}. "
            f"Conflicting groups: {[dict(d._mapping) for d in dupes]}"
        )

    # Check across PostgreSQL catalog for any index with this name
    all_matching = conn.execute(sa.text(f"""
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
            pg_get_indexdef(i.indexrelid) AS indexdef,
            obj_description(i.indexrelid, 'pg_class') AS index_comment
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n_c ON n_c.oid = c.relnamespace
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n_t ON n_t.oid = t.relnamespace
        WHERE c.relname = :idx_name
    """), {"idx_name": index_name}).fetchall()

    target_table_indexes = [
        idx for idx in all_matching 
        if idx.table_schema == schema and idx.table_name == table_name and idx.index_schema == schema
    ]
    other_schema_indexes = [
        idx for idx in all_matching 
        if idx not in target_table_indexes
    ]

    # Detect ambiguity if index exists elsewhere in other schemas or tables
    if other_schema_indexes:
        raise RuntimeError(
            f"Ambiguity detected: Index name '{index_name}' already exists in another schema or table: "
            f"{[f'{idx.index_schema}.{idx.index_name} on {idx.table_schema}.{idx.table_name}' for idx in other_schema_indexes]}"
        )

    if target_table_indexes:
        if len(target_table_indexes) > 1:
            raise RuntimeError(
                f"Ambiguity detected: Multiple indexes named {index_name} found on {schema}.{table_name}."
            )
        # Pre-existing index: strictly validate definition
        validate_existing_index(target_table_indexes[0], expected_schema=schema, expected_table=table_name)
        return False
    else:
        # Create new index and stamp ownership comment
        conn.execute(sa.text(f"""
            CREATE UNIQUE INDEX {index_name}
            ON {schema}.{table_name} (organization_id, LOWER(email))
            WHERE email IS NOT NULL AND TRIM(email) != '';
        """))
        conn.execute(sa.text(f"""
            COMMENT ON INDEX {schema}.{index_name} IS '{INDEX_CREATED_COMMENT}';
        """))
        return True


def perform_downgrade(conn, schema: str = 'public', table_name: str = 'contacts', index_name: str = 'uq_contacts_org_lower_email') -> bool:
    """Core downgrade logic. Only drops index if created by this migration revision.
    
    Preserves pre-existing indexes that were merely adopted during upgrade.
    Returns True if index was dropped, False if preserved.
    """
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
            pg_get_indexdef(i.indexrelid) AS indexdef,
            obj_description(i.indexrelid, 'pg_class') AS index_comment
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n_c ON n_c.oid = c.relnamespace
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n_t ON n_t.oid = t.relnamespace
        WHERE c.relname = :idx_name
    """), {"idx_name": index_name}).fetchall()

    if not all_matching:
        return False

    if len(all_matching) > 1:
        raise RuntimeError(
            f"Downgrade aborted: Ambiguity detected: Multiple indexes named '{index_name}' exist across schemas."
        )

    # Check for any index in another schema or table
    for idx in all_matching:
        if idx.table_schema != schema or idx.table_name != table_name or idx.index_schema != schema:
            raise RuntimeError(
                f"Downgrade aborted: Refusing to drop unrelated index '{index_name}' "
                f"belonging to '{idx.index_schema}.{idx.index_name}' on '{idx.table_schema}.{idx.table_name}'."
            )

    # Validate that the index on target table matches the migration's intended definition
    for idx in all_matching:
        try:
            validate_existing_index(idx, expected_schema=schema, expected_table=table_name)
        except Exception as e:
            raise RuntimeError(
                f"Downgrade aborted: Refusing to drop index '{schema}.{index_name}' "
                f"because its definition does not match this migration's expected definition: {e}"
            ) from e

    # Distinguish whether index was created by this migration or pre-existed
    target_idx = all_matching[0]
    if target_idx.index_comment == INDEX_CREATED_COMMENT:
        conn.execute(sa.text(f"DROP INDEX {schema}.{index_name};"))
        return True
    else:
        # Pre-existed prior to migration: preserve it!
        return False


def upgrade() -> None:
    conn = op.get_bind()
    perform_upgrade(conn, schema='public', table_name='contacts', index_name='uq_contacts_org_lower_email')


def downgrade() -> None:
    conn = op.get_bind()
    perform_downgrade(conn, schema='public', table_name='contacts', index_name='uq_contacts_org_lower_email')
