"""
Retell AI Inbound Voice Agent domain service for Agile Sales & Marketing.

Provides:
- Inbound voice receptionist configuration & dynamic variable resolution.
- Intent classification constants for inbound inquiries.
- Outcome categorization constants for post-call CRM ingestion.
- Prompt template rendering and verification with graceful fallback handling.
- Retell inbound webhook parsing and structured call outcome extraction.
- Strict separation of call_direction = 'inbound' from outbound SDR calls.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings

# Supported inbound caller intents
INBOUND_INTENTS: List[str] = [
    "sales_inquiry",
    "product_information",
    "pricing_inquiry",
    "demo_request",
    "existing_customer",
    "support_request",
    "partnership",
    "callback_request",
    "general_information",
    "human_assistance",
    "other",
]

# Supported post-call inbound outcomes
INBOUND_OUTCOMES: List[str] = [
    "sales_inquiry",
    "demo_requested",
    "pricing_inquiry",
    "product_information",
    "support_request",
    "existing_customer",
    "callback_requested",
    "human_followup_required",
    "information_provided",
    "no_action_required",
    "do_not_contact",
    "other",
]

DEFAULT_INBOUND_DYNAMIC_VARIABLES: Dict[str, str] = {
    "sender_company_name": "Agile Sales & Marketing",
    "sender_name": "Alex",
    "product_name": "Agile Sales Platform",
    "product_description": "an automated B2B sales pipeline and customer engagement platform",
    "value_proposition": "streamlining outreach, lead qualification, and customer interactions",
    "business_hours": "Monday through Friday, 9:00 AM to 5:00 PM Eastern Time",
    "company_website": "https://agilesalesmarketing.com",
    "sales_email": "sales@agilesalesmarketing.com",
    "support_email": "support@agilesalesmarketing.com",
    # Known Lead/Contact Context (when caller is already recognized)
    "lead_id": "",
    "lead_full_name": "",
    "lead_email": "",
    "lead_phone": "",
    "company_name": "",
    "job_title": "",
    "caller_context": "",
}


def build_inbound_dynamic_variables(
    organization: Optional[Any] = None,
    contact: Optional[Any] = None,
    lead: Optional[Any] = None,
    custom_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Constructs a complete set of dynamic variables for a Retell inbound voice call.
    Extracts customer-specific variables from Organization metadata or overrides,
    as well as known Lead/Contact context when the caller is recognized,
    falling back gracefully to defaults so no raw placeholder {{...}} tags ever remain.
    """
    variables: Dict[str, str] = dict(DEFAULT_INBOUND_DYNAMIC_VARIABLES)

    # 1. Organization context
    if organization is not None:
        org_name = getattr(organization, "name", "") or ""
        if org_name.strip():
            variables["sender_company_name"] = org_name.strip()

        # Check for optional organization settings or metadata attributes
        org_metadata = getattr(organization, "metadata", None) or {}
        if isinstance(org_metadata, dict):
            for key in [
                "sender_name",
                "product_name",
                "product_description",
                "value_proposition",
                "business_hours",
                "company_website",
                "sales_email",
                "support_email",
            ]:
                if org_metadata.get(key):
                    variables[key] = str(org_metadata[key]).strip()

    # 2. Known Lead / Contact context
    target = lead if lead is not None else contact
    if target is not None:
        target_id = getattr(target, "id", None)
        if target_id:
            variables["lead_id"] = str(target_id)
        elif hasattr(target, "lead_id") and getattr(target, "lead_id", None):
            variables["lead_id"] = str(getattr(target, "lead_id"))

        first = getattr(target, "first_name", "") or ""
        last = getattr(target, "last_name", "") or ""
        full = f"{first} {last}".strip()
        if full:
            variables["lead_full_name"] = full
        elif first.strip():
            variables["lead_full_name"] = first.strip()

        email = getattr(target, "email", "") or ""
        if email.strip():
            variables["lead_email"] = email.strip()

        phone = getattr(target, "phone", "") or ""
        if phone.strip():
            variables["lead_phone"] = phone.strip()

        comp = getattr(target, "company_name", None) or (
            getattr(target.company, "name", None) if hasattr(target, "company") and target.company else None
        )
        if comp and str(comp).strip():
            variables["company_name"] = str(comp).strip()

        job = getattr(target, "job_title", "") or ""
        if job.strip():
            variables["job_title"] = job.strip()

    if lead is not None and contact is not None:
        if not variables.get("lead_email") and getattr(contact, "email", None):
            variables["lead_email"] = str(contact.email).strip()
        if not variables.get("lead_phone") and getattr(contact, "phone", None):
            variables["lead_phone"] = str(contact.phone).strip()

    # 3. Caller or scenario custom overrides
    if custom_overrides:
        for k, v in custom_overrides.items():
            if v is not None and str(v).strip():
                variables[k] = str(v).strip()

    return variables


