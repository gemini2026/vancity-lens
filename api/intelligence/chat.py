"""
RAG-powered chat endpoint for VanCity Lens intelligence layer.

This module handles:
- Context retrieval from documents and intelligence signals
- Claude API integration for RAG-based responses
- Citation extraction and tracking
- Chat message persistence

Search pipeline uses K2 search (with local BM25 fallback).
"""

import logging
import re
import uuid
from urllib.parse import urlparse
from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Any

import asyncpg

from .llm_backend import generate_chat
from .models import ChatResponse, SourceCitation, SignalResponse
from .prepared_queries import QueryBuilder, build_signal_feed_query
from .retrieval_backend import retrieve_document_chunks
from .chat_sessions import (
    create_session,
    get_session_history,
    build_context_window,
)

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are VanCity Lens, an AI real estate intelligence analyst specializing in Vancouver development, zoning, and policy. You provide sophisticated analysis for real estate investors and developers.

CORE INSTRUCTIONS:
1. Answer questions ONLY using the provided context (retrieved document chunks and intelligence signals below)
2. If information is not in the context, say explicitly: "I don't have sufficient information to answer that based on my available sources."
3. Always cite your sources with document titles and URLs
4. Be specific about addresses, numbers, dates, and vote counts - precision matters for investment decisions
5. Format responses for a sophisticated real estate investor audience - assume knowledge of Vancouver zoning, TOA, and development process
6. When discussing decisions, include vote counts, dates, and decision status (approved/denied/deferred/pending)
7. Acknowledge uncertainty when confidence is low
8. When structured intelligence signals are present, treat them as the primary source of truth for decision status, event dates, vote counts, and addresses
9. Consolidate duplicate signals that refer to the same event instead of repeating them

RESPONSE FORMAT:
- Lead with the direct answer
- Use specific data from sources
- Include reasoning
- Provide citations inline like: [Source: Document Title]
- End with a summary of confidence level and any caveats

