"""Scraping Service — bridges the existing scrapping_module into the Sales AI pipeline.

This service wraps the production-grade scraper from the root-level module
so that all Sales AI agents can use it without knowing the underlying implementation.

Key integration points:
  - scraper.Scraper          → async httpx + Playwright engine
  - extractor.extract()      → HTML → structured dict
  - scrapping_module.social  → SocialScraper for LinkedIn / Instagram

All three modules live at the project root alongside this app/ package,
so they are directly importable — no sys.path manipulation needed.
"""

from __future__ import annotations

from typing import Any

from scraper import Scraper, ScrapeResult
from extractor import extract
from scrapping_module.social import SocialScraper

from app.core.logging import get_logger
from app.config import get_settings

logger = get_logger(__name__)
_settings = get_settings()


class ScrapingService:
    """High-level async scraping service used by Web Intelligence Agent."""

    def __init__(self, proxy: str | None = None, render_js: bool = False) -> None:
        self.proxy = proxy
        self.render_js = render_js

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape_websites(
        self, urls: list[str]
    ) -> list[dict[str, Any]]:
        """Scrape a list of web URLs and extract structured content.

        Returns a list of extraction dicts (one per URL).
        """
        scraper = Scraper(proxy=self.proxy, render_js=self.render_js)
        raw: list[ScrapeResult] = await scraper.scrape_urls(urls)

        results: list[dict[str, Any]] = []
        for r in raw:
            if r.success and r.html:
                extracted = extract(r.html, r.url)
                extracted["scrape_success"] = True
                extracted["elapsed_ms"] = r.elapsed_ms
                extracted["rendered"] = r.rendered
                results.append(extracted)
                logger.info(
                    "scraping_service.scraped",
                    url=r.url,
                    elapsed_ms=r.elapsed_ms,
                    rendered=r.rendered,
                )
            else:
                results.append({
                    "url": r.url,
                    "scrape_success": False,
                    "error": r.error,
                    "elapsed_ms": r.elapsed_ms,
                })
                logger.warning("scraping_service.failed", url=r.url, reason=r.error)

        return results

    async def scrape_social(
        self, urls: list[str]
    ) -> list[dict[str, Any]]:
        """Scrape social media profiles (LinkedIn, Instagram).

        Delegates to the existing multi-strategy SocialScraper.
        """
        social_scraper = SocialScraper(proxy=self.proxy)
        results = await social_scraper.scrape_batch(urls)
        for r, url in zip(results, urls):
            r.setdefault("url", url)
        return results

    async def scrape_competitor_homepage(self, website: str) -> dict[str, Any]:
        """Convenience method — scrape a single competitor website."""
        results = await self.scrape_websites([website])
        return results[0] if results else {"url": website, "scrape_success": False, "error": "no result"}
