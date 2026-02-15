"""
Hybrid search engine for VanCity Lens intelligence layer.

Architecture:
  Stage 1: Parallel retrieval
    - Dense: Cohere embed-english-v3.0 -> pgvector cosine similarity
    - Sparse: PostgreSQL tsvector/tsquery -> GIN index full-text search
  Stage 2: Reciprocal Rank Fusion (RRF) with k=60
  Stage 3: Optional Cohere Rerank v3.5 for final ordering

Switched from OpenAI embeddings to Cohere for:
  - Better retrieval quality (embed-english-v3.0 is SOTA for search)
  - Native search_document / search_query input types
  - Built-in reranking as a second stage
"""

import asyncio
import logging
import os
from typing import List, Dict, Optional, Any

import asyncpg
import cohere

from .external_clients_cohere import COHERE_SEMAPHORE, COHERE_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# -- Cohere configuration -----------------------------------------------------
EMBEDDING_MODEL = "embed-english-v3.0"
EMBEDDING_DIMENSION = 1024  # embed-english-v3.0 outputs 1024 dims
RERANK_MODEL = "rerank-english-v3.0"
DEFAULT_BATCH_SIZE = 96  # Cohere allows up to 96 texts per batch
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
RRF_K = 60  # Reciprocal Rank Fusion smoothing constant
DEFAULT_CHUNK_INSERT_CONCURRENCY = 10


class EmbeddingError(Exception):
    """Custom exception for embedding operations."""
    pass


# -- Embedding generation ------------------------------------------------------

async def generate_embedding(
    text: str,
    api_key: str,
    input_type: str = "search_query",
    max_retries: int = MAX_RETRIES
) -> List[float]:
    """
    Generate a single embedding using Cohere API.

    Args:
        text: Text to embed
        api_key: Cohere API key
        input_type: 'search_document' for indexing, 'search_query' for queries
        max_retries: Retry attempts with exponential backoff

    Returns:
        1024-dimensional embedding vector
    """
    text = text[:4096]  # Cohere max input is ~512 tokens, but truncates gracefully

    backoff = INITIAL_BACKOFF
    last_error = None

    async with cohere.AsyncClient(api_key=api_key) as co:
        for attempt in range(max_retries):
            try:
                async with COHERE_SEMAPHORE:
                    response = await asyncio.wait_for(
                        co.embed(
                            texts=[text],
                            model=EMBEDDING_MODEL,
                            input_type=input_type,
                            embedding_types=["float"],
                        ),
                        timeout=COHERE_TIMEOUT_SECONDS,
                    )

                embedding = response.embeddings.float_[0]

                if not embedding or len(embedding) != EMBEDDING_DIMENSION:
                    raise EmbeddingError(
                        f"Invalid embedding dimension: {len(embedding)} != {EMBEDDING_DIMENSION}"
                    )

                logger.debug(f"Generated embedding ({input_type}) for text of length {len(text)}")
                return embedding

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        "Embedding attempt %s failed: %s, backing off %ss",
                        attempt + 1,
                        e,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 32.0)
                else:
                    break

    raise EmbeddingError(f"Failed after {max_retries} attempts: {last_error}")


