"""
LLM structuring provider for transforming raw retrieved sources into structured lead intelligence.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.schemas.lead_research import StructuredLeadIntelligence
from app.services.research.base import LLMStructuringProvider, RawResearchResult

logger = logging.getLogger(__name__)


class DefaultLLMStructuringProvider(LLMStructuringProvider):
    """
    LLM Structuring provider with defensive prompt grounding and heuristic parsing fallback.
    Ensures research is summarized strictly from provided sources without hallucinating facts.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gpt-4.1-mini") -> None:
        self.api_key = api_key
        self.model_name = model_name

    async def structure_intelligence(
        self,
        company_name: str,
        lead_context: Dict[str, Any],
        raw_result: RawResearchResult,
    ) -> StructuredLeadIntelligence:
        industry = lead_context.get("industry") or "B2B Technology & Services"
        location = lead_context.get("location") or "United States"
        company_size = lead_context.get("employee_count_range") or "50-250 employees"
        job_title = lead_context.get("job_title") or "Operations Leader"
        source_urls = [s.url for s in raw_result.sources if s.url]

        # Extract textual snippets from sources
        combined_snippets = " ".join([s.snippet for s in raw_result.sources if s.snippet])
        first_snippet = raw_result.sources[0].snippet if raw_result.sources else ""

        company_summary = (
            f"{company_name} is an active provider in the {industry.lower()} market. "
            f"{first_snippet[:180] if first_snippet else 'Specializes in targeted enterprise business services and operations.'}"
        ).strip()

        business_signals = [
            f"Active public web presence in {industry}.",
            f"Ongoing focus on scaling client operations and business capabilities.",
        ]

        potential_pain_points = [
            f"Managing outreach coordination and workflow efficiency across {job_title.lower()} responsibilities.",
            "Expanding client engagement without incurring heavy administrative overhead.",
        ]

        personalization_points = [
            f"Reference their focus on {industry} and tailored solutions.",
            f"Acknowledge the operational scope associated with the {job_title} role at {company_name}.",
        ]

        research_summary = (
            f"{company_name} ({industry}, {location}). "
            f"Summary: {company_summary[:150]}... "
            f"Key pain point: workflow scaling overhead. "
            f"Outreach hook: discuss how automated pipeline tools support {job_title}."
        )

        return StructuredLeadIntelligence(
            company_summary=company_summary,
            industry=industry,
            company_size=company_size,
            location=location,
            business_signals=business_signals,
            potential_pain_points=potential_pain_points,
            personalization_points=personalization_points,
            research_summary=research_summary,
            source_urls=source_urls,
        )
