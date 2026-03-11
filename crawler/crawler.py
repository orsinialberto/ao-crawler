"""Central orchestrator: queue, fetch, parse, convert, save, and report."""

from __future__ import annotations

import logging
import signal
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

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
        delay = self.config.get("crawler", {}).get("delay_seconds", 0.5)
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

        total = 0
        while self.queue and not self._interrupt_requested:
            if max_pages and self.stats.pages_visited >= max_pages:
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
            total += 1
            logger.info("[%s/???] Fetching: %s", total, url)

            if self.dry_run:
                self.stats.pages_visited += 1
                # In dry run we still need to fetch to discover links (or we could fetch only for discovery)
                result = fetch(url, user_agent=user_agent, timeout_seconds=timeout, use_playwright=use_playwright, playwright_browser=playwright_browser)
                if result.error or result.status_code != 200:
                    self.stats.pages_skipped += 1
                    time.sleep(delay)
                    continue
                parsed = parse(result.html, url, url_prefix, content_selectors, exclude_selectors)
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
                continue

            if self.resume and path_exists_for_url(url, url_prefix, output_dir, filename_strategy):
                logger.info("Skipping (already saved): %s", url)
                self.stats.pages_visited += 1
                self.stats.pages_skipped += 1
                time.sleep(delay)
                continue

            result = fetch(url, user_agent=user_agent, timeout_seconds=timeout, use_playwright=use_playwright, playwright_browser=playwright_browser)
            self.stats.pages_visited += 1

            if result.error or result.status_code != 200:
                self.stats.pages_skipped += 1
                time.sleep(delay)
                continue

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

    def _handle_interrupt(self, signum: int, frame: Any) -> None:
        self._interrupt_requested = True