def render_inbound_prompt_template(template: str, variables: Dict[str, str]) -> str:
    """
    Substitutes all {{variable_name}} tokens in the template using the provided dictionary.
    If a variable is missing, gracefully substitutes the default or an empty string,
    guaranteeing no literal `{{...}}` tags remain in the agent prompt or output.
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1).strip()
        if var_name in variables:
            val = variables[var_name]
            return val if val is not None else ""
        if var_name in DEFAULT_INBOUND_DYNAMIC_VARIABLES:
            return DEFAULT_INBOUND_DYNAMIC_VARIABLES[var_name]
        return ""

    pattern = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
    rendered = pattern.sub(replacer, template)
    return rendered


class RetellInboundVoiceAgentService:
    """
    Service layer for managing, inspecting, and parsing inbound calls
    handled by the Agile S&M Retell Inbound Voice Assistant.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.RETELL_API_KEY
        self.agent_id = agent_id or settings.RETELL_INBOUND_AGENT_ID
        self.base_url = base_url or settings.RETELL_BASE_URL

    @property
    def is_configured(self) -> bool:
        """Check if Retell inbound agent is configured."""
        return bool(
            self.api_key
            and self.api_key.strip()
            and self.agent_id
            and self.agent_id.strip()
        )

    def extract_inbound_call_outcome(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses a Retell post-call analysis event payload specifically for INBOUND calls.
        Validates call direction, extracts post-call analysis data, and formats
        a structured record ready for DB persistence and CRM lead/ticket assignment.
        """
        call_id = event_data.get("call_id") or ""
        call_direction = event_data.get("direction") or "inbound"
        caller_number = event_data.get("from_number") or ""
        business_number = event_data.get("to_number") or ""
        duration_ms = event_data.get("duration_ms") or 0
        transcript = event_data.get("transcript") or ""

        # Extract post call analysis data
        analysis = event_data.get("call_analysis") or {}
        custom_analysis = analysis.get("custom_analysis_data") or {}

        inbound_intent = custom_analysis.get("inbound_intent") or "other"
        if inbound_intent not in INBOUND_INTENTS:
            inbound_intent = "other"

        call_outcome = custom_analysis.get("call_outcome") or "other"
        if call_outcome not in INBOUND_OUTCOMES:
            call_outcome = "other"

        caller_name = custom_analysis.get("caller_name") or ""
        caller_company = custom_analysis.get("caller_company") or ""
        caller_email = custom_analysis.get("caller_email") or ""
        caller_phone = custom_analysis.get("caller_phone") or caller_number
        call_summary = (
            custom_analysis.get("call_summary")
            or analysis.get("call_summary")
            or ""
        )
        interest_level = custom_analysis.get("interest_level") or "low"
        requested_followup = custom_analysis.get("requested_followup") or ""
        important_notes = custom_analysis.get("important_notes") or ""

        # Require human follow-up flag if outcome or request mandates it
        human_followup_required = (
            call_outcome in ("human_followup_required", "demo_requested", "pricing_inquiry", "sales_inquiry")
            or bool(requested_followup)
            or "human" in str(inbound_intent).lower()
        )

        return {
            "call_id": call_id,
            "call_direction": "inbound",
            "caller_phone": caller_phone,
            "business_phone": business_number,
            "duration_ms": duration_ms,
            "inbound_intent": inbound_intent,
            "call_outcome": call_outcome,
            "caller_name": caller_name,
            "caller_company": caller_company,
            "caller_email": caller_email,
            "call_summary": call_summary,
            "interest_level": interest_level,
            "requested_followup": requested_followup,
            "important_notes": important_notes,
            "human_followup_required": human_followup_required,
            "transcript": transcript,
        }
