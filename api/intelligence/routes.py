"""
FastAPI router for VanCity Lens intelligence endpoints.

Provides REST API access to:
- RAG-powered chat with document context
- Intelligence signal feeds and filtering
- Spatial signal queries (near parcels)
- Dashboard statistics
- Admin operations (scraping, extraction, processing)
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import HTMLResponse

from ..auth import require_admin
from ..rate_limit import rate_limit_llm

from .chat import handle_chat
from .chat_sessions import (
    create_session,
    get_session,
    list_sessions,
    get_session_history,
    delete_session,
)
from .models import (
    ChatRequest,
    ChatResponse,
    SignalResponse,
    SignalFeedResponse,
    NeighborhoodSummary,
    NeighborhoodScorecard,
    NeighborhoodComparison,
    ChatSession,
    ChatSessionList,
    ChatMessageHistory,
    IngestUrlRequest,
    IngestUrlResponse,
    DocumentViewResponse,
    DocumentStatusResponse,
    SearchConfigRequest,
    SearchConfigResponse,
)
from .signals import (
    get_signal_feed,
    get_signal_by_id,
    get_signal_document,
    get_signals_for_parcel,
    get_signal_stats,
    get_neighborhoods,
    get_signals_geojson,
)
from . import alert_routes
from . import opportunity_routes
from . import digest_routes
from . import pipeline_routes
from . import scraper_schools_routes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/intel", tags=["intelligence"])

# Include alert routes
router.include_router(alert_routes.router)

# Include opportunity routes
router.include_router(opportunity_routes.router)

# Include digest routes
router.include_router(digest_routes.router)

# Include pipeline routes
router.include_router(pipeline_routes.router)

# Include scraper schools routes
router.include_router(scraper_schools_routes.router)


# ── Utility: Get API keys from environment ────────────────────────────


def _normalize_api_key(raw: Optional[str]) -> Optional[str]:
    """
    Treat common docker-compose placeholder values as "not configured".

    This keeps local dev in DEMO mode unless real keys are provided.
    """
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if key in {"sk-placeholder", "placeholder"}:
        return None
    return key


def get_anthropic_api_key() -> str:
    """Get Anthropic API key from environment. Raises 500 if missing."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.error("ANTHROPIC_API_KEY not set in environment")
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY not configured. Please set the environment variable.",
        )
    return key


def get_cohere_api_key() -> str:
    """Get Cohere API key from environment. Raises 500 if missing."""
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        logger.error("COHERE_API_KEY not set in environment")
        raise HTTPException(
            status_code=500,
            detail="COHERE_API_KEY not configured. Please set the environment variable.",
        )
    return key


def get_anthropic_api_key_optional() -> Optional[str]:
    """Get Anthropic API key from environment, or None if not set."""
    return _normalize_api_key(os.environ.get("ANTHROPIC_API_KEY"))


def get_cohere_api_key_optional() -> Optional[str]:
    """Get Cohere API key from environment, or None if not set."""
    return _normalize_api_key(os.environ.get("COHERE_API_KEY"))


def get_db_pool(request: Request) -> asyncpg.Pool:
    """Get database pool from app state."""
    pool = getattr(request.app.state, "pool", None)
    if not pool:
        logger.error("Database pool not initialized")
        raise HTTPException(
            status_code=500,
            detail="Database connection not available",
        )
    return pool


# ── Chat Endpoint ────────────────────────────────────────────────────


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with intelligence system",
    description=(
        "RAG-powered chat endpoint. Accepts a natural language query, retrieves "
        "relevant document chunks via hybrid search (Cohere + BM25), and returns "
        "an AI-generated answer with citations and related signals."
    ),
    dependencies=[Depends(rate_limit_llm)],
)
async def post_chat(request: Request, chat_request: ChatRequest) -> ChatResponse:
    """
    Ask a question about Vancouver development, zoning, or real estate intelligence.

    Operates in three tiers based on available API keys:
    - FULL:    Anthropic + Cohere → hybrid search + Claude RAG
    - PARTIAL: Anthropic only    → sparse (BM25) search + Claude RAG
    - DEMO:    No keys           → sparse (BM25) search + formatted results
    """
    try:
        db_pool = get_db_pool(request)
        anthropic_key = get_anthropic_api_key_optional()
        cohere_key = get_cohere_api_key_optional()

        # Log operating mode
        if anthropic_key and cohere_key:
            mode = "FULL"
        elif anthropic_key:
            mode = "PARTIAL"
        else:
            mode = "DEMO"
        logger.info(f"Chat query received ({mode} mode): {chat_request.query[:100]}...")

        response = await handle_chat(
            db_pool=db_pool,
            query=chat_request.query,
            anthropic_api_key=anthropic_key,
            cohere_api_key=cohere_key,
            session_id=chat_request.session_id,
            neighborhood_filter=chat_request.neighborhood_filter,
            date_from=chat_request.date_from,
            date_to=chat_request.date_to,
        )

        logger.info(f"Chat response generated with session_id: {response.session_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}",
        )


# ── Signal Feed Endpoints ─────────────────────────────────────────────


@router.get(
    "/signals",
    response_model=SignalFeedResponse,
    summary="Get signal feed",
    description=(
        "Retrieve a paginated feed of intelligence signals with optional filtering "
        "by neighborhood, type, severity, and date range."
    ),
)
async def get_signals(
    request: Request,
    neighborhood: Optional[str] = Query(
        None, description="Filter by neighborhood name"
    ),
    signal_type: Optional[str] = Query(
        None,
        description="Filter by signal type (e.g., rezoning_decision, permit_approval)",
    ),
    severity_min: Optional[str] = Query(
        None,
        description="Minimum severity level (info, low, medium, high, critical)",
    ),
    date_range: Optional[str] = Query(
        None,
        description="Convenience lookback window: 7d|30d|90d|all (client-friendly alias for date_from/date_to)",
    ),
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> SignalFeedResponse:
    """
    Get a paginated feed of intelligence signals with filtering.

    Results are sorted by event_date (most recent first).
    """
    try:
        db_pool = get_db_pool(request)

        logger.info(
            f"Signal feed query: neighborhood={neighborhood}, type={signal_type}, "
            f"severity_min={severity_min}, limit={limit}, offset={offset}"
        )

        effective_date_from = date_from
        effective_date_to = date_to
        if effective_date_from is None and effective_date_to is None and date_range:
            dr = date_range.strip().lower()
            if dr != "all":
                try:
                    days = int(dr[:-1]) if dr.endswith("d") else int(dr)
                    effective_date_from = date.today() - timedelta(days=days)
                    effective_date_to = date.today()
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid date_range: {date_range}")

        feed = await get_signal_feed(
            db_pool=db_pool,
            neighborhood=neighborhood,
            signal_type=signal_type,
            severity_min=severity_min,
            date_from=effective_date_from,
            date_to=effective_date_to,
            limit=limit,
            offset=offset,
        )

        return feed

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signal feed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve signals: {str(e)}",
        )


