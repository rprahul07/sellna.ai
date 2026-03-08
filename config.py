"""Root-level scraper configuration.

Used by: scraper.py, scrapping_module/social.py, scrapping_module/stealth.py

Values can be overridden via environment variables or a .env file
(loaded by python-dotenv if available).  The app/config/settings.py
Pydantic Settings class is the canonical config for the FastAPI layer;
these constants are read by the low-level scraping engine directly.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # dotenv is optional


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Concurrency & Timing
# ---------------------------------------------------------------------------
MAX_CONCURRENT_REQUESTS: int = _int("MAX_CONCURRENT_REQUESTS", 5)
REQUEST_TIMEOUT: int = _int("REQUEST_TIMEOUT", 30)   # seconds
RETRY_TIMES: int = _int("RETRY_TIMES", 3)
RETRY_HTTP_CODES: list[int] = [500, 502, 503, 504, 408, 429]
MIN_DELAY: float = _float("MIN_DELAY", 1.0)          # seconds between same-domain requests
MAX_DELAY: float = _float("MAX_DELAY", 5.0)
AUTOTHROTTLE_TARGET_CONCURRENCY: float = _float("AUTOTHROTTLE_TARGET_CONCURRENCY", 2.0)

# ---------------------------------------------------------------------------
# JS Rendering (Playwright)
# ---------------------------------------------------------------------------
JS_RENDER_TIMEOUT: int = _int("JS_RENDER_TIMEOUT", 30_000)   # ms
BROWSER_HEADLESS: bool = _bool("BROWSER_HEADLESS", True)
BROWSER_TYPE: str = os.getenv("BROWSER_TYPE", "chromium")    # chromium | firefox | webkit

# ---------------------------------------------------------------------------
# User-Agent Pool — realistic browser strings used for HTTP rotation
# ---------------------------------------------------------------------------
USER_AGENTS: list[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# ---------------------------------------------------------------------------
# Default browser-like request headers
# ---------------------------------------------------------------------------
DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
