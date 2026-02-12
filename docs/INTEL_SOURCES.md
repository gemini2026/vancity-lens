# Intelligence Sources (Config-Driven Ingestion)

This repo supports config-driven ingestion of public documents into the RAG + intelligence pipeline.

The config file is:

- `pipeline/sources.yaml`

The runner is:

- `scripts/ingest_sources.py`

## What Gets Ingested

The config currently prioritizes **ShapeYourCity Vancouver (EngagementHQ)** sources because many `vancouver.ca` subdomains are protected by Cloudflare and can block non-browser crawlers.

The key ShapeYourCity ingestion patterns are:

- **Project Finder → Projects → Project Pages → Document Library PDFs**
- **Document library pages** (Plan/policy pages) → document links → `/download` PDFs

## How To Run

Run inside the API container (recommended; has Python deps + DB connectivity prewired):

```bash
cd bill47
docker compose exec api python scripts/ingest_sources.py --dry-run
```

Ingest a single source:

```bash
docker compose exec api python scripts/ingest_sources.py \
  --source syc_development_applications \
  --max-projects 25
```

Ingest multiple sources (repeat `--source`):

```bash
docker compose exec api python scripts/ingest_sources.py \
  --source syc_development_applications \
  --source syc_broadway_plan_documents
```

Run the full pipeline (scrape + embed + extract signals):

```bash
docker compose exec api bash -lc 'export COHERE_API_KEY=... ANTHROPIC_API_KEY=...; python scripts/ingest_sources.py --process'
```

Notes:

- `--process` requires `COHERE_API_KEY` and `ANTHROPIC_API_KEY`.
- By default the script only stores documents; you can process later with existing tooling.

## How ShapeYourCity Document URLs Work

On ShapeYourCity, links like:

- `https://www.shapeyourcity.ca/<project_id>/widgets/<widget_id>/documents/<doc_id>`

are **HTML pages**. The actual file download is:

- the same URL with `/download` appended.

The ingestion runner automatically appends `/download` for document-library links.

## Updating Sources

Edit `pipeline/sources.yaml`:

- Toggle sources with `enabled: true/false`
- Add new ShapeYourCity document library pages using:
  - `discover.type: syc_document_library_page`
  - `discover.page_url: https://www.shapeyourcity.ca/<slug>/documents`
- Add new project-finder based collections using:
  - `discover.type: syc_projectfinder`
  - `discover.embed_url` for token discovery
  - `discover.projects_api_template` for project listing

## Optional: Open-Web Search (API-Based Discovery)

You can expand discovery beyond known ShapeYourCity pages by using `discover.type: web_search`.

How it works:
- A search provider API (recommended: Brave Search API) is called with your configured queries.
- Result URLs are filtered by `allow_domains` / regex filters.
- Those URLs are ingested via the existing `scrape_url -> chunk -> extract` pipeline.

Config:
- Add a source with:
  - `discover.type: web_search`
  - `discover.provider: brave`
  - `discover.queries: [...]`
  - `discover.allow_domains: [...]` (keep this tight)

Secrets:
- Set `BRAVE_SEARCH_API_KEY` (see `.env.example`).

Why API-based:
- Scraping Google/Bing result pages is brittle and usually violates ToS; use an official API instead.
