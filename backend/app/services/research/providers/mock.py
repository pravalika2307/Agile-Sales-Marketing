"""
Mock Web Research and LLM Structuring providers for deterministic testing and local development.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.lead_research import StructuredLeadIntelligence
from app.services.research.base import (
    LLMStructuringProvider,
    RawResearchResult,
    RawSource,
    WebResearchProvider,
)


class MockWebResearchProvider(WebResearchProvider):
    """
    Mock researcher returning realistic, targeted B2B company web sources.
    Prioritizes official domain website and public business listings.
    """

    def __init__(self, should_fail: bool = False, custom_sources: Optional[List[RawSource]] = None) -> None:
        self.should_fail = should_fail
        self.custom_sources = custom_sources

    async def search_and_fetch(
        self,
        company_name: str,
        company_domain: Optional[str] = None,
        industry: Optional[str] = None,
        max_sources: int = 4,
    ) -> RawResearchResult:
        if self.should_fail:
            return RawResearchResult(
                query=f"{company_name} official overview",
                company_name=company_name,
                company_domain=company_domain,
                sources=[],
                success=False,
                error="Mock research provider connection failure.",
            )

        if self.custom_sources:
            return RawResearchResult(
                query=f"{company_name} business profile",
                company_name=company_name,
                company_domain=company_domain,
                sources=self.custom_sources[:max_sources],
                success=True,
            )

        domain = company_domain or f"{company_name.lower().replace(' ', '')}.com"
        sources = [
            RawSource(
                title=f"{company_name} - Official Homepage & Solutions",
                url=f"https://{domain}",
                snippet=f"{company_name} provides specialized {industry or 'B2B enterprise'} solutions and technology services for scaling organizations.",
                content=f"{company_name} is an established provider operating in the {industry or 'technology'} space. Focus areas include operational streamlining, automated customer workflows, and digital infrastructure.",
            ),
            RawSource(
                title=f"About {company_name} | Leadership & Company Overview",
                url=f"https://{domain}/about",
                snippet=f"Founded to modernize workflows, {company_name} helps clients reduce administrative overhead and accelerate delivery.",
                content=f"About {company_name}: Headquartered with regional teams. Emphasizes modern operational tooling and fast turnaround times.",
            ),
            RawSource(
                title=f"{company_name} Business Profile & Recent Expansion",
                url=f"https://public-business-index.org/co/{domain}",
                snippet=f"Recent growth announcements and service line expansions at {company_name}.",
                content=f"Recent announcements show {company_name} expanding client operations and actively adopting software automation.",
            ),
        ]

        return RawResearchResult(
            query=f"site:{domain} OR \"{company_name}\"",
            company_name=company_name,
            company_domain=company_domain,
            sources=sources[:max_sources],
            success=True,
        )


class MockLLMStructuringProvider(LLMStructuringProvider):
    """
    Mock LLM structuring provider producing grounded, non-hallucinatory intelligence.
    """

    def __init__(self, should_fail: bool = False, custom_intelligence: Optional[StructuredLeadIntelligence] = None) -> None:
        self.should_fail = should_fail
        self.custom_intelligence = custom_intelligence

    async def structure_intelligence(
        self,
        company_name: str,
        lead_context: Dict[str, Any],
        raw_result: RawResearchResult,
    ) -> StructuredLeadIntelligence:
        if self.should_fail or not raw_result.success:
            raise ValueError(raw_result.error or "LLM structuring failed due to provider error.")

        if self.custom_intelligence:
            return self.custom_intelligence

        # Derive attributes from raw sources and lead context
        industry = lead_context.get("industry") or "B2B Services & Technology"
        location = lead_context.get("location") or "United States"
        company_size = lead_context.get("employee_count_range") or "50-200 employees"
        job_title = lead_context.get("job_title") or "Operations"
        source_urls = [s.url for s in raw_result.sources]

        summary = (
            f"{company_name} is a growing {industry.lower()} provider focused on operational efficiency "
            f"and modern client delivery."
        )

        signals = [
            f"Active investments in operational modernizations within {industry}.",
            "Recent service line expansion indicating increased operational volume.",
        ]

        pain_points = [
            f"Manual coordination bottlenecks between {job_title.lower()} and customer-facing teams.",
            "Scaling outreach and client communication workflows without increasing headcount.",
        ]

        personalization = [
            f"Mention their focus on streamlining workflows in {industry}.",
            f"Reference relevance to the {job_title} role at {company_name}.",
        ]

        research_summary = (
            f"{company_name} operates in {industry} ({company_size}). "
            f"Key challenge is scaling client workflows efficiently. "
            f"SDR hook: explore how automated outreach frees up operational bandwidth for {job_title}."
        )

        return StructuredLeadIntelligence(
            company_summary=summary,
            industry=industry,
            company_size=company_size,
            location=location,
            business_signals=signals,
            potential_pain_points=pain_points,
            personalization_points=personalization,
            research_summary=research_summary,
            source_urls=source_urls,
        )
