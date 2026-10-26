"""API v1 Router aggregation."""
from fastapi import APIRouter
from .auth import router as auth_router
from .campaign_execution import router as campaign_execution_router
from .campaign_steps import router as campaign_steps_router
from .campaigns import router as campaigns_router
from .companies import router as companies_router
from .contacts import router as contacts_router
from .contact_lists import router as contact_lists_router
from .deals import router as deals_router
from .icp import router as icp_router
from .integrations.hubspot import router as hubspot_router
from .leads import router as leads_router
from .lead_research import router as lead_research_router
from .routing_rules import router as routing_rules_router
from .outreach import router as outreach_router
from .pipeline import router as pipeline_router
from .sms import router as sms_router
from .tracking import router as tracking_router, tracking_webhook_router
from .voice_webhook import router as voice_webhook_router
from .physical_mail import router as physical_mail_router

from .analytics import router as analytics_router
from .email_templates import router as email_templates_router
from .entitlements import router as entitlements_router
from .inbound_emails import router as inbound_emails_router

api_router = APIRouter()
api_router.include_router(analytics_router)
api_router.include_router(email_templates_router)
api_router.include_router(entitlements_router)
api_router.include_router(inbound_emails_router)
api_router.include_router(auth_router)
api_router.include_router(campaign_execution_router)
api_router.include_router(campaign_steps_router)
api_router.include_router(campaigns_router)
api_router.include_router(companies_router)
api_router.include_router(contacts_router)
api_router.include_router(contact_lists_router)
api_router.include_router(pipeline_router)
api_router.include_router(deals_router)
api_router.include_router(outreach_router)
api_router.include_router(sms_router)
api_router.include_router(tracking_router)
api_router.include_router(tracking_webhook_router)
api_router.include_router(voice_webhook_router)
api_router.include_router(physical_mail_router)
api_router.include_router(hubspot_router)
api_router.include_router(icp_router)
api_router.include_router(leads_router)
api_router.include_router(lead_research_router)
api_router.include_router(routing_rules_router)

__all__ = ["api_router"]


