"""HTML to Markdown conversion with frontmatter."""

import re
from markdownify import markdownify as md


def _normalize_markdown(text: str) -> str:
    """Collapse consecutive blank lines (max 2 newlines = 1 blank line), strip trailing whitespace."""
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines)


def convert(
    content_html: str,
    title: str,
    source_url: str,
) -> str:
    """Convert HTML to Markdown with YAML frontmatter (title, source_url)."""
    markdown_body = md(
        content_html,
        heading_style="ATX",
        strip=["script", "style"],
    )
    markdown_body = _normalize_markdown(markdown_body or "")

    title_esc = title.replace('"', '\\"')
    source_url_esc = source_url.replace('"', '\\"')
    frontmatter = f'''---
title: "{title_esc}"
source_url: "{source_url_esc}"
---

'''
    return frontmatter + markdown_body
