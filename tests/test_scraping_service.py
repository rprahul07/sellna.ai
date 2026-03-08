"""Tests for the Scraping Service (integration with existing scrapping_module)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scraping_service import ScrapingService


@pytest.mark.asyncio
async def test_scrape_websites_success():
    """ScrapingService should return structured data on successful scrape."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.html = "<html><head><title>Acme Corp</title></head><body><p>We build AI sales tools.</p></body></html>"
    mock_result.url = "https://acme.example.com"
    mock_result.elapsed_ms = 120.0
    mock_result.rendered = False

    with patch("app.services.scraping_service.Scraper") as MockScraper:
        instance = MockScraper.return_value
        instance.scrape_urls = AsyncMock(return_value=[mock_result])

        svc = ScrapingService()
        results = await svc.scrape_websites(["https://acme.example.com"])

    assert len(results) == 1
    assert results[0]["scrape_success"] is True
    assert results[0]["url"] == "https://acme.example.com"
    assert "title" in results[0]


@pytest.mark.asyncio
async def test_scrape_websites_failure():
    """ScrapingService should handle scrape failures gracefully."""
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.html = ""
    mock_result.url = "https://blocked.example.com"
    mock_result.error = "HTTP 403"
    mock_result.elapsed_ms = 5000.0

    with patch("app.services.scraping_service.Scraper") as MockScraper:
        instance = MockScraper.return_value
        instance.scrape_urls = AsyncMock(return_value=[mock_result])

        svc = ScrapingService()
        results = await svc.scrape_websites(["https://blocked.example.com"])

    assert len(results) == 1
    assert results[0]["scrape_success"] is False
    assert "error" in results[0]


@pytest.mark.asyncio
async def test_scrape_competitor_homepage():
    """Convenience method should return single result dict."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.html = "<html><title>Competitor</title><body><p>Features here.</p></body></html>"
    mock_result.url = "https://competitor.example.com"
    mock_result.elapsed_ms = 200.0
    mock_result.rendered = False

    with patch("app.services.scraping_service.Scraper") as MockScraper:
        instance = MockScraper.return_value
        instance.scrape_urls = AsyncMock(return_value=[mock_result])

        svc = ScrapingService()
        result = await svc.scrape_competitor_homepage("https://competitor.example.com")

    assert isinstance(result, dict)
    assert result.get("scrape_success") is True