async def batch_embed(
    texts: List[str],
    api_key: str,
    input_type: str = "search_document",
    batch_size: int = DEFAULT_BATCH_SIZE
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts using Cohere batch API.

    Args:
        texts: List of texts to embed
        api_key: Cohere API key
        input_type: 'search_document' for indexing, 'search_query' for queries
        batch_size: Texts per API call (max 96 for Cohere)

    Returns:
        List of 1024-dim embedding vectors
    """
    if not texts:
        return []

    batch_size = min(batch_size, 96)
    all_embeddings = []

    async with cohere.AsyncClient(api_key=api_key) as co:
        for i in range(0, len(texts), batch_size):
            batch = [t[:4096] for t in texts[i:i + batch_size]]

            backoff = INITIAL_BACKOFF
            last_error = None

            for attempt in range(MAX_RETRIES):
                try:
                    logger.info(f"Embedding batch {i // batch_size + 1} ({len(batch)} texts)")

                    async with COHERE_SEMAPHORE:
                        response = await asyncio.wait_for(
                            co.embed(
                                texts=batch,
                                model=EMBEDDING_MODEL,
                                input_type=input_type,
                                embedding_types=["float"],
                            ),
                            timeout=COHERE_TIMEOUT_SECONDS,
                        )

                    batch_embeddings = response.embeddings.float_
                    if len(batch_embeddings) != len(batch):
                        raise EmbeddingError(
                            f"Batch size mismatch: got {len(batch_embeddings)}, expected {len(batch)}"
                        )

                    all_embeddings.extend(batch_embeddings)
                    break

                except Exception as e:
                    last_error = e
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            "Batch %s attempt %s failed: %s, backing off %ss",
                            i // batch_size + 1,
                            attempt + 1,
                            e,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 32.0)
                    else:
                        logger.error(f"Batch {i // batch_size + 1} failed: {e}")
                        raise EmbeddingError(f"Batch embedding failed: {last_error}")

    logger.info(f"Embedded {len(all_embeddings)} texts total")
    return all_embeddings


# -- Reranking -----------------------------------------------------------------

async def rerank_results(
    query: str,
    documents: List[str],
    api_key: str,
    top_n: int = 10
) -> List[Dict[str, Any]]:
    """
    Rerank candidate documents using Cohere Rerank v3.

    Args:
        query: The search query
        documents: List of document texts to rerank
        api_key: Cohere API key
        top_n: Number of top results to return

    Returns:
        List of dicts with 'index' (original position) and 'relevance_score'
    """
    if not documents:
        return []

    try:
        async with cohere.AsyncClient(api_key=api_key) as co:
            async with COHERE_SEMAPHORE:
                response = await asyncio.wait_for(
                    co.rerank(
                        model=RERANK_MODEL,
                        query=query,
                        documents=documents,
                        top_n=min(top_n, len(documents)),
                    ),
                    timeout=COHERE_TIMEOUT_SECONDS,
                )

        results = [
            {"index": r.index, "relevance_score": r.relevance_score}
            for r in response.results
        ]

        logger.info(f"Reranked {len(documents)} documents -> top {len(results)}")
        return results

    except Exception as e:
        logger.warning(f"Reranking failed, returning original order: {e}")
        # Graceful fallback: return original order
        return [{"index": i, "relevance_score": 1.0 - (i * 0.01)} for i in range(min(top_n, len(documents)))]


# -- Chunk storage -------------------------------------------------------------

async def store_chunk_with_embedding(
    db_pool: asyncpg.Pool,
    document_id: int,
    chunk_index: int,
    chunk_text: str,
    section_header: Optional[str],
    token_count: int,
    embedding: List[float]
) -> int:
    """
    Store a chunk with embedding + tsvector in the database.

    The tsvector column is populated automatically by a trigger (see migration 007),
    or we generate it inline here as a fallback.
    """
    embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'

    query = """
        INSERT INTO document_chunks (
            document_id, chunk_index, chunk_text, section_header,
            token_count, embedding, chunk_tsvector
        )
        VALUES (
            $1, $2, $3, $4, $5, $6::vector,
            to_tsvector('english', $3)
        )
        RETURNING id
    """

    async with db_pool.acquire() as conn:
        try:
            chunk_id = await conn.fetchval(
                query, document_id, chunk_index, chunk_text,
                section_header, token_count, embedding_str
            )
            logger.debug(f"Stored chunk {chunk_index} for doc {document_id}")
            return chunk_id
        except Exception as e:
            logger.error(f"Error storing chunk {chunk_index} for doc {document_id}: {e}")
            raise


# -- Full document processing --------------------------------------------------

async def process_document_chunks(
    db_pool: asyncpg.Pool,
    document_id: int,
    api_key: str
) -> int:
    """
    Full pipeline: chunk document -> embed with Cohere -> store with tsvector.

    Args:
        db_pool: AsyncPG connection pool
        document_id: ID of the document to process
        api_key: Cohere API key

    Returns:
        Count of chunks created
    """
    from .chunker import chunk_document

    # Fetch document
    async with db_pool.acquire() as conn:
        doc_row = await conn.fetchrow(
            "SELECT id, raw_text FROM documents WHERE id = $1", document_id
        )

    if not doc_row:
        raise ValueError(f"Document {document_id} not found")

    raw_text = doc_row['raw_text']
    if not raw_text:
        logger.warning(f"Document {document_id} has no raw_text")
        return 0

    # Chunk
    logger.info(f"Chunking document {document_id}")
    chunks = chunk_document(raw_text)
    if not chunks:
        logger.warning(f"No chunks generated for document {document_id}")
        return 0

    # Embed
    chunk_texts = [c['chunk_text'] for c in chunks]
    logger.info(f"Embedding {len(chunks)} chunks with Cohere")
    try:
        embeddings = await batch_embed(chunk_texts, api_key, input_type="search_document")
    except EmbeddingError as e:
        logger.error(f"Embedding failed for document {document_id}: {e}")
        raise

    if len(embeddings) != len(chunks):
        raise EmbeddingError(f"Count mismatch: {len(embeddings)} embeddings vs {len(chunks)} chunks")

    # Store
    insert_concurrency = int(os.getenv("CHUNK_INSERT_MAX_CONCURRENCY", DEFAULT_CHUNK_INSERT_CONCURRENCY))
    insert_concurrency = max(1, min(insert_concurrency, 50))
    insert_sem = asyncio.Semaphore(insert_concurrency)

    async def _store_one(chunk: dict, embedding: List[float]) -> int:
        async with insert_sem:
            try:
                await store_chunk_with_embedding(
                    db_pool,
                    document_id,
                    chunk["chunk_index"],
                    chunk["chunk_text"],
                    chunk.get("section_header"),
                    chunk.get("approx_token_count", 0),
                    embedding,
                )
                return 1
            except Exception as e:
                logger.error(f"Failed to store chunk {chunk['chunk_index']}: {e}")
                return 0

    tasks = [_store_one(chunk, embedding) for chunk, embedding in zip(chunks, embeddings)]
    stored = sum(await asyncio.gather(*tasks))

    logger.info(f"Document {document_id}: stored {stored}/{len(chunks)} chunks")
    return stored


# -- Hybrid search -------------------------------------------------------------

async def hybrid_search(
    db_pool: asyncpg.Pool,
    query_text: str,
    api_key: str,
    limit: int = 10,
    use_rerank: bool = True,
    vector_weight: float = 0.5,
    text_weight: float = 0.5,
    neighborhood: Optional[str] = None,
    date_from: Optional[Any] = None,
    date_to: Optional[Any] = None,
    signal_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Hybrid search: dense (pgvector) + sparse (tsvector) with RRF fusion.

    Stage 1: Parallel vector + full-text retrieval (top 30 each)
    Stage 2: Reciprocal Rank Fusion (k=60)
    Stage 3: Optional Cohere rerank on top candidates

    Args:
        db_pool: AsyncPG connection pool
        query_text: Natural language search query
        api_key: Cohere API key
        limit: Number of final results
        use_rerank: Whether to apply Cohere reranking
        vector_weight: RRF weight for vector results (default 0.5)
        text_weight: RRF weight for text results (default 0.5)
        neighborhood: RAG-008 -- pre-filter by neighborhood
        date_from: RAG-008 -- pre-filter documents published on/after this date
        date_to: RAG-008 -- pre-filter documents published on/before this date
        signal_type: RAG-008 -- pre-filter by signal_type (via chunk metadata)

    Returns:
        List of result dicts with chunk_text, document_id, score, metadata
    """
    # Step 1: Embed the query
    logger.info(f"Hybrid search: '{query_text[:80]}...'")
    query_embedding = await generate_embedding(query_text, api_key, input_type="search_query")
    embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

    # RAG-008: Build optional metadata pre-filter JOIN and WHERE clauses
    doc_filter_clauses = []
    extra_params: list = []
    param_offset = 6  # first 6 params are fixed ($1-$6)

    if neighborhood:
        param_offset += 1
        doc_filter_clauses.append(f"d_filt.metadata->>'neighborhood' = ${param_offset} OR EXISTS (SELECT 1 FROM intelligence_signals isig WHERE isig.document_id = dc.document_id AND isig.neighborhood = ${param_offset})")
        extra_params.append(neighborhood)

    if date_from:
        param_offset += 1
        doc_filter_clauses.append(f"d_filt.published_date >= ${param_offset}")
        extra_params.append(date_from)

    if date_to:
        param_offset += 1
        doc_filter_clauses.append(f"d_filt.published_date <= ${param_offset}")
        extra_params.append(date_to)

    # Build the filter JOIN snippet
    if doc_filter_clauses:
        filter_join = "JOIN documents d_filt ON dc.document_id = d_filt.id"
        filter_where = " AND (" + " AND ".join(f"({c})" for c in doc_filter_clauses) + ")"
    else:
        filter_join = ""
        filter_where = ""

    # Step 2: Combined query with RRF fusion
    rrf_query = f"""
        WITH vector_search AS (
            SELECT
                dc.id, dc.chunk_text, dc.document_id, dc.section_header, dc.chunk_index,
                ROW_NUMBER() OVER (ORDER BY dc.embedding <=> $1::vector) AS vrank
            FROM document_chunks dc
            {filter_join}
            WHERE dc.embedding IS NOT NULL{filter_where}
            LIMIT 30
        ),
        text_search AS (
            SELECT
                dc.id, dc.chunk_text, dc.document_id, dc.section_header, dc.chunk_index,
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank_cd(dc.chunk_tsvector, plainto_tsquery('english', $2)) DESC
                ) AS trank
            FROM document_chunks dc
            {filter_join}
            WHERE dc.chunk_tsvector @@ plainto_tsquery('english', $2){filter_where}
            LIMIT 30
        ),
        fused AS (
            SELECT
                COALESCE(v.id, t.id) AS id,
                COALESCE(v.chunk_text, t.chunk_text) AS chunk_text,
                COALESCE(v.document_id, t.document_id) AS document_id,
                COALESCE(v.section_header, t.section_header) AS section_header,
                COALESCE(v.chunk_index, t.chunk_index) AS chunk_index,
                (
                    $3::float * COALESCE(1.0 / ($5::int + v.vrank), 0.0) +
                    $4::float * COALESCE(1.0 / ($5::int + t.trank), 0.0)
                ) AS rrf_score
            FROM vector_search v
            FULL OUTER JOIN text_search t ON v.id = t.id
        )
        SELECT
            f.id AS chunk_id,
            f.chunk_text,
            f.document_id,
            f.section_header,
            f.chunk_index,
            f.rrf_score,
            d.title AS document_title,
            d.source_url,
            d.source_type,
            d.published_date
        FROM fused f
        JOIN documents d ON f.document_id = d.id
        ORDER BY f.rrf_score DESC
        LIMIT $6
    """

    # Fetch more candidates than needed if we're going to rerank
    fetch_limit = limit * 3 if use_rerank else limit

    all_params = [
        embedding_str,      # $1: query embedding
        query_text,          # $2: text query
        vector_weight,       # $3: vector weight
        text_weight,         # $4: text weight
        RRF_K,               # $5: RRF k constant
        fetch_limit,         # $6: limit
    ] + extra_params

    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch(rrf_query, *all_params)
        except Exception as e:
            logger.error(f"Hybrid search query failed: {e}")
            raise

    if not rows:
        logger.info("Hybrid search returned 0 results")
        return []

    # Build result list
    candidates = []
    for row in rows:
        candidates.append({
            'chunk_id': row['chunk_id'],
            'chunk_text': row['chunk_text'],
            'document_id': row['document_id'],
            'section_header': row['section_header'],
            'chunk_index': row['chunk_index'],
            'rrf_score': float(row['rrf_score']),
            'document_title': row['document_title'],
            'source_url': row['source_url'],
            'source_type': row['source_type'],
            'published_date': row['published_date'],
        })

    # Step 3: Optional Cohere reranking
    if use_rerank and len(candidates) > 1:
        logger.info(f"Reranking {len(candidates)} candidates with Cohere")
        doc_texts = [c['chunk_text'] for c in candidates]

        rerank_hits = await rerank_results(query_text, doc_texts, api_key, top_n=limit)

        # Reorder candidates by rerank score
        reranked = []
        for r in rerank_hits:
            candidate = candidates[r['index']].copy()
            candidate['rerank_score'] = r['relevance_score']
            candidate['final_score'] = r['relevance_score']
            reranked.append(candidate)

        logger.info(f"Hybrid search: {len(reranked)} final results (reranked)")
        return reranked

    # No reranking -- use RRF scores directly
    results = candidates[:limit]
    for r in results:
        r['final_score'] = r['rrf_score']

    logger.info(f"Hybrid search: {len(results)} final results (RRF only)")
    return results


# -- Sparse (BM25-only) search ------------------------------------------------


async def sparse_search(
    db_pool: asyncpg.Pool,
    query_text: str,
    limit: int = 10,
    neighborhood: Optional[str] = None,
    date_from: Optional[Any] = None,
    date_to: Optional[Any] = None,
    signal_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    BM25-only text search -- no API keys required.

    Uses PostgreSQL tsvector/tsquery full-text search on document_chunks.
    Returns the same dict format as hybrid_search() for drop-in compatibility.

    Args:
        db_pool: AsyncPG connection pool
        query_text: Natural language search query
        limit: Number of results to return
        neighborhood: Optional neighborhood filter
        date_from: Optional start date filter
        date_to: Optional end date filter
        signal_type: Optional signal type filter (unused, kept for interface compat)

    Returns:
        List of result dicts with chunk_text, document_id, score, metadata
    """
    logger.info(f"Sparse search (BM25): '{query_text[:80]}...'")

    # Build parameterized query with optional filters
    params: list = [query_text, limit]
    filter_clauses: list = []
    param_idx = 2  # $1=query, $2=limit

    if neighborhood:
        param_idx += 1
        filter_clauses.append(
            f"(d.metadata->>'neighborhood' = ${param_idx} OR EXISTS "
            f"(SELECT 1 FROM intelligence_signals isig "
            f"WHERE isig.document_id = dc.document_id AND isig.neighborhood = ${param_idx}))"
        )
        params.append(neighborhood)

    if date_from:
        param_idx += 1
        filter_clauses.append(f"d.published_date >= ${param_idx}")
        params.append(date_from)

    if date_to:
        param_idx += 1
        filter_clauses.append(f"d.published_date <= ${param_idx}")
        params.append(date_to)

    extra_where = ""
    if filter_clauses:
        extra_where = " AND " + " AND ".join(filter_clauses)

    query = f"""
        SELECT
            dc.id AS chunk_id,
            dc.chunk_text,
            dc.document_id,
            dc.section_header,
            dc.chunk_index,
            ts_rank_cd(dc.chunk_tsvector, plainto_tsquery('english', $1)) AS text_score,
            d.title AS document_title,
            d.source_url,
            d.source_type,
            d.published_date
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.chunk_tsvector @@ plainto_tsquery('english', $1){extra_where}
        ORDER BY text_score DESC
        LIMIT $2
    """

    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
        except Exception as e:
            logger.error(f"Sparse search query failed: {e}")
            raise

    if not rows:
        logger.info("Sparse search returned 0 results")
        return []

    results = []
    for row in rows:
        results.append({
            "chunk_id": row["chunk_id"],
            "chunk_text": row["chunk_text"],
            "document_id": row["document_id"],
            "section_header": row["section_header"],
            "chunk_index": row["chunk_index"],
            "text_score": float(row["text_score"]),
            "rrf_score": float(row["text_score"]),
            "final_score": float(row["text_score"]),
            "document_title": row["document_title"],
            "source_url": row["source_url"],
            "source_type": row["source_type"],
            "published_date": row["published_date"],
        })

    logger.info(f"Sparse search: {len(results)} results")
    return results


# -- Legacy compatibility alias ------------------------------------------------

async def semantic_search(
    db_pool: asyncpg.Pool,
    query_text: str,
    api_key: str,
    limit: int = 10,
    **kwargs
) -> List[Dict[str, Any]]:
    """Backward-compatible alias for hybrid_search."""
    return await hybrid_search(db_pool, query_text, api_key, limit=limit)
