"""HTML parsing, link extraction, and content isolation."""

import logging
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from utils.url_utils import extract_links, is_internal

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of parsing a page."""
    title: str
    content_html: str
    links: list[str]


def parse(
    html: str,
    url: str,
    url_prefix: str,
    content_selectors: list[str],
    exclude_selectors: list[str],
) -> ParseResult:
    """Parse HTML: extract title, main content, and internal links."""
    soup = BeautifulSoup(html, "lxml")

    # Title: <title> or first <h1>
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        title = title_tag.get_text(strip=True)
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title = url.split("/")[-1] or "Untitled"

    # Main content: first matching selector
    content_node = None
    for sel in content_selectors:
        content_node = soup.select_one(sel)
        if content_node:
            break
    if not content_node:
        logger.warning("No content selector matched for %s, using body", url)
        content_node = soup.find("body") or soup

    # Clone so we don't mutate the original tree
    content_soup = BeautifulSoup(str(content_node), "lxml")
    root = content_soup.find() or content_soup

    # Remove excluded blocks
    for sel in exclude_selectors:
        for node in root.select(sel):
            node.decompose()

    content_html = str(root) if root else ""

    # Extract and filter links
    all_links = extract_links(html, url)
    links = [link for link in all_links if is_internal(link, url_prefix)]

    return ParseResult(title=title, content_html=content_html, links=links)
