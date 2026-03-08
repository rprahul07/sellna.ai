from playwright.async_api import Page
from playwright_stealth import Stealth

async def apply_stealth(page: Page):
    """Apply stealth plugin to the page to minimize detection."""
    await Stealth().apply_stealth_async(page)
    
    # Additional manual stealth overrides if needed
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
