"""Domain service managing Contact Lists, Memberships, and Campaign Associations."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.normalization import normalize_email
from app.models.call_record import CallRecord
from app.models.campaign import Campaign, CampaignContact
from app.models.contact_list import CampaignList, ContactList, ContactListMember
from app.models.crm import Contact, Company
from app.models.lead import Lead
from app.models.outreach import Outreach
from app.schemas.contact_list import (
    CampaignListItem,
    CampaignListAttachResponse,
    CampaignListSyncResponse,
    ContactListAddMembersResponse,
    ContactListCreate,
    ContactListDetailResponse,
    ContactListMemberItem,
    ContactListResponse,
    ContactListUpdate,
)
from app.services.lead_generation.service import convert_lead_to_crm

logger = logging.getLogger(__name__)


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class ContactListServiceError(Exception):
    """Base exception for contact list operations."""
    pass


class ContactListNotFoundError(ContactListServiceError):
    """Raised when a list is not found within the tenant organization."""
    pass


class DuplicateContactListNameError(ContactListServiceError):
    """Raised when a list with the same name already exists in the organization."""
    pass


class ContactListMemberNotFoundError(ContactListServiceError):
    """Raised when a member is not found in the list."""
    pass


class CampaignNotFoundError(ContactListServiceError):
    """Raised when a campaign is not found in the organization."""
    pass


# ── Service Operations ────────────────────────────────────────────────────────

def create_contact_list(
    db: Session,
    org_id: uuid.UUID,
    data: ContactListCreate,
) -> ContactList:
    """Create a new contact list scoped strictly to the tenant organization."""
    norm_name = data.name.strip()
    if not norm_name:
        raise ValueError("List name cannot be empty.")

    # Enforce case-insensitive uniqueness per organization
    existing = (
        db.query(ContactList)
        .filter(
            ContactList.organization_id == org_id,
            func.lower(ContactList.name) == norm_name.lower(),
        )
        .first()
    )
    if existing:
        raise DuplicateContactListNameError(f"A list named '{norm_name}' already exists in your organization.")

    new_list = ContactList(
        organization_id=org_id,
        name=norm_name,
        description=data.description.strip() if data.description else None,
        type=data.type or "static",
    )
    db.add(new_list)
    db.commit()
    db.refresh(new_list)
    return new_list


def get_contact_list(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
) -> Optional[ContactList]:
    """Retrieve a contact list by ID strictly scoped to the tenant organization."""
    return (
        db.query(ContactList)
        .filter(ContactList.id == list_id, ContactList.organization_id == org_id)
        .first()
    )


def list_contact_lists(
    db: Session,
    org_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    list_type: Optional[str] = None,
) -> Tuple[List[ContactListResponse], int]:
    """List contact lists with member and campaign counts."""
    query = db.query(ContactList).filter(ContactList.organization_id == org_id)
    if list_type and list_type.lower() != "all":
        query = query.filter(ContactList.type == list_type)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(ContactList.name).like(term))

    total = query.count()
    lists = query.order_by(ContactList.created_at.desc()).offset(skip).limit(limit).all()

    items: List[ContactListResponse] = []
    for cl in lists:
        m_count = (
            db.query(func.count(ContactListMember.id))
            .filter(ContactListMember.contact_list_id == cl.id)
            .scalar()
            or 0
        )
        c_count = (
            db.query(func.count(CampaignList.id))
            .filter(CampaignList.contact_list_id == cl.id)
            .scalar()
            or 0
        )
        items.append(
            ContactListResponse(
                id=cl.id,
                organization_id=cl.organization_id,
                name=cl.name,
                description=cl.description,
                type=cl.type,
                member_count=m_count,
                campaigns_count=c_count,
                created_at=cl.created_at,
                updated_at=cl.updated_at,
            )
        )

    return items, total


def get_contact_list_detail(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
) -> ContactListDetailResponse:
    """Retrieve complete details, breakdown of valid/unresolved emails, and activity metrics for a list."""
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    members = (
        db.query(ContactListMember)
        .filter(ContactListMember.contact_list_id == cl.id)
        .all()
    )
    total_members = len(members)

    valid_email_count = 0
    unresolved_email_count = 0
    contact_ids: List[uuid.UUID] = []

    for m in members:
        email = None
        if m.contact_id:
            contact_ids.append(m.contact_id)
            c = db.query(Contact).filter(Contact.id == m.contact_id).first()
            if c and c.email:
                email = c.email
        elif m.lead_id:
            ld = db.query(Lead).filter(Lead.id == m.lead_id).first()
            if ld and ld.email:
                email = ld.email

        if email and "@" in email and "." in email.split("@")[-1]:
            valid_email_count += 1
        else:
            unresolved_email_count += 1

    # Associated campaigns
    camp_links = (
        db.query(CampaignList, Campaign)
        .join(Campaign, CampaignList.campaign_id == Campaign.id)
        .filter(CampaignList.contact_list_id == cl.id)
        .all()
    )
    associated_campaigns: List[CampaignListItem] = []
    associated_campaign_ids: List[uuid.UUID] = []
    for link, camp in camp_links:
        associated_campaign_ids.append(camp.id)
        associated_campaigns.append(
            CampaignListItem(
                id=camp.id,
                name=camp.name,
                status=camp.status,
                type=camp.type,
                associated_at=link.associated_at,
            )
        )

    # Activity metrics across associated campaigns for members of this list
    outreach_sent = 0
    outreach_delivered = 0
    outreach_replied = 0
    outreach_bounced = 0
    meetings_booked = 0

    if contact_ids and associated_campaign_ids:
        outreach_query = (
            db.query(Outreach)
            .filter(
                Outreach.organization_id == org_id,
                Outreach.contact_id.in_(contact_ids),
                Outreach.campaign_id.in_(associated_campaign_ids),
            )
        )
        outreach_sent = outreach_query.filter(Outreach.status == "sent").count()
        outreach_delivered = outreach_query.filter(Outreach.first_delivered_at.isnot(None)).count()
        outreach_replied = outreach_query.filter(Outreach.first_replied_at.isnot(None)).count()
        outreach_bounced = outreach_query.filter(Outreach.first_bounced_at.isnot(None)).count()

        meetings_booked = (
            db.query(func.count(CallRecord.id))
            .filter(
                CallRecord.organization_id == org_id,
                CallRecord.contact_id.in_(contact_ids),
                CallRecord.call_outcome == "MEETING_REQUESTED",
            )
            .scalar()
            or 0
        )

    return ContactListDetailResponse(
        id=cl.id,
        organization_id=cl.organization_id,
        name=cl.name,
        description=cl.description,
        type=cl.type,
        member_count=total_members,
        valid_email_count=valid_email_count,
        unresolved_email_count=unresolved_email_count,
        campaigns_count=len(associated_campaigns),
        associated_campaigns=associated_campaigns,
        outreach_sent=outreach_sent,
        outreach_delivered=outreach_delivered,
        outreach_replied=outreach_replied,
        outreach_bounced=outreach_bounced,
        meetings_booked=meetings_booked,
        created_at=cl.created_at,
        updated_at=cl.updated_at,
    )


def update_contact_list(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
    data: ContactListUpdate,
) -> ContactList:
    """Update list name or description with unique name check."""
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    if data.name is not None:
        norm_name = data.name.strip()
        if not norm_name:
            raise ValueError("List name cannot be empty.")
        if norm_name.lower() != cl.name.lower():
            existing = (
                db.query(ContactList)
                .filter(
                    ContactList.organization_id == org_id,
                    func.lower(ContactList.name) == norm_name.lower(),
                )
                .first()
            )
            if existing:
                raise DuplicateContactListNameError(f"A list named '{norm_name}' already exists in your organization.")
            cl.name = norm_name

    if data.description is not None:
        cl.description = data.description.strip() or None

    cl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cl)
    return cl


def delete_contact_list(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
) -> bool:
    """Safely delete a list, cascading only membership and campaign links. Preserves contacts, leads, and outreach."""
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        return False

    db.delete(cl)
    db.commit()
    return True


def add_members_to_list(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
    contact_ids: Optional[List[uuid.UUID]] = None,
    lead_ids: Optional[List[uuid.UUID]] = None,
) -> ContactListAddMembersResponse:
    """
    Add contacts and/or leads to a list with strict tenant isolation and in-list deduplication.
    Leads with no email are preserved without creating unnecessary CRM contacts.
    """
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    added_count = 0
    already_members_count = 0
    failed_count = 0
    added_member_ids: List[uuid.UUID] = []
    errors: List[str] = []

    # 1. Process contact_ids
    if contact_ids:
        for cid in contact_ids:
            contact = (
                db.query(Contact)
                .filter(Contact.id == cid, Contact.organization_id == org_id)
                .first()
            )
            if not contact:
                failed_count += 1
                errors.append(f"Contact '{cid}' not found in your organization.")
                continue

            # Check existing membership
            existing = (
                db.query(ContactListMember)
                .filter(
                    ContactListMember.contact_list_id == cl.id,
                    ContactListMember.contact_id == cid,
                )
                .first()
            )
            if existing:
                already_members_count += 1
                continue

            member = ContactListMember(
                contact_list_id=cl.id,
                contact_id=cid,
                lead_id=None,
            )
            db.add(member)
            db.flush()
            added_count += 1
            added_member_ids.append(member.id)

    # 2. Process lead_ids
    if lead_ids:
        for lid in lead_ids:
            lead = (
                db.query(Lead)
                .filter(Lead.id == lid, Lead.organization_id == org_id)
                .first()
            )
            if not lead:
                failed_count += 1
                errors.append(f"Lead '{lid}' not found in your organization.")
                continue

            norm_lead_email = normalize_email(lead.email) if lead.email else None

            # Resolve contact pointer if lead already has contact_id or matching contact email exists
            resolved_contact_id = lead.contact_id
            if not resolved_contact_id and norm_lead_email:
                matching_contact = (
                    db.query(Contact)
                    .filter(
                        Contact.organization_id == org_id,
                        func.lower(Contact.email) == norm_lead_email,
                    )
                    .first()
                )
                if matching_contact:
                    resolved_contact_id = matching_contact.id
                    lead.contact_id = matching_contact.id

            # Check if prospect is already a member (either by lead_id or resolved contact_id)
            existing_query = db.query(ContactListMember).filter(
                ContactListMember.contact_list_id == cl.id
            )
            if resolved_contact_id:
                existing = existing_query.filter(
                    or_(
                        ContactListMember.lead_id == lid,
                        ContactListMember.contact_id == resolved_contact_id,
                    )
                ).first()
            else:
                existing = existing_query.filter(ContactListMember.lead_id == lid).first()

            if existing:
                # If existing had no lead_id, link it now
                if not existing.lead_id:
                    existing.lead_id = lid
                already_members_count += 1
                continue

            member = ContactListMember(
                contact_list_id=cl.id,
                contact_id=resolved_contact_id,
                lead_id=lid,
            )
            db.add(member)
            db.flush()
            added_count += 1
            added_member_ids.append(member.id)

    db.commit()

    return ContactListAddMembersResponse(
        list_id=cl.id,
        added_count=added_count,
        already_members_count=already_members_count,
        failed_count=failed_count,
        added_member_ids=added_member_ids,
        errors=errors,
    )


def remove_member_from_list(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
    target_id: uuid.UUID,
) -> bool:
    """
    Remove a member record from a list.
    target_id can be the membership id, or the underlying contact_id / lead_id.
    Preserves the Contact and Lead completely.
    """
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    member = (
        db.query(ContactListMember)
        .filter(
            ContactListMember.contact_list_id == cl.id,
            or_(
                ContactListMember.id == target_id,
                ContactListMember.contact_id == target_id,
                ContactListMember.lead_id == target_id,
            ),
        )
        .first()
    )
    if not member:
        return False

    db.delete(member)
    db.commit()
    return True


def list_members(
    db: Session,
    org_id: uuid.UUID,
    list_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    has_unresolved_email: Optional[bool] = None,
) -> Tuple[List[ContactListMemberItem], int]:
    """List members of a contact list with rich contact and company snapshot attributes."""
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    query = (
        db.query(ContactListMember)
        .filter(ContactListMember.contact_list_id == cl.id)
    )
    total = query.count()
    members = query.order_by(ContactListMember.added_at.desc()).offset(skip).limit(limit).all()

    items: List[ContactListMemberItem] = []
    for m in members:
        first_name = None
        last_name = None
        email = None
        phone = None
        company_name = None
        job_title = None
        source = None

        if m.contact_id:
            c = db.query(Contact).filter(Contact.id == m.contact_id).first()
            if c:
                first_name = c.first_name
                last_name = c.last_name
                email = c.email
                phone = c.phone
                job_title = c.job_title
                source = "crm_contact"
                if c.company_id:
                    comp = db.query(Company).filter(Company.id == c.company_id).first()
                    if comp:
                        company_name = comp.name

        if m.lead_id:
            ld = db.query(Lead).filter(Lead.id == m.lead_id).first()
            if ld:
                if not first_name:
                    first_name = ld.first_name
                if not last_name:
                    last_name = ld.last_name
                if not email:
                    email = ld.email
                if not phone:
                    phone = ld.phone
                if not company_name:
                    company_name = ld.company_name
                if not job_title:
                    job_title = ld.job_title
                source = ld.source or "lead"

        full_name_parts = [p for p in (first_name, last_name) if p]
        full_name = " ".join(full_name_parts) if full_name_parts else (company_name or "Unknown Prospect")
        has_valid_email = bool(email and "@" in email and "." in email.split("@")[-1])
        is_unresolved = not has_valid_email

        if has_unresolved_email is True and not is_unresolved:
            continue
        if has_unresolved_email is False and is_unresolved:
            continue

        # Filter by search term if provided
        if search and search.strip():
            st = search.strip().lower()
            match = (
                (full_name and st in full_name.lower())
                or (email and st in email.lower())
                or (company_name and st in company_name.lower())
            )
            if not match:
                continue

        items.append(
            ContactListMemberItem(
                id=m.id,
                contact_id=m.contact_id,
                lead_id=m.lead_id,
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
                email=email,
                phone=phone,
                company_name=company_name,
                job_title=job_title,
                source=source,
                has_valid_email=has_valid_email,
                is_unresolved_email=is_unresolved,
                added_at=m.added_at,
            )
        )

    return items, total


def attach_list_to_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    list_id: uuid.UUID,
) -> CampaignListAttachResponse:
    """
    Attach a contact list to a campaign and execute initial safe synchronization.
    Enrolls eligible contacts as 'queued' (Step 0) without triggering emails.
    Skips unresolved-email leads and suppressed contacts.
    """
    # 1. Validate Campaign
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    # 2. Validate List
    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    # 3. Create or reuse CampaignList association
    assoc = (
        db.query(CampaignList)
        .filter(
            CampaignList.campaign_id == campaign.id,
            CampaignList.contact_list_id == cl.id,
        )
        .first()
    )
    if not assoc:
        assoc = CampaignList(
            campaign_id=campaign.id,
            contact_list_id=cl.id,
        )
        db.add(assoc)
        db.flush()

    # 4. Synchronize members
    sync_res = _execute_list_sync_to_campaign(db, org_id, campaign, cl)
    db.commit()

    return CampaignListAttachResponse(
        campaign_id=campaign.id,
        contact_list_id=cl.id,
        newly_enrolled_count=sync_res["newly_enrolled_count"],
        already_enrolled_count=sync_res["already_enrolled_count"],
        unresolved_email_count=sync_res["unresolved_email_count"],
        suppressed_opt_out_count=sync_res["suppressed_opt_out_count"],
        unresolved_members=sync_res["unresolved_members"],
    )


def sync_list_to_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    list_id: uuid.UUID,
) -> CampaignListSyncResponse:
    """
    Explicitly synchronize an attached list with a campaign.
    Enrolls any newly added members without resetting or duplicating existing enrollments.
    """
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    cl = get_contact_list(db, org_id, list_id)
    if not cl:
        raise ContactListNotFoundError(f"Contact list '{list_id}' not found.")

    # Verify association exists
    assoc = (
        db.query(CampaignList)
        .filter(
            CampaignList.campaign_id == campaign.id,
            CampaignList.contact_list_id == cl.id,
        )
        .first()
    )
    if not assoc:
        raise ContactListServiceError(f"List '{cl.name}' is not attached to campaign '{campaign.name}'.")

    sync_res = _execute_list_sync_to_campaign(db, org_id, campaign, cl)
    db.commit()

    return CampaignListSyncResponse(
        campaign_id=campaign.id,
        contact_list_id=cl.id,
        newly_enrolled_count=sync_res["newly_enrolled_count"],
        already_enrolled_count=sync_res["already_enrolled_count"],
        unresolved_email_count=sync_res["unresolved_email_count"],
        suppressed_opt_out_count=sync_res["suppressed_opt_out_count"],
        unresolved_members=sync_res["unresolved_members"],
    )


def detach_list_from_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    list_id: uuid.UUID,
) -> bool:
    """
    Detach a contact list from a campaign.
    Preserves all existing CampaignContact enrollments and historical outreach records.
    """
    assoc = (
        db.query(CampaignList)
        .join(Campaign, CampaignList.campaign_id == Campaign.id)
        .filter(
            CampaignList.campaign_id == campaign_id,
            CampaignList.contact_list_id == list_id,
            Campaign.organization_id == org_id,
        )
        .first()
    )
    if not assoc:
        return False

    db.delete(assoc)
    db.commit()
    return True


def list_campaign_attached_lists(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> List[ContactListResponse]:
    """Retrieve all lists currently attached to a campaign."""
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found.")

    links = (
        db.query(CampaignList, ContactList)
        .join(ContactList, CampaignList.contact_list_id == ContactList.id)
        .filter(CampaignList.campaign_id == campaign.id)
        .all()
    )

    items: List[ContactListResponse] = []
    for link, cl in links:
        m_count = (
            db.query(func.count(ContactListMember.id))
            .filter(ContactListMember.contact_list_id == cl.id)
            .scalar()
            or 0
        )
        c_count = (
            db.query(func.count(CampaignList.id))
            .filter(CampaignList.contact_list_id == cl.id)
            .scalar()
            or 0
        )
        items.append(
            ContactListResponse(
                id=cl.id,
                organization_id=cl.organization_id,
                name=cl.name,
                description=cl.description,
                type=cl.type,
                member_count=m_count,
                campaigns_count=c_count,
                created_at=cl.created_at,
                updated_at=cl.updated_at,
            )
        )
    return items


# ── Internal Helper Functions ─────────────────────────────────────────────────

def _execute_list_sync_to_campaign(
    db: Session,
    org_id: uuid.UUID,
    campaign: Campaign,
    contact_list: ContactList,
) -> Dict[str, Any]:
    """
    Helper executing the core enrollment evaluation of list members into a campaign.
    Guarantees:
    - Zero emails or calls triggered.
    - Missing email leads are skipped and reported.
    - Suppressed contacts (opted_out) are skipped and reported.
    - Existing enrollments are preserved at current steps without duplication.
    """
    members = (
        db.query(ContactListMember)
        .filter(ContactListMember.contact_list_id == contact_list.id)
        .all()
    )

    newly_enrolled = 0
    already_enrolled = 0
    unresolved_email = 0
    suppressed_count = 0
    unresolved_members: List[Dict[str, Any]] = []

    for m in members:
        effective_contact_id = m.contact_id

        # If only lead_id is present, inspect lead for email and convert if needed
        if not effective_contact_id and m.lead_id:
            lead = db.query(Lead).filter(Lead.id == m.lead_id).first()
            if not lead or not lead.email:
                unresolved_email += 1
                unresolved_members.append({
                    "lead_id": str(m.lead_id),
                    "name": lead.company_name if lead else "Unknown Lead",
                    "reason": "Missing email address",
                })
                continue

            # Convert or link CRM contact
            conv = convert_lead_to_crm(db, lead.organization, lead.id)
            if conv.contact_id:
                effective_contact_id = conv.contact_id
                m.contact_id = conv.contact_id
                db.flush()
            else:
                unresolved_email += 1
                unresolved_members.append({
                    "lead_id": str(m.lead_id),
                    "name": lead.company_name,
                    "reason": "Could not resolve CRM contact",
                })
                continue

        if not effective_contact_id:
            unresolved_email += 1
            continue

        # Check contact validity and suppression
        contact = (
            db.query(Contact)
            .filter(Contact.id == effective_contact_id, Contact.organization_id == org_id)
            .first()
        )
        if not contact or not contact.email:
            unresolved_email += 1
            unresolved_members.append({
                "contact_id": str(effective_contact_id),
                "name": f"{contact.first_name} {contact.last_name}" if contact else "Missing Contact",
                "reason": "Missing valid contact email",
            })
            continue

        if contact.lead_status in ("opted_out", "unsubscribed"):
            suppressed_count += 1
            continue

        # Check if already enrolled in this campaign
        existing_enrollment = (
            db.query(CampaignContact)
            .filter(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.contact_id == effective_contact_id,
            )
            .first()
        )
        if existing_enrollment:
            already_enrolled += 1
            continue

        # Create new enrollment strictly in 'queued' status with current_step = 0
        new_cc = CampaignContact(
            campaign_id=campaign.id,
            contact_id=effective_contact_id,
            enrollment_status="queued",
            current_step=0,
        )
        db.add(new_cc)
        db.flush()
        newly_enrolled += 1

    return {
        "newly_enrolled_count": newly_enrolled,
        "already_enrolled_count": already_enrolled,
        "unresolved_email_count": unresolved_email,
        "suppressed_opt_out_count": suppressed_count,
        "unresolved_members": unresolved_members,
    }


def sync_source_and_category_lists(
    db: Session,
    org_id: uuid.UUID,
) -> Dict[str, Any]:
    """
    Idempotent organization-scoped synchronization that organizes existing leads
    into source lists ('HubSpot Contacts', 'CSV Imports', 'Manually Added Leads')
    and verified industry lists using reliable metadata.
    Guarantees:
    - Zero outreach initiated, zero emails sent, zero calls placed.
    - Zero duplicate CRM contacts or leads created.
    - Tenant isolation strictly enforced (org_id).
    - Missing industries are left unassigned (no guessing).
    - Retell voice call leads are not forced into an unrelated list.
    """
    source_configs = [
        {
            "source": "hubspot",
            "name": "HubSpot Contacts",
            "description": "Contacts and leads synchronized from HubSpot CRM.",
            "type": "source",
        },
        {
            "source": "csv_import",
            "name": "CSV Imports",
            "description": "Prospects and leads imported from CSV files.",
            "type": "source",
        },
        {
            "source": "manual",
            "name": "Manually Added Leads",
            "description": "Leads entered manually through the CRM interface.",
            "type": "source",
        },
    ]

    synced_results = []
    total_added = 0

    # 1. Process Source Lists
    for cfg in source_configs:
        matching_lead_ids = [
            row[0]
            for row in db.query(Lead.id)
            .filter(Lead.organization_id == org_id, Lead.source == cfg["source"])
            .all()
        ]
        if not matching_lead_ids:
            continue

        # Find or create list
        contact_list = (
            db.query(ContactList)
            .filter(
                ContactList.organization_id == org_id,
                func.lower(ContactList.name) == cfg["name"].lower(),
            )
            .first()
        )
        if not contact_list:
            contact_list = ContactList(
                organization_id=org_id,
                name=cfg["name"],
                description=cfg["description"],
                type=cfg["type"],
                filter_criteria={"source": cfg["source"]},
            )
            db.add(contact_list)
            db.flush()

        add_res = add_members_to_list(db, org_id, contact_list.id, lead_ids=matching_lead_ids)
        total_added += add_res.added_count
        synced_results.append({
            "list_id": str(contact_list.id),
            "name": contact_list.name,
            "type": contact_list.type,
            "matching_leads_count": len(matching_lead_ids),
            "newly_added_count": add_res.added_count,
            "already_members_count": add_res.already_members_count,
        })

    # 2. Process Verified Industry Lists (no guessing: only non-null, non-empty distinct industries)
    distinct_industries = [
        row[0].strip()
        for row in db.query(Lead.industry)
        .filter(
            Lead.organization_id == org_id,
            Lead.industry.isnot(None),
            func.trim(Lead.industry) != "",
        )
        .distinct()
        .all()
        if row[0] and row[0].strip()
    ]

    for ind in distinct_industries:
        matching_lead_ids = [
            row[0]
            for row in db.query(Lead.id)
            .filter(
                Lead.organization_id == org_id,
                func.lower(func.trim(Lead.industry)) == ind.lower(),
            )
            .all()
        ]
        if not matching_lead_ids:
            continue

        contact_list = (
            db.query(ContactList)
            .filter(
                ContactList.organization_id == org_id,
                func.lower(ContactList.name) == ind.lower(),
            )
            .first()
        )
        if not contact_list:
            contact_list = ContactList(
                organization_id=org_id,
                name=ind,
                description=f"Leads categorized in the {ind} industry.",
                type="industry",
                filter_criteria={"industry": ind},
            )
            db.add(contact_list)
            db.flush()

        add_res = add_members_to_list(db, org_id, contact_list.id, lead_ids=matching_lead_ids)
        total_added += add_res.added_count
        synced_results.append({
            "list_id": str(contact_list.id),
            "name": contact_list.name,
            "type": contact_list.type,
            "matching_leads_count": len(matching_lead_ids),
            "newly_added_count": add_res.added_count,
            "already_members_count": add_res.already_members_count,
        })

    db.commit()

    return {
        "synced_lists": synced_results,
        "total_lists_synced": len(synced_results),
        "total_new_memberships": total_added,
    }