PROHIBITED:
- Do not invent or speculate about facts not in the context
- Do not provide general real estate advice beyond what is documented
- Do not extrapolate beyond stated policies or decisions"""


_DECISION_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("approved", ("approved", "approve", "approval", "enacted")),
    ("denied", ("denied", "deny", "rejected", "reject")),
    ("deferred", ("deferred", "defer")),
    ("referred", ("referred", "refer")),
    ("pending", ("pending", "under review", "in review")),
]


def _normalize_query_text(query: str) -> str:
    return " ".join(query.lower().split())


def _extract_decision_filter(normalized_query: str) -> Optional[str]:
    for decision, terms in _DECISION_PATTERNS:
        if any(term in normalized_query for term in terms):
            return decision
    return None


def _infer_lookback_days(normalized_query: str) -> Optional[int]:
    match = re.search(
        r"\b(?:last|past)\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)\b",
        normalized_query,
    )
    if match:
        quantity = int(match.group(1))
        unit = match.group(2)
        multipliers = {
            "day": 1,
            "days": 1,
            "week": 7,
            "weeks": 7,
            "month": 30,
            "months": 30,
            "year": 365,
            "years": 365,
        }
        return quantity * multipliers[unit]

    if any(phrase in normalized_query for phrase in ("last month", "past month")):
        return 31
    if any(phrase in normalized_query for phrase in ("last quarter", "past quarter")):
        return 93
    if any(phrase in normalized_query for phrase in ("last year", "past year")):
        return 365
    if any(term in normalized_query for term in ("recent", "recently", "latest")):
        return 365
    return None


def _structured_signal_filters(
    query: str,
    *,
    neighborhood: Optional[str] = None,
    limit: int = 5,
) -> Optional[dict[str, Any]]:
    normalized_query = _normalize_query_text(query)
    if "rezoning" not in normalized_query and "rezone" not in normalized_query:
        return None

    decision = _extract_decision_filter(normalized_query)
    if not decision:
        return None

    filters: dict[str, Any] = {
        "signal_type": "rezoning_decision",
        "limit": limit,
        "offset": 0,
    }
    if neighborhood:
        filters["neighborhood"] = neighborhood
    filters["decision"] = decision

    lookback_days = _infer_lookback_days(normalized_query)
    if lookback_days is not None:
        filters["date_from"] = date.today() - timedelta(days=lookback_days)
        filters["date_to"] = date.today()

    return filters


def _signal_prefers_context(query: str, *, neighborhood: Optional[str] = None) -> bool:
    return _structured_signal_filters(query, neighborhood=neighborhood, limit=5) is not None


def _row_to_signal(row: Any) -> SignalResponse:
    return SignalResponse(
        id=row["id"],
        document_id=row["document_id"],
        signal_type=row["signal_type"],
        summary=row["summary"],
        headline=row["headline"],
        addresses=row["addresses"] or [],
        neighborhood=row["neighborhood"],
        decision=row["decision"],
        vote_for=row["vote_for"],
        vote_against=row["vote_against"],
        sentiment=row["sentiment"],
        severity=row["severity"],
        confidence=row["confidence"],
        event_date=row["event_date"],
        source_title=row["source_title"],
        source_url=row["source_url"],
        source_type=row["source_type"],
        source_date=row["source_date"],
    )


def _dedupe_signals(signals: List[SignalResponse]) -> List[SignalResponse]:
    deduped: List[SignalResponse] = []
    seen: set[tuple[Any, ...]] = set()

    for signal in signals:
        key = (
            signal.signal_type,
            (signal.headline or signal.summary).strip().lower(),
            tuple(addr.strip().lower() for addr in signal.addresses),
            signal.event_date,
            (signal.decision or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)

    return deduped


def _is_safe_http_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _preferred_citation_url(
    source_url: Optional[str],
    *,
    url_status: Optional[str] = None,
    archive_url: Optional[str] = None,
) -> str:
    source = (source_url or "").strip()
    archive = (archive_url or "").strip()

    if url_status == "dead":
        if archive and _is_safe_http_url(archive):
            return archive
        return source if _is_safe_http_url(source) else ""

    if source and _is_safe_http_url(source):
        return source
    if archive and _is_safe_http_url(archive):
        return archive
    return ""


def _build_signal_citations(
    signals: List[SignalResponse],
    document_health: dict[int, dict[str, Any]],
) -> List[SourceCitation]:
    citations: List[SourceCitation] = []
    for signal in signals:
        health = document_health.get(signal.document_id, {})
        url_status = health.get("url_status")
        archive_url = health.get("archive_url")
        citations.append(
            SourceCitation(
                document_title=signal.source_title or signal.headline or "Signal",
                document_url=_preferred_citation_url(
                    signal.source_url,
                    url_status=url_status,
                    archive_url=archive_url,
                ),
                source_type=signal.source_type or "unknown",
                published_date=signal.source_date or signal.event_date,
                relevance_score=float(signal.confidence or 0.0),
                excerpt=signal.summary[:300],
                document_id=signal.document_id,
                chunk_id=None,
                url_status=url_status,
                archive_url=archive_url,
            )
        )
    return citations


def _dedupe_citations(citations: List[SourceCitation]) -> List[SourceCitation]:
    deduped: List[SourceCitation] = []
    seen: set[tuple[Any, ...]] = set()

    for citation in citations:
        key = (
            citation.document_id,
            citation.document_title.strip().lower(),
            citation.document_url.strip().lower(),
            citation.excerpt.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)

    return deduped


async def handle_chat(
    db_pool: asyncpg.Pool,
    query: str,
    anthropic_api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ChatResponse:
    """
    Handle a chat query using RAG (Retrieval-Augmented Generation).

    Operates in two tiers based on available API keys:
    - FULL: Anthropic key present → K2 search + Claude RAG
    - DEMO: No keys               → K2/BM25 search + formatted results

    Args:
        db_pool: AsyncPG connection pool
        query: User's question
        anthropic_api_key: Anthropic API key for Claude (optional)
        session_id: Optional session ID for grouping messages
        neighborhood_filter: Optional neighborhood to filter results
        date_from: Optional start date for document filtering
        date_to: Optional end date for document filtering

    Returns:
        ChatResponse with answer, citations, and related signals
    """

    # Determine search mode
    has_anthropic = bool(anthropic_api_key)
    search_mode = "full" if has_anthropic else "demo"
    logger.info(f"Chat mode: {search_mode} (anthropic={has_anthropic})")

    # Create or retrieve session
    if not session_id:
        try:
            session = await create_session(db_pool)
            session_id = session.session_id
            logger.info(f"Created new chat session: {session_id}")
        except Exception as e:
            # Non-fatal: fall back to generating a UUID for this chat
            logger.warning(f"Failed to create session, using generated UUID: {e}")
            session_id = str(uuid.uuid4())
    else:
        # Validate that session exists
        try:
            history = await get_session_history(db_pool, session_id, limit=1)
            if history is None:
                # Session doesn't exist, but we'll still store messages with this ID
                logger.warning(
                    f"Session {session_id} not found, will create on first message"
                )
        except Exception as e:
            logger.error(f"Error validating session {session_id}: {e}")
            # Continue anyway - session may be new

    try:
        signal_first = _signal_prefers_context(
            query, neighborhood=neighborhood_filter
        )

        # Step 1: Retrieve relevant document chunks
        logger.info(f"Retrieving document chunks for query: {query[:100]}...")
        chunks = await retrieve_document_chunks(
            db_pool=db_pool,
            query=query,
            search_mode=search_mode,
            neighborhood_filter=neighborhood_filter,
            date_from=date_from,
            date_to=date_to,
        )

        # Step 2: Retrieve matching intelligence signals
        logger.info("Retrieving intelligence signals...")
        signals = await get_relevant_signals(
            db_pool, query, neighborhood=neighborhood_filter, limit=5
        )

        # Step 3: Build context string from chunks and signals
        context_parts = []

        def append_signal_context() -> None:
            if not signals:
                return
            context_parts.append("\n## INTELLIGENCE SIGNALS:\n")
            for i, signal in enumerate(signals, 1):
                context_parts.append(
                    f"\n### Signal {i}: {signal.headline or signal.summary[:50]}"
                )
                context_parts.append(
                    f"Type: {signal.signal_type} | Severity: {signal.severity}"
                )
                if signal.addresses:
                    context_parts.append(f"Addresses: {', '.join(signal.addresses)}")
                if signal.neighborhood:
                    context_parts.append(f"Neighborhood: {signal.neighborhood}")
                if signal.event_date:
                    context_parts.append(f"Event Date: {signal.event_date}")
                if signal.decision:
                    votes_str = ""
                    if signal.vote_for is not None and signal.vote_against is not None:
                        votes_str = f" ({signal.vote_for}-{signal.vote_against})"
                    context_parts.append(f"Decision: {signal.decision}{votes_str}")
                context_parts.append(f"Source: {signal.source_title}")
                context_parts.append(f"Source URL: {signal.source_url or ''}")
                context_parts.append(f"\n{signal.summary}\n")

        def append_chunk_context() -> None:
            if not chunks:
                return
            context_parts.append("## RETRIEVED DOCUMENT CHUNKS:\n")
            for i, chunk in enumerate(chunks, 1):
                score = chunk.get("final_score", chunk.get("rrf_score", 0.0))
                context_parts.append(f"\n### Chunk {i} (Score: {score:.3f})")
                context_parts.append(
                    f"Source: {chunk.get('document_title', 'Unknown')}"
                )
                context_parts.append(f"URL: {chunk.get('source_url', '')}")
                if chunk.get("section_header"):
                    context_parts.append(f"Section: {chunk['section_header']}")
                context_parts.append(f"\n{chunk['chunk_text']}\n")

        if signal_first:
            append_signal_context()
            append_chunk_context()
        else:
            append_chunk_context()
            append_signal_context()

        context = "\n".join(context_parts)

        if not chunks and not signals:
            logger.warning("No relevant chunks or signals found for query")
            context = "No relevant information found in the knowledge base."

        # Step 4: Generate answer based on mode
        if search_mode == "demo":
            # Demo mode: format retrieval results without LLM
            answer = _build_demo_answer(query, chunks, signals)
        else:
            # Full mode: call LLM (Gemini or Anthropic based on LLM_BACKEND)
            logger.info("Building multi-turn context...")
            history_context = ""
            try:
                history_context = await build_context_window(
                    db_pool, session_id, max_messages=10
                )
            except Exception as e:
                logger.warning(f"Could not build context window: {e}")

            user_content = f"""Context information:

