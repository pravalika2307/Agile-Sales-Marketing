"""QA Sandbox isolation and fail-closed production data safeguards.

Guarantees:
1. Designates organization c0aae7f1-95bb-485f-bb9b-e3ed95469912 as the official QA Sandbox.
2. Forbids exploratory test scripts and QA routines from mutating operational production organization
   0d85dc9f-1520-4bcb-8af4-8aad025255cb (Agile Sales & Marketing).
3. Fails closed when the target organization is ambiguous or unspecified.
4. Prevents silent fallback to Organization.first() or operational production tenants.
5. Preserves backward compatibility with existing E2E testing workflows.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional, Union, TYPE_CHECKING
from sqlalchemy import event, or_
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.tenant import Organization


# Operational production organization that must NEVER be mutated by exploratory test scripts
PRODUCTION_ORG_ID = uuid.UUID("0d85dc9f-1520-4bcb-8af4-8aad025255cb")
PRODUCTION_ORG_SLUG = "agile-sales-marketing-org"

# Designated official QA Sandbox organization (reused from clean zero-data E2E testing tenant)
QA_SANDBOX_ORG_ID = uuid.UUID("c0aae7f1-95bb-485f-bb9b-e3ed95469912")
QA_SANDBOX_SLUG = "agile-qa-sandbox-org"
QA_LEGACY_SLUG = "e2e-testing-org"


class QASafeguardError(Exception):
    """Base exception for QA organization safeguards and environment isolation."""
    pass


class ProductionDataProtectionError(QASafeguardError):
    """Raised when an exploratory test script attempts to write to the operational production organization."""
    pass


class AmbiguousOrganizationError(QASafeguardError):
    """Raised when the target organization is ambiguous or unspecified, preventing silent fallback."""
    pass


class QASandboxNotFoundError(QASafeguardError):
    """Raised when the designated QA Sandbox organization cannot be found in the database."""
    pass


def assert_safe_test_organization(
    target_org_id: Union[uuid.UUID, str],
    caller_context: Optional[str] = None,
) -> None:
    """
    Assert that the target organization is safe for testing.
    Fails closed if the organization matches the operational production tenant (0d85dc9f...).
    """
    if isinstance(target_org_id, str):
        try:
            target_uuid = uuid.UUID(target_org_id)
        except ValueError:
            target_uuid = None
    else:
        target_uuid = target_org_id

    if target_uuid == PRODUCTION_ORG_ID:
        # Require explicit, unambiguous override for genuine production administration
        allow_override = os.getenv("ALLOW_PRODUCTION_CRM_MUTATION", "").strip().lower() in ("true", "1")
        if not allow_override:
            context_msg = f" in context '{caller_context}'" if caller_context else ""
            raise ProductionDataProtectionError(
                f"CRITICAL SAFETY VIOLATION: Test/exploratory script{context_msg} attempted to target "
                f"the operational production organization '{PRODUCTION_ORG_ID}' (Agile Sales & Marketing). "
                f"Exploratory tests and scratch scripts MUST target the QA Sandbox organization "
                f"'{QA_SANDBOX_ORG_ID}' (slug: '{QA_SANDBOX_SLUG}'). "
                f"Execution aborted to protect production data."
            )


def get_qa_organization(db: Session) -> Organization:
    """
    Retrieve the designated official QA Sandbox organization.
    Resolves by explicit QA_SANDBOX_ORG_ID or known QA slugs.
    Fails closed if not found; NEVER falls back to production or Organization.first().
    """
    from app.models.tenant import Organization
    org = (
        db.query(Organization)
        .filter(
            or_(
                Organization.id == QA_SANDBOX_ORG_ID,
                Organization.slug == QA_SANDBOX_SLUG,
                Organization.slug == QA_LEGACY_SLUG,
            )
        )
        .first()
    )

    if not org:
        raise QASandboxNotFoundError(
            f"Official QA Sandbox organization not found (expected ID: '{QA_SANDBOX_ORG_ID}', "
            f"slug: '{QA_SANDBOX_SLUG}'). Ensure database setup has completed."
        )

    return org


def resolve_script_target_organization(
    db: Session,
    target_id: Optional[Union[uuid.UUID, str]] = None,
    target_slug: Optional[str] = None,
    allow_default_to_qa: bool = True,
    caller_context: Optional[str] = None,
) -> Organization:
    """
    Deterministically resolve the target organization for an exploratory script.

    Rules:
    1. If target_id is provided, validates against production protection guard and retrieves org.
    2. If target_slug is provided, validates it is not production slug and retrieves org.
    3. If environment variables TARGET_ORGANIZATION_ID or TARGET_ORGANIZATION_SLUG exist, uses them.
    4. If no target specified and allow_default_to_qa is True, safely defaults to QA Sandbox.
    5. Otherwise, fails closed with AmbiguousOrganizationError.
    """
    # 1. Target ID passed explicitly
    from app.models.tenant import Organization
    if target_id is not None:
        assert_safe_test_organization(target_id, caller_context=caller_context)
        org_uuid = uuid.UUID(str(target_id))
        org = db.query(Organization).filter(Organization.id == org_uuid).first()
        if not org:
            raise QASandboxNotFoundError(f"Specified target organization ID '{target_id}' was not found.")
        return org

    # 2. Target slug passed explicitly
    if target_slug is not None:
        if target_slug.strip().lower() == PRODUCTION_ORG_SLUG:
            assert_safe_test_organization(PRODUCTION_ORG_ID, caller_context=caller_context)
        org = db.query(Organization).filter(Organization.slug == target_slug.strip().lower()).first()
        if not org:
            raise QASandboxNotFoundError(f"Specified target organization slug '{target_slug}' was not found.")
        assert_safe_test_organization(org.id, caller_context=caller_context)
        return org

    # 3. Environment variables
    env_id = os.getenv("TARGET_ORGANIZATION_ID")
    if env_id:
        return resolve_script_target_organization(
            db, target_id=env_id, caller_context=caller_context or "TARGET_ORGANIZATION_ID env"
        )

    env_slug = os.getenv("TARGET_ORGANIZATION_SLUG")
    if env_slug:
        return resolve_script_target_organization(
            db, target_slug=env_slug, caller_context=caller_context or "TARGET_ORGANIZATION_SLUG env"
        )

    # 4. Default to QA Sandbox
    if allow_default_to_qa:
        return get_qa_organization(db)

    # 5. Fail closed
    raise AmbiguousOrganizationError(
        "CRITICAL SAFETY VIOLATION: Target organization for exploratory test script is ambiguous. "
        "Scripts must explicitly pass target_id, target_slug, or call get_qa_organization(db). "
        "Silent fallback to production is prohibited."
    )


def install_production_mutation_guard(db: Session) -> None:
    """
    Attach a fail-closed listener to the SQLAlchemy Session.
    Intercepts before_flush and raises ProductionDataProtectionError if any added
    or modified entity belongs to the operational production organization without override.
    """
    @event.listens_for(db, "before_flush")
    def _guard_before_flush(session, flush_context, instances):
        allow_override = os.getenv("ALLOW_PRODUCTION_CRM_MUTATION", "").strip().lower() in ("true", "1")
        if allow_override:
            return

        for obj in list(session.new) + list(session.dirty):
            obj_org_id = getattr(obj, "organization_id", None)
            if obj_org_id == PRODUCTION_ORG_ID:
                table_name = getattr(obj, "__tablename__", type(obj).__name__)
                raise ProductionDataProtectionError(
                    f"CRITICAL SAFETY VIOLATION: An exploratory test operation attempted to write a "
                    f"'{table_name}' record into production tenant '{PRODUCTION_ORG_ID}' (Agile Sales & Marketing). "
                    f"Exploratory operations must target QA Sandbox organization '{QA_SANDBOX_ORG_ID}'."
                )
