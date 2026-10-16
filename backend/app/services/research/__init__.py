"""Pre-call Lead Intelligence & Web Research package."""
from app.services.research.base import (
    LLMStructuringProvider,
    RawResearchResult,
    RawSource,
    WebResearchProvider,
)
from app.services.research.providers import (
    DefaultLLMStructuringProvider,
    HttpWebResearchProvider,
    MockLLMStructuringProvider,
    MockWebResearchProvider,
)
from app.services.research.service import (
    LeadNotFoundError,
    LeadResearchService,
)

__all__ = [
    "LLMStructuringProvider",
    "RawResearchResult",
    "RawSource",
    "WebResearchProvider",
    "DefaultLLMStructuringProvider",
    "HttpWebResearchProvider",
    "MockLLMStructuringProvider",
    "MockWebResearchProvider",
    "LeadNotFoundError",
    "LeadResearchService",
]
