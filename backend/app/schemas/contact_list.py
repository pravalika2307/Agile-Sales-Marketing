"""Pydantic schemas for Contact Lists, Membership, and Campaign Associations."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContactListBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the lead/contact list")
    description: Optional[str] = Field(None, max_length=2000, description="Optional description of the list")
    type: str = Field("static", max_length=50, description="List type ('static' or 'dynamic')")


class ContactListCreate(ContactListBase):
    pass


class ContactListUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)


class CampaignListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    type: str
    associated_at: datetime


class ContactListResponse(ContactListBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    member_count: int = 0
    campaigns_count: int = 0
    created_at: datetime
    updated_at: datetime


class ContactListCatalogResponse(BaseModel):
    items: List[ContactListResponse]
    total: int
    skip: int
    limit: int


class ContactListDetailResponse(ContactListResponse):
    valid_email_count: int = 0
    unresolved_email_count: int = 0
    associated_campaigns: List[CampaignListItem] = []
    outreach_sent: int = 0
    outreach_delivered: int = 0
    outreach_replied: int = 0
    outreach_bounced: int = 0
    meetings_booked: int = 0


class ContactListMemberItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID  # Membership record ID
    contact_id: Optional[uuid.UUID] = None
    lead_id: Optional[uuid.UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    source: Optional[str] = None
    has_valid_email: bool = False
    is_unresolved_email: bool = False
    added_at: datetime


class ContactListMemberListResponse(BaseModel):
    items: List[ContactListMemberItem]
    total: int
    skip: int
    limit: int


class ContactListAddMembersRequest(BaseModel):
    contact_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="IDs of CRM contacts to add")
    lead_ids: Optional[List[uuid.UUID]] = Field(default_factory=list, description="IDs of prospect leads to add")


class ContactListAddMembersResponse(BaseModel):
    list_id: uuid.UUID
    added_count: int
    already_members_count: int
    failed_count: int
    added_member_ids: List[uuid.UUID] = []
    errors: List[str] = []


class CampaignListAttachRequest(BaseModel):
    contact_list_id: uuid.UUID
    sync_immediately: bool = True


class CampaignListAttachResponse(BaseModel):
    campaign_id: uuid.UUID
    contact_list_id: uuid.UUID
    newly_enrolled_count: int
    already_enrolled_count: int
    unresolved_email_count: int
    suppressed_opt_out_count: int
    unresolved_members: List[Dict[str, Any]] = []


class CampaignListSyncResponse(BaseModel):
    campaign_id: uuid.UUID
    contact_list_id: uuid.UUID
    newly_enrolled_count: int
    already_enrolled_count: int
    unresolved_email_count: int
    suppressed_opt_out_count: int
    unresolved_members: List[Dict[str, Any]] = []
