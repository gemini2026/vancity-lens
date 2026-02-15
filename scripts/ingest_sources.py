#!/usr/bin/env python3
"""
VanCity Lens — Config-driven document ingestion (RAG)

Reads `pipeline/sources.yaml`, discovers URLs, then ingests them into the
`documents` table via the same internal flow as `/api/v1/intel/ingest-url`:

  scrape_url() -> process_document_chunks() -> process_document()

By default this script only SCRAPES (stores documents). Use `--process` to run
embedding + signal extraction (requires COHERE_API_KEY + ANTHROPIC_API_KEY).

Examples (run inside Docker):
  docker compose exec api python scripts/ingest_sources.py --dry-run
  docker compose exec api python scripts/ingest_sources.py --source syc_development_applications --max-projects 25
  docker compose exec api python scripts/ingest_sources.py --source syc_broadway_plan_documents --process
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.parse import urljoin

import aiohttp
import asyncpg
import yaml
from bs4 import BeautifulSoup


# Add project root to path (so `import api.*` works when run from container or host)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("ingest_sources")


@dataclass(frozen=True)
class DiscoveredDoc:
    url: str
    source_type: str
    title: Optional[str] = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean_title(text: str) -> str:
    """
    Clean ShapeYourCity anchor text like:
      "Notification postcard (142 KB) (pdf)"
      "Broadway Plan review summary sheet (PDF, 1.5MB)"
    """
    t = " ".join((text or "").split())
    if not t:
        return t

    # Remove trailing "(pdf)" or "(PDF, 1.5MB)" style suffixes (one or more)
    # Keep internal parentheses to avoid over-stripping titles that legitimately contain them.
    for _ in range(3):
        t2 = re.sub(r"\s*\(\s*pdf\s*\)\s*$", "", t, flags=re.IGNORECASE)
        t2 = re.sub(
            r"\s*\(\s*pdf\s*,\s*\d+(?:\.\d+)?\s*(?:kb|mb|gb)\s*\)\s*$",
            "",
            t2,
            flags=re.IGNORECASE,
        )
        t2 = re.sub(
            r"\s*\(\s*\d+(?:\.\d+)?\s*(?:kb|mb|gb)\s*\)\s*$",
            "",
            t2,
            flags=re.IGNORECASE,
        )
        if t2 == t:
            break
        t = t2.strip()

    return t.strip()


def _ensure_syc_download_url(url: str) -> str:
    """
    ShapeYourCity document links are HTML pages. Actual file download is at the same
    path with `/download` appended.
    """
    u = url.rstrip("/")
    if u.endswith("/download"):
        return u
    return u + "/download"


async def _fetch_text(session: aiohttp.ClientSession, url: str, *, headers: dict[str, str], timeout_s: int) -> str:
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as resp:
        resp.raise_for_status()
        return await resp.text(errors="replace")


async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict[str, str],
    timeout_s: int,
) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    async with session.get(url, headers=headers, timeout=timeout, allow_redirects=True) as resp:
        resp.raise_for_status()
        return await resp.json()


def _extract_next_data(html: str) -> dict[str, Any]:
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
    if not m:
        raise ValueError("Could not find __NEXT_DATA__ in projectfinder embed HTML")
    return json.loads(m.group(1))


async def _syc_get_anonymous_token(
    session: aiohttp.ClientSession,
    embed_url: str,
    *,
    headers: dict[str, str],
    timeout_s: int,
) -> str:
    html = await _fetch_text(session, embed_url, headers=headers, timeout_s=max(timeout_s, 60))
    data = _extract_next_data(html)
    token = (
        data.get("props", {})
        .get("pageProps", {})
        .get("initialState", {})
        .get("anonymousUser", {})
        .get("token")
    )
    if not token:
        raise ValueError("Could not extract anonymousUser.token from projectfinder embed __NEXT_DATA__")
    return token


def _parse_syc_project_published_at(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Example: "2026-02-09T16:24:38-07:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None


async def discover_syc_projectfinder(
    session: aiohttp.ClientSession,
    discover_cfg: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: int,
    max_concurrency: int,
    max_projects_override: Optional[int],
    days_back_override: Optional[int],
) -> list[DiscoveredDoc]:
    embed_url = discover_cfg["embed_url"]
    api_template = discover_cfg["projects_api_template"]
    per_page = int(discover_cfg.get("per_page", 200))
    max_pages = int(discover_cfg.get("max_pages", 10))
    project_base_url = str(discover_cfg.get("project_base_url", "https://www.shapeyourcity.ca")).rstrip("/")
    days_back = int(discover_cfg.get("days_back", 0) or 0)
    if days_back_override is not None:
        days_back = days_back_override

    ingest_project_pages = bool(discover_cfg.get("ingest_project_pages", True))
    ingest_project_documents = bool(discover_cfg.get("ingest_project_documents", True))
    store_cfg = discover_cfg.get("store") or {}
    page_source_type = store_cfg.get("project_page_source_type", "syc_project_page")
    doc_source_type = store_cfg.get("project_document_source_type", "syc_project_document")

    token = await _syc_get_anonymous_token(session, embed_url, headers=headers, timeout_s=timeout_s)

    api_headers = {
        **headers,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    cutoff: Optional[datetime] = None
    if days_back > 0:
        cutoff = _now_utc() - timedelta(days=days_back)

    max_projects_cfg = discover_cfg.get("max_projects")
    max_projects = int(max_projects_cfg) if max_projects_cfg else None
    if max_projects_override is not None:
        max_projects = max_projects_override

    # Fetch just enough pages to satisfy cutoff/max_projects.
    filtered_projects: list[dict[str, Any]] = []
    stop = False
    for page in range(1, max_pages + 1):
        url = api_template.format(page=page, per_page=per_page)
        payload = await _fetch_json(session, url, headers=api_headers, timeout_s=max(timeout_s, 60))
        batch = payload.get("data") or []
        if not batch:
            break

        for p in batch:
            attrs = p.get("attributes") or {}
            published_at = _parse_syc_project_published_at(attrs.get("published-at"))
            if cutoff and published_at:
                pub_utc = published_at.astimezone(timezone.utc) if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
                # The API is ordered by published_at desc; if we hit older-than-cutoff,
                # we can stop paging entirely.
                if pub_utc < cutoff:
                    stop = True
                    break

            filtered_projects.append(p)
            if max_projects and len(filtered_projects) >= max_projects:
                stop = True
                break

        if stop:
            break

        links = payload.get("links") or {}
        if not links.get("next"):
            break

    docs: list[DiscoveredDoc] = []
    seen: set[str] = set()

    semaphore = asyncio.Semaphore(max_concurrency)
    base_for_join = project_base_url + "/"

    async def fetch_project_docs(p: dict[str, Any]) -> None:
        attrs = p.get("attributes") or {}
        name = str(attrs.get("name") or "").strip()
        permalink = str(attrs.get("permalink") or "").strip().lstrip("/")
        if not permalink:
            return

        project_url = f"{project_base_url}/{permalink}"

        if ingest_project_pages:
            if project_url not in seen:
                seen.add(project_url)
                docs.append(
                    DiscoveredDoc(
                        url=project_url,
                        source_type=page_source_type,
                        title=name or permalink,
                    )
                )

        if not ingest_project_documents:
            return

        def append_doc_links(soup_obj: BeautifulSoup) -> None:
            for a in soup_obj.select("a.document-library-widget-link[href]"):
                href = a.get("href")
                if not href:
                    continue
                abs_url = urljoin(base_for_join, href)
                dl_url = _ensure_syc_download_url(abs_url)
                title = _clean_title(a.get_text(" ", strip=True))
                if name and title and not title.lower().startswith(name.lower()):
                    title = f"{name} — {title}"
                if dl_url in seen:
                    continue
                seen.add(dl_url)
                docs.append(
                    DiscoveredDoc(
                        url=dl_url,
                        source_type=doc_source_type,
                        title=title or name or permalink,
                    )
                )

        async with semaphore:
            try:
                html = await _fetch_text(session, project_url, headers=headers, timeout_s=max(timeout_s, 60))
            except Exception as e:
                logger.warning(f"[syc] Failed to fetch project page for docs: {project_url}: {e}")
                return

        soup = BeautifulSoup(html, "html.parser")
        append_doc_links(soup)

        # Secondary: follow "more.." document library pages if present (to avoid missing extra docs)
        more_links: list[str] = []
        for a in soup.select(".more-link-block a[href]"):
            href = a.get("href")
            if not href:
                continue
            # Example: "/88-e-pender-st/widgets/213909/documents"
            more_links.append(urljoin(base_for_join, href))
        for more_url in list(dict.fromkeys(more_links))[:3]:
            async with semaphore:
                try:
                    more_html = await _fetch_text(session, more_url, headers=headers, timeout_s=max(timeout_s, 60))
                except Exception as e:
                    logger.debug(f"[syc] Failed to fetch more-docs page: {more_url}: {e}")
                    continue
            more_soup = BeautifulSoup(more_html, "html.parser")
            append_doc_links(more_soup)

    await asyncio.gather(*(fetch_project_docs(p) for p in filtered_projects))
    return docs


async def discover_syc_document_library_page(
    session: aiohttp.ClientSession,
    discover_cfg: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: int,
) -> list[DiscoveredDoc]:
    page_url = discover_cfg["page_url"]
    ingest_page = bool(discover_cfg.get("ingest_page", False))
    store_cfg = discover_cfg.get("store") or {}
    page_source_type = store_cfg.get("page_source_type", "syc_doc_library_page")
    doc_source_type = store_cfg.get("document_source_type", "syc_doc_library_document")

    html = await _fetch_text(session, page_url, headers=headers, timeout_s=max(timeout_s, 60))
    soup = BeautifulSoup(html, "html.parser")

    docs: list[DiscoveredDoc] = []
    seen: set[str] = set()

    def append_doc_links(soup_obj: BeautifulSoup, base_url: str) -> None:
        for a in soup_obj.select("a.document-library-widget-link[href]"):
            href = a.get("href")
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            dl_url = _ensure_syc_download_url(abs_url)
            title = _clean_title(a.get_text(" ", strip=True))
            if dl_url in seen:
                continue
            seen.add(dl_url)
            docs.append(DiscoveredDoc(url=dl_url, source_type=doc_source_type, title=title or None))

    if ingest_page:
        docs.append(DiscoveredDoc(url=page_url, source_type=page_source_type))
        seen.add(page_url)

    append_doc_links(soup, page_url)

    # Follow "more.." pages if present
    for more in soup.select(".more-link-block a[href]"):
        href = more.get("href")
        if not href:
            continue
        more_url = urljoin(page_url, href)
        try:
            more_html = await _fetch_text(session, more_url, headers=headers, timeout_s=max(timeout_s, 60))
        except Exception:
            continue
        more_soup = BeautifulSoup(more_html, "html.parser")
        append_doc_links(more_soup, more_url)

    return docs


async def discover_static_urls(discover_cfg: dict[str, Any]) -> list[DiscoveredDoc]:
    store_cfg = discover_cfg.get("store") or {}
    source_type = store_cfg.get("source_type", "external")
    urls = discover_cfg.get("urls") or []
    return [DiscoveredDoc(url=u, source_type=source_type) for u in urls]


async def discover_rss(
    session: aiohttp.ClientSession,
    discover_cfg: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: int,
) -> list[DiscoveredDoc]:
    try:
        import feedparser  # type: ignore
    except Exception as e:
        raise RuntimeError("feedparser is required for RSS sources") from e

    feed_url = discover_cfg["feed_url"]
    max_items = int(discover_cfg.get("max_items", 20))
    store_cfg = discover_cfg.get("store") or {}
    source_type = store_cfg.get("source_type", "news")

    xml = await _fetch_text(session, feed_url, headers=headers, timeout_s=timeout_s)
    feed = feedparser.parse(xml)

    docs: list[DiscoveredDoc] = []
    for entry in (feed.entries or [])[:max_items]:
        url = entry.get("link") or ""
        title = entry.get("title") or None
        if not url:
            continue
        docs.append(DiscoveredDoc(url=url, source_type=source_type, title=title))
    return docs


def _url_allowed(
    url: str,
    *,
    allow_domains: list[str] | None,
    deny_domains: list[str] | None,
    allow_url_regex: str | None,
    deny_url_regex: str | None,
) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""

    if deny_domains:
        for d in deny_domains:
            d = d.strip().lower()
            if not d:
                continue
            if host == d or host.endswith("." + d):
                return False

    if allow_domains:
        ok = False
        for d in allow_domains:
            d = d.strip().lower()
            if not d:
                continue
            if host == d or host.endswith("." + d):
                ok = True
                break
        if not ok:
            return False

    if allow_url_regex:
        if not re.search(allow_url_regex, url, flags=re.IGNORECASE):
            return False

    if deny_url_regex:
        if re.search(deny_url_regex, url, flags=re.IGNORECASE):
            return False

    return True


async def _brave_web_search(
    session: aiohttp.ClientSession,
    *,
    api_key: str,
    query: str,
    count: int,
    country: str | None,
    search_lang: str | None,
    freshness: str | None,
    timeout_s: int,
) -> list[dict[str, Any]]:
    """
    Brave Search API: https://api.search.brave.com/res/v1/web/search?q=...

    Returns list of result dicts (url/title/etc), best-effort.
    """
    if not api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is not set")

    params: dict[str, str] = {
        "q": query,
        "count": str(max(1, min(count, 20))),
    }
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang
    if freshness:
        params["freshness"] = freshness

    timeout = aiohttp.ClientTimeout(total=max(timeout_s, 15))
    async with session.get(
        "https://api.search.brave.com/res/v1/web/search",
        params=params,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        timeout=timeout,
    ) as resp:
        if resp.status != 200:
            body = await resp.text(errors="replace")
            raise RuntimeError(f"Brave Search API error: HTTP {resp.status}: {body[:500]}")
        payload = await resp.json()

    web = payload.get("web") or {}
    results = web.get("results") or []
    if isinstance(results, list):
        return results
    return []


async def discover_web_search(
    session: aiohttp.ClientSession,
    discover_cfg: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_s: int,
) -> list[DiscoveredDoc]:
    """
    Open-web search discovery (API-based; does not scrape search result pages).

    Example YAML:
      discover:
        type: web_search
        provider: brave
        queries:
          - "site:shapeyourcity.ca rezoning staff report pdf vancouver"
        max_results_per_query: 10
        allow_domains: ["shapeyourcity.ca", "bclaws.gov.bc.ca"]
        store:
          source_type: "web_search"
    """
    store_cfg = discover_cfg.get("store") or {}
    source_type = store_cfg.get("source_type", "web_search")

    provider = (discover_cfg.get("provider") or os.environ.get("WEB_SEARCH_PROVIDER") or "brave").strip().lower()

    queries_raw = discover_cfg.get("queries")
    if not queries_raw:
        queries_raw = discover_cfg.get("query")
    if isinstance(queries_raw, str):
        queries = [q.strip() for q in [queries_raw] if q.strip()]
    else:
        queries = [str(q).strip() for q in (queries_raw or []) if str(q).strip()]

    if not queries:
        return []

    max_results_per_query = int(discover_cfg.get("max_results_per_query", 10))
    allow_domains = discover_cfg.get("allow_domains") or None
    deny_domains = discover_cfg.get("deny_domains") or None
    allow_url_regex = discover_cfg.get("allow_url_regex") or None
    deny_url_regex = discover_cfg.get("deny_url_regex") or None
    freshness = (discover_cfg.get("freshness") or "").strip() or None
    country = (discover_cfg.get("country") or os.environ.get("WEB_SEARCH_COUNTRY") or "").strip() or None
    search_lang = (discover_cfg.get("search_lang") or os.environ.get("WEB_SEARCH_LANG") or "").strip() or None

    docs: list[DiscoveredDoc] = []
    seen: set[str] = set()

    for q in queries:
        if provider == "brave":
            api_key = (os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip()
            results = await _brave_web_search(
                session,
                api_key=api_key,
                query=q,
                count=max_results_per_query,
                country=country,
                search_lang=search_lang,
                freshness=freshness,
                timeout_s=timeout_s,
            )
        else:
            raise RuntimeError(f"Unsupported web_search provider: {provider}")

        for r in results:
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip() or None
            if not url or url in seen:
                continue
            if not _url_allowed(
                url,
                allow_domains=allow_domains,
                deny_domains=deny_domains,
                allow_url_regex=allow_url_regex,
                deny_url_regex=deny_url_regex,
            ):
                continue
            seen.add(url)
            docs.append(DiscoveredDoc(url=url, source_type=source_type, title=title))

    return docs


async def _get_pool() -> asyncpg.Pool:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://vancity:vancity_dev@localhost:5432/vancity_lens",
    )
    logger.info("Connecting to database...")
    return await asyncpg.create_pool(db_url, min_size=2, max_size=10)


async def _document_exists(pool: asyncpg.Pool, url: str) -> Optional[dict[str, Any]]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, processed_at FROM documents WHERE source_url = $1",
            url,
        )
    return dict(row) if row else None


async def _ingest_docs(
    pool: asyncpg.Pool,
    discovered: list[DiscoveredDoc],
    *,
    process: bool,
    dry_run: bool,
    max_total: Optional[int],
) -> dict[str, Any]:
    from api.intelligence.scraper_url import scrape_url

    cohere_key = os.environ.get("COHERE_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if process and (not cohere_key or not anthropic_key):
        raise RuntimeError("COHERE_API_KEY and ANTHROPIC_API_KEY must be set to run --process")

    if process:
        from api.intelligence.local_rag.embeddings import process_document_chunks
        from api.intelligence.extractor import process_document

    stats = {
        "found": len(discovered),
        "new": 0,
        "skipped_exists": 0,
        "processed": 0,
        "errors": 0,
    }

    for i, doc in enumerate(discovered, 1):
        if max_total and stats["new"] >= max_total:
            break

        if dry_run:
            print(f"{doc.source_type}\t{doc.url}\t{doc.title or ''}")
            continue

        try:
            existing = await _document_exists(pool, doc.url)
            if existing:
                stats["skipped_exists"] += 1
                continue

            result = await scrape_url(pool, doc.url, source_type=doc.source_type, title=doc.title)
            if result.get("status") == "new":
                stats["new"] += 1
            else:
                stats["skipped_exists"] += 1
                continue

            if process:
                doc_id = int(result["document_id"])
                await process_document_chunks(pool, doc_id, cohere_key)
                await process_document(pool, doc_id, anthropic_key)
                stats["processed"] += 1

        except Exception as e:
            logger.warning(f"Ingest failed: {doc.url}: {e}")
            stats["errors"] += 1

    return stats


async def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest intelligence sources from pipeline/sources.yaml")
    parser.add_argument("--config", default="pipeline/sources.yaml", help="Path to sources YAML")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source id to run (repeatable). If omitted, runs all enabled sources.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print discovered URLs, do not write to DB")
    parser.add_argument("--process", action="store_true", help="After ingest, embed + extract signals (needs API keys)")
    parser.add_argument("--max-total", type=int, default=None, help="Stop after ingesting N new documents total")
    parser.add_argument("--max-projects", type=int, default=None, help="Override max projects for SYC projectfinder sources")
    parser.add_argument("--days-back", type=int, default=None, help="Override days_back for sources that support it")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    defaults = cfg.get("defaults") or {}
    http_defaults = defaults.get("http") or {}
    user_agent = http_defaults.get("user_agent", "VanCityLensBot/0.1")
    timeout_s = int(http_defaults.get("timeout_s", 30))
    max_concurrency = int(http_defaults.get("max_concurrency", 6))

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    requested = set(args.source or [])
    sources = cfg.get("sources") or []
    to_run = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        if not sid:
            continue
        if requested and sid not in requested:
            continue
        if not requested and not s.get("enabled", False):
            continue
        to_run.append(s)

    if not to_run:
        logger.error("No sources selected (check --source or enabled: true in YAML)")
        return 2

    pool: Optional[asyncpg.Pool] = None
    if not args.dry_run:
        pool = await _get_pool()

    connector = aiohttp.TCPConnector(limit=max_concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        all_docs: list[DiscoveredDoc] = []

        for src in to_run:
            sid = src["id"]
            discover = src.get("discover") or {}
            dtype = discover.get("type")
            logger.info(f"Discovering: {sid} ({dtype})")

            try:
                if dtype == "syc_projectfinder":
                    docs = await discover_syc_projectfinder(
                        session,
                        discover,
                        headers=headers,
                        timeout_s=timeout_s,
                        max_concurrency=max_concurrency,
                        max_projects_override=args.max_projects,
                        days_back_override=args.days_back,
                    )
                elif dtype == "syc_document_library_page":
                    docs = await discover_syc_document_library_page(
                        session, discover, headers=headers, timeout_s=timeout_s
                    )
                elif dtype == "static_urls":
                    docs = await discover_static_urls(discover)
                elif dtype == "rss":
                    docs = await discover_rss(session, discover, headers=headers, timeout_s=timeout_s)
                elif dtype == "web_search":
                    docs = await discover_web_search(session, discover, headers=headers, timeout_s=timeout_s)
                elif dtype == "note":
                    logger.info(f"Skipping note source: {sid}")
                    docs = []
                else:
                    logger.warning(f"Unsupported discover.type={dtype} for source {sid}")
                    docs = []

                logger.info(f"  -> {len(docs)} URLs discovered")
                all_docs.extend(docs)
            except Exception as e:
                logger.warning(f"Discovery failed for {sid}: {e}")

        # De-dupe by URL, prefer first title/source_type encountered.
        dedup: dict[str, DiscoveredDoc] = {}
        for d in all_docs:
            if d.url not in dedup:
                dedup[d.url] = d
        discovered = list(dedup.values())

        logger.info(f"Total discovered (deduped): {len(discovered)}")

        if args.dry_run:
            # Print as TSV for easy copy/paste/grep
            print("source_type\turl\ttitle")
            for d in sorted(discovered, key=lambda x: (x.source_type, x.url)):
                print(f"{d.source_type}\t{d.url}\t{d.title or ''}")
            return 0

        assert pool is not None
        stats = await _ingest_docs(
            pool,
            discovered,
            process=args.process,
            dry_run=args.dry_run,
            max_total=args.max_total,
        )
        logger.info(f"Done. Stats: {stats}")

    if pool is not None:
        await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
