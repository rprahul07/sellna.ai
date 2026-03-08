import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).resolve().parent))

from scraper import Scraper

async def test():
    print("Initializing Scraper...")
    s = Scraper(render_js=False) # Test static first, it should fallback to JS
    print("Scraping Calgary Zoo...")
    res = await s.scrape_urls(["https://www.calgaryzoo.com/events/penguin-walk/"])
    for r in res:
        print(f"URL: {r.url}")
        print(f"Status: {r.status}")
        print(f"Success: {r.success}")
        print(f"Error: {r.error}")
        print(f"HTML Length: {len(r.html)}")
    await s.close()

if __name__ == "__main__":
    asyncio.run(test())
