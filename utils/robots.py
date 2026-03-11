"""robots.txt parsing and compliance checking."""

from __future__ import annotations

import logging
from urllib.parse import urlparse, urljoin

import httpx

logger = logging.getLogger(__name__)

# Simple rule: list of (path_prefix, allowed). If none match, allow.
# We only support Allow/Disallow for the configured path prefix.
def _parse_robots_content(content: str, user_agent: str) -> list[tuple[str, bool]]:
    """Parse robots.txt and return (path_prefix, allowed) rules for user_agent."""
    rules: list[tuple[str, bool]] = []
    current_ua: str | None = None
    in_matching_ua = False

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "user-agent":
            current_ua = value.lower()
            in_matching_ua = current_ua == "*" or user_agent.lower().startswith(current_ua) or current_ua in user_agent.lower()
        elif key in ("allow", "disallow") and in_matching_ua:
            path = value if key == "allow" else value
            allowed = key == "allow"
            rules.append((path, allowed))
    return rules


def can_fetch(url: str, user_agent: str, robots_content: str | None) -> bool:
    """Return True if robots.txt allows fetching the given URL."""
    if not robots_content:
        return True
    parsed = urlparse(url)
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    rules = _parse_robots_content(robots_content, user_agent)
    # Last matching rule wins (per common robots.txt semantics)
    allowed = True
    for prefix, is_allow in rules:
        if prefix and path.startswith(prefix):
            allowed = is_allow
    return allowed


def fetch_robots_txt(base_url: str, user_agent: str, timeout: float = 10) -> str | None:
    """Fetch robots.txt for the site and return its content, or None on failure."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = httpx.get(robots_url, headers={"User-Agent": user_agent}, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        logger.debug("Could not fetch robots.txt: %s", e)
    return None
