"""
Lead Research domain service orchestrating pre-call intelligence, caching, and voice context generation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.lead_research import LeadResearch
from app.schemas.lead_research import StructuredLeadIntelligence
from app.services.research.base import LLMStructuringProvider, WebResearchProvider
from app.services.research.providers.http_web import HttpWebResearchProvider
from app.services.research.providers.llm import DefaultLLMStructuringProvider
from app.services.research.providers.mock import MockLLMStructuringProvider, MockWebResearchProvider

logger = logging.getLogger(__name__)


class LeadNotFoundError(Exception):
    """Raised when the specified lead is not found within the tenant organization."""
    pass


class LeadResearchService:
    """
    Manages pre-call web research lifecycle:
    - Freshness verification and recent research caching.
    - Targeted public web retrieval (prioritizing company domain).
    - LLM-grounded structuring into key business signals, pain points, and hooks.
    - Translation into Retell dynamic variables for live voice calls.
    """

    def __init__(
        self,
        web_provider: Optional[WebResearchProvider] = None,
        llm_provider: Optional[LLMStructuringProvider] = None,
    ) -> None:
        self.web_provider = web_provider or HttpWebResearchProvider()
        self.llm_provider = llm_provider or DefaultLLMStructuringProvider()

    async def get_or_research_lead(
        self,
        db: Session,
        org_id: uuid.UUID,
        lead_id: uuid.UUID,
        max_age_days: int = 7,
        force_refresh: bool = False,
    ) -> LeadResearch:
        """
        Retrieves existing fresh research or performs targeted pre-call research for the lead.
        Enforces strict tenant isolation.
        """
        # 1. Fetch Lead with strict tenant scoping
        lead = (
            db.query(Lead)
            .filter(Lead.id == lead_id, Lead.organization_id == org_id)
            .first()
        )
        if not lead:
            raise LeadNotFoundError(f"Lead '{lead_id}' not found for tenant '{org_id}'.")

        # 2. Check Freshness of existing research
        existing_research = (
            db.query(LeadResearch)
            .filter(LeadResearch.lead_id == lead.id, LeadResearch.organization_id == org_id)
            .first()
        )

        if existing_research and not force_refresh:
            if existing_research.check_freshness(max_age_days=max_age_days):
                logger.info(
                    "Reusing fresh existing research for lead %s (researched_at=%s)",
                    lead.id,
                    existing_research.researched_at,
                )
                return existing_research

        # 3. Compile Lead Context for Research
        lead_context: Dict[str, Any] = {
            "lead_id": str(lead.id),
            "company_name": lead.company_name,
            "company_domain": lead.company_domain,
            "industry": lead.industry,
            "employee_count_range": lead.employee_count_range,
            "location": f"{lead.city or ''}, {lead.country or ''}".strip(", "),
            "job_title": lead.job_title or "",
            "first_name": lead.first_name or "",
            "last_name": lead.last_name or "",
        }

        # 4. Execute Web Research
        logger.info("Executing pre-call web research for lead company: %s", lead.company_name)
        raw_result = await self.web_provider.search_and_fetch(
            company_name=lead.company_name,
            company_domain=lead.company_domain,
            industry=lead.industry,
            max_sources=4,
        )

        now = datetime.now(timezone.utc)

        if not raw_result.success:
            logger.warning("Web research failed for lead %s: %s", lead.id, raw_result.error)
            research_record = existing_research or LeadResearch(
                organization_id=org_id,
                lead_id=lead.id,
            )
            research_record.research_status = "failed"
            research_record.error_message = raw_result.error or "Web search failed."
            research_record.researched_at = now
            db.add(research_record)
            db.commit()
            db.refresh(research_record)
            return research_record

        # 5. Execute LLM Structuring
        try:
            structured = await self.llm_provider.structure_intelligence(
                company_name=lead.company_name,
                lead_context=lead_context,
                raw_result=raw_result,
            )
        except Exception as exc:
            logger.error("LLM structuring failed for lead %s: %s", lead.id, exc)
            research_record = existing_research or LeadResearch(
                organization_id=org_id,
                lead_id=lead.id,
            )
            research_record.research_status = "failed"
            research_record.error_message = f"Structuring error: {str(exc)}"
            research_record.researched_at = now
            db.add(research_record)
            db.commit()
            db.refresh(research_record)
            return research_record

        # 6. Save or Update LeadResearch Record
        research_record = existing_research or LeadResearch(
            organization_id=org_id,
            lead_id=lead.id,
        )
        research_record.company_summary = structured.company_summary
        research_record.industry = structured.industry or lead.industry
        research_record.company_size = structured.company_size or lead.employee_count_range
        research_record.location = structured.location or lead_context.get("location")
        research_record.business_signals = structured.business_signals
        research_record.potential_pain_points = structured.potential_pain_points
        research_record.personalization_points = structured.personalization_points
        research_record.research_summary = structured.research_summary
        research_record.source_urls = structured.source_urls
        research_record.researched_at = now
        research_record.research_status = "completed"
        research_record.error_message = None

        db.add(research_record)
        db.commit()
        db.refresh(research_record)

        logger.info("Successfully persisted pre-call intelligence for lead %s", lead.id)
        return research_record

    @staticmethod
    def format_voice_dynamic_context(research: Optional[LeadResearch]) -> Dict[str, str]:
        """
        Translates a LeadResearch record into clean, conversational strings
        designed to be passed as dynamic variables to Retell AI voice agents.
        Guarantees no raw JSON or broken syntax is spoken by the voice agent.
        """
        if not research or research.research_status != "completed":
            return {
                "research_company_summary": "",
                "research_industry": "",
                "research_pain_points": "",
                "research_personalization_point": "",
                "research_business_signals": "",
                "research_summary": "",
            }

        # Format pain points into a natural conversational phrase
        pain_points_str = ""
        if research.potential_pain_points:
            pain_points_str = "; ".join(research.potential_pain_points[:2])

        # Pick primary personalization hook
        personalization_str = ""
        if research.personalization_points:
            personalization_str = research.personalization_points[0]

        # Summarize business signals
        signals_str = ""
        if research.business_signals:
            signals_str = " | ".join(research.business_signals[:2])

        return {
            "research_company_summary": research.company_summary or "",
            "research_industry": research.industry or "",
            "research_pain_points": pain_points_str,
            "research_personalization_point": personalization_str,
            "research_business_signals": signals_str,
            "research_summary": research.research_summary or "",
        }
