from .base import SocialEngine
from playwright.async_api import Page
import json

class InstagramEngine(SocialEngine):
    def identify(self, url: str) -> bool:
        return "instagram.com" in url

    async def scrape(self, page: Page, url: str) -> dict:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        data = {
            "platform": "Instagram",
            "url": url,
            "username": "",
            "bio": "",
            "followers": 0,
            "following": 0,
            "posts_count": 0,
            "posts": []
        }

        try:
            # Instagram often embeds data in JSON-LD or shared state
            # Try to find the username first
            if "/p/" in url:
                # Post page
                data["type"] = "post"
                data["caption"] = await page.inner_text("h1") if await page.query_selector("h1") else ""
            else:
                # Profile page
                data["type"] = "profile"
                h2 = await page.query_selector("h2")
                if h2:
                    data["username"] = await h2.inner_text()
                
                # Bio
                bio_sel = "section main header section div span"
                bios = await page.query_selector_all(bio_sel)
                if bios:
                    data["bio"] = await bios[-1].inner_text()

                # Stats (Followers, Following, Posts)
                stats = await page.query_selector_all("ul li span")
                if len(stats) >= 3:
                    try:
                        data["posts_count"] = await stats[0].get_attribute("title") or await stats[0].inner_text()
                        data["followers"] = await stats[1].get_attribute("title") or await stats[1].inner_text()
                        data["following"] = await stats[2].inner_text()
                    except (IndexError, AttributeError):
                        pass

        except Exception as e:
            data["error"] = str(e)

        return data
