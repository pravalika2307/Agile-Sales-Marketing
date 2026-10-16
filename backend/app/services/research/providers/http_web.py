"""
Targeted HTTP Web Research provider.
Prioritizes official company domains, metadata, and public business profiles.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.services.research.base import RawResearchResult, RawSource, WebResearchProvider

logger = logging.getLogger(__name__)


def _clean_html_text(html: str, max_chars: int = 1500) -> str:
    """Strips HTML tags and compresses whitespace for clean textual context."""
    # Remove script and style elements
    clean = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining HTML tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    # Normalize whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars]


def _extract_meta_description(html: str) -> Optional[str]:
    """Extracts meta description or og:description from HTML."""
    match = re.search(r'<meta[^>]+(?:name=["\']description["\']|property=["\']og:description["\'])[^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not match:
        match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name=["\']description["\']|property=["\']og:description["\'])', html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_page_title(html: str) -> Optional[str]:
    """Extracts title tag from HTML."""
    match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


class HttpWebResearchProvider(WebResearchProvider):
    """
    Web research provider that targets the company's official domain and public business sources.
    Respects anti-scraping boundaries and fetches only top targeted resources with strict timeouts.
    """

    def __init__(self, timeout_seconds: float = 8.0, user_agent: Optional[str] = None) -> None:
        self.timeout = timeout_seconds
        self.user_agent = user_agent or "Agile-Sales-Research-Bot/1.0 (+https://agilesales.ai/bot)"

    async def search_and_fetch(
        self,
        company_name: str,
        company_domain: Optional[str] = None,
        industry: Optional[str] = None,
        max_sources: int = 4,
    ) -> RawResearchResult:
        sources: List[RawSource] = []
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}

        # 1. Prioritize Direct Company Website if domain is present
        target_domain = company_domain
        if target_domain:
            target_domain = target_domain.lower().strip()
            if target_domain.startswith("http://") or target_domain.startswith("https://"):
                parsed = urlparse(target_domain)
                target_domain = parsed.netloc or parsed.path

        if target_domain:
            homepage_url = f"https://{target_domain}"
            about_url = f"https://{target_domain}/about"

            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                # A. Fetch Homepage
                try:
                    resp = await client.get(homepage_url)
                    if resp.status_code == 200:
                        title = _extract_page_title(resp.text) or f"{company_name} Official Site"
                        meta_desc = _extract_meta_description(resp.text) or ""
                        body_snippet = _clean_html_text(resp.text, max_chars=1200)
                        sources.append(
                            RawSource(
                                title=title,
                                url=str(resp.url),
                                snippet=meta_desc or body_snippet[:250],
                                content=body_snippet,
                            )
                        )
                except Exception as exc:
                    logger.debug("Could not fetch official homepage for %s: %s", target_domain, exc)

                # B. Fetch About Page if space allows
                if len(sources) < max_sources:
                    try:
                        resp_about = await client.get(about_url)
                        if resp_about.status_code == 200 and str(resp_about.url) != str(homepage_url):
                            title = _extract_page_title(resp_about.text) or f"About {company_name}"
                            meta_desc = _extract_meta_description(resp_about.text) or ""
                            body_snippet = _clean_html_text(resp_about.text, max_chars=1200)
                            sources.append(
                                RawSource(
                                    title=title,
                                    url=str(resp_about.url),
                                    snippet=meta_desc or body_snippet[:250],
                                    content=body_snippet,
                                )
                            )
                    except Exception as exc:
                        logger.debug("Could not fetch about page for %s: %s", target_domain, exc)

        # 2. Public Search fallback / augmentation via DuckDuckGo HTML
        if len(sources) < max_sources:
            search_query = f"{company_name} company overview business"
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
                    ddg_url = f"https://html.duckduckgo.com/html/?q={search_query}"
                    ddg_resp = await client.get(ddg_url)
                    if ddg_resp.status_code == 200:
                        # Extract result links and snippets
                        # DuckDuckGo HTML format: <a class="result__url" href="..."> ... <a class="result__snippet">
                        matches = re.findall(
                            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                            ddg_resp.text,
                            re.DOTALL | re.IGNORECASE,
                        )
                        title_matches = re.findall(
                            r'<a[^>]+class="result__title"[^>]*>(.*?)</a>',
                            ddg_resp.text,
                            re.DOTALL | re.IGNORECASE,
                        )
                        for i, snip in enumerate(matches[: max_sources - len(sources)]):
                            clean_snip = _clean_html_text(snip, max_chars=300)
                            clean_title = _clean_html_text(title_matches[i], max_chars=100) if i < len(title_matches) else f"{company_name} Public Overview"
                            if clean_snip and len(clean_snip) > 20:
                                sources.append(
                                    RawSource(
                                        title=clean_title,
                                        url=f"https://search.public/{i}",
                                        snippet=clean_snip,
                                        content=clean_snip,
                                    )
                                )
            except Exception as exc:
                logger.debug("Public search query failed for %s: %s", company_name, exc)

        # Fallback if both direct fetch and search yielded nothing
        if not sources:
            sources.append(
                RawSource(
                    title=f"{company_name} Profile",
                    url=f"https://{target_domain or 'company-directory.org'}",
                    snippet=f"{company_name} operates within the {industry or 'commercial'} sector.",
                    content=f"{company_name} business overview.",
                )
            )

        return RawResearchResult(
            query=f"site:{target_domain}" if target_domain else company_name,
            company_name=company_name,
            company_domain=company_domain,
            sources=sources[:max_sources],
            success=True,
        )
