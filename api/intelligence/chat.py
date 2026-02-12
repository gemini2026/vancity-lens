"""
RAG-powered chat endpoint for VanCity Lens intelligence layer.

This module handles:
- Context retrieval from documents and intelligence signals
- Claude API integration for RAG-based responses
- Citation extraction and tracking
- Chat message persistence

Search pipeline uses Cohere embeddings + BM25 hybrid search with RRF fusion.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, date, timezone
from typing import Optional, List

import asyncpg
from anthropic import AsyncAnthropic, NotFoundError

from .external_clients import ANTHROPIC_CHAT_TIMEOUT_SECONDS, ANTHROPIC_SEMAPHORE
from .models import ChatResponse, SourceCitation, SignalResponse
from .prepared_queries import QueryBuilder
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


async def handle_chat(
    db_pool: asyncpg.Pool,
    query: str,
    anthropic_api_key: Optional[str] = None,
    cohere_api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    neighborhood_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ChatResponse:
    """
    Handle a chat query using RAG (Retrieval-Augmented Generation).

    Operates in three tiers based on available API keys:
    - FULL:    Anthropic + Cohere → hybrid search + Claude RAG
    - PARTIAL: Anthropic only    → sparse (BM25) search + Claude RAG
    - DEMO:    No keys           → sparse (BM25) search + formatted results

    Args:
        db_pool: AsyncPG connection pool
        query: User's question
        anthropic_api_key: Anthropic API key for Claude (optional)
        cohere_api_key: Cohere API key for embeddings + reranking (optional)
        session_id: Optional session ID for grouping messages
        neighborhood_filter: Optional neighborhood to filter results
        date_from: Optional start date for document filtering
        date_to: Optional end date for document filtering

    Returns:
        ChatResponse with answer, citations, and related signals
    """

    # Determine search mode
    has_anthropic = bool(anthropic_api_key)
    has_cohere = bool(cohere_api_key)

    if has_anthropic and has_cohere:
        search_mode = "full"
    elif has_anthropic:
        search_mode = "partial"
    else:
        search_mode = "demo"

    logger.info(f"Chat mode: {search_mode} (anthropic={has_anthropic}, cohere={has_cohere})")

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
                logger.warning(f"Session {session_id} not found, will create on first message")
        except Exception as e:
            logger.error(f"Error validating session {session_id}: {e}")
            # Continue anyway - session may be new

    try:
        # Step 1: Retrieve relevant document chunks
        logger.info(f"Retrieving document chunks for query: {query[:100]}...")
        chunks = await retrieve_document_chunks(
            db_pool=db_pool,
            query=query,
            search_mode=search_mode,
            cohere_api_key=cohere_api_key,
            neighborhood_filter=neighborhood_filter,
            date_from=date_from,
            date_to=date_to,
        )

        # Step 2: Retrieve matching intelligence signals
        logger.info("Retrieving intelligence signals...")
        signals = await get_relevant_signals(
            db_pool,
            query,
            neighborhood=neighborhood_filter,
            limit=5
        )

        # Step 3: Build context string from chunks and signals
        context_parts = []

        if chunks:
            context_parts.append("## RETRIEVED DOCUMENT CHUNKS:\n")
            for i, chunk in enumerate(chunks, 1):
                score = chunk.get('final_score', chunk.get('rrf_score', 0.0))
                context_parts.append(f"\n### Chunk {i} (Score: {score:.3f})")
                context_parts.append(f"Source: {chunk.get('document_title', 'Unknown')}")
                context_parts.append(f"URL: {chunk.get('source_url', '')}")
                if chunk.get('section_header'):
                    context_parts.append(f"Section: {chunk['section_header']}")
                context_parts.append(f"\n{chunk['chunk_text']}\n")

        if signals:
            context_parts.append("\n## INTELLIGENCE SIGNALS:\n")
            for i, signal in enumerate(signals, 1):
                context_parts.append(f"\n### Signal {i}: {signal.headline or signal.summary[:50]}")
                context_parts.append(f"Type: {signal.signal_type} | Severity: {signal.severity}")
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
                context_parts.append(f"\n{signal.summary}\n")

        context = "\n".join(context_parts)

        if not chunks and not signals:
            logger.warning("No relevant chunks or signals found for query")
            context = "No relevant information found in the knowledge base."

        # Step 4: Generate answer based on mode
        if search_mode == "demo":
            # Demo mode: format retrieval results without LLM
            answer = _build_demo_answer(query, chunks, signals)
        else:
            # Full or partial mode: call Claude API
            logger.info("Building multi-turn context...")
            history_context = ""
            try:
                history_context = await build_context_window(db_pool, session_id, max_messages=10)
            except Exception as e:
                logger.warning(f"Could not build context window: {e}")

            logger.info("Calling Claude API...")
            client = AsyncAnthropic(api_key=anthropic_api_key)

            user_content = f"""Context information:

{context}

{history_context}

