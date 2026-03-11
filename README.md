# Doc Crawler

A Python CLI tool for crawling technical documentation websites. Given a seed URL, it recursively navigates all sub-pages belonging to the same domain/path, extracts the main content, converts it to Markdown, and saves it to disk.

## Features

- **Recursive crawling** — discover and visit all internal links within a URL prefix
- **Content extraction** — isolate main content (exclude header, footer, nav, sidebar)
- **Markdown conversion** — clean HTML → Markdown with YAML frontmatter
- **Folder structure** — `.md` files mirror the URL path hierarchy
- **Rate limiting** — configurable delay between requests
- **Optional Playwright** — for JS-heavy pages (disabled by default)
- **Optional robots.txt** — respect robots.txt when enabled

## Installation

```bash
pip3 install -r requirements.txt
```

If you plan to use Playwright (`use_playwright: true` in config):

```bash
playwright install chromium
```

## Configuration

```bash
cp config.yaml.example config.yaml
# Edit seed_url and url_prefix in config.yaml
```

## Usage

```bash
# Basic run (uses config.yaml)
python3 main.py

# CLI overrides
python3 main.py --seed-url https://docs.example.com/en/ --output ./my-docs

# Alternative config file
python3 main.py --config custom-config.yaml

# Dry run (print discovered URLs without downloading)
python3 main.py --dry-run

# Resume interrupted crawl (skip URLs already in output folder)
python3 main.py --resume
```

## Project Structure

```
doc-crawler/
├── config.yaml
├── main.py
├── crawler/
│   ├── crawler.py    # Orchestrator
│   ├── fetcher.py    # HTTP / Playwright
│   ├── parser.py     # HTML parsing, content extraction
│   ├── converter.py  # HTML → Markdown
│   └── storage.py    # File saving
├── utils/
│   ├── logger.py
│   ├── url_utils.py
│   └── robots.py
└── requirements.txt
```

## Requirements

- Python 3.10+
