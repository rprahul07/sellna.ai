from .base import SocialEngine
from playwright.async_api import Page
import re

class LinkedInEngine(SocialEngine):
    def identify(self, url: str) -> bool:
        return "linkedin.com" in url

    async def scrape(self, page: Page, url: str) -> dict:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # Public profiles often have a specific structure
        data = {
            "platform": "LinkedIn",
            "url": url,
            "profile_name": "",
            "headline": "",
            "location": "",
            "about": "",
            "experience": []
        }

        try:
            # Basic profile info
            name_el = await page.query_selector("h1.top-card-layout__title")
            data["profile_name"] = await name_el.inner_text() if name_el else ""
            
            headline_el = await page.query_selector("h2.top-card-layout__headline")
            data["headline"] = await headline_el.inner_text() if headline_el else ""
            
            loc_el = await page.query_selector("span.top-card__subline-item")
            data["location"] = await loc_el.inner_text() if loc_el else ""
            
            # About section
            about_sel = "section.summary p"
            about_el = await page.query_selector(about_sel)
            if about_el:
                data["about"] = await about_el.inner_text()

            # Experience list
            exp_items = await page.query_selector_all("li.experience-item")
            experience_list = []
            for item in exp_items:
                title_el = await item.query_selector("h3.experience-item__title")
                title = await title_el.inner_text() if title_el else ""
                
                company_el = await item.query_selector("h4.experience-item__subtitle")
                company = await company_el.inner_text() if company_el else ""
                
                if title:
                    experience_list.append({"title": title.strip(), "company": company.strip()})
            data["experience"] = experience_list

        except Exception as e:
            data["error"] = str(e)

        return data
