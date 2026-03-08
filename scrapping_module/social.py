"""Social media scraper — multi-strategy approach with LinkedIn bypass.

Strategy order for LinkedIn:
  1. httpx with realistic browser headers + Referer trick (fast, no JS)
  2. Google cache fetch via httpx (gets real public data)
  3. Playwright sync in thread pool (fallback, Windows-safe)

Instagram uses Playwright sync in thread pool.
"""

import asyncio
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bs4 import BeautifulSoup

import httpx

sys.path.append(str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
import config

_executor = ThreadPoolExecutor(max_workers=2)

# ------------------------------------------------------------------
# LinkedIn Bypass — httpx strategies (no browser needed)
# ------------------------------------------------------------------

def _scrape_linkedin_via_google(url: str, proxy: str | None) -> dict:
    """
    Scrape LinkedIn profile data via Google Search SERP.
    Google indexes LinkedIn profiles fully and returns real data
    in search snippets without requiring LinkedIn authentication.
    """
    # Extract username from URL
    username = url.rstrip("/").split("/in/")[-1].rstrip("/")

    search_query = f'linkedin.com/in/{username}'
    search_url = f"https://www.google.com/search?q={search_query}&hl=en&num=3"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=15,
            proxies=proxy,
        ) as client:
            resp = client.get(search_url)
            if resp.status_code != 200:
                return {}

            soup = BeautifulSoup(resp.text, "html.parser")

            profile_name = ""
            headline = ""
            about = ""
            avatar = ""

            # Strategy A: Google Knowledge Panel (rich card)
            # Find all search result divs
            for result in soup.select("div.g, div[data-hveid]"):
                # Look for LinkedIn link
                link = result.find("a", href=re.compile(r"linkedin\.com/in/", re.I))
                if not link:
                    continue

                # Title from <h3>
                h3 = result.find("h3")
                if h3:
                    raw_title = h3.get_text(strip=True)
                    # LinkedIn titles: "Elon Musk - CEO · Tesla | LinkedIn"
                    raw_title = raw_title.replace("| LinkedIn", "").replace("LinkedIn", "").strip(" |·")
                    if " - " in raw_title:
                        parts = raw_title.split(" - ", 1)
                        profile_name = parts[0].strip()
                        headline = parts[1].strip(" ·|")
                    elif " · " in raw_title:
                        parts = raw_title.split(" · ", 1)
                        profile_name = parts[0].strip()
                        headline = parts[1].strip()
                    else:
                        profile_name = raw_title

                # Snippet text (description)
                snippet_el = result.select_one("div.VwiC3b, span.aCOpRe, div[style*='webkit-line-clamp']")
                if snippet_el:
                    about = snippet_el.get_text(strip=True)

                if profile_name and profile_name.lower() not in ("sign up", "join linkedin", "linkedin"):
                    break

            # Strategy B: og:title from Google's cached version
            if not profile_name:
                cache_headers = {**headers, "Referer": "https://www.google.com/"}
                cache_url = f"https://webcache.googleusercontent.com/search?q=cache:linkedin.com/in/{username}&hl=en"
                try:
                    cache_resp = client.get(cache_url, headers=cache_headers)
                    if cache_resp.status_code == 200:
                        csoup = BeautifulSoup(cache_resp.text, "html.parser")
                        og = csoup.find("meta", property="og:title")
                        if og and og.get("content"):
                            raw = og["content"].replace("| LinkedIn", "").strip()
                            if " - " in raw:
                                parts = raw.split(" - ", 1)
                                profile_name = parts[0].strip()
                                headline = parts[1].strip()
                            else:
                                profile_name = raw
                        desc = csoup.find("meta", property="og:description")
                        if desc:
                            about = (desc.get("content") or "").strip()
                        img = csoup.find("meta", property="og:image")
                        if img:
                            v = img.get("content", "")
                            avatar = v if "favicon" not in v else ""
                except Exception:
                    pass

            if not profile_name or profile_name.lower() in ("sign up", "join linkedin", "linkedin", ""):
                return {}

            return {
                "platform": "LinkedIn",
                "url": url,
                "profile_name": profile_name,
                "headline": headline,
                "location": "",
                "about": about,
                "avatar": avatar,
                "experience": [],
                "source": "Google SERP",
            }

    except Exception as e:
        return {"error": str(e), "url": url}

    return {}


