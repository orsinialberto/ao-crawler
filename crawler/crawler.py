"""Central orchestrator: queue, fetch, parse, convert, save, and report."""

from __future__ import annotations

import logging
import signal
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import httpx

from crawler.converter import convert
from crawler.fetcher import fetch
from crawler.parser import parse
from crawler.storage import save_markdown, update_index, path_exists_for_url
from utils.url_utils import normalize_url, should_skip_resource
from utils.robots import fetch_robots_txt, can_fetch

logger = logging.getLogger(__name__)


@dataclass
class CrawlStats:
    """Statistics for the final report."""
    pages_visited: int = 0
    pages_saved: int = 0
    pages_skipped: int = 0
    interrupted: bool = False


class DocCrawler:
    """Orchestrates crawling: BFS queue, fetch -> parse -> convert -> save."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        dry_run: bool = False,
        resume: bool = False,
    ):
        self.config = config
        self.dry_run = dry_run
        self.resume = resume
        self.visited: set[str] = set()
        self.queue: deque[tuple[str, int]] = deque()  # (url, depth)
        self.stats = CrawlStats()
        self.saved_entries: list[tuple[str, str, str]] = []  # (title, rel_path, source_url)
        self._robots_content: str | None = None
        self._interrupt_requested = False

    def run(self, seed_url: str | None = None) -> CrawlStats:
        """Run the crawl. If seed_url is given, it overrides config."""
        seed = seed_url or self.config.get("crawler", {}).get("seed_url", "")
        if not seed:
            logger.error("No seed URL configured or provided.")
            return self.stats

        seed = normalize_url(seed)
        url_prefix = self.config.get("crawler", {}).get("url_prefix") or seed
        url_prefix = normalize_url(url_prefix).rstrip("/") + "/"
        # If url_prefix equals the seed (full page URL), derive directory so we crawl the whole section
        if url_prefix.rstrip("/") == seed:
            from urllib.parse import urlparse
            p = urlparse(seed)
            path_parts = [x for x in p.path.split("/") if x]
            if path_parts:
                parent_path = "/" + "/".join(path_parts[:-1])
                url_prefix = f"{p.scheme}://{p.netloc}{parent_path}/"
            else:
                url_prefix = f"{p.scheme}://{p.netloc}/"
        max_depth = self.config.get("crawler", {}).get("max_depth", 0)
        max_pages = self.config.get("crawler", {}).get("max_pages", 0)
        delay = self.config.get("crawler", {}).get("delay_seconds", 0.2)
        concurrency = max(1, int(self.config.get("crawler", {}).get("concurrency", 4)))
        respect_robots = self.config.get("crawler", {}).get("respect_robots_txt", True)
        user_agent = self.config.get("crawler", {}).get("user_agent", "DocCrawler/1.0")
        timeout = self.config.get("crawler", {}).get("timeout_seconds", 15)
        output_dir = self.config.get("output", {}).get("directory", "./output")
        filename_strategy = self.config.get("output", {}).get("filename_strategy", "path")
        index_file = self.config.get("output", {}).get("index_file", True)
        use_playwright = self.config.get("fetcher", {}).get("use_playwright", False)
        playwright_browser = self.config.get("fetcher", {}).get("playwright_browser", "chromium")
        content_selectors = self.config.get("parser", {}).get("content_selectors", ["main", "article"])
        exclude_selectors = self.config.get("parser", {}).get("exclude_selectors", ["nav", "header", "footer"])

        if respect_robots:
            self._robots_content = fetch_robots_txt(seed, user_agent, timeout)

        self.queue.append((seed, 0))
        logger.info("Starting crawl from: %s", seed)

        try:
            signal.signal(signal.SIGINT, self._handle_interrupt)
        except (ValueError, AttributeError):
            pass

        playwright_lock = threading.Lock() if (use_playwright and concurrency > 1) else None
        fetch_kwargs = {
            "user_agent": user_agent,
            "timeout_seconds": timeout,
            "use_playwright": use_playwright,
            "playwright_browser": playwright_browser,
            "client": None,
            "browser": None,
            "playwright_lock": playwright_lock,
        }

        def run_crawl_loop(
            *,
            client: httpx.Client | None = None,
            browser: Any = None,
        ) -> None:
            fetch_kwargs["client"] = client
            fetch_kwargs["browser"] = browser
            total = 0
            executor = ThreadPoolExecutor(max_workers=concurrency) if concurrency > 1 else None
            try:
                while self.queue and not self._interrupt_requested:
                    if max_pages and self.stats.pages_visited >= max_pages:
                        break
                    batch: list[tuple[str, int]] = []
                    while len(batch) < concurrency and self.queue and not self._interrupt_requested:
                        if max_pages and self.stats.pages_visited + len(batch) >= max_pages:
                            break
                        url, depth = self.queue.popleft()
                        if max_depth and depth > max_depth:
                            continue
                        if url in self.visited:
                            continue
                        if should_skip_resource(url):
                            continue
                        if respect_robots and self._robots_content is not None and not can_fetch(url, user_agent, self._robots_content):
                            logger.debug("Skipping (robots.txt): %s", url)
                            continue
                        self.visited.add(url)
                        batch.append((url, depth))

                    if not batch:
                        break

                    for (url, depth) in batch:
                        total += 1
                        logger.info("[%s/???] Fetching: %s", total, url)

                    if concurrency == 1:
                        for (url, depth) in batch:
                            if self._interrupt_requested:
                                break
                            self._process_one_url(
                                url=url,
                                depth=depth,
                                fetch_kwargs=fetch_kwargs,
                                delay=delay,
                                dry_run=self.dry_run,
                                resume=self.resume,
                                url_prefix=url_prefix,
                                output_dir=output_dir,
                                filename_strategy=filename_strategy,
                                content_selectors=content_selectors,
                                exclude_selectors=exclude_selectors,
                            )
                    else:
                        futures = {
                            executor.submit(fetch, url, **fetch_kwargs): (url, depth)
                            for (url, depth) in batch
                        }
                        for future in as_completed(futures):
                            if self._interrupt_requested:
                                break
                            url, depth = futures[future]
                            try:
                                result = future.result()
                            except Exception as e:
                                logger.warning("Fetch task failed for %s: %s", url, e)
                                self.stats.pages_visited += 1
                                self.stats.pages_skipped += 1
                                time.sleep(delay)
                                continue
                            self._process_one_result(
                                url=url,
                                depth=depth,
                                result=result,
                                delay=delay,
                                url_prefix=url_prefix,
                                output_dir=output_dir,
                                filename_strategy=filename_strategy,
                                content_selectors=content_selectors,
                                exclude_selectors=exclude_selectors,
                            )
            finally:
                if executor is not None:
                    executor.shutdown(wait=True)

        if use_playwright:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch() if playwright_browser == "chromium" else getattr(p, playwright_browser).launch()
                try:
                    run_crawl_loop(browser=browser)
                finally:
                    browser.close()
        else:
            with httpx.Client(
                follow_redirects=True,
                headers={"User-Agent": user_agent},
                timeout=timeout,
            ) as client:
                run_crawl_loop(client=client)

        if self._interrupt_requested:
            self.stats.interrupted = True
            logger.info("Crawl interrupted by user.")

        if index_file and self.saved_entries:
            update_index(output_dir, self.saved_entries)

        logger.info("Crawl complete.")
        logger.info("Pages visited : %s", self.stats.pages_visited)
        logger.info("Pages saved   : %s", self.stats.pages_saved)
        logger.info("Pages skipped : %s", self.stats.pages_skipped)
        logger.info("Output dir    : %s", output_dir)
        return self.stats

    def _process_one_url(
        self,
        *,
        url: str,
        depth: int,
        fetch_kwargs: dict[str, Any],
        delay: float,
        dry_run: bool,
        resume: bool,
        url_prefix: str,
        output_dir: str,
        filename_strategy: str,
        content_selectors: list[str],
        exclude_selectors: list[str],
    ) -> None:
        """Fetch one URL and process the result (used when concurrency == 1)."""
        if dry_run:
            result = fetch(url, **fetch_kwargs)
            self.stats.pages_visited += 1
            if result.error or result.status_code != 200:
                self.stats.pages_skipped += 1
                time.sleep(delay)
                return
            self.visited.add(result.url)
            parsed = parse(result.html, result.url, url_prefix, content_selectors, exclude_selectors)
            if not parsed.links:
                logger.warning(
                    "No internal links found on %s (url_prefix=%s). "
                    "If the site is JS-rendered, set fetcher.use_playwright: true in config.",
                    url, url_prefix,
                )
            for link in parsed.links:
                if link not in self.visited and not any(u == link for u, _ in self.queue):
                    self.queue.append((link, depth + 1))
            time.sleep(delay)
            return
        if resume and path_exists_for_url(url, url_prefix, output_dir, filename_strategy):
            logger.info("Skipping (already saved): %s", url)
            self.stats.pages_visited += 1
            self.stats.pages_skipped += 1
            time.sleep(delay)
            return
        result = fetch(url, **fetch_kwargs)
        self._process_one_result(
            url=url,
            depth=depth,
            result=result,
            delay=delay,
            url_prefix=url_prefix,
            output_dir=output_dir,
            filename_strategy=filename_strategy,
            content_selectors=content_selectors,
            exclude_selectors=exclude_selectors,
        )

    def _process_one_result(
        self,
        *,
        url: str,
        depth: int,
        result: Any,
        delay: float,
        url_prefix: str,
        output_dir: str,
        filename_strategy: str,
        content_selectors: list[str],
        exclude_selectors: list[str],
    ) -> None:
        """Process a fetch result: parse, convert, save, enqueue links."""
        self.stats.pages_visited += 1
        if result.error or result.status_code != 200:
            self.stats.pages_skipped += 1
            time.sleep(delay)
            return
        canonical_url = result.url
        self.visited.add(canonical_url)
        parsed = parse(result.html, canonical_url, url_prefix, content_selectors, exclude_selectors)
        if not parsed.links and len(self.visited) <= 1:
            logger.warning(
                "No internal links found on %s (url_prefix=%s). "
                "If the site is JS-rendered, set fetcher.use_playwright: true in config.",
                canonical_url, url_prefix,
            )
        markdown = convert(parsed.content_html, parsed.title, canonical_url)
        out_path = save_markdown(canonical_url, url_prefix, output_dir, markdown, filename_strategy, title=parsed.title)
        self.stats.pages_saved += 1
        rel_path = out_path.replace(output_dir.rstrip("/") + "/", "")
        self.saved_entries.append((parsed.title, rel_path, canonical_url))
        for link in parsed.links:
            if link not in self.visited and not any(u == link for u, _ in self.queue):
                self.queue.append((link, depth + 1))
        time.sleep(delay)

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        self._interrupt_requested = True
