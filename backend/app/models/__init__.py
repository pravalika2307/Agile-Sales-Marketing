"""SQLAlchemy domain models for Agile Sales & Marketing."""
from app.models.tenant import Organization, User
from app.models.business import BusinessProfile
from app.models.crm import (
    Company,
    Contact,
    Deal,
    Pipeline,
    PipelineStage,
    ALLOWED_DEAL_STATUSES,
    ALLOWED_LEAD_STATUSES,
)
from app.models.campaign import (
    Campaign,
    CampaignContact,
    ALLOWED_CAMPAIGN_STATUSES,
    ALLOWED_CAMPAIGN_TYPES,
    ALLOWED_ENROLLMENT_STATUSES,
)
from app.models.campaign_step import (
    CampaignStep,
    ALLOWED_STEP_TYPES,
)
from app.models.outreach import (
    Outreach,
    OutreachEvent,
    ALLOWED_OUTREACH_CHANNELS,
    ALLOWED_OUTREACH_EVENT_TYPES,
    ALLOWED_OUTREACH_STATUSES,
)
from app.models.icp import IdealCustomerProfile
from app.models.lead import Lead
from app.models.lead_research import LeadResearch, ALLOWED_RESEARCH_STATUSES
from app.models.routing_rule import LeadRoutingRule
from app.models.call_record import CallRecord
from app.models.hubspot_sync import HubSpotSyncRun
from app.models.contact_list import ContactList, ContactListMember, CampaignList
from app.models.email_template import EmailTemplate, ALLOWED_TEMPLATE_CATEGORIES

__all__ = [
    "EmailTemplate",
    "ALLOWED_TEMPLATE_CATEGORIES",
    "ContactList",
    "ContactListMember",
    "CampaignList",
    "LeadRoutingRule",
    "CallRecord",
    "HubSpotSyncRun",
    "Organization",
    "User",
    "BusinessProfile",
    "Company",
    "Contact",
    "Pipeline",
    "PipelineStage",
    "Deal",
    "ALLOWED_DEAL_STATUSES",
    "ALLOWED_LEAD_STATUSES",
    "Campaign",
    "CampaignContact",
    "ALLOWED_CAMPAIGN_STATUSES",
    "ALLOWED_CAMPAIGN_TYPES",
    "ALLOWED_ENROLLMENT_STATUSES",
    "Outreach",
    "OutreachEvent",
    "ALLOWED_OUTREACH_CHANNELS",
    "ALLOWED_OUTREACH_STATUSES",
    "ALLOWED_OUTREACH_EVENT_TYPES",
    "CampaignStep",
    "ALLOWED_STEP_TYPES",
    "IdealCustomerProfile",
    "Lead",
    "LeadResearch",
    "ALLOWED_RESEARCH_STATUSES",
]
