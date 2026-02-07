"""Tests for Cohere embeddings, hybrid search, and reranking."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.intelligence.embeddings import (
    generate_embedding,
    batch_embed,
    rerank_results,
    store_chunk_with_embedding,
    process_document_chunks,
    hybrid_search,
    semantic_search,
    EmbeddingError,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    RERANK_MODEL,
    RRF_K,
)


# ── Configuration constants ──────────────────────────────────

class TestConstants:
    """Test module-level constants."""

    def test_embedding_dimension(self):
        """Cohere embed-english-v3.0 uses 1024 dims."""
        assert EMBEDDING_DIMENSION == 1024

    def test_embedding_model(self):
        """Verify model name."""
        assert EMBEDDING_MODEL == "embed-english-v3.0"

    def test_rerank_model(self):
        """Verify rerank model name."""
        assert RERANK_MODEL == "rerank-english-v3.0"

    def test_rrf_k_constant(self):
        """RRF k should be 60."""
        assert RRF_K == 60


# ── generate_embedding ───────────────────────────────────────

class TestGenerateEmbedding:
    """Test single-text embedding generation."""

    @pytest.mark.asyncio
    async def test_successful_embedding(self):
        """Test successful single embedding generation."""
        mock_embedding = [0.1] * 1024

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [mock_embedding]
            mock_client.embed.return_value = mock_response

            result = await generate_embedding("test text", "test-key")

            assert len(result) == 1024
            assert result == mock_embedding
            mock_client.embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embedding_uses_correct_input_type(self):
        """Test that input_type is passed correctly."""
        mock_embedding = [0.1] * 1024

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [mock_embedding]
            mock_client.embed.return_value = mock_response

            await generate_embedding("text", "key", input_type="search_document")

            call_kwargs = mock_client.embed.call_args
            assert call_kwargs.kwargs.get('input_type') == "search_document" or \
                   call_kwargs[1].get('input_type') == "search_document"

    @pytest.mark.asyncio
    async def test_embedding_truncates_long_text(self):
        """Test that long text is truncated to 4096 chars."""
        long_text = "x" * 10000
        mock_embedding = [0.1] * 1024

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [mock_embedding]
            mock_client.embed.return_value = mock_response

            await generate_embedding(long_text, "key")

            call_args = mock_client.embed.call_args
            passed_text = call_args.kwargs.get('texts', call_args[1].get('texts', ['']))[0]
            assert len(passed_text) <= 4096

    @pytest.mark.asyncio
    async def test_embedding_wrong_dimension_raises(self):
        """Test that wrong embedding dimension raises EmbeddingError."""
        wrong_embedding = [0.1] * 512  # Wrong dimension

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [wrong_embedding]
            mock_client.embed.return_value = mock_response

            with pytest.raises(EmbeddingError):
                await generate_embedding("text", "key", max_retries=1)

    @pytest.mark.asyncio
    async def test_embedding_retries_on_failure(self):
        """Test retry logic with exponential backoff."""
        mock_embedding = [0.1] * 1024

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            with patch("api.intelligence.embeddings.asyncio.sleep") as mock_sleep:
                mock_client = MagicMock()
                mock_cohere_mod.Client.return_value = mock_client

                # Fail first, succeed second
                mock_response = MagicMock()
                mock_response.embeddings.float_ = [mock_embedding]
                mock_client.embed.side_effect = [
                    Exception("Rate limited"),
                    mock_response,
                ]

                result = await generate_embedding("text", "key", max_retries=2)

                assert len(result) == 1024
                mock_sleep.assert_called_once()


# ── batch_embed ──────────────────────────────────────────────

class TestBatchEmbed:
    """Test batch embedding generation."""

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """Test batch_embed with empty list."""
        result = await batch_embed([], "key")
        assert result == []

    @pytest.mark.asyncio
    async def test_single_batch(self):
        """Test batch embedding with few texts."""
        texts = ["text 1", "text 2", "text 3"]
        mock_embeddings = [[0.1] * 1024] * 3

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = mock_embeddings
            mock_client.embed.return_value = mock_response

            result = await batch_embed(texts, "key")

            assert len(result) == 3
            mock_client.embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_size_mismatch_raises(self):
        """Test error when API returns wrong number of embeddings."""
        texts = ["text 1", "text 2"]

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [[0.1] * 1024]  # Only 1, expected 2
            mock_client.embed.return_value = mock_response

            with pytest.raises(EmbeddingError):
                await batch_embed(texts, "key")


# ── rerank_results ───────────────────────────────────────────

class TestRerankResults:
    """Test Cohere reranking."""

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        """Test reranking with empty document list."""
        result = await rerank_results("query", [], "key")
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_success(self):
        """Test successful reranking."""
        docs = ["doc 1 content", "doc 2 content", "doc 3 content"]

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client

            mock_result1 = MagicMock(index=2, relevance_score=0.95)
            mock_result2 = MagicMock(index=0, relevance_score=0.8)
            mock_response = MagicMock()
            mock_response.results = [mock_result1, mock_result2]
            mock_client.rerank.return_value = mock_response

            result = await rerank_results("query", docs, "key", top_n=2)

            assert len(result) == 2
            assert result[0]["index"] == 2
            assert result[0]["relevance_score"] == 0.95
            assert result[1]["index"] == 0

    @pytest.mark.asyncio
    async def test_rerank_graceful_fallback(self):
        """Test fallback to original order when reranking fails."""
        docs = ["doc 1", "doc 2", "doc 3"]

        with patch("api.intelligence.embeddings.cohere") as mock_cohere_mod:
            mock_client = MagicMock()
            mock_cohere_mod.Client.return_value = mock_client
            mock_client.rerank.side_effect = Exception("API error")

            result = await rerank_results("query", docs, "key", top_n=3)

            # Should return fallback with sequential indices
            assert len(result) == 3
            assert result[0]["index"] == 0
            assert result[1]["index"] == 1


# ── hybrid_search ────────────────────────────────────────────

class TestHybridSearch:
    """Test the hybrid search pipeline (dense + sparse + RRF)."""

    @pytest.mark.asyncio
    async def test_hybrid_search_empty_results(self):
        """Test hybrid search when no results found."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        with patch("api.intelligence.embeddings.generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            result = await hybrid_search(mock_pool, "test query", "key")

            assert result == []

    @pytest.mark.asyncio
    async def test_hybrid_search_with_results(self):
        """Test hybrid search returns properly structured results."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock database rows
        mock_row = {
            'chunk_id': 1,
            'chunk_text': 'Council approved rezoning',
            'document_id': 10,
            'section_header': 'Rezoning Decision',
            'chunk_index': 0,
            'rrf_score': 0.85,
            'document_title': 'Council Meeting Jan 2024',
            'source_url': 'https://example.com/meeting',
            'source_type': 'council_minutes',
            'published_date': '2024-01-15',
        }
        conn.fetch.return_value = [mock_row]

        with patch("api.intelligence.embeddings.generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            result = await hybrid_search(
                mock_pool, "rezoning decisions", "key",
                limit=5, use_rerank=False
            )

            assert len(result) == 1
            assert result[0]['chunk_text'] == 'Council approved rezoning'
            assert result[0]['document_title'] == 'Council Meeting Jan 2024'
            assert 'final_score' in result[0]

    @pytest.mark.asyncio
    async def test_hybrid_search_with_rerank(self):
        """Test hybrid search with Cohere reranking enabled."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_rows = [
            {
                'chunk_id': i,
                'chunk_text': f'Document text {i}',
                'document_id': 10,
                'section_header': None,
                'chunk_index': i,
                'rrf_score': 0.9 - (i * 0.1),
                'document_title': 'Test Doc',
                'source_url': 'https://example.com',
                'source_type': 'council_minutes',
                'published_date': None,
            }
            for i in range(3)
        ]
        conn.fetch.return_value = mock_rows

        with patch("api.intelligence.embeddings.generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            with patch("api.intelligence.embeddings.rerank_results") as mock_rerank:
                mock_rerank.return_value = [
                    {"index": 2, "relevance_score": 0.99},
                    {"index": 0, "relevance_score": 0.85},
                ]

                result = await hybrid_search(
                    mock_pool, "test", "key",
                    limit=2, use_rerank=True
                )

                assert len(result) == 2
                # Reranked order: index 2 first
                assert result[0]['chunk_text'] == 'Document text 2'
                assert result[0]['rerank_score'] == 0.99


# ── semantic_search alias ────────────────────────────────────

class TestSemanticSearchAlias:
    """Test backward-compatible semantic_search alias."""

    @pytest.mark.asyncio
    async def test_alias_calls_hybrid_search(self):
        """Test that semantic_search delegates to hybrid_search."""
        with patch("api.intelligence.embeddings.hybrid_search") as mock_hybrid:
            mock_hybrid.return_value = [{"chunk_text": "result"}]

            mock_pool = AsyncMock()
            result = await semantic_search(mock_pool, "query", "key", limit=5)

            mock_hybrid.assert_called_once_with(mock_pool, "query", "key", limit=5)
            assert result == [{"chunk_text": "result"}]


# ── store_chunk_with_embedding ───────────────────────────────

class TestStoreChunkWithEmbedding:
    """Test chunk storage with embedding."""

    @pytest.mark.asyncio
    async def test_store_chunk_success(self):
        """Test successful chunk storage."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchval.return_value = 42  # returned chunk ID

        embedding = [0.1] * 1024

        chunk_id = await store_chunk_with_embedding(
            mock_pool,
            document_id=1,
            chunk_index=0,
            chunk_text="Test chunk text",
            section_header="Section 1",
            token_count=10,
            embedding=embedding,
        )

        assert chunk_id == 42
        conn.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_chunk_db_error(self):
        """Test chunk storage with database error."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchval.side_effect = Exception("DB Error")

        embedding = [0.1] * 1024

        with pytest.raises(Exception, match="DB Error"):
            await store_chunk_with_embedding(
                mock_pool, 1, 0, "text", None, 5, embedding
            )


# ── process_document_chunks ──────────────────────────────────

class TestProcessDocumentChunks:
    """Test full document processing pipeline."""

    @pytest.mark.asyncio
    async def test_document_not_found(self):
        """Test processing non-existent document."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchrow.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await process_document_chunks(mock_pool, 999, "key")

    @pytest.mark.asyncio
    async def test_document_no_text(self):
        """Test processing document with no raw_text."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchrow.return_value = {"id": 1, "raw_text": ""}

        result = await process_document_chunks(mock_pool, 1, "key")
        assert result == 0

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Test successful end-to-end processing."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetchrow.return_value = {"id": 1, "raw_text": "Test document content here."}
        conn.fetchval.return_value = 42  # chunk ID

        with patch("api.intelligence.embeddings.batch_embed") as mock_batch:
            mock_batch.return_value = [[0.1] * 1024]  # 1 chunk → 1 embedding

            result = await process_document_chunks(mock_pool, 1, "key")

            assert result == 1
            mock_batch.assert_called_once()