{context}

{history_context}

User query: {query}"""

            logger.info("Calling LLM...")
            answer, model_used, llm_latency = await generate_chat(
                system_prompt=CHAT_SYSTEM_PROMPT,
                user_message=user_content,
                max_tokens=2000,
                anthropic_api_key=anthropic_api_key,
            )
            logger.info("LLM responded in %.1fs (model=%s)", llm_latency, model_used)

        # Step 5: Extract citations from used chunks and structured signals.
        citations: List[SourceCitation] = []

        # Batch-fetch url_status and archive_url for cited documents.
        doc_ids = list(
            {
                doc_id
                for doc_id in [
                    *(c.get("document_id") for c in chunks),
                    *(s.document_id for s in signals),
                ]
                if doc_id
            }
        )
        url_health_map: dict = {}
        if doc_ids:
            try:
                async with db_pool.acquire() as conn:
                    health_rows = await conn.fetch(
                        "SELECT id, url_status, archive_url FROM documents WHERE id = ANY($1)",
                        doc_ids,
                    )
                    for hr in health_rows:
                        url_health_map[hr["id"]] = {
                            "url_status": hr["url_status"],
                            "archive_url": hr["archive_url"],
                        }
            except Exception as e:
                logger.warning(f"Could not fetch URL health for citations: {e}")

        for chunk in chunks:
            # Include top chunks as citations (reranking already sorted by relevance)
            score = chunk.get("final_score", chunk.get("rrf_score", 0.0))
            doc_id = chunk.get("document_id")
            health = url_health_map.get(doc_id, {})
            citations.append(
                SourceCitation(
                    document_title=chunk.get("document_title", "Unknown"),
                    document_url=_preferred_citation_url(
                        chunk.get("source_url"),
                        url_status=health.get("url_status") or chunk.get("url_status"),
                        archive_url=health.get("archive_url")
                        or chunk.get("archive_url"),
                    ),
                    source_type=chunk.get("source_type", "unknown"),
                    published_date=chunk.get("published_date"),
                    relevance_score=score,
                    excerpt=chunk["chunk_text"][:300],
                    document_id=doc_id,
                    chunk_id=chunk.get("chunk_id"),
                    url_status=health.get("url_status") or chunk.get("url_status"),
                    archive_url=health.get("archive_url") or chunk.get("archive_url"),
                )
            )

        signal_citations = _build_signal_citations(signals, url_health_map)
        if signal_first:
            citations = signal_citations + citations
        else:
            citations.extend(signal_citations)

        citations = _dedupe_citations(citations)[:5]

        # Step 6: Store chat message in database
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO chat_messages (
                        session_id, role, content,
                        source_chunks, source_signals, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    uuid.UUID(session_id),
                    "user",
                    query,
                    [c.get("chunk_id") for c in chunks if c.get("chunk_id")],
                    [s.id for s in signals],
                    datetime.now(timezone.utc),
                )
                await conn.execute(
                    """
                    INSERT INTO chat_messages (
                        session_id, role, content, created_at
                    )
                    VALUES ($1, $2, $3, $4)
                """,
                    uuid.UUID(session_id),
                    "assistant",
                    answer,
                    datetime.now(timezone.utc),
                )
        except Exception as e:
            logger.error(f"Failed to store chat message: {e}")
            # Continue anyway - don't fail the response

        # Step 7: Return ChatResponse
        logger.info(
            f"Chat response generated ({search_mode} mode) with {len(citations)} citations"
        )
        return ChatResponse(
            answer=answer,
            citations=citations,
            related_signals=signals[:5],
            session_id=session_id,
            mode=search_mode,
        )

    except Exception as e:
        logger.error(f"Error in handle_chat: {e}", exc_info=True)
        raise


def _build_demo_answer(
    query: str,
    chunks: List[dict],
    signals: List[SignalResponse],
) -> str:
    """
    Build a formatted answer from retrieval results without calling an LLM.

    Used in demo mode when no API keys are configured.
    """
    parts: List[str] = []

    parts.append(f"**Search results for:** {query}\n")

    if not chunks and not signals:
        parts.append(
            "No relevant documents or signals were found for this query. "
            "Try broadening your search terms or checking that document chunks have been seeded."
        )
        parts.append(
            "\n---\n*This is a retrieval-only result. "
            "For AI-generated analysis, configure ANTHROPIC_API_KEY.*"
        )
        return "\n".join(parts)

    if chunks:
        parts.append(f"### Top {min(len(chunks), 5)} Document Matches\n")
        for i, chunk in enumerate(chunks[:5], 1):
            score = chunk.get("final_score", chunk.get("rrf_score", 0.0))
            title = chunk.get("document_title", "Unknown Document")
            section = chunk.get("section_header")
            excerpt = chunk["chunk_text"][:400]
            if len(chunk["chunk_text"]) > 400:
                excerpt += "..."

            parts.append(f"**{i}. {title}** (relevance: {score:.3f})")
            if section:
                parts.append(f"   Section: {section}")
            parts.append(f"   > {excerpt}\n")

    if signals:
        parts.append(f"### Related Intelligence Signals ({len(signals)})\n")
        for signal in signals[:5]:
            headline = signal.headline or signal.summary[:60]
            parts.append(
                f"- **{headline}** — {signal.signal_type} | Severity: {signal.severity}"
            )
            if signal.decision:
                parts.append(f"  Decision: {signal.decision}")
            if signal.neighborhood:
                parts.append(f"  Neighborhood: {signal.neighborhood}")

    parts.append(
        "\n---\n*This is a retrieval-only result. "
        "For AI-generated analysis, configure ANTHROPIC_API_KEY.*"
    )

    return "\n".join(parts)


async def get_relevant_signals(
    db_pool: asyncpg.Pool,
    query: str,
    neighborhood: Optional[str] = None,
    limit: int = 5,
) -> List[SignalResponse]:
    """
    Retrieve intelligence signals matching query keywords and optional neighborhood.

    Uses PostgreSQL full-text search on summary/headline for keyword matching.
    """

    try:
        async with db_pool.acquire() as conn:
            structured_filters = _structured_signal_filters(
                query, neighborhood=neighborhood, limit=limit
            )
            if structured_filters:
                structured_query, structured_params, _, _ = build_signal_feed_query(
                    structured_filters
                )
                rows = await conn.fetch(structured_query, *structured_params)
                signals = _dedupe_signals([_row_to_signal(row) for row in rows])
                if signals:
                    logger.info(
                        "Retrieved %d structured signals for query", len(signals)
                    )
                    return signals[:limit]

            # Fallback: plain keyword matching for broader exploratory queries.
            builder = QueryBuilder()
            builder.params = [query]
            builder.conditions = [
                "to_tsvector('english', isig.summary || ' ' || COALESCE(isig.headline, '')) "
                "@@ plainto_tsquery('english', $1)"
            ]

            if neighborhood:
                builder.add_filter("isig.neighborhood", "=", neighborhood)

            where_clause, params = builder.build()
            param_num = len(params) + 1
            base_query = f"""
                SELECT
                    isig.id,
                    isig.document_id,
                    isig.signal_type,
                    isig.summary,
                    isig.headline,
                    isig.addresses,
                    isig.neighborhood,
                    isig.decision,
                    isig.vote_for,
                    isig.vote_against,
                    isig.sentiment,
                    isig.severity,
                    isig.confidence,
                    isig.event_date,
                    d.title AS source_title,
                    d.source_url,
                    d.source_type,
                    d.published_date AS source_date
                FROM intelligence_signals isig
                JOIN documents d ON isig.document_id = d.id
                WHERE {where_clause}
                ORDER BY isig.event_date DESC NULLS LAST, isig.severity DESC
                LIMIT ${param_num}
            """
            params.append(limit)
            rows = await conn.fetch(base_query, *params)

        signals = _dedupe_signals([_row_to_signal(row) for row in rows])

        logger.info(f"Retrieved {len(signals)} relevant signals")
        return signals

    except Exception as e:
        logger.error(f"Error retrieving signals: {e}", exc_info=True)
        return []
