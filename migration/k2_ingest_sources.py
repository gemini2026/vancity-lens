#!/usr/bin/env python3
"""Ingest pipeline/sources.yaml into a K2 corpus (URL-based ingestion).

This script runs the same URL discovery logic as `scripts/ingest_sources.py`,
but instead of downloading/parsing content into Postgres it sends discovered
URLs to K2 via the SDK.

K2 is expected to handle parsing, chunking, and indexing.

Requirements (env):
  K2_API_HOST (optional; defaults to https://api-dev.knowledge2.ai)
  K2_API_KEY
  K2_CORPUS_ID  (can be a corpus UUID OR a corpus name; the script will resolve)

Example:
  K2_API_KEY=... K2_CORPUS_ID=vancity python3 migration/k2_ingest_sources.py --dry-run
  K2_API_KEY=... K2_CORPUS_ID=vancity python3 migration/k2_ingest_sources.py --wait --build-indexes
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
import ssl
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp
import certifi
import yaml

# Ensure repo root on sys.path so `import sdk` and `import scripts.*` work.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from sdk import Knowledge2  # noqa: E402
from sdk.errors import Knowledge2Error  # noqa: E402

from scripts.ingest_sources import (  # noqa: E402
    DiscoveredDoc,
    discover_rss,
    discover_static_urls,
    discover_syc_document_library_page,
    discover_syc_projectfinder,
    discover_web_search,
)

logger = logging.getLogger("k2_ingest_sources")


@dataclass(frozen=True)
class K2Runtime:
    client: Knowledge2
    corpus_id: str


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _k2_client_from_env() -> Knowledge2:
    api_host = (os.environ.get("K2_API_HOST") or "https://api-dev.knowledge2.ai").strip().rstrip("/")
    api_key = _require_env("K2_API_KEY")
    return Knowledge2(api_host=api_host, api_key=api_key)


def _resolve_corpus_id(client: Knowledge2, corpus_ref: str) -> str:
    """Accept a corpus UUID or a corpus name; resolve to UUID."""
    corpus_ref = corpus_ref.strip()
    if not corpus_ref:
        raise SystemExit("K2_CORPUS_ID is empty")

    corpora = (client.list_corpora(limit=200, offset=0) or {}).get("corpora") or []
    for c in corpora:
        if c.get("id") == corpus_ref:
            return corpus_ref

    matches = [c for c in corpora if c.get("name") == corpus_ref and c.get("id")]
    if len(matches) == 1:
        resolved = matches[0]["id"]
        logger.info("Resolved K2 corpus name '%s' -> '%s'", corpus_ref, resolved)
        return resolved
    if len(matches) > 1:
        raise SystemExit(
            f"Ambiguous K2 corpus name '{corpus_ref}'. Set K2_CORPUS_ID to the corpus UUID."
        )

    raise SystemExit(
        f"K2 corpus not found: '{corpus_ref}'. Ensure your key can access it and that the name/ID is correct."
    )


async def _discover_docs(
    cfg_path: str,
    *,
    source_id: str | None,
    max_projects: int | None,
    days_back: int | None,
    enabled_only: bool,
) -> list[DiscoveredDoc]:
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    defaults = cfg.get("defaults") or {}
    http_defaults = defaults.get("http") or {}
    user_agent = str(http_defaults.get("user_agent") or "VanCityLensBot/0.1")
    timeout_s = int(http_defaults.get("timeout_s") or 30)
    max_concurrency = int(http_defaults.get("max_concurrency") or 6)

    headers = {"User-Agent": user_agent}

    sources = cfg.get("sources") or []
    if source_id:
        sources = [s for s in sources if s.get("id") == source_id]
        if not sources:
            raise SystemExit(f"Unknown --source '{source_id}' (not found in {cfg_path})")

    all_docs: list[DiscoveredDoc] = []

    # On some host environments (notably macOS + python.org Python), the default
    # CA bundle can be missing which breaks HTTPS discovery for ShapeYourCity and
    # other sources. Use certifi's CA store so this script works reliably.
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        for src in sources:
            sid = src.get("id")
            enabled = bool(src.get("enabled", False))
            if enabled_only and not enabled:
                logger.info("Skipping disabled source: %s", sid)
                continue

            discover = src.get("discover") or {}
            dtype = str(discover.get("type") or "").strip()
            if not dtype:
                logger.warning("Skipping source with missing discover.type: %s", sid)
                continue

            logger.info("Discovering: %s (%s)", sid, dtype)
            try:
                if dtype == "syc_projectfinder":
                    docs = await discover_syc_projectfinder(
                        session,
                        discover,
                        headers=headers,
                        timeout_s=timeout_s,
                        max_concurrency=max_concurrency,
                        max_projects_override=max_projects,
                        days_back_override=days_back,
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
                    logger.info("Skipping note source: %s", sid)
                    docs = []
                else:
                    logger.warning("Unsupported discover.type=%s for source=%s", dtype, sid)
                    docs = []

                logger.info("  -> %s URLs discovered", len(docs))
                all_docs.extend(docs)
            except Exception as e:
                logger.warning("Discovery failed for %s: %s", sid, e)

    # De-dupe by URL, prefer first title/source_type encountered.
    dedup: dict[str, DiscoveredDoc] = {}
    for d in all_docs:
        if d.url not in dedup:
            dedup[d.url] = d
    discovered = list(dedup.values())
    logger.info("Total discovered (deduped): %s", len(discovered))
    return discovered


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _list_k2_document_urls(client: Knowledge2, corpus_id: str) -> set[str]:
    """Best-effort list of document URLs already present in the corpus."""

    urls: set[str] = set()
    limit = 200
    offset = 0
    while True:
        resp = client.list_documents(corpus_id, limit=limit, offset=offset)
        docs = resp.get("documents") or []
        if not docs:
            break
        for d in docs:
            meta = d.get("metadata") or {}
            u = meta.get("source_url") or meta.get("url") or d.get("source_uri") or meta.get("source_uri") or ""
            u = _normalize_url(str(u))
            if u:
                urls.add(u)
        offset += len(docs)
    return urls


def _k2_url_item(doc: DiscoveredDoc) -> dict[str, Any]:
    meta: dict[str, Any] = {
        # Keep consistent with Bill47 citation mapping (api/intelligence/k2_client.py)
        "title": doc.title or "",
        "source_url": doc.url,
        "source_type": doc.source_type,
    }
    if not meta["title"]:
        meta.pop("title")

    return {
        "url": doc.url,
        "title": doc.title,
        "metadata": meta,
    }


def _wait_for_jobs(client: Knowledge2, job_ids: list[str], *, poll_s: int, timeout_s: float | None) -> None:
    start = time.monotonic()
    pending = set(job_ids)
    last_status: dict[str, str] = {}

    while pending:
        for job_id in list(pending):
            job = client.get_job(job_id)
            status = str(job.get("status") or "")
            if last_status.get(job_id) != status:
                logger.info("Job %s status=%s", job_id, status)
                last_status[job_id] = status

            if status in {"succeeded", "failed", "canceled"}:
                pending.remove(job_id)
                if status != "succeeded":
                    raise SystemExit(job.get("error_message") or f"Job {job_id} ended with status={status}")

        if pending:
            if timeout_s is not None and (time.monotonic() - start) > timeout_s:
                raise SystemExit(f"Timed out waiting for jobs: {sorted(pending)}")
            time.sleep(poll_s)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Discover URLs and ingest them into K2.")
    parser.add_argument("--config", default="pipeline/sources.yaml")
    parser.add_argument("--source", help="Source id from sources.yaml (default: all enabled sources)")
    parser.add_argument("--include-disabled", action="store_true", help="Include disabled sources")
    parser.add_argument("--max-projects", type=int, default=None, help="Override max projects for syc_projectfinder")
    parser.add_argument("--days-back", type=int, default=None, help="Override days_back for syc_projectfinder")
    parser.add_argument("--dry-run", action="store_true", help="Only print discovered URLs (no ingest)")
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip URLs already present in the K2 corpus (default: true). Use --no-skip-existing to re-ingest.",
    )
    parser.add_argument(
        "--auto-index",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Whether K2 should auto-index after URL ingestion. "
            "Default: true unless --build-indexes is set."
        ),
    )
    parser.add_argument("--batch-size", type=int, default=25, help="Number of URLs per K2 ingest_urls call")
    parser.add_argument("--wait", action="store_true", help="Wait for ingestion jobs to complete")
    parser.add_argument("--poll-s", type=int, default=3, help="Polling interval when --wait")
    parser.add_argument("--timeout-s", type=float, default=None, help="Max seconds to wait for all jobs when --wait")
    parser.add_argument("--build-indexes", action="store_true", help="Build sparse+dense indexes after ingest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    discovered = await _discover_docs(
        args.config,
        source_id=args.source,
        max_projects=args.max_projects,
        days_back=args.days_back,
        enabled_only=not args.include_disabled,
    )

    if args.dry_run:
        print("source_type\turl\ttitle")
        for d in sorted(discovered, key=lambda x: (x.source_type, x.url)):
            print(f"{d.source_type}\t{d.url}\t{d.title or ''}")
        return 0

    client = _k2_client_from_env()
    corpus_ref = _require_env("K2_CORPUS_ID")
    corpus_id = _resolve_corpus_id(client, corpus_ref)

    existing_urls: set[str] = set()
    if args.skip_existing:
        logger.info("Listing existing K2 corpus documents to skip already-ingested URLs...")
        existing_urls = _list_k2_document_urls(client, corpus_id)
        logger.info("Existing K2 URLs: %s", len(existing_urls))

    items: list[dict[str, Any]] = []
    skipped = 0
    for d in discovered:
        if args.skip_existing and _normalize_url(d.url) in existing_urls:
            skipped += 1
            continue
        items.append(_k2_url_item(d))

    logger.info(
        "K2 ingest plan: discovered=%s skipped_existing=%s to_ingest=%s",
        len(discovered),
        skipped,
        len(items),
    )
    batches = _chunked(items, max(args.batch_size, 1))

    # Default behavior:
    # - For initial bulk loads, prefer --build-indexes (which implies auto_index=false) to avoid
    #   triggering indexing repeatedly per batch.
    # - For incremental sync runs, default to auto_index=true so newly ingested docs are searchable
    #   without a full corpus re-index.
    if args.auto_index is None:
        auto_index = not args.build_indexes
    else:
        auto_index = bool(args.auto_index)

    job_ids: list[str] = []
    submitted_total = 0
    for batch in batches:
        if not batch:
            continue
        try:
            resp = client.ingest_urls(
                corpus_id,
                batch,
                auto_index=auto_index,
                wait=False,
            )
        except Knowledge2Error as exc:
            logger.error("K2 ingest_urls failed: %s", exc)
            raise SystemExit(2)

        job_id = resp.get("job_id")
        submitted = int(resp.get("submitted") or 0)
        submitted_total += submitted
        if job_id:
            job_ids.append(job_id)

        logger.info("Submitted batch: submitted=%s job_id=%s", submitted, job_id)

    logger.info(
        "All batches submitted: total_urls=%s total_submitted=%s jobs=%s",
        len(items),
        submitted_total,
        len(job_ids),
    )

    if args.wait and job_ids:
        _wait_for_jobs(client, job_ids, poll_s=max(args.poll_s, 1), timeout_s=args.timeout_s)
        logger.info("All ingestion jobs succeeded.")

    if args.build_indexes:
        logger.info("Building K2 indexes (dense+sparse)...")
        try:
            resp = client.build_indexes(corpus_id, dense=True, sparse=True, mode="full", wait=True, poll_s=2)
        except Knowledge2Error as exc:
            logger.error("K2 build_indexes failed: %s", exc)
            raise SystemExit(2)
        logger.info("Index build response: %s", resp)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