# ------------------------------------------------------------------
# Instagram scraper — multi-strategy
# ------------------------------------------------------------------

_IG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.instagram.com/",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def _parse_ig_user_data(user: dict, url: str, extra_posts: list | None = None) -> dict:
    """Extract structured data from Instagram API user object.
    Handles both the old edge-based format and the newer flat format.
    """
    import datetime

    username = user.get("username", "")
    full_name = user.get("full_name", "")
    bio = user.get("biography", "")
    avatar = user.get("profile_pic_url_hd", "") or user.get("profile_pic_url", "")
    is_verified = user.get("is_verified", False)
    is_private = user.get("is_private", False)
    external_url = user.get("external_url", "")

    # --- Stats: support both old (edge_followed_by.count) and new (follower_count) ---
    followers = (
        user.get("follower_count")
        or user.get("edge_followed_by", {}).get("count", 0)
    )
    following = (
        user.get("following_count")
        or user.get("edge_follow", {}).get("count", 0)
    )
    posts_count = (
        user.get("media_count")
        or user.get("edge_owner_to_timeline_media", {}).get("count", 0)
    )

    # --- Posts: old edge format ---
    posts = []
    edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])

    # New format: user.timeline_feed_items or user.edge_felix_video_timeline
    if not edges:
        edges = user.get("edge_felix_video_timeline", {}).get("edges", [])

    # extra_posts injected from a separate GQL timeline response
    if not edges and extra_posts:
        edges = extra_posts

    for edge in edges[:10]:
        node = edge.get("node", {}) if isinstance(edge, dict) and "node" in edge else edge
        if not node:
            continue

        # Caption
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else node.get("caption", "")
        if isinstance(caption, dict):
            caption = caption.get("text", "")
        caption = caption or ""

        # Likes & Comments — try both old and new fields
        likes = (
            node.get("like_count")
            or node.get("edge_liked_by", {}).get("count")
            or node.get("edge_media_preview_like", {}).get("count", 0)
        )
        comments = (
            node.get("comment_count")
            or node.get("edge_media_to_comment", {}).get("count", 0)
        )

        # Media URL
        media_url = node.get("display_url", "") or node.get("image_versions2", {}).get("candidates", [{}])[0].get("url", "")
        thumbnail = node.get("thumbnail_src", "") or media_url

        # Timestamp
        ts = node.get("taken_at_timestamp") or node.get("taken_at", 0)
        dt = datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M") if ts else ""

        # Post type
        typename = node.get("__typename", "") or node.get("media_type", "")
        type_map = {"GraphImage": "Photo", "GraphVideo": "Video", "GraphSidecar": "Carousel", 1: "Photo", 2: "Video", 8: "Carousel"}
        post_type = type_map.get(typename, "Photo")

        shortcode = node.get("shortcode", "") or node.get("code", "")

        posts.append({
            "shortcode": shortcode,
            "url": f"https://www.instagram.com/p/{shortcode}/" if shortcode else "",
            "type": post_type,
            "caption": caption[:300] + ("..." if len(caption) > 300 else ""),
            "likes": likes,
            "comments": comments,
            "media_url": thumbnail,
            "posted_at": dt,
        })

    return {
        "platform": "Instagram",
        "url": url,
        "username": username,
        "full_name": full_name,
        "bio": bio,
        "avatar": avatar,
        "followers": followers,
        "following": following,
        "posts_count": posts_count,
        "is_verified": is_verified,
        "is_private": is_private,
        "external_url": external_url,
        "latest_posts": posts,
        "type": "Profile",
    }


