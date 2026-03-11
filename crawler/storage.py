"""Saving Markdown files and maintaining folder structure and index."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from utils.url_utils import url_to_filepath

logger = logging.getLogger(__name__)


def save_markdown(
    url: str,
    base_url: str,
    output_dir: str,
    markdown: str,
    filename_strategy: str,
    title: Optional[str] = None,
) -> str:
    """Save markdown to a file. Returns the path of the saved file."""
    if filename_strategy == "title" and title:
        # Simple safe filename from title; still use path for hierarchy when possible
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()[:100]
        path = url_to_filepath(url, base_url, output_dir)
        parent = str(Path(path).parent)
        file_path = f"{parent}/{safe_title}.md"
    else:
        file_path = url_to_filepath(url, base_url, output_dir)

    path_obj = Path(file_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(markdown, encoding="utf-8")
    logger.debug("Saved %s", file_path)
    return file_path


def update_index(
    output_dir: str,
    entries: list[tuple[str, str, str]],
) -> None:
    """Write index.md with title, relative path, and source URL for each document."""
    index_path = Path(output_dir) / "index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Index",
        "",
        "| Title | Path | Source URL |",
        "|-------|------|------------|",
    ]
    for title, rel_path, source_url in entries:
        lines.append(f'| {title} | {rel_path} | {source_url} |')
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.debug("Updated index at %s", index_path)


def path_exists_for_url(url: str, base_url: str, output_dir: str, filename_strategy: str, title: Optional[str] = None) -> bool:
    """Return True if a file already exists for this URL (for resume)."""
    if filename_strategy == "title" and title:
        path = url_to_filepath(url, base_url, output_dir)
        parent = str(Path(path).parent)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()[:100]
        file_path = Path(f"{parent}/{safe_title}.md")
    else:
        file_path = Path(url_to_filepath(url, base_url, output_dir))
    return file_path.exists()
