from __future__ import annotations
from abc import ABC, abstractmethod
from playwright.async_api import Page
import asyncio

import random

class SocialEngine(ABC):
    @abstractmethod
    def identify(self, url: str) -> bool:
        """Check if this engine can handle the given URL."""
        return False

    @abstractmethod
    async def scrape(self, page: Page, url: str) -> dict:
        """Perform platform-specific scraping."""
        return {}

    async def auto_scroll(self, page: Page, max_scrolls: int = 5):
        """Scroll down to trigger lazy loading."""
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5 + (0.5 * random.random()))
