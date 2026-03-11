# Doc Crawler — Project Specification

## Goal

Build a Python CLI tool for crawling technical documentation websites. Given a seed URL, the tool recursively navigates all sub-pages belonging to the same domain/path, extracts the textual content of each page, converts it into normalized Markdown, and saves it to disk.

---

## Functional Requirements

1. **Recursive crawling** — starting from a seed URL, discover and visit all internal links that match the configured URL prefix
2. **Content extraction** — isolate the main content of each page (excluding header, footer, navbar, sidebar)
3. **Markdown conversion** — transform the content HTML into clean, readable Markdown
4. **File saving** — each page is saved as a `.md` file named after its URL path or `<h1>` title
5. **Folder structure** — `.md` files mirror the URL path hierarchy
6. **Deduplication** — each URL is visited only once
7. **Rate limiting** — configurable delay between requests to avoid overloading the server
8. **Error handling** — unreachable pages or HTTP errors are logged and skipped without interrupting the crawl
9. **Final report** — a summary is printed at the end: pages visited, pages skipped, files saved

---

## Non-Functional Requirements

- Compatible with Python 3.10+
- Fully configurable via YAML file (`config.yaml`) and/or CLI arguments
- Console logging with configurable levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- No headless browser dependency by default (Playwright is optional, enabled via config)
- `robots.txt` compliance (optional, enabled via config)

---

## Project Structure

```
doc-crawler/
├── config.yaml              # Main configuration file
├── main.py                  # CLI entry point
├── crawler/
│   ├── __init__.py
│   ├── crawler.py           # Crawling logic and queue management
│   ├── fetcher.py           # HTTP requests (httpx / Playwright)
│   ├── parser.py            # HTML parsing, link extraction, content isolation
│   ├── converter.py         # HTML → Markdown conversion
│   └── storage.py           # .md file saving and path management
├── utils/
│   ├── __init__.py
│   ├── logger.py            # Logging setup
│   ├── url_utils.py         # URL normalization and filtering
│   └── robots.py            # robots.txt parsing and compliance
├── requirements.txt
└── README.md
```

---

## Module Descriptions

### `config.yaml`

Main configuration file. Must support at least the following fields:

```yaml
crawler:
  seed_url: "https://docs.example.com/en/docs/welcome"
  url_prefix: "https://docs.example.com/en/docs/"   # Restricts crawling to this prefix
  max_depth: 10                                       # Maximum crawl depth (0 = unlimited)
  max_pages: 500                                      # Maximum number of pages to visit (0 = unlimited)
  delay_seconds: 0.5                                  # Delay between requests
  respect_robots_txt: true
  user_agent: "DocCrawler/1.0"
  timeout_seconds: 15

fetcher:
  use_playwright: false         # If true, use Playwright for JS-heavy pages
  playwright_browser: chromium  # chromium | firefox | webkit

parser:
  content_selectors:            # CSS selectors for main content (in priority order)
    - "main"
    - "article"
    - ".content"
    - ".docs-content"
    - "#main-content"
  exclude_selectors:            # CSS selectors to remove before extraction
    - "nav"
    - "header"
    - "footer"
    - ".sidebar"
    - ".toc"
    - ".breadcrumb"

output:
  directory: "./output"         # Destination folder for .md files
  filename_strategy: "path"     # "path" (use URL path) | "title" (use H1 title)
  index_file: true              # Generate an index.md listing all saved docs

logging:
  level: "INFO"                 # DEBUG | INFO | WARNING | ERROR
  file: null                    # If set, also write logs to this file
```

---

### `main.py` — CLI Entry Point

Command-line interface built with `argparse` or `typer`. Must support:

```bash
# Basic run (uses config.yaml)
python main.py

# CLI overrides
python main.py --seed-url https://docs.example.com/en/ --output ./my-docs

# Use an alternative config file
python main.py --config custom-config.yaml

# Print discovered URLs without downloading anything
python main.py --dry-run

# Resume an interrupted crawl (skip URLs already present in the output folder)
python main.py --resume
```

---

### `crawler/fetcher.py`

Responsible for HTTP requests. Must:

- Use `httpx` with configurable timeout
- Handle redirects automatically
- Set `User-Agent` from config
- If `use_playwright: true`, spin up a headless browser and return the rendered HTML
- Return a `FetchResult` dataclass with fields: `url`, `status_code`, `html`, `error`

---

