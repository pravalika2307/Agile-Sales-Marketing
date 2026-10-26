"""Physical Mail campaign orchestration service for Poplar direct mail operations."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Contact, Company
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization
from app.services.physical_mail.address_validator import validate_usps_address
from app.services.physical_mail.poplar_client import (
    PoplarClient,
    PoplarError,
    PoplarRecipient,
    PoplarValidationError,
    get_poplar_client,
)

logger = logging.getLogger(__name__)

# Default estimated unit cost ($1.15 covers full-color print, stock, and USPS First Class postage)
DEFAULT_UNIT_COST = 1.15

# In-memory approval token registry for idempotency during campaign submissions
_EXECUTED_APPROVAL_TOKENS: set[str] = set()


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class PhysicalMailError(Exception):
    """Base exception for physical mail operations."""
    pass


class UnapprovedCampaignError(PhysicalMailError):
    """Raised when submission is attempted without explicit user approval."""
    pass


class DuplicateSubmissionError(PhysicalMailError):
    """Raised when duplicate submission is attempted with an already-used approval token."""
    pass


class CampaignNotFoundError(PhysicalMailError):
    """Raised when campaign is not found or belongs to another tenant."""
    pass


class RecipientNotFoundError(PhysicalMailError):
    """Raised when target recipient contact or lead is not found."""
    pass


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class RecipientAuditItem:
    recipient_id: uuid.UUID
    recipient_type: str  # "contact" or "lead"
    full_name: str
    company_name: Optional[str]
    is_valid: bool
    errors: List[str]
    cleaned_address: Optional[Dict[str, str]] = None


@dataclass
class MailValidationReport:
    campaign_id: uuid.UUID
    total_recipients: int
    valid_count: int
    invalid_count: int
    valid_recipients: List[RecipientAuditItem] = field(default_factory=list)
    invalid_recipients: List[RecipientAuditItem] = field(default_factory=list)


@dataclass
class MailPreviewResult:
    campaign_id: uuid.UUID
    poplar_campaign_id: str
    poplar_creative_id: Optional[str]
    unit_cost: float
    total_recipients: int
    valid_count: int
    invalid_count: int
    estimated_total_cost: float
    sample_preview: Optional[Dict[str, Any]]
    invalid_recipients: List[Dict[str, Any]]
    approval_required: bool = True


@dataclass
class SingleMailingOutcome:
    recipient_id: uuid.UUID
    outreach_id: uuid.UUID
    success: bool
    status: str
    mailing_id: Optional[str] = None
    proof_url: Optional[str] = None
    error: Optional[str] = None
    simulated: bool = False


@dataclass
class CampaignSubmissionResult:
    campaign_id: uuid.UUID
    total_processed: int
    total_submitted: int
    total_failed: int
    estimated_cost: float
    outcomes: List[SingleMailingOutcome] = field(default_factory=list)


# ── Physical Mail Service ─────────────────────────────────────────────────────

class PhysicalMailService:
    """
    Manages physical direct mail campaigns, address pre-flight audits,
    cost calculations, explicit approval gates, and 1-to-1 Poplar submissions.
    """

    def __init__(self, db: Session, client: Optional[PoplarClient] = None) -> None:
        self.db = db
        self.client = client

    def _get_active_client(self) -> PoplarClient:
        if self.client is not None:
            return self.client
        return get_poplar_client()

    def _extract_recipient_details(self, entity: Union[Contact, Lead, Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize address attributes across Contact, Lead, or dictionary."""
        if isinstance(entity, dict):
            return {
                "id": entity.get("id"),
                "full_name": entity.get("full_name") or f"{entity.get('first_name', '')} {entity.get('last_name', '')}".strip(),
                "first_name": entity.get("first_name"),
                "last_name": entity.get("last_name"),
                "company": entity.get("company") or entity.get("company_name"),
                "email": entity.get("email"),
                "address_1": entity.get("address_1") or entity.get("address_line_1"),
                "address_2": entity.get("address_2") or entity.get("address_line_2"),
                "city": entity.get("city"),
                "state": entity.get("state"),
                "postal_code": entity.get("postal_code") or entity.get("zip"),
                "country": entity.get("country") or "US",
            }
        
        # Entity is Contact or Lead model
        first = getattr(entity, "first_name", None) or ""
        last = getattr(entity, "last_name", None) or ""
        full_name = f"{first} {last}".strip()
        company = getattr(entity, "company_name", None)
        if not company and hasattr(entity, "company") and getattr(entity, "company"):
            company = getattr(entity.company, "name", None)

        return {
            "id": entity.id,
            "full_name": full_name or None,
            "first_name": first or None,
            "last_name": last or None,
            "company": company,
            "email": getattr(entity, "email", None),
            "address_1": getattr(entity, "address_line_1", None),
            "address_2": getattr(entity, "address_line_2", None),
            "city": getattr(entity, "city", None),
            "state": getattr(entity, "state", None),
            "postal_code": getattr(entity, "postal_code", None),
            "country": getattr(entity, "country", None) or "US",
        }

    def validate_campaign_recipients(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        recipient_ids: Optional[List[uuid.UUID]] = None,
    ) -> MailValidationReport:
        """
        Runs pre-flight address validation on all enrolled recipients for a campaign.
        Enforces tenant isolation and itemizes all invalid addresses.
        """
        campaign = self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        ).scalar_one_or_none()
        if not campaign:
            raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found for this organization.")

        # Query enrollments
        query = select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)
        if recipient_ids:
            query = query.where(CampaignContact.contact_id.in_(recipient_ids))
        enrollments = self.db.execute(query).scalars().all()

        valid_items: List[RecipientAuditItem] = []
        invalid_items: List[RecipientAuditItem] = []

        for enroll in enrollments:
            contact = self.db.execute(
                select(Contact).where(Contact.id == enroll.contact_id, Contact.organization_id == org_id)
            ).scalar_one_or_none()
            if not contact:
                continue

            extracted = self._extract_recipient_details(contact)
            val_res = validate_usps_address(
                address_1=extracted["address_1"],
                address_2=extracted["address_2"],
                city=extracted["city"],
                state=extracted["state"],
                postal_code=extracted["postal_code"],
                country=extracted["country"],
                full_name=extracted["full_name"],
                company=extracted["company"],
            )

            item = RecipientAuditItem(
                recipient_id=contact.id,
                recipient_type="contact",
                full_name=extracted["full_name"] or "Unknown",
                company_name=extracted["company"],
                is_valid=val_res.is_valid,
                errors=val_res.errors,
                cleaned_address=val_res.cleaned_address,
            )
            if val_res.is_valid:
                valid_items.append(item)
            else:
                invalid_items.append(item)

        return MailValidationReport(
            campaign_id=campaign_id,
            total_recipients=len(valid_items) + len(invalid_items),
            valid_count=len(valid_items),
            invalid_count=len(invalid_items),
            valid_recipients=valid_items,
            invalid_recipients=invalid_items,
        )

    def preview_campaign_mail(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        unit_cost: float = DEFAULT_UNIT_COST,
        poplar_campaign_id: Optional[str] = None,
        poplar_creative_id: Optional[str] = None,
    ) -> MailPreviewResult:
        """
        Generates personalized mail preview and estimated total production cost.
        """
        report = self.validate_campaign_recipients(org_id=org_id, campaign_id=campaign_id)
        resolved_campaign_id = poplar_campaign_id or settings.POPLAR_DEFAULT_CAMPAIGN_ID or "cmp_agile_default"
        resolved_creative_id = poplar_creative_id or settings.POPLAR_DEFAULT_CREATIVE_ID

        estimated_total_cost = round(report.valid_count * unit_cost, 2)

        sample_preview = None
        if report.valid_recipients:
            sample = report.valid_recipients[0]
            sample_preview = {
                "recipient": sample.cleaned_address,
                "merge_tags": {
                    "full_name": sample.full_name,
                    "company": sample.company_name or "",
                },
                "estimated_delivery_days": "4-6 business days",
            }

        invalid_summary = [
            {
                "recipient_id": str(item.recipient_id),
                "full_name": item.full_name,
                "errors": item.errors,
            }
            for item in report.invalid_recipients
        ]

        return MailPreviewResult(
            campaign_id=campaign_id,
            poplar_campaign_id=resolved_campaign_id,
            poplar_creative_id=resolved_creative_id,
            unit_cost=unit_cost,
            total_recipients=report.total_recipients,
            valid_count=report.valid_count,
            invalid_count=report.invalid_count,
            estimated_total_cost=estimated_total_cost,
            sample_preview=sample_preview,
            invalid_recipients=invalid_summary,
            approval_required=True,
        )

    def submit_approved_campaign(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        approved: bool,
        approval_token: str,
        poplar_campaign_id: Optional[str] = None,
        poplar_creative_id: Optional[str] = None,
        recipient_ids: Optional[List[uuid.UUID]] = None,
        force_mock: bool = False,
    ) -> CampaignSubmissionResult:
        """
        Submits physical mail for all valid recipients in the campaign.
        Strictly enforces:
        1. Explicit approval (`approved=True`)
        2. Idempotency on `approval_token`
        3. Fail-closed test mode unless `settings.POPLAR_ALLOW_LIVE_SENDING=True`
        4. 1-to-1 submission loop with per-recipient error trapping (partial failures handled)
        """
        # 1. Explicit Approval Gate
        if not approved:
            raise UnapprovedCampaignError(
                "Physical mail campaign requires explicit approval before dispatch. "
                "Verify addresses and cost preview, then submit with approved=True."
            )

        token_key = f"{org_id}:{approval_token.strip()}"
        if token_key in _EXECUTED_APPROVAL_TOKENS:
            raise DuplicateSubmissionError(
                f"Campaign submission with approval token '{approval_token}' has already been processed."
            )

        # 2. Validation report
        report = self.validate_campaign_recipients(
            org_id=org_id,
            campaign_id=campaign_id,
            recipient_ids=recipient_ids,
        )
        resolved_campaign_id = poplar_campaign_id or settings.POPLAR_DEFAULT_CAMPAIGN_ID or "cmp_agile_default"
        resolved_creative_id = poplar_creative_id or settings.POPLAR_DEFAULT_CREATIVE_ID

        # Determine if real live API calls are permitted
        should_live_send = (
            settings.POPLAR_ENABLED
            and settings.POPLAR_ALLOW_LIVE_SENDING
            and not force_mock
        )

        outcomes: List[SingleMailingOutcome] = []
        total_submitted = 0
        total_failed = 0

        # Mark approval token as executing to prevent concurrent double-clicks
        _EXECUTED_APPROVAL_TOKENS.add(token_key)

        for item in report.valid_recipients:
            addr = item.cleaned_address or {}
            # Locate or create Outreach record with channel='physical_mail'
            outreach = self.db.execute(
                select(Outreach).where(
                    Outreach.organization_id == org_id,
                    Outreach.campaign_id == campaign_id,
                    Outreach.contact_id == item.recipient_id,
                    Outreach.channel == "physical_mail",
                )
            ).scalar_one_or_none()

            if not outreach:
                # Find campaign_contact_id
                enroll = self.db.execute(
                    select(CampaignContact).where(
                        CampaignContact.campaign_id == campaign_id,
                        CampaignContact.contact_id == item.recipient_id,
                    )
                ).scalar_one_or_none()

                outreach = Outreach(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    campaign_id=campaign_id,
                    contact_id=item.recipient_id,
                    campaign_contact_id=enroll.id if enroll else None,
                    channel="physical_mail",
                    status="draft",
                    recipient=f"{addr.get('address_1')}, {addr.get('city')}, {addr.get('state')} {addr.get('postal_code')}",
                )
                self.db.add(outreach)
                self.db.flush()

            # Prevent double-send if already completed or in-flight
            if outreach.status in ("sending", "sent"):
                outcomes.append(
                    SingleMailingOutcome(
                        recipient_id=item.recipient_id,
                        outreach_id=outreach.id,
                        success=True,
                        status=outreach.status,
                        mailing_id=outreach.provider_message_id,
                    )
                )
                total_submitted += 1
                continue

            poplar_recipient = PoplarRecipient(
                address_1=addr.get("address_1", ""),
                address_2=addr.get("address_2"),
                city=addr.get("city", ""),
                state=addr.get("state", ""),
                postal_code=addr.get("postal_code", ""),
                full_name=item.full_name,
                company=item.company_name,
                identifier=str(outreach.id),
            )
            merge_tags = {
                "full_name": item.full_name,
                "company": item.company_name or "",
            }

            try:
                if should_live_send:
                    client = self._get_active_client()
                    result = client.create_mailing(
                        campaign_id=resolved_campaign_id,
                        recipient=poplar_recipient,
                        merge_tags=merge_tags,
                        creative_id=resolved_creative_id,
                    )
                    mailing_id = result.id
                    proof_url = result.proof_url
                    outreach.status = "sending"
                    outreach.provider_message_id = mailing_id
                    is_simulated = False
                else:
                    # Safe mock mode (fail-closed)
                    mock_hex = uuid.uuid4().hex[:12]
                    mailing_id = f"mlg_mock_{mock_hex}"
                    proof_url = None
                    outreach.status = "sending"
                    outreach.provider_message_id = mailing_id
                    is_simulated = True

                self.db.add(
                    OutreachEvent(
                        organization_id=org_id,
                        outreach_id=outreach.id,
                        event_type="sending",
                        event_metadata={"mailing_id": mailing_id, "simulated": is_simulated},
                        occurred_at=datetime.now(timezone.utc),
                    )
                )
                self.db.commit()

                outcomes.append(
                    SingleMailingOutcome(
                        recipient_id=item.recipient_id,
                        outreach_id=outreach.id,
                        success=True,
                        status="sending",
                        mailing_id=mailing_id,
                        proof_url=proof_url,
                        simulated=is_simulated,
                    )
                )
                total_submitted += 1

            except PoplarError as exc:
                logger.warning("Poplar mailing failed for recipient %s: %s", item.recipient_id, exc)
                outreach.status = "failed"
                self.db.add(
                    OutreachEvent(
                        organization_id=org_id,
                        outreach_id=outreach.id,
                        event_type="failed",
                        event_metadata={"error": str(exc)},
                        occurred_at=datetime.now(timezone.utc),
                    )
                )
                self.db.commit()

                outcomes.append(
                    SingleMailingOutcome(
                        recipient_id=item.recipient_id,
                        outreach_id=outreach.id,
                        success=False,
                        status="failed",
                        error=str(exc),
                    )
                )
                total_failed += 1

        # Also account for invalid recipients as failed items in the report
        for inv in report.invalid_recipients:
            total_failed += 1
            outcomes.append(
                SingleMailingOutcome(
                    recipient_id=inv.recipient_id,
                    outreach_id=uuid.uuid4(),
                    success=False,
                    status="invalid_address",
                    error="; ".join(inv.errors),
                )
            )

        return CampaignSubmissionResult(
            campaign_id=campaign_id,
            total_processed=report.total_recipients,
            total_submitted=total_submitted,
            total_failed=total_failed,
            estimated_cost=round(total_submitted * DEFAULT_UNIT_COST, 2),
            outcomes=outcomes,
        )