@router.get(
    "/signals/geojson",
    summary="Get signals as GeoJSON for map overlay",
    description=(
        "Return geocoded intelligence signals as a GeoJSON FeatureCollection "
        "for rendering on the map. Only includes signals with coordinates."
    ),
)
async def get_signals_geojson_endpoint(
    request: Request,
    limit: int = Query(200, ge=1, le=1000, description="Max number of signals"),
    days: int = Query(90, ge=1, le=365, description="Look back window in days"),
):
    """
    Get intelligence signals as GeoJSON for the map overlay layer.
    """
    try:
        db_pool = get_db_pool(request)
        geojson = await get_signals_geojson(db_pool, limit=limit, days=days)
        return geojson
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating signals GeoJSON: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate signals GeoJSON: {str(e)}",
        )


@router.get(
    "/signals/parcel/{pid}",
    response_model=list[SignalResponse],
    summary="Get signals near a parcel",
    description=(
        "Retrieve intelligence signals within a specified radius of a parcel "
        "(using spatial proximity via PostGIS). Useful for contextualizing parcel details."
    ),
)
async def get_parcel_signals(
    request: Request,
    pid: str,
    radius: int = Query(500, ge=100, le=5000, description="Search radius in metres"),
) -> list[SignalResponse]:
    """
    Find intelligence signals near a specific parcel.

    Uses PostGIS spatial queries to find signals within the specified radius.
    """
    try:
        db_pool = get_db_pool(request)

        logger.info(f"Fetching signals for parcel {pid} within {radius}m")

        signals = await get_signals_for_parcel(db_pool, pid, radius)

        logger.info(f"Found {len(signals)} signals for parcel {pid}")
        return signals

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signals for parcel {pid}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve parcel signals: {str(e)}",
        )


@router.get(
    "/signals/{signal_id}/document",
    summary="Get signal's source document",
    description=(
        "Retrieve the full source document content linked to a signal, "
        "including the document's raw text and the signal's extracted details."
    ),
)
async def get_signal_document_endpoint(request: Request, signal_id: int):
    """
    Get the source document and extracted details for a signal.

    Returns the document title, source type, published date, raw text content,
    plus the signal's extracted metadata (decision, vote, zoning changes, etc).
    """
    try:
        db_pool = get_db_pool(request)

        result = await get_signal_document(db_pool, signal_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Signal {signal_id} not found",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document for signal {signal_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve signal document: {str(e)}",
        )


