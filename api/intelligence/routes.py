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
from datetime import date
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks

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
)
from .signals import (
    get_signal_feed,
    get_signal_by_id,
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


def get_anthropic_api_key() -> str:
    """Get Anthropic API key from environment."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        logger.error("ANTHROPIC_API_KEY not set in environment")
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY not configured. Please set the environment variable.",
        )
    return key


def get_cohere_api_key() -> str:
    """Get Cohere API key from environment for embeddings + reranking."""
    key = os.environ.get("COHERE_API_KEY")
    if not key:
        logger.error("COHERE_API_KEY not set in environment")
        raise HTTPException(
            status_code=500,
            detail="COHERE_API_KEY not configured. Please set the environment variable.",
        )
    return key


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

    The system will search relevant documents and signals using hybrid search
    (dense Cohere embeddings + sparse BM25), then generate a contextual
    answer with proper citations.
    """
    try:
        db_pool = get_db_pool(request)
        anthropic_key = get_anthropic_api_key()
        cohere_key = get_cohere_api_key()

        logger.info(f"Chat query received: {chat_request.query[:100]}...")

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

        feed = await get_signal_feed(
            db_pool=db_pool,
            neighborhood=neighborhood,
            signal_type=signal_type,
            severity_min=severity_min,
            date_from=date_from,
            date_to=date_to,
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
                logger.error(f"Failed to process document {doc_id}: {e}")

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
