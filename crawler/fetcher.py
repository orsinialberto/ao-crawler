"""HTTP fetching via httpx or Playwright."""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a fetch operation."""
    url: str
    status_code: int
    html: str
    error: Optional[str] = None


def _fetch_httpx(
    url: str,
    user_agent: str,
    timeout_seconds: float,
) -> FetchResult:
    """Fetch URL with httpx."""
    try:
        with httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            final_url = str(r.url)
            return FetchResult(url=final_url, status_code=r.status_code, html=r.text, error=None)
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP %s for %s", e.response.status_code, url)
        return FetchResult(
            url=url,
            status_code=e.response.status_code,
            html="",
            error=str(e),
        )
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
        return FetchResult(url=url, status_code=-1, html="", error=str(e))


def _fetch_playwright(
    url: str,
    user_agent: str,
    timeout_seconds: float,
    browser_kind: str = "chromium",
) -> FetchResult:
    """Fetch URL with Playwright (lazy import)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install %s", browser_kind)
        return FetchResult(url=url, status_code=-1, html="", error="Playwright not installed")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch() if browser_kind == "chromium" else getattr(p, browser_kind).launch()
            try:
                page = browser.new_page()
                page.set_extra_http_headers({"User-Agent": user_agent})
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                html = page.content()
                return FetchResult(url=url, status_code=200, html=html, error=None)
            finally:
                browser.close()
    except Exception as e:
        logger.warning("Playwright fetch failed for %s: %s", url, e)
        return FetchResult(url=url, status_code=-1, html="", error=str(e))


def fetch(
    url: str,
    user_agent: str,
    timeout_seconds: float,
    use_playwright: bool = False,
    playwright_browser: str = "chromium",
) -> FetchResult:
    """Fetch a URL and return FetchResult. Uses httpx or Playwright based on config."""
    if use_playwright:
        return _fetch_playwright(url, user_agent, timeout_seconds, playwright_browser)
    return _fetch_httpx(url, user_agent, timeout_seconds)
