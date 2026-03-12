"""HTTP fetching via httpx or Playwright."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import httpx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from threading import Lock


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
    client: Optional[httpx.Client] = None,
) -> FetchResult:
    """Fetch URL with httpx. If client is provided, reuse it; otherwise create one."""
    own_client = client is None
    if own_client:
        client = httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
        )
    try:
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
    finally:
        if own_client and client is not None:
            client.close()


def _fetch_playwright(
    url: str,
    user_agent: str,
    timeout_seconds: float,
    browser_kind: str = "chromium",
    browser: Any = None,
    playwright_lock: Optional["Lock"] = None,
) -> FetchResult:
    """Fetch URL with Playwright. If browser is provided, reuse it (new page per fetch)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install %s", browser_kind)
        return FetchResult(url=url, status_code=-1, html="", error="Playwright not installed")

    def _do_fetch(b: Any) -> FetchResult:
        try:
            page = b.new_page()
            try:
                page.set_extra_http_headers({"User-Agent": user_agent})
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                html = page.content()
                return FetchResult(url=url, status_code=200, html=html, error=None)
            finally:
                page.close()
        except Exception as e:
            logger.warning("Playwright fetch failed for %s: %s", url, e)
            return FetchResult(url=url, status_code=-1, html="", error=str(e))

    if browser is not None:
        if playwright_lock is not None:
            with playwright_lock:
                return _do_fetch(browser)
        return _do_fetch(browser)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch() if browser_kind == "chromium" else getattr(p, browser_kind).launch()
            try:
                return _do_fetch(b)
            finally:
                b.close()
    except Exception as e:
        logger.warning("Playwright fetch failed for %s: %s", url, e)
        return FetchResult(url=url, status_code=-1, html="", error=str(e))


def fetch(
    url: str,
    user_agent: str,
    timeout_seconds: float,
    use_playwright: bool = False,
    playwright_browser: str = "chromium",
    client: Optional[httpx.Client] = None,
    browser: Optional[Any] = None,
    playwright_lock: Optional["Lock"] = None,
) -> FetchResult:
    """Fetch a URL and return FetchResult. Uses httpx or Playwright based on config.
    When client (httpx) or browser (Playwright) is provided, reuses it for connection/browser reuse.
    """
    if use_playwright:
        return _fetch_playwright(
            url, user_agent, timeout_seconds, playwright_browser,
            browser=browser, playwright_lock=playwright_lock,
        )
    return _fetch_httpx(url, user_agent, timeout_seconds, client=client)
