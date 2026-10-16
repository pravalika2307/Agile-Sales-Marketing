"""
Base abstractions and data contracts for Pre-Call Lead Intelligence.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.lead_research import StructuredLeadIntelligence


@dataclass
class RawSource:
    """Represents a single retrieved public web source."""
    title: str
    url: str
    snippet: str
    content: str = ""


@dataclass
class RawResearchResult:
    """Raw search and content fetch result before LLM structuring."""
    query: str
    company_name: str
    company_domain: Optional[str] = None
    sources: List[RawSource] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class WebResearchProvider(abc.ABC):
    """
    Abstract provider interface for targeted B2B web research.
    Prioritizes official company web pages and relevant public business sources.
    """

    @abc.abstractmethod
    async def search_and_fetch(
        self,
        company_name: str,
        company_domain: Optional[str] = None,
        industry: Optional[str] = None,
        max_sources: int = 4,
    ) -> RawResearchResult:
        """
        Execute targeted public search and fetch top relevant pages.
        """
        pass


class LLMStructuringProvider(abc.ABC):
    """
    Abstract provider for structuring retrieved raw research into clean SDR intelligence.
    """

    @abc.abstractmethod
    async def structure_intelligence(
        self,
        company_name: str,
        lead_context: Dict[str, Any],
        raw_result: RawResearchResult,
    ) -> StructuredLeadIntelligence:
        """
        Structures and summarizes raw web sources into the target Lead Intelligence schema.
        Must strictly avoid hallucinations and ground findings in retrieved sources.
        """
        pass
