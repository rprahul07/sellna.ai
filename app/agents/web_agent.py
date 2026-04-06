"""Web Intelligence Agent.

Scrapes competitor websites using the existing scrapping_module and
extracts features, pricing, marketing copy, and value propositions.
"""

from __future__ import annotations

import asyncio
import time

from app.core.logging import get_logger
from app.schemas.competitor import CompetitorDiscovered, CompetitorWebData
from app.services.scraping_service import ScrapingService

logger = get_logger(__name__)


class WebAgent:
    """Scrapes competitor websites and structures the raw extracted data."""

    def __init__(self, proxy: str | None = None, render_js: bool = False) -> None:
        self._scraper = ScrapingService(proxy=proxy, render_js=render_js)

    async def run(
        self, competitors: list[CompetitorDiscovered]
    ) -> list[CompetitorWebData]:
        t0 = time.perf_counter()
        logger.info(
            "web_agent.start",
            module_name="WebAgent",
            input_summary=f"competitors={len(competitors)}",
        )

        tasks = [self._scrape_one(comp) for comp in competitors]
        results: list[CompetitorWebData] = await asyncio.gather(*tasks, return_exceptions=False)

        elapsed = time.perf_counter() - t0
        successful = sum(1 for r in results if r.scrape_success)
        logger.info(
            "web_agent.complete",
            module_name="WebAgent",
            execution_time=round(elapsed, 3),
            output_summary=f"scraped={successful}/{len(competitors)} sites",
        )
        return results

    async def _scrape_one(self, comp: CompetitorDiscovered) -> CompetitorWebData:
        website = comp.website.strip()
        if not website:
            return CompetitorWebData(
                competitor_id=comp.competitor_id,
                website=website,
                scrape_success=False,
                error="No website URL",
            )

        raw = await self._scraper.scrape_competitor_homepage(website)

        if not raw.get("scrape_success") and "404" in raw.get("error", ""):
            from urllib.parse import urlparse
            parsed = urlparse(website)
            if parsed.path and parsed.path != "/":
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                logger.info(
                    "web_agent.fallback", original=website, fallback=base_url
                )
                raw = await self._scraper.scrape_competitor_homepage(base_url)
                website = base_url

        if not raw.get("scrape_success"):
            return CompetitorWebData(
                competitor_id=comp.competitor_id,
                website=website,
                scrape_success=False,
                error=raw.get("error", "Unknown scrape failure"),
            )

        # Map extracted HTML data to structured fields
        headings: dict[str, list[str]] = raw.get("headings", {})
        paragraphs: list[str] = raw.get("paragraphs", [])

        # Heuristic feature extraction: pick headings & paragraphs referencing feature keywords
        feature_kw = {"feature", "capability", "tool", "integration", "function", "module", "built"}
        features = [
            h
            for level in ("h2", "h3", "h4")
            for h in headings.get(level, [])
            if any(kw in h.lower() for kw in feature_kw)
        ][:15]

        # Pricing: look for paragraphs containing price signals
        price_kw = {"pricing", "price", "plan", "per month", "per user", "free", "starter", "enterprise"}
        pricing_tiers = [
            p[:200] for p in paragraphs if any(kw in p.lower() for kw in price_kw)
        ][:5]

        # Marketing copy: title + meta description + first h1
        title = raw.get("title", "")
        meta_desc = raw.get("meta_description", "")
        h1s = headings.get("h1", [])
        marketing_copy = f"{title}. {meta_desc}. {' '.join(h1s[:2])}"

        # Value proposition: first substantial paragraph
        value_prop = next(
            (p for p in paragraphs if len(p) > 60), meta_desc or title
        )

        return CompetitorWebData(
            competitor_id=comp.competitor_id,
            website=website,
            features=features,
            pricing_tiers=pricing_tiers,
            marketing_copy=marketing_copy[:1000],
            value_proposition=value_prop[:500],
            target_audience=", ".join(headings.get("h2", [])[:3]),
            raw_headings=headings,
            raw_paragraphs=paragraphs[:30],
            scrape_success=True,
        )
