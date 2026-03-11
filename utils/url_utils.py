"""URL normalization, filtering, and link extraction."""

import re
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

from bs4 import BeautifulSoup


# Query params that are typically irrelevant for document identity (e.g. tracking)
IRRELEVANT_PARAMS = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"})


def normalize_url(url: str) -> str:
    """Strip fragments, remove irrelevant query params, normalize trailing slashes."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    # Normalize path (collapse multiple slashes, decode then re-encode if needed)
    path = "/" + "/".join(p for p in path.split("/") if p)

    query = parsed.query
    if query:
        params = parse_qs(query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k.lower() not in IRRELEVANT_PARAMS}
        query = urlencode(filtered, doseq=True)

    # No fragment
    normalized = urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, query, ""))
    return normalized


def is_internal(url: str, prefix: str) -> bool:
    """Return True if the URL belongs to the configured prefix."""
    norm = normalize_url(url)
    prefix_norm = normalize_url(prefix).rstrip("/")
    return norm == prefix_norm or norm.startswith(prefix_norm + "/")


def url_to_filepath(url: str, base_url: str, output_dir: str) -> str:
    """Convert a URL into a relative file path under output_dir, preserving hierarchy."""
    parsed = urlparse(url)
    path = parsed.path.strip("/") or "index"
    has_trailing_slash = url.rstrip("/") != url

    if has_trailing_slash:
        # e.g. .../api/ -> output/.../api/index.md
        relative = f"{path}/index.md"
    else:
        parts = path.split("/")
        name = parts[-1]
        if not name.lower().endswith(".md"):
            name = name + ".md"
        relative = "/".join(parts[:-1] + [name]) if len(parts) > 1 else name

    return f"{output_dir.rstrip('/')}/{relative}"


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract and normalize all links from the page HTML."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        full = urljoin(base_url, href)
        norm = normalize_url(full)
        if norm not in seen:
            seen.add(norm)
            links.append(norm)
    return links


def should_skip_resource(url: str) -> bool:
    """Return True for PDF, ZIP, images and other non-HTML resources."""
    path = urlparse(url).path.lower()
    skip_extensions = (
        ".pdf", ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".mp4", ".webm", ".mp3", ".wav", ".woff", ".woff2", ".ttf", ".eot",
    )
    return any(path.endswith(ext) for ext in skip_extensions)