@router.get(
    "/documents/{document_id}/view",
    response_model=DocumentViewResponse,
    summary="RAG-001: View archived document content",
    description=(
        "View the cached/archived content of a document. Useful when the original "
        "source_url is dead or inaccessible. Returns the stored raw_text with "
        "URL health status and archive fallback link."
    ),
)
async def get_document_view(request: Request, document_id: int) -> DocumentViewResponse:
    """
    View archived document content (RAG-001).

    Returns the stored raw_text along with URL health info and archive fallback.
    """
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, source_url, source_type, published_date,
                       raw_text, text_length, page_count, url_status, archive_url
                FROM documents WHERE id = $1
                """,
                document_id,
            )

        if not row:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        return DocumentViewResponse(
            id=row["id"],
            title=row["title"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            published_date=row["published_date"],
            raw_text=row["raw_text"] or "",
            text_length=row["text_length"] or 0,
            page_count=row["page_count"] or 0,
            url_status=row["url_status"],
            archive_url=row["archive_url"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing document {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to view document: {str(e)}")


@router.get(
    "/documents/{document_id}/page",
    response_class=HTMLResponse,
    summary="Render document as readable HTML page",
    description="Serves the cached document content as a styled HTML page for demo/viewing.",
)
async def get_document_page(request: Request, document_id: int):
    """Render a document as a standalone HTML page."""
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT d.id, d.title, d.source_url, d.source_type, d.published_date,
                       d.raw_text, d.url_status, d.archive_url,
                       (SELECT COUNT(*) FROM intelligence_signals s WHERE s.document_id = d.id) AS signal_count
                FROM documents d WHERE d.id = $1
                """,
                document_id,
            )

        if not row:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        import html as html_mod

        title = html_mod.escape(row["title"] or "Untitled Document")
        source_type = (row["source_type"] or "document").replace("_", " ").title()
        pub_date = str(row["published_date"]) if row["published_date"] else ""
        raw_text = html_mod.escape(row["raw_text"] or "No content available.")
        source_url = html_mod.escape(row["source_url"] or "")
        url_status = row["url_status"] or "unchecked"
        signal_count = row["signal_count"] or 0

        # Build source-box link/label based on URL health status
        if url_status == "dead":
            source_link_html = f'<span style="color: #64748b; word-break: break-all;">{source_url}</span>'
            status_html = "Content served from VanCity Lens intelligence archive"
        elif url_status == "alive":
            source_link_html = f'<a href="{source_url}" target="_blank" rel="noopener">{source_url}</a>'
            status_html = f'<a href="{source_url}" target="_blank" rel="noopener" style="color: #86efac;">Live — visit original source &rarr;</a>'
        else:
            source_link_html = f'<a href="{source_url}" target="_blank" rel="noopener">{source_url}</a>'
            status_html = f'<a href="{source_url}" target="_blank" rel="noopener" style="color: #94a3b8;">Visit original source (unverified) &rarr;</a>'

        # Convert plain text paragraphs to HTML
        paragraphs = raw_text.split("\n")
        body_html = "\n".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

        page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} — VanCity Lens</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Georgia', 'Times New Roman', serif; background: #0f172a; color: #e2e8f0; line-height: 1.8; }}
  .banner {{ background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%); border-bottom: 1px solid #334155; padding: 12px 0; text-align: center; font-size: 13px; color: #94a3b8; font-family: system-ui, sans-serif; }}
  .banner a {{ color: #60a5fa; text-decoration: none; font-weight: 600; }}
  .container {{ max-width: 720px; margin: 0 auto; padding: 40px 24px 80px; }}
  .meta {{ font-family: system-ui, sans-serif; margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid #334155; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
  .badge-type {{ background: #1e3a5f; color: #93c5fd; }}
  .badge-signals {{ background: #1a2e1a; color: #86efac; }}
  .badge-status {{ background: #3b1a1a; color: #fca5a5; }}
  h1 {{ font-size: 28px; font-weight: 700; color: #f1f5f9; margin: 16px 0 12px; line-height: 1.3; }}
  .pub-info {{ font-size: 14px; color: #94a3b8; font-family: system-ui, sans-serif; margin-top: 8px; }}
  .content p {{ margin-bottom: 1.2em; font-size: 17px; color: #cbd5e1; }}
  .source-box {{ margin-top: 40px; padding: 16px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; font-family: system-ui, sans-serif; font-size: 13px; color: #94a3b8; }}
  .source-box a {{ color: #60a5fa; word-break: break-all; }}
  .footer {{ text-align: center; margin-top: 48px; padding-top: 24px; border-top: 1px solid #1e293b; font-size: 12px; color: #475569; font-family: system-ui, sans-serif; }}
</style>
</head>
<body>
  <div class="banner">Cached document from <a href="/">VanCity Lens</a> intelligence archive</div>
  <div class="container">
    <div class="meta">
      <span class="badge badge-type">{source_type}</span>
      {"" if not signal_count else f' <span class="badge badge-signals">{signal_count} signal{"s" if signal_count != 1 else ""} extracted</span>'}
      {' <span class="badge badge-status">Source offline</span>' if url_status == "dead" else ""}
      <h1>{title}</h1>
      <div class="pub-info">
        {"Published " + pub_date + " &middot; " if pub_date else ""}Document ID {document_id}
      </div>
    </div>
    <div class="content">
      {body_html}
    </div>
    <div class="source-box">
      <strong>Original source:</strong> {source_link_html}
      <br><strong>Status:</strong> {status_html}
    </div>
    <div class="footer">VanCity Lens &mdash; Intelligence for Vancouver Real Estate Development</div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=page_html)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rendering document page {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to render document: {str(e)}")


@router.get(
    "/documents/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="RAG-011: Poll document processing status",
    description=(
        "Check the processing status of a document. Use after ingestion to poll "
        "whether chunking, embedding, and signal extraction have completed."
    ),
)
async def get_document_status(request: Request, document_id: int) -> DocumentStatusResponse:
    """
    Poll document processing status (RAG-011).

    Returns the current state: pending (no raw_text), processing (has text but
    not yet processed), completed (processed_at set), or failed.
    """
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT d.id, d.title, d.raw_text IS NOT NULL AS has_raw_text,
                       d.scraped_at, d.processed_at,
                       (SELECT COUNT(*) FROM document_chunks dc WHERE dc.document_id = d.id) AS chunk_count,
                       (SELECT COUNT(*) FROM intelligence_signals isig WHERE isig.document_id = d.id) AS signal_count
                FROM documents d WHERE d.id = $1
                """,
                document_id,
            )

        if not row:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        # Determine status
        if row["processed_at"]:
            status = "completed"
        elif row["has_raw_text"] and row["chunk_count"] > 0:
            status = "processing"
        elif row["has_raw_text"]:
            status = "processing"
        else:
            status = "pending"

        return DocumentStatusResponse(
            document_id=row["id"],
            title=row["title"],
            status=status,
            has_raw_text=row["has_raw_text"],
            chunk_count=row["chunk_count"],
            signal_count=row["signal_count"],
            scraped_at=row["scraped_at"],
            processed_at=row["processed_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document status {document_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get document status: {str(e)}")


@router.get(
    "/signals/{signal_id}",
    response_model=SignalResponse,
    summary="Get single signal",
    description="Retrieve detailed information about a specific intelligence signal.",
)
async def get_signal_detail(request: Request, signal_id: int) -> SignalResponse:
    """
    Get a single intelligence signal by ID with full source information.
    """
    try:
        db_pool = get_db_pool(request)

        signal = await get_signal_by_id(db_pool, signal_id)

        if not signal:
            raise HTTPException(
                status_code=404,
                detail=f"Signal {signal_id} not found",
            )

        return signal

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signal {signal_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve signal: {str(e)}",
        )


# ── Statistics Endpoint ───────────────────────────────────────────────


@router.get(
    "/stats",
    summary="Dashboard statistics",
    description="Get aggregate statistics on intelligence signals (counts by type, neighborhood, severity).",
)
async def get_stats(request: Request):
    """
    Get dashboard statistics on intelligence signals.

    Returns aggregate counts by signal type, neighborhood, and severity,
    as well as recent activity metrics (7d, 30d).
    """
    try:
        db_pool = get_db_pool(request)

        logger.info("Fetching signal statistics")

        stats = await get_signal_stats(db_pool)

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signal statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve statistics: {str(e)}",
        )


# ── Neighborhoods Endpoint ────────────────────────────────────────────


@router.get(
    "/neighborhoods",
    response_model=list[str],
    summary="List all neighborhoods",
    description=(
        "Get a list of all distinct neighborhoods present in the intelligence signal database. "
        "Useful for populating filter dropdowns."
    ),
)
async def get_all_neighborhoods(request: Request) -> list[str]:
    """
    Get all distinct neighborhoods with intelligence signals.

    Returns a sorted list of neighborhood names.
    """
    try:
        db_pool = get_db_pool(request)

        logger.info("Fetching neighborhoods")

        neighborhoods = await get_neighborhoods(db_pool)

        return neighborhoods

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving neighborhoods: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve neighborhoods: {str(e)}",
        )


# ── Admin Endpoints ───────────────────────────────────────────────────


async def _background_scrape_task(
    db_pool: asyncpg.Pool, source: str, days_back: int
):
    """
    Background task for document scraping.

    Calls the actual scraper functions based on source type.
    """
    logger.info(f"Background scraping started: source={source}, days_back={days_back}")
    try:
        from datetime import datetime, timedelta
        from .scraper_council import scrape_and_store as scrape_council
        from .scraper_rezoning import scrape_and_store as scrape_rezoning
        from .scraper_dpb import download_and_store as scrape_dpb
        from .scraper_news import scrape_news_feeds

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        if source in ('council', 'all'):
            logger.info("Scraping council minutes...")
            await scrape_council(db_pool, start_date, end_date)

        if source in ('rezoning', 'all'):
            logger.info("Scraping rezoning applications...")
            await scrape_rezoning(db_pool)

        if source in ('dpb', 'all'):
            logger.info("Scraping DPB minutes...")
            await scrape_dpb(db_pool)

        if source in ('news', 'all'):
            logger.info("Scraping news feeds...")
            await scrape_news_feeds(db_pool, days_back=days_back)

        logger.info(f"Scraping complete: source={source}")
    except Exception as e:
        logger.error(f"Background scraping failed: {e}", exc_info=True)


async def _background_process_task(db_pool: asyncpg.Pool, batch_size: int):
    """
    Background task for document processing (chunking + embedding + extraction).

    Processes unprocessed documents through the full pipeline:
    1. Chunk with semchunk
    2. Embed with Cohere
    3. Extract signals with Claude
    """
    logger.info(f"Background processing started: batch_size={batch_size}")
    try:
        cohere_key = os.environ.get("COHERE_API_KEY", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

        from .embeddings import process_document_chunks
        from .extractor import process_document

        # Get unprocessed documents
        async with db_pool.acquire() as conn:
            doc_ids = await conn.fetch(
                """
                SELECT id FROM documents
                WHERE processed_at IS NULL AND raw_text IS NOT NULL
                ORDER BY scraped_at DESC
                LIMIT $1
                """,
                batch_size
            )

        if not doc_ids:
            logger.info("No unprocessed documents found")
            return

        logger.info(f"Processing {len(doc_ids)} documents")

        # Process documents concurrently; vendor calls are concurrency-limited globally
        async def _process_one(doc_id: int):
            try:
                chunks_stored = await process_document_chunks(db_pool, doc_id, cohere_key)
                logger.info(f"Doc {doc_id}: {chunks_stored} chunks embedded")

                signals_stored = await process_document(db_pool, doc_id, anthropic_key)
                logger.info(f"Doc {doc_id}: {signals_stored} signals extracted")
            except Exception as e:
                logger.error(f"Failed to process document {doc_id}: {e}", exc_info=True)

        tasks = [_process_one(row["id"]) for row in doc_ids]
        await asyncio.gather(*tasks)

        logger.info("Processing complete")
    except Exception as e:
        logger.error(f"Background processing failed: {e}", exc_info=True)


@router.post(
    "/admin/scrape",
    summary="Admin: trigger document scraping",
    dependencies=[Depends(require_admin)],
    description=(
        "Start a background scraping task to fetch documents from City of Vancouver sources. "
        "This is an admin-only operation. Runs asynchronously."
    ),
)
async def admin_trigger_scrape(
    request: Request,
    background_tasks: BackgroundTasks,
    source: str = Query(
        "all",
        description="Document source to scrape: council, rezoning, dpb, or all",
    ),
    days_back: int = Query(
        180, ge=1, le=3650, description="How many days back to scrape"
    ),
):
    """
    Trigger document scraping in the background.

    Supported sources: council, rezoning, dpb, all

    Returns immediately; scraping continues asynchronously.
    """
    try:
        # Validate source
        valid_sources = ["council", "rezoning", "dpb", "news", "all"]
        if source not in valid_sources:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source. Must be one of: {', '.join(valid_sources)}",
            )

        db_pool = get_db_pool(request)

        logger.info(f"Admin scrape initiated: source={source}, days_back={days_back}")

        # Schedule background task
        background_tasks.add_task(_background_scrape_task, db_pool, source, days_back)

        return {
            "status": "scraping started",
            "source": source,
            "days_back": days_back,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating scrape: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate scraping: {str(e)}",
        )


@router.post(
    "/admin/process",
    summary="Admin: trigger AI extraction and embedding",
    dependencies=[Depends(require_admin), Depends(rate_limit_llm)],
    description=(
        "Start a background task to process unprocessed documents: chunk with semchunk, "
        "embed with Cohere, and extract intelligence signals using Claude. "
        "This is an admin-only operation. Runs asynchronously."
    ),
)
async def admin_trigger_process(
    request: Request,
    background_tasks: BackgroundTasks,
    batch_size: int = Query(
        10,
        ge=1,
        le=100,
        description="Number of documents to process in parallel",
    ),
):
    """
    Trigger document processing (chunking + embedding + extraction) in the background.

    Processing includes:
    - Semantic chunking via semchunk
    - Cohere embeddings for hybrid search (dense + BM25 sparse)
    - LLM-based signal extraction from each chunk
    - Storage of results in database

    Returns immediately; processing continues asynchronously.
    """
    try:
        db_pool = get_db_pool(request)

        logger.info(f"Admin process initiated: batch_size={batch_size}")

        # Schedule background task
        background_tasks.add_task(_background_process_task, db_pool, batch_size)

        return {
            "status": "processing started",
            "batch_size": batch_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating processing: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate processing: {str(e)}",
        )


@router.get(
    "/admin/feeds",
    summary="Admin: list configured news feeds",
    dependencies=[Depends(require_admin)],
    description="Get the list of all configured RSS/news feeds and their settings.",
)
async def admin_get_feeds():
    """Return the list of configured news feeds with their URLs and priorities."""
    try:
        from .scraper_news import get_configured_feeds

        feeds = await get_configured_feeds()
        return {"feeds": feeds, "count": len(feeds)}

    except Exception as e:
        logger.error(f"Error listing feeds: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list feeds: {str(e)}",
        )


@router.get(
    "/admin/status",
    summary="Admin: get ingestion status",
    dependencies=[Depends(require_admin)],
    description=(
        "Get statistics on the document ingestion pipeline: "
        "how many documents are scraped, processed, chunked, etc."
    ),
)
async def admin_get_status(request: Request):
    """
    Get detailed status of the document ingestion pipeline.

    Returns counts of:
    - Total documents
    - Documents processed (with signals extracted)
    - Documents unprocessed
    - Total document chunks
    - Total intelligence signals
    """
    try:
        db_pool = get_db_pool(request)

        logger.info("Admin status query")

        async with db_pool.acquire() as conn:
            # Get document stats
            doc_stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_documents,
                    COUNT(CASE WHEN processed_at IS NOT NULL THEN 1 END) AS processed_documents,
                    COUNT(CASE WHEN processed_at IS NULL THEN 1 END) AS unprocessed_documents
                FROM documents
                """
            )

            # Get chunk stats
            chunk_stats = await conn.fetchrow(
                """
                SELECT COUNT(*) AS total_chunks
                FROM document_chunks
                """
            )

            # Get signal stats
            signal_stats = await conn.fetchrow(
                """
                SELECT COUNT(*) AS total_signals
                FROM intelligence_signals
                """
            )

        return {
            "documents": {
                "total": doc_stats["total_documents"],
                "processed": doc_stats["processed_documents"],
                "unprocessed": doc_stats["unprocessed_documents"],
            },
            "chunks": chunk_stats["total_chunks"],
            "signals": signal_stats["total_signals"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}",
        )


# ── URL Ingestion Endpoints ─────────────────────────────────────────


async def _background_ingest_url_process(db_pool: asyncpg.Pool, document_id: int):
    """Background task: chunk, embed, and extract signals from an ingested URL document."""
    logger.info(f"Background processing started for ingested document {document_id}")
    try:
        cohere_key = os.environ.get("COHERE_API_KEY", "")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

        from .embeddings import process_document_chunks
        from .extractor import process_document

        chunks_stored = await process_document_chunks(db_pool, document_id, cohere_key)
        logger.info(f"Ingested doc {document_id}: {chunks_stored} chunks embedded")

        signals_stored = await process_document(db_pool, document_id, anthropic_key)
        logger.info(f"Ingested doc {document_id}: {signals_stored} signals extracted")
    except Exception as e:
        logger.error(f"Background processing failed for document {document_id}: {e}", exc_info=True)


@router.post(
    "/admin/ingest-url",
    response_model=IngestUrlResponse,
    summary="Admin: ingest a document from URL",
    dependencies=[Depends(require_admin)],
    description=(
        "Download a document from an external URL (PDF or HTML), parse it, store it, "
        "and automatically trigger the full intelligence pipeline (chunk, embed, extract). "
        "Admin-only. Returns immediately; processing continues in background."
    ),
)
async def admin_ingest_url(
    request: Request,
    body: IngestUrlRequest,
    background_tasks: BackgroundTasks,
) -> IngestUrlResponse:
    """
    Ingest a document from a URL with full pipeline processing.

    Downloads, parses (PDF or HTML), stores in documents table,
    then runs chunking + embedding + signal extraction in background.
    Duplicate URLs return the existing document without reprocessing.
    """
    try:
        from .scraper_url import scrape_url

        db_pool = get_db_pool(request)

        result = await scrape_url(
            db_pool, body.url, source_type=body.source_type, title=body.title
        )

        processing = False
        if result["status"] == "new":
            background_tasks.add_task(
                _background_ingest_url_process, db_pool, result["document_id"]
            )
            processing = True

        return IngestUrlResponse(
            document_id=result["document_id"],
            title=result["title"],
            text_length=result["text_length"],
            page_count=result["page_count"],
            status=result["status"],
            processing=processing,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ingest URL: {str(e)}",
        )


@router.post(
    "/ingest-url",
    response_model=IngestUrlResponse,
    summary="Ingest a document from URL",
    dependencies=[Depends(rate_limit_llm)],
    description=(
        "Download a document from an external URL (PDF or HTML), parse it, store it, "
        "and automatically trigger the full intelligence pipeline. "
        "Rate-limited since it triggers LLM extraction."
    ),
)
async def public_ingest_url(
    request: Request,
    body: IngestUrlRequest,
    background_tasks: BackgroundTasks,
) -> IngestUrlResponse:
    """
    Ingest a document from a URL (public, rate-limited).

    Same as admin endpoint but with LLM rate limiting applied.
    """
    try:
        from .scraper_url import scrape_url

        db_pool = get_db_pool(request)

        result = await scrape_url(
            db_pool, body.url, source_type=body.source_type, title=body.title
        )

        processing = False
        if result["status"] == "new":
            background_tasks.add_task(
                _background_ingest_url_process, db_pool, result["document_id"]
            )
            processing = True

        return IngestUrlResponse(
            document_id=result["document_id"],
            title=result["title"],
            text_length=result["text_length"],
            page_count=result["page_count"],
            status=result["status"],
            processing=processing,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ingest URL: {str(e)}",
        )


# ── RAG-002 + RAG-003: URL Health Check Endpoints ──────────────────


@router.post(
    "/admin/url-health-check",
    summary="Admin: check source URL health",
    dependencies=[Depends(require_admin)],
    description=(
        "Check liveness of document source URLs. Marks dead URLs and auto-generates "
        "Internet Archive (Wayback Machine) fallback links. Runs in background."
    ),
)
async def admin_url_health_check(
    request: Request,
    background_tasks: BackgroundTasks,
    limit: int = Query(100, ge=1, le=1000, description="Max URLs to check"),
    recheck_hours: int = Query(24, ge=1, le=720, description="Skip URLs checked within this window"),
):
    """Trigger URL health checking for document source URLs."""
    try:
        from .url_health import check_document_urls

        db_pool = get_db_pool(request)

        async def _run_health_check(pool, lim, hrs):
            stats = await check_document_urls(pool, limit=lim, recheck_hours=hrs)
            logger.info(f"URL health check complete: {stats}")

        background_tasks.add_task(_run_health_check, db_pool, limit, recheck_hours)

        return {
            "status": "url_health_check_started",
            "limit": limit,
            "recheck_hours": recheck_hours,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating URL health check: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start URL health check: {str(e)}")


@router.get(
    "/admin/url-health-stats",
    summary="Admin: URL health statistics",
    dependencies=[Depends(require_admin)],
    description="Get aggregate URL health status across all documents.",
)
async def admin_url_health_stats(request: Request):
    """Get URL health statistics."""
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT url_status, COUNT(*) AS cnt
                FROM documents
                GROUP BY url_status
                ORDER BY cnt DESC
                """
            )

        stats = {row["url_status"] or "unchecked": row["cnt"] for row in rows}
        total = sum(stats.values())

        return {
            "total_documents": total,
            "by_status": stats,
            "dead_count": stats.get("dead", 0),
            "alive_count": stats.get("alive", 0),
            "unchecked_count": stats.get("unchecked", 0),
        }

    except Exception as e:
        logger.error(f"Error getting URL health stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get URL health stats")


# ── RAG-007: Search Configuration Endpoints ────────────────────────


@router.get(
    "/admin/search-config",
    response_model=SearchConfigResponse,
    summary="Admin: get search configuration",
    dependencies=[Depends(require_admin)],
    description="Get current hybrid search weight configuration.",
)
async def admin_get_search_config(request: Request) -> SearchConfigResponse:
    """Get current search configuration."""
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT vector_weight, text_weight, rrf_k, rerank_enabled, updated_at FROM search_config ORDER BY id DESC LIMIT 1"
            )

        if not row:
            return SearchConfigResponse(
                vector_weight=0.5, text_weight=0.5, rrf_k=60, rerank_enabled=True
            )

        return SearchConfigResponse(
            vector_weight=float(row["vector_weight"]),
            text_weight=float(row["text_weight"]),
            rrf_k=row["rrf_k"],
            rerank_enabled=row["rerank_enabled"],
            updated_at=row["updated_at"],
        )

    except Exception as e:
        logger.error(f"Error getting search config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get search config")


@router.post(
    "/admin/search-config",
    response_model=SearchConfigResponse,
    summary="Admin: update search configuration",
    dependencies=[Depends(require_admin)],
    description="Update hybrid search weights, RRF k, and reranking toggle.",
)
async def admin_update_search_config(
    request: Request,
    body: SearchConfigRequest,
) -> SearchConfigResponse:
    """Update search configuration."""
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            # Get current config
            current = await conn.fetchrow(
                "SELECT vector_weight, text_weight, rrf_k, rerank_enabled FROM search_config ORDER BY id DESC LIMIT 1"
            )

            vw = body.vector_weight if body.vector_weight is not None else (float(current["vector_weight"]) if current else 0.5)
            tw = body.text_weight if body.text_weight is not None else (float(current["text_weight"]) if current else 0.5)
            rk = body.rrf_k if body.rrf_k is not None else (current["rrf_k"] if current else 60)
            re = body.rerank_enabled if body.rerank_enabled is not None else (current["rerank_enabled"] if current else True)

            row = await conn.fetchrow(
                """
                UPDATE search_config
                SET vector_weight = $1, text_weight = $2, rrf_k = $3,
                    rerank_enabled = $4, updated_at = NOW(), updated_by = 'admin'
                WHERE id = (SELECT id FROM search_config ORDER BY id DESC LIMIT 1)
                RETURNING vector_weight, text_weight, rrf_k, rerank_enabled, updated_at
                """,
                vw, tw, rk, re,
            )

        if not row:
            raise HTTPException(status_code=500, detail="No search config row to update")

        logger.info(f"Search config updated: vw={vw}, tw={tw}, rrf_k={rk}, rerank={re}")

        return SearchConfigResponse(
            vector_weight=float(row["vector_weight"]),
            text_weight=float(row["text_weight"]),
            rrf_k=row["rrf_k"],
            rerank_enabled=row["rerank_enabled"],
            updated_at=row["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating search config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update search config")


# ── RAG-012: Scheduler Admin Endpoints ────────────────────────────


@router.get(
    "/admin/scheduler/status",
    summary="Admin: get scraper scheduler status",
    dependencies=[Depends(require_admin)],
    description="Get status of all registered scrapers including schedule, last/next run, and enabled state.",
)
async def admin_scheduler_status(request: Request):
    """Get scheduler status for all registered scrapers (RAG-012)."""
    try:
        from .scheduler import ScraperScheduler

        db_pool = get_db_pool(request)
        scheduler = ScraperScheduler(db_pool)
        return scheduler.get_status()
    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get scheduler status")


@router.post(
    "/admin/scheduler/{scraper_name}/trigger",
    summary="Admin: manually trigger a scraper",
    dependencies=[Depends(require_admin)],
    description="Manually trigger a named scraper (council, dpb, rezoning, news, opendata). Runs in background.",
)
async def admin_scheduler_trigger(
    request: Request,
    scraper_name: str,
    background_tasks: BackgroundTasks,
):
    """Manually trigger a scraper run (RAG-012)."""
    valid_names = ["council", "dpb", "rezoning", "news", "opendata"]
    if scraper_name not in valid_names:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scraper. Must be one of: {', '.join(valid_names)}",
        )

    try:
        db_pool = get_db_pool(request)

        background_tasks.add_task(
            _background_scrape_task, db_pool, scraper_name, 7
        )

        return {
            "status": "triggered",
            "scraper_name": scraper_name,
        }
    except Exception as e:
        logger.error(f"Error triggering scraper {scraper_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraper: {str(e)}")


@router.get(
    "/admin/scheduler/history",
    summary="Admin: get scraper run history",
    dependencies=[Depends(require_admin)],
    description="Get recent scraper run history from the scraper_runs table.",
)
async def admin_scheduler_history(
    request: Request,
    scraper_name: Optional[str] = Query(None, description="Filter by scraper name"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
):
    """Get recent scraper run history (RAG-012)."""
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            if scraper_name:
                rows = await conn.fetch(
                    """
                    SELECT scraper_name, started_at, completed_at, status,
                           documents_found, documents_new, documents_skipped, errors
                    FROM scraper_runs
                    WHERE scraper_name = $1
                    ORDER BY started_at DESC LIMIT $2
                    """,
                    scraper_name, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT scraper_name, started_at, completed_at, status,
                           documents_found, documents_new, documents_skipped, errors
                    FROM scraper_runs
                    ORDER BY started_at DESC LIMIT $1
                    """,
                    limit,
                )

        import json as json_mod
        runs = []
        for row in rows:
            errors_raw = row["errors"]
            if isinstance(errors_raw, str):
                try:
                    errors_raw = json_mod.loads(errors_raw)
                except Exception:
                    errors_raw = [errors_raw] if errors_raw else []
            runs.append({
                "scraper_name": row["scraper_name"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "status": row["status"],
                "documents_found": row["documents_found"],
                "documents_new": row["documents_new"],
                "documents_skipped": row["documents_skipped"],
                "errors": errors_raw or [],
            })

        return {"runs": runs, "count": len(runs)}

    except Exception as e:
        logger.error(f"Error getting scheduler history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get scheduler history")


@router.post(
    "/admin/scrape-opendata",
    summary="Admin: trigger open data scraping for neighborhood metrics",
    dependencies=[Depends(require_admin)],
    description=(
        "Start a background task to scrape open data sources (crime, parks, transit, "
        "permits, property tax), persist metrics, and compute neighborhood scores."
    ),
)
async def admin_trigger_opendata_scrape(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Trigger open data scraping pipeline in the background.

    Scrapes: VPD crime, CoV parks, TransLink transit, CoV permits, CoV property tax.
    Then persists metrics and computes normalized scores + composite rankings.
    """
    try:
        db_pool = get_db_pool(request)

        async def _run_opendata_scrapers(pool):
            import aiohttp
            from .scraper_opendata import run_all_scrapers
            async with aiohttp.ClientSession() as session:
                results = await run_all_scrapers(session, pool)
                logger.info("Open data scraping results: %s", results)

        background_tasks.add_task(_run_opendata_scrapers, db_pool)

        return {
            "status": "open data scraping started",
            "sources": ["vpd_crime", "cov_parks", "translink_transit", "development", "cov_permits", "cov_property_tax"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error initiating open data scrape: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate open data scraping: {str(e)}",
        )


# ── Neighborhood Scorecard Endpoints ─────────────────────────


@router.get("/neighborhoods/scorecards")
async def list_neighborhood_scorecards(request: Request):
    """Get all neighborhoods with their latest overall scores.

    Returns a ranked list of all 22 Vancouver neighborhoods
    with summary scores and top/bottom categories.
    """
    from api.intelligence.neighborhoods import get_all_neighborhood_summaries
    db_pool = get_db_pool(request)
    summaries = await get_all_neighborhood_summaries(db_pool)
    return summaries


@router.get("/neighborhoods/compare")
async def compare_neighborhood_scorecards(request: Request, slugs: str):
    """Compare 2-4 neighborhoods side by side.

    Query params:
        slugs: Comma-separated neighborhood slugs (e.g., "kitsilano,downtown")

    Returns category-by-category comparison for selected neighborhoods.
    """
    from api.intelligence.neighborhoods import compare_neighborhoods

    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    if len(slug_list) < 2 or len(slug_list) > 4:
        raise HTTPException(
            status_code=400,
            detail="Provide 2-4 neighborhood slugs separated by commas",
        )

    db_pool = get_db_pool(request)

    result = await compare_neighborhoods(db_pool, slug_list)
    if not result:
        raise HTTPException(status_code=404, detail="No neighborhoods found")
    return result


@router.get("/neighborhoods/{slug}/scorecard")
async def get_single_neighborhood_scorecard(slug: str, request: Request):
    """Get full Madlan-style scorecard for a single neighborhood.

    Includes:
    - Overall score (0-10) and rank (1-22)
    - Category scores with trends (safety, schools, transit, etc.)
    - Contextual intelligence stats (active rezonings, permits, signals)
    """
    from api.intelligence.neighborhoods import get_neighborhood_scorecard

    db_pool = get_db_pool(request)
    result = await get_neighborhood_scorecard(db_pool, slug)
    if not result:
        raise HTTPException(status_code=404, detail=f"Neighborhood '{slug}' not found")
    return result


# ── Chat Session Management Endpoints ────────────────────────────


@router.post(
    "/chat/sessions",
    response_model=ChatSession,
    summary="Create a new chat session",
    description="Create a new chat session for starting a conversation.",
)
async def post_create_session(
    request: Request,
    user_label: str = Query("default", description="User label for analytics")
) -> ChatSession:
    """
    Create a new chat session.

    Sessions are used to group related chat messages for multi-turn
    conversations and history tracking.
    """
    try:
        db_pool = get_db_pool(request)
        session = await create_session(db_pool, user_label=user_label)
        logger.info(f"Created new chat session: {session.session_id}")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create chat session",
        )


@router.get(
    "/chat/sessions",
    response_model=ChatSessionList,
    summary="List user's chat sessions",
    description="Get a paginated list of chat sessions for a user.",
)
async def get_list_sessions(
    request: Request,
    user_label: str = Query("default", description="User label to filter by"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> ChatSessionList:
    """
    Get a paginated list of chat sessions for a user.

    Results are ordered by creation date (most recent first).
    """
    try:
        db_pool = get_db_pool(request)
        session_list = await list_sessions(
            db_pool,
            user_label=user_label,
            limit=limit,
            offset=offset
        )
        logger.info(
            f"Listed {len(session_list.sessions)} sessions for user '{user_label}'"
        )
        return session_list
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing sessions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to list chat sessions",
        )


@router.get(
    "/chat/sessions/{session_id}",
    response_model=ChatSession,
    summary="Get session details",
    description="Get metadata and statistics for a specific chat session.",
)
async def get_session_details(
    session_id: str,
    request: Request,
) -> ChatSession:
    """
    Get details for a specific chat session including message count and last activity.
    """
    try:
        db_pool = get_db_pool(request)
        session = await get_session(db_pool, session_id)

        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found"
            )

        logger.info(f"Retrieved session details: {session_id}")
        return session

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve session details",
        )


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatMessageHistory,
    summary="Get session message history",
    description="Get the full conversation history for a session.",
)
async def get_session_messages(
    session_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Max messages to retrieve"),
) -> ChatMessageHistory:
    """
    Get the full message history for a session.

    Messages are ordered chronologically (oldest first).
    """
    try:
        db_pool = get_db_pool(request)
        history = await get_session_history(db_pool, session_id, limit=limit)

        if history is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found"
            )

        logger.info(f"Retrieved {len(history.messages)} messages for session {session_id}")
        return history

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session history {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve session history",
        )


@router.delete(
    "/chat/sessions/{session_id}",
    summary="Delete a chat session",
    description="Delete a session and all its messages.",
)
async def delete_chat_session(
    session_id: str,
    request: Request,
) -> dict:
    """
    Delete a chat session and all its messages.

    WARNING: This operation is not reversible.
    """
    try:
        db_pool = get_db_pool(request)
        success = await delete_session(db_pool, session_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found or already deleted"
            )

        logger.info(f"Deleted session: {session_id}")
        return {
            "status": "deleted",
            "session_id": session_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to delete session",
        )


# ── Materialized View Endpoints (VCL-79 / PERF-011) ─────────────────

@router.get(
    "/neighborhoods/rankings",
    response_model=list[NeighborhoodSummary],
    summary="Get neighborhood rankings from materialized view",
    description=(
        "Get all Vancouver neighborhoods ranked by overall composite score. "
        "Served from materialized view for maximum performance. "
        "Includes top/bottom categories for quick scanning."
    ),
)
async def get_neighborhood_rankings(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Max neighborhoods to return"),
) -> list[NeighborhoodSummary]:
    """
    Get ranked neighborhoods from materialized view (fast).

    Returns all neighborhoods sorted by overall score and rank.
    """
    try:
        from .materialized_views import get_neighborhood_rankings as mv_rankings

        db_pool = get_db_pool(request)
        rankings = await mv_rankings(db_pool, limit=limit)

        logger.info(f"Retrieved {len(rankings)} neighborhood rankings")
        return rankings

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving neighborhood rankings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve neighborhood rankings",
        )


@router.get(
    "/neighborhoods/{slug}/scorecard",
    response_model=NeighborhoodScorecard,
    summary="Get detailed neighborhood scorecard",
    description=(
        "Get full Madlan-style scorecard for a single neighborhood from materialized view. "
        "Includes overall score, category breakdown, rank, and intelligence stats. "
        "Cached for performance."
    ),
)
async def get_neighborhood_scorecard(
    slug: str,
    request: Request,
) -> NeighborhoodScorecard:
    """
    Get full scorecard for a neighborhood from materialized view.

    Returns category scores, rank, active rezonings, and recent permits.
    """
    try:
        from .materialized_views import get_neighborhood_detail

        db_pool = get_db_pool(request)
        scorecard = await get_neighborhood_detail(db_pool, slug)

        if not scorecard:
            raise HTTPException(
                status_code=404,
                detail=f"Neighborhood '{slug}' not found",
            )

        logger.info(f"Retrieved scorecard for neighborhood: {slug}")
        return scorecard

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving scorecard for {slug}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve neighborhood scorecard",
        )


@router.post(
    "/neighborhoods/compare",
    response_model=NeighborhoodComparison,
    summary="Compare neighborhoods side-by-side",
    description=(
        "Compare 2-4 neighborhoods with category-by-category breakdown. "
        "Served from materialized view for fast comparisons."
    ),
)
async def post_compare_neighborhoods(
    request: Request,
    body: dict = None,
) -> NeighborhoodComparison:
    """
    Compare 2-4 neighborhoods side-by-side.

    Request body should contain:
        {
            "slugs": ["kitsilano", "downtown", "west-point-grey"]
        }

    Returns category-by-category comparison with all neighborhoods.
    """
    try:
        from .materialized_views import compare_neighborhoods

        db_pool = get_db_pool(request)

        # Parse request body
        if body is None:
            body = await request.json()

        slugs = body.get("slugs", [])

        if not slugs or len(slugs) < 2 or len(slugs) > 4:
            raise HTTPException(
                status_code=400,
                detail="Provide 2-4 neighborhood slugs in 'slugs' array",
            )

        comparison = await compare_neighborhoods(db_pool, slugs)

        if not comparison:
            raise HTTPException(
                status_code=404,
                detail="One or more neighborhoods not found",
            )

        logger.info(f"Compared {len(slugs)} neighborhoods")
        return comparison

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing neighborhoods: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to compare neighborhoods",
        )


@router.post(
    "/admin/refresh-views",
    summary="Admin: refresh materialized views",
    dependencies=[Depends(require_admin)],
    description=(
        "Manually trigger a refresh of all materialized views (neighborhoods scores, signal activity). "
        "Admin-only operation. Returns refresh timing and statistics."
    ),
)
async def admin_refresh_views(request: Request) -> dict:
    """
    Trigger manual refresh of materialized views.

    Refreshes:
    - mv_neighborhood_scores
    - mv_neighborhood_signal_activity

    Returns timing information and row counts.
    """
    try:
        from .materialized_views import refresh_all_views

        db_pool = get_db_pool(request)

        logger.info("Admin refresh of materialized views initiated")

        result = await refresh_all_views(db_pool)

        logger.info(
            f"Materialized views refreshed: "
            f"success={result.get('all_success')}, "
            f"duration_ms={result.get('total_duration_ms')}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing materialized views: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh materialized views",
        )


# ── Geocoding Endpoints (VCL-84) ───────────────────────────────────────────


@router.post(
    "/admin/geocode/backfill",
    summary="Admin: backfill missing signal geocodes",
    dependencies=[Depends(require_admin)],
    description=(
        "Find intelligence signals with addresses but no geom and attempt to geocode them. "
        "Uses parcels table as primary geocoding source. "
        "Returns statistics on attempted, succeeded, and failed geocodings."
    ),
)
async def admin_geocode_backfill(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Max signals to process"),
) -> dict:
    """
    Trigger backfill of missing geocodes for intelligence signals.

    Finds signals with addresses but no geom and attempts to geocode them
    using exact match, fuzzy match, and regex-based extraction strategies.

    Returns statistics on the operation.
    """
    try:
        from .geocoder import VancouverGeocoder

        db_pool = get_db_pool(request)
        geocoder = VancouverGeocoder(db_pool)

        logger.info(f"Starting geocode backfill with limit={limit}")

        stats = await geocoder.backfill_missing_geocodes(limit=limit)

        logger.info(
            f"Geocode backfill completed: "
            f"attempted={stats['attempted']}, "
            f"succeeded={stats['succeeded']}, "
            f"failed={stats['failed']}"
        )

        return {
            "status": "completed",
            "attempted": stats["attempted"],
            "succeeded": stats["succeeded"],
            "failed": stats["failed"],
        }

    except Exception as e:
        logger.error(f"Error during geocode backfill: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to perform geocode backfill",
        )


@router.get(
    "/admin/geocode/stats",
    summary="Admin: geocoding coverage statistics",
    dependencies=[Depends(require_admin)],
    description=(
        "Get statistics on signal geocoding coverage. "
        "Returns total signal count, geocoded count, and missing count."
    ),
)
async def admin_geocode_stats(request: Request) -> dict:
    """
    Get geocoding coverage statistics.

    Returns counts for:
    - total_signals: Total signals in database
    - geocoded_signals: Signals with non-null geom
    - missing_signals: Signals with null geom
    - addressable_missing: Signals with addresses but no geom
    """
    try:
        db_pool = get_db_pool(request)

        async with db_pool.acquire() as conn:
            # Get all signal counts
            counts = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_signals,
                    COUNT(geom) as geocoded_signals,
                    COUNT(*) FILTER (WHERE geom IS NULL) as missing_signals,
                    COUNT(*) FILTER (WHERE geom IS NULL AND addresses IS NOT NULL AND array_length(addresses, 1) > 0) as addressable_missing
                FROM intelligence_signals
                """
            )

            if not counts:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to query signal statistics",
                )

            stats = {
                "total_signals": counts["total_signals"],
                "geocoded_signals": counts["geocoded_signals"],
                "missing_signals": counts["missing_signals"],
                "addressable_missing": counts["addressable_missing"],
                "geocoding_coverage_pct": (
                    round(
                        (counts["geocoded_signals"] / counts["total_signals"] * 100)
                        if counts["total_signals"] > 0
                        else 0,
                        2,
                    )
                ),
            }

            logger.info(f"Geocoding stats retrieved: {stats}")
            return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving geocoding statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve geocoding statistics",
        )


@router.post(
    "/admin/geocode/test",
    summary="Admin: test geocode a single address",
    dependencies=[Depends(require_admin)],
    description=(
        "Test geocoding a single address. "
        "Returns the geocoded (lng, lat) or null if address cannot be matched."
    ),
)
async def admin_geocode_test(
    request: Request,
    address: str = Query(..., description="Address to test geocoding"),
) -> dict:
    """
    Test geocoding for a single address.

    Useful for verifying geocoding quality and debugging address matching issues.

    Returns:
        {
            "address": "input address",
            "result": [lng, lat] or null,
            "found": true/false
        }
    """
    try:
        from .geocoder import VancouverGeocoder

        db_pool = get_db_pool(request)
        geocoder = VancouverGeocoder(db_pool)

        logger.info(f"Testing geocode for address: {address}")

        result = await geocoder.geocode_address(address)

        if result:
            lng, lat = result
            return {
                "address": address,
                "result": [lng, lat],
                "found": True,
            }
        else:
            return {
                "address": address,
                "result": None,
                "found": False,
            }

    except Exception as e:
        logger.error(f"Error testing geocode for '{address}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to test geocode",
        )
