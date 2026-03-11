#!/usr/bin/env python3
"""CLI entry point for doc-crawler."""

import os
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml

# Ensure project root is on path when run as script
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

from crawler.crawler import DocCrawler
from utils.logger import setup_logging

app = typer.Typer(help="Crawl documentation sites and save as Markdown.")


def load_config(path: str) -> dict:
    """Load YAML config with sensible defaults."""
    defaults = {
        "crawler": {
            "seed_url": "",
            "url_prefix": "",
            "max_depth": 10,
            "max_pages": 500,
            "delay_seconds": 0.5,
            "respect_robots_txt": True,
            "user_agent": "DocCrawler/1.0",
            "timeout_seconds": 15,
        },
        "fetcher": {"use_playwright": False, "playwright_browser": "chromium"},
        "parser": {
            "content_selectors": ["main", "article", ".content", ".docs-content", "#main-content"],
            "exclude_selectors": ["nav", "header", "footer", ".sidebar", ".toc", ".breadcrumb"],
        },
        "output": {"directory": "./output", "filename_strategy": "path", "index_file": True},
        "logging": {"level": "INFO", "file": None},
    }
    config_path = Path(path) if os.path.isabs(path) else _script_dir / path
    if not config_path.is_file():
        return defaults
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for key, default in defaults.items():
        if key not in data:
            data[key] = default
        elif isinstance(default, dict) and isinstance(data[key], dict):
            for k, v in default.items():
                if k not in data[key]:
                    data[key][k] = v
    return data


@app.command()
def run(
    config: str = typer.Option("config.yaml", "--config", "-c", help="Path to config file"),
    seed_url: Optional[str] = typer.Option(None, "--seed-url", help="Override seed URL"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Override output directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print discovered URLs only, do not save"),
    resume: bool = typer.Option(False, "--resume", help="Skip URLs already present in output folder"),
):
    """Run the documentation crawler."""
    cfg = load_config(config)
    if seed_url:
        cfg["crawler"]["seed_url"] = seed_url
        cfg["crawler"]["url_prefix"] = seed_url.rstrip("/") + "/"
    if output:
        cfg["output"]["directory"] = output

    log_cfg = cfg.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file"),
    )

    crawler = DocCrawler(cfg, dry_run=dry_run, resume=resume)
    crawler.run(seed_url=seed_url or cfg["crawler"].get("seed_url"))


if __name__ == "__main__":
    app()
