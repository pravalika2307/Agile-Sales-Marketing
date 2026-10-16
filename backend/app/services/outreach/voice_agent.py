"""
Retell AI Outbound Sales/SDR Voice Agent domain service for Agile Sales & Marketing.

Provides:
- Dynamic variable extraction and graceful fallback formatting for B2B voice calls.
- Prompt template rendering and verification.
- Outcome classification constants for SDR post-call analysis.
- Safe integration layer linking Outreach records to Retell AI voice agent.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings

# Supported qualification outcomes aligned with SDR qualification flow
QUALIFICATION_OUTCOMES: List[str] = [
    "interested",
    "somewhat_interested",
    "not_interested",
    "callback_requested",
    "wrong_person",
    "unavailable",
    "do_not_call",
    "qualified",
    "unqualified",
]

DEFAULT_VOICE_DYNAMIC_VARIABLES: Dict[str, str] = {
    "lead_id": "",
    "lead_first_name": "there",
    "lead_last_name": "",
    "lead_full_name": "there",
    "lead_phone": "",
    "lead_email": "",
    "prospect_company_name": "your team",
    "prospect_job_title": "",
    "campaign_id": "",
    "campaign_name": "Outbound Introduction",
    "campaign_context": "exploring alignment with your business initiatives",
    "sender_name": "Alex",
    "sender_company_name": "Agile Sales & Marketing",
    "product_name": "Agile Sales Platform",
    "product_description": "automated B2B outbound pipeline and lead outreach",
    "value_proposition": "streamlining your team's outreach and qualified meetings",
    # Pre-call Lead Intelligence & Web Research Context
    "research_company_summary": "",
    "research_industry": "",
    "research_pain_points": "",
    "research_personalization_point": "",
    "research_business_signals": "",
    "research_summary": "",
}


def build_voice_dynamic_variables(
    contact: Optional[Any] = None,
    company: Optional[Any] = None,
    campaign: Optional[Any] = None,
    organization: Optional[Any] = None,
    lead_research: Optional[Any] = None,
    lead: Optional[Any] = None,
    custom_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Constructs a complete set of dynamic variables for a Retell outbound sales call.
    Applies defensive fallback substitution so no variable is left as empty brackets or raw tags.
    """
    variables: Dict[str, str] = dict(DEFAULT_VOICE_DYNAMIC_VARIABLES)

    # 1. Lead / Contact Variables (Source of truth)
    target = lead if lead is not None else contact
    if target is not None:
        target_id = getattr(target, "id", None)
        if target_id:
            variables["lead_id"] = str(target_id)
        elif hasattr(target, "lead_id") and getattr(target, "lead_id", None):
            variables["lead_id"] = str(getattr(target, "lead_id"))

        first = getattr(target, "first_name", "") or ""
        last = getattr(target, "last_name", "") or ""
        email = getattr(target, "email", "") or ""
        phone = getattr(target, "phone", "") or ""
        job_title = getattr(target, "job_title", "") or ""

        if first.strip():
            variables["lead_first_name"] = first.strip()
        if last.strip():
            variables["lead_last_name"] = last.strip()
        
        full = f"{first} {last}".strip()
        if full:
            variables["lead_full_name"] = full
        elif first.strip():
            variables["lead_full_name"] = first.strip()

        if email.strip():
            variables["lead_email"] = email.strip()
        if phone.strip():
            variables["lead_phone"] = phone.strip()
        if job_title.strip():
            variables["prospect_job_title"] = job_title.strip()

        # Check company_name directly on Lead
        lead_comp = getattr(target, "company_name", None)
        if lead_comp and str(lead_comp).strip():
            variables["prospect_company_name"] = str(lead_comp).strip()

    # If both contact and lead were provided, contact can supplement
    if lead is not None and contact is not None:
        if not variables.get("lead_email") and getattr(contact, "email", None):
            variables["lead_email"] = str(contact.email).strip()
        if not variables.get("lead_phone") and getattr(contact, "phone", None):
            variables["lead_phone"] = str(contact.phone).strip()

    # 2. Target Company Record
    if company is not None:
        comp_name = getattr(company, "name", "") or ""
        if comp_name.strip():
            variables["prospect_company_name"] = comp_name.strip()
    elif contact is not None and getattr(contact, "company", None) is not None:
        comp_name = getattr(contact.company, "name", "") or ""
        if comp_name.strip():
            variables["prospect_company_name"] = comp_name.strip()

    # 3. Campaign & Value Proposition Context
    if campaign is not None:
        camp_id = getattr(campaign, "id", None)
        if camp_id:
            variables["campaign_id"] = str(camp_id)
        camp_name = getattr(campaign, "name", "") or ""
        camp_desc = getattr(campaign, "description", "") or ""
        if camp_name.strip():
            variables["campaign_name"] = camp_name.strip()
        if camp_desc.strip():
            variables["campaign_context"] = camp_desc.strip()

    # 4. Organization / Sender Identity
    if organization is not None:
        org_name = getattr(organization, "name", "") or ""
        if org_name.strip():
            variables["sender_company_name"] = org_name.strip()

    # 5. Pre-call Lead Research Context
    if lead_research is not None:
        from app.services.research.service import LeadResearchService
        res_vars = LeadResearchService.format_voice_dynamic_context(lead_research)
        for k, v in res_vars.items():
            if v:
                variables[k] = v

    # 6. Caller-provided overrides
    if custom_overrides:
        for k, v in custom_overrides.items():
            if v is not None and str(v).strip():
                variables[k] = str(v).strip()

    return variables


def render_prompt_template(template: str, variables: Dict[str, str]) -> str:
    """
    Substitutes all {{variable_name}} tokens in the template using the provided dictionary.
    If a variable is missing, gracefully substitutes the default or an empty string,
    guaranteeing no literal `{{...}}` tags remain in the agent output.
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1).strip()
        if var_name in variables:
            val = variables[var_name]
            return val if val is not None else ""
        if var_name in DEFAULT_VOICE_DYNAMIC_VARIABLES:
            return DEFAULT_VOICE_DYNAMIC_VARIABLES[var_name]
        return ""

    pattern = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
    rendered = pattern.sub(replacer, template)
    return rendered


class RetellVoiceAgentService:
    """
    Service layer providing management, validation, and safe variable injection
    for the Agile S&M Retell outbound sales voice agent.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.RETELL_API_KEY
        self.agent_id = agent_id or settings.RETELL_AGENT_ID
        self.base_url = base_url or settings.RETELL_BASE_URL

    @property
    def is_configured(self) -> bool:
        return bool(
            self.api_key
            and self.api_key.strip()
            and self.agent_id
            and self.agent_id.strip()
        )