def send_single_physical_mail_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    raise_on_failure: bool = False,
    force_mock: bool = False,
) -> Outreach:
    """Dispatches an individual physical mail outreach item."""
    outreach = db.execute(
        select(Outreach).where(Outreach.id == outreach_id, Outreach.organization_id == org_id)
    ).scalar_one_or_none()
    if not outreach:
        raise RecipientNotFoundError(f"Outreach '{outreach_id}' not found.")

    contact = outreach.contact
    if not contact:
        outreach.status = "failed"
        db.commit()
        return outreach

    service = PhysicalMailService(db=db)
    extracted = service._extract_recipient_details(contact)
    val = validate_usps_address(
        address_1=extracted["address_1"],
        address_2=extracted["address_2"],
        city=extracted["city"],
        state=extracted["state"],
        postal_code=extracted["postal_code"],
        country=extracted["country"],
        full_name=extracted["full_name"],
        company=extracted["company"],
    )
    if not val.is_valid:
        outreach.status = "failed"
        db.add(
            OutreachEvent(
                organization_id=org_id,
                outreach_id=outreach.id,
                event_type="failed",
                event_metadata={"error": "; ".join(val.errors)},
                occurred_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return outreach

    should_live = settings.POPLAR_ENABLED and settings.POPLAR_ALLOW_LIVE_SENDING and not force_mock
    if should_live:
        client = get_poplar_client()
        res = client.create_mailing(
            campaign_id=settings.POPLAR_DEFAULT_CAMPAIGN_ID or "cmp_agile_default",
            recipient=PoplarRecipient(
                address_1=val.cleaned_address["address_1"],
                address_2=val.cleaned_address.get("address_2"),
                city=val.cleaned_address["city"],
                state=val.cleaned_address["state"],
                postal_code=val.cleaned_address["postal_code"],
                full_name=extracted["full_name"],
                company=extracted["company"],
                identifier=str(outreach.id),
            ),
        )
        outreach.status = "sending"
        outreach.provider_message_id = res.id
    else:
        outreach.status = "sending"
        outreach.provider_message_id = f"mlg_mock_{uuid.uuid4().hex[:12]}"

    db.add(
        OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="sending",
            event_metadata={"mailing_id": outreach.provider_message_id},
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return outreach