User query: {query}"""

            messages = [
                {
                    "role": "user",
                    "content": user_content
                }
            ]

            try:
                # Prefer configured model, but fall back to known-good Claude model IDs.
                model_candidates: list[str] = []
                configured_model = (os.environ.get("ANTHROPIC_MODEL") or "").strip()
                if configured_model:
                    model_candidates.append(configured_model)
                model_candidates.extend(
                    [
                        # Prefer broadly-available models; keep fallbacks short to avoid long 404 chains.
                        "claude-3-5-sonnet-20240620",
                        "claude-3-5-haiku-20241022",
                        "claude-3-haiku-20240307",
                    ]
                )

                last_exc: Exception | None = None
                for model in model_candidates:
                    try:
                        async with ANTHROPIC_SEMAPHORE:
                            response = await asyncio.wait_for(
                                client.messages.create(
                                    model=model,
                                    max_tokens=2000,
                                    system=CHAT_SYSTEM_PROMPT,
                                    messages=messages,
                                ),
                                timeout=ANTHROPIC_CHAT_TIMEOUT_SECONDS,
                            )
                        break
                    except NotFoundError as e:
                        last_exc = e
                        logger.warning(f"Anthropic model not found: {model}; trying fallback.")
                        continue
                    except Exception as e:
                        last_exc = e
                        # If the configured/default model isn't available, try the next candidate.
                        msg = str(e)
                        if "Error code: 404" in msg and ("model:" in msg or "not_found_error" in msg):
                            logger.warning(f"Anthropic model not found: {model}; trying fallback.")
                            continue
                        raise
                else:
                    assert last_exc is not None
                    raise last_exc
            finally:
                await client.close()

            answer = response.content[0].text

        # Step 5: Extract citations from used chunks with provenance (RAG-005)
        citations: List[SourceCitation] = []

        # Batch-fetch url_status and archive_url for cited documents
        doc_ids = list({c.get('document_id') for c in chunks if c.get('document_id')})
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
            score = chunk.get('final_score', chunk.get('rrf_score', 0.0))
            doc_id = chunk.get('document_id')
            health = url_health_map.get(doc_id, {})
            citations.append(
                SourceCitation(
                    document_title=chunk.get('document_title', 'Unknown'),
                    document_url=chunk.get('source_url', ''),
                    source_type=chunk.get('source_type', 'unknown'),
                    published_date=chunk.get('published_date'),
                    relevance_score=score,
                    excerpt=chunk['chunk_text'][:300],
                    document_id=doc_id,
                    chunk_id=chunk.get('chunk_id'),
                    url_status=health.get('url_status'),
                    archive_url=health.get('archive_url'),
                )
            )

        # Limit citations to top 5
        citations = citations[:5]

        # Step 6: Store chat message in database
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO chat_messages (
                        session_id, role, content,
                        source_chunks, source_signals, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    uuid.UUID(session_id),
                    'user',
                    query,
                    [c.get('chunk_id') for c in chunks if c.get('chunk_id')],
                    [s.id for s in signals],
                    datetime.now(timezone.utc)
                )
                await conn.execute("""
                    INSERT INTO chat_messages (
                        session_id, role, content, created_at
                    )
                    VALUES ($1, $2, $3, $4)
                """,
                    uuid.UUID(session_id),
                    'assistant',
                    answer,
                    datetime.now(timezone.utc)
                )
        except Exception as e:
            logger.error(f"Failed to store chat message: {e}")
            # Continue anyway - don't fail the response

        # Step 7: Return ChatResponse
        logger.info(f"Chat response generated ({search_mode} mode) with {len(citations)} citations")
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
                f"- **{headline}** — {signal.signal_type} | "
                f"Severity: {signal.severity}"
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
    limit: int = 5
) -> List[SignalResponse]:
    """
    Retrieve intelligence signals matching query keywords and optional neighborhood.

    Uses PostgreSQL full-text search on summary/headline for keyword matching.
    """

    try:
        # Build parameterized query using QueryBuilder
        builder = QueryBuilder()

        # Base WHERE condition for full-text search (param 1 is the query)
        builder.params = [query]
        builder.conditions = [
            "to_tsvector('english', isig.summary || ' ' || COALESCE(isig.headline, '')) "
            "@@ plainto_tsquery('english', $1)"
        ]

        # Add neighborhood filter if provided
        if neighborhood:
            builder.add_filter("isig.neighborhood", "=", neighborhood)

        where_clause, params = builder.build()

        # Build the full query with ordering and limit
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

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(base_query, *params)

        signals = []
        for row in rows:
            signal = SignalResponse(
                id=row['id'],
                document_id=row['document_id'],
                signal_type=row['signal_type'],
                summary=row['summary'],
                headline=row['headline'],
                addresses=row['addresses'] or [],
                neighborhood=row['neighborhood'],
                decision=row['decision'],
                vote_for=row['vote_for'],
                vote_against=row['vote_against'],
                sentiment=row['sentiment'],
                severity=row['severity'],
                confidence=row['confidence'],
                event_date=row['event_date'],
                source_title=row['source_title'],
                source_url=row['source_url'],
                source_type=row['source_type'],
                source_date=row['source_date']
            )
            signals.append(signal)

        logger.info(f"Retrieved {len(signals)} relevant signals")
        return signals

    except Exception as e:
        logger.error(f"Error retrieving signals: {e}", exc_info=True)
        return []