### `crawler/parser.py`

Responsible for HTML parsing. Must:

- Use `BeautifulSoup` with the `lxml` parser
- Extract all `<a href>` links from the page and filter them via `url_utils`
- Locate the main content block using `content_selectors` (first match wins)
- Remove blocks matching `exclude_selectors`
- Extract the page title (`<title>` tag or first `<h1>`)
- Return a `ParseResult` dataclass with fields: `title`, `content_html`, `links`

---

### `crawler/converter.py`

Responsible for HTML → Markdown conversion. Must:

- Use the `markdownify` library
- Normalize the produced Markdown:
  - Collapse consecutive blank lines (maximum 2)
  - Strip trailing whitespace
  - Prepend a YAML frontmatter block with `title` and `source_url`
- Return a Markdown string ready to be written to disk

Expected output example:

```markdown
---
title: "Getting Started with ContactLab"
source_url: "https://docs.example.com/en/docs/intro"
---

# Getting Started with ContactLab

This document describes...
```

---

### `crawler/storage.py`

Responsible for writing files to disk. Must:

- Derive the `.md` file path from the URL, preserving the folder hierarchy
- Create missing directories automatically
- Avoid filename collisions (e.g. use `index.md` for URLs ending with `/`)
- If `index_file: true`, keep an `index.md` up to date with all saved documents (title + relative path + source URL)

URL → file path mapping examples:

```
https://docs.example.com/en/docs/welcome        → output/en/docs/welcome.md
https://docs.example.com/en/docs/api/intro      → output/en/docs/api/intro.md
https://docs.example.com/en/docs/api/           → output/en/docs/api/index.md
```

---

### `crawler/crawler.py`

Central orchestrator. Must:

- Maintain a **queue** of URLs to visit (BFS or DFS, configurable)
- Maintain a **set** of already-visited URLs
- For each URL: fetch → parse → convert → save
- Respect `max_depth` and `max_pages` limits
- Apply the configured delay between requests
- Log each operation at the appropriate level
- Collect statistics for the final report

---

### `utils/url_utils.py`

URL utility functions. Must include:

- `normalize_url(url)` — strips fragments (`#section`), removes irrelevant query params, normalizes trailing slashes
- `is_internal(url, prefix)` — returns `True` if the URL belongs to the configured prefix
- `url_to_filepath(url, base_url, output_dir)` — converts a URL into a relative file path
- `extract_links(html, base_url)` — extracts and normalizes all links from a page's HTML

---

## Python Dependencies (`requirements.txt`)

```
httpx>=0.27
beautifulsoup4>=4.12
lxml>=5.0
markdownify>=0.12
pyyaml>=6.0
typer>=0.12        # or argparse (stdlib)
rich>=13.0         # colored console output and progress bar
playwright>=1.44   # optional, only needed if use_playwright: true
```

---

## Expected Edge Case Behavior

| Situation | Expected behavior |
|---|---|
| URL with fragment (`#section`) | Fragment is stripped; the base URL is visited only once |
| Links to PDF, ZIP, or image files | Ignored, not downloaded |
| Page returns 404 or 500 | Logged as an error, skipped, crawl continues |
| Link outside the URL prefix | Ignored |
| Redirect to an internal URL | Followed and processed normally |
| Redirect to an external URL | Ignored |
| No content selector matches | Full `<body>` is used as fallback, warning is logged |
| Manual interruption (Ctrl+C) | Partial report is saved, process exits cleanly |

---

## Expected Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Configure
cp config.yaml.example config.yaml
# → edit seed_url and url_prefix in config.yaml

# Run
python main.py

# Expected console output:
# [INFO] Starting crawl from: https://docs.example.com/en/docs/welcome
# [INFO] [1/???] Fetching: https://docs.example.com/en/docs/welcome
# [INFO] [2/???] Fetching: https://docs.example.com/en/docs/getting-started
# ...
# [INFO] Crawl complete.
# [INFO] Pages visited : 47
# [INFO] Pages saved   : 45
# [INFO] Pages skipped : 2
# [INFO] Output dir    : ./output
```

---

## Development Notes

- Use **type hints** throughout all modules
- Each module should have a primary class that is testable in isolation
- Prefer **dataclasses** or **Pydantic** for data transfer objects (`FetchResult`, `ParseResult`)
- The project must work correctly even without Playwright installed (lazy/optional import)
- `config.yaml` must have sensible default values for all optional fields