def _scrape_instagram_api(url: str, proxy: str | None) -> dict:
    """Strategy 1: Instagram's unofficial web_profile_info API endpoint."""
    username = url.rstrip("/").split("/")[-1].lstrip("@")
    # Remove query params if any
    username = username.split("?")[0]
    
    api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    
    # First get a session cookie by visiting Instagram
    try:
        with httpx.Client(
            headers={
                "User-Agent": _IG_HEADERS["User-Agent"],
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            timeout=15,
            proxies=proxy,
        ) as client:
            # Grab cookies + csrf token
            home_resp = client.get("https://www.instagram.com/")
            csrf = ""
            for cookie in client.cookies.jar:
                if cookie.name == "csrftoken":
                    csrf = cookie.value
                    break

            api_headers = {
                **_IG_HEADERS,
                "X-CSRFToken": csrf,
                "Cookie": "; ".join([f"{c.name}={c.value}" for c in client.cookies.jar]),
            }

            resp = client.get(api_url, headers=api_headers)
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("data", {}).get("user", {})
                if user:
                    return _parse_ig_user_data(user, url)
    except Exception:
        pass
    return {}


def _scrape_instagram_json_embed(url: str, proxy: str | None) -> dict:
    """Strategy 2: Extract embedded JSON from Instagram page source."""
    username = url.rstrip("/").split("/")[-1].lstrip("@").split("?")[0]
    
    try:
        with httpx.Client(
            headers={
                "User-Agent": _IG_HEADERS["User-Agent"],
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/",
            },
            follow_redirects=True,
            timeout=15,
            proxies=proxy,
        ) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return {}

            html = resp.text
            # Look for window.__additionalDataLoaded or similar JSON blobs
            patterns = [
                r'window\.__additionalDataLoaded\s*\(\s*["\']profile["\'],\s*(\{.+?\})\s*\)',
                r'"ProfilePage"\s*:\s*\[(\{.+?\})\]',
                r'window\._sharedData\s*=\s*(\{.+?\})\s*;',
            ]
            for pat in patterns:
                m = re.search(pat, html, re.DOTALL)
                if m:
                    try:
                        import json
                        raw = json.loads(m.group(1))
                        # Walk the nested structure
                        user = (
                            raw.get("graphql", {}).get("user")
                            or raw.get("entry_data", {}).get("ProfilePage", [{}])[0].get("graphql", {}).get("user")
                            or raw.get("user")
                            or {}
                        )
                        if user:
                            return _parse_ig_user_data(user, url)
                    except Exception:
                        continue

            # Fallback: og meta tags only
            soup = BeautifulSoup(html, "html.parser")

            def get_meta(prop: str, attr: str = "property") -> str:
                tag = soup.find("meta", {attr: prop})
                return (tag.get("content") or "").strip() if tag else ""

            og_title = get_meta("og:title")
            og_desc = get_meta("og:description")
            og_image = get_meta("og:image")

            followers = following = posts_count = ""
            if og_desc:
                nums = re.findall(r"([\d,\.]+[KMkm]?)\s+(\w+)", og_desc)
                for val, label in nums:
                    lbl = label.lower()
                    if "follower" in lbl: followers = val
                    elif "following" in lbl: following = val
                    elif "post" in lbl: posts_count = val

            display_name = ""
            if og_title:
                # "Display Name (@username) • Instagram"
                m2 = re.match(r"^(.+?)\s*\(", og_title)
                display_name = m2.group(1).strip() if m2 else og_title.replace("• Instagram", "").strip()

            if username:
                return {
                    "platform": "Instagram",
                    "url": url,
                    "username": username,
                    "full_name": display_name,
                    "bio": og_desc[:200] if og_desc else "",
                    "avatar": og_image,
                    "followers": followers,
                    "following": following,
                    "posts_count": posts_count,
                    "is_verified": False,
                    "is_private": False,
                    "external_url": "",
                    "latest_posts": [],
                    "type": "Profile",
                    "source": "meta-tags",
                }
    except Exception:
        pass
    return {}


def _scrape_instagram_browser(url: str, proxy: str | None) -> dict:
    """Strategy 3: Playwright + intercept ALL GQL responses (profile + timeline)."""
    try:
        captured_user: dict = {}
        captured_posts: list = []

        with sync_playwright() as p:
            launch_options: dict = {
                "headless": config.BROWSER_HEADLESS,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if proxy:
                launch_options["proxy"] = {"server": proxy}

            browser = p.chromium.launch(**launch_options)
            context = browser.new_context(
                user_agent=_IG_HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)

            page = context.new_page()

            def handle_response(response):
                nonlocal captured_user, captured_posts
                url_r = response.url
                try:
                    import json as _json
                    # Profile data endpoints
                    if "web_profile_info" in url_r:
                        body = response.json()
                        user = (
                            body.get("data", {}).get("user")
                            or body.get("graphql", {}).get("user")
                            or {}
                        )
                        if user and user.get("username") and not captured_user:
                            captured_user = user

                    # GQL timeline / media endpoints
                    elif "graphql/query" in url_r or "api/v1/feed/user" in url_r:
                        body = response.json()
                        # Old GQL format
                        edges = (
                            body.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
                            or body.get("graphql", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
                        )
                        if edges:
                            captured_posts.extend(edges)
                        # New format: items array
                        items = body.get("items", [])
                        if items:
                            captured_posts.extend([{"node": item} for item in items])
                except Exception:
                    pass

            page.on("response", handle_response)
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Scroll to trigger lazy-load of posts
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(2000)

            browser.close()

        if captured_user:
            return _parse_ig_user_data(captured_user, url, extra_posts=captured_posts or None)

        return {}

    except Exception as e:
        return {"error": str(e), "url": url}


def _scrape_instagram_sync(url: str, proxy: str | None) -> dict:
    """Try Instagram strategies in order."""
    # Strategy 1: Unofficial API
    result = _scrape_instagram_api(url, proxy)
    if result and result.get("username"):
        result["source"] = "Instagram API"
        return result

    # Strategy 2: JSON from page source
    result = _scrape_instagram_json_embed(url, proxy)
    if result and result.get("username"):
        if "source" not in result:
            result["source"] = "Page Source"
        return result

    # Strategy 3: Browser + network intercept
    result = _scrape_instagram_browser(url, proxy)
    if result and result.get("username"):
        result["source"] = "Browser Intercept"
        return result

    return {"error": "Instagram profile could not be scraped. Profile may be private.", "url": url}


# ------------------------------------------------------------------
# Main dispatch
# ------------------------------------------------------------------

def _scrape_sync(url: str, proxy: str | None) -> dict:
    """Route to the correct scraper based on URL."""
    if "linkedin.com" in url:
        result = _scrape_linkedin_via_google(url, proxy)
        if result and "error" not in result:
            return result
        # If Google SERP failed, return meaningful error
        return {
            "error": "LinkedIn requires authentication or was rate-limited by Google. Try again or use a proxy.",
            "url": url,
            "platform": "LinkedIn",
        }

    elif "instagram.com" in url:
        return _scrape_instagram_sync(url, proxy)

    return {"error": "Unsupported platform or URL", "url": url}


class SocialScraper:
    def __init__(self, proxy: str | None = None):
        self.proxy = proxy

    async def scrape_batch(self, urls: list[str]) -> list[dict]:
        """Run all scrapes concurrently using thread pool (Windows-safe)."""
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(_executor, _scrape_sync, url, self.proxy)
            for url in urls
        ]
        return list(await asyncio.gather(*tasks))
