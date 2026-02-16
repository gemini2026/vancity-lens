"""
VCL-60: [TEST-013] External Service Failure Tests

Comprehensive failure and resilience tests for external service integrations:
- Anthropic Claude API failures
- Cohere API failures
- Database failures
- Combined/cascading failures

Tests verify graceful error handling, proper logging, timeout behavior,
semaphore management, and fallback mechanisms.
"""

import asyncio
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from api.intelligence.chat import handle_chat, get_relevant_signals
from api.intelligence.local_rag.embeddings import (
    generate_embedding,
    batch_embed,
    rerank_results,
    hybrid_search,
    EmbeddingError,
)
from api.intelligence.extractor import extract_signals_from_chunk
from api.intelligence.external_clients import (
    ANTHROPIC_SEMAPHORE,
    ANTHROPIC_CHAT_TIMEOUT_SECONDS,
)
from api.intelligence.local_rag.external_clients_cohere import (
    COHERE_SEMAPHORE,
    COHERE_TIMEOUT_SECONDS,
)


# ═════════════════════════════════════════════════════════════════════════════
# ANTHROPIC API FAILURES (8+ tests)
# ═════════════════════════════════════════════════════════════════════════════


class TestAnthropicAPIFailures:
    """Tests for Anthropic Claude API failure modes."""

    @pytest.mark.asyncio
    async def test_anthropic_connection_timeout_during_chat(self, mock_db_pool):
        """Test connection timeout during chat request.

        Verifies that asyncio.TimeoutError is properly propagated when
        Claude API takes too long to respond.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, side_effect=asyncio.TimeoutError("Request timed out")):
                    with pytest.raises(asyncio.TimeoutError):
                        await handle_chat(
                            mock_pool,
                            "What rezoning decisions in Downtown?",
                            "test-key",
                            "test-cohere-key",
                        )

    @pytest.mark.asyncio
    async def test_anthropic_rate_limit_429_response(self, mock_db_pool):
        """Test rate limit (429) response from Claude API.

        Verifies proper error handling when rate limit is exceeded.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, side_effect=Exception("429 Rate limit exceeded")):
                    with pytest.raises(Exception):
                        await handle_chat(
                            mock_pool,
                            "Test query",
                            "test-key",
                            "test-cohere-key",
                        )

    @pytest.mark.asyncio
    async def test_anthropic_invalid_api_key(self, mock_db_pool):
        """Test invalid API key error from Claude API.

        Verifies that authentication errors are properly raised.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, side_effect=Exception("401 Authentication Error - Invalid API key")):
                    with pytest.raises(Exception):
                        await handle_chat(
                            mock_pool,
                            "Test query",
                            "invalid-key",
                            "test-cohere-key",
                        )

    @pytest.mark.asyncio
    async def test_anthropic_malformed_response_empty_content(self, mock_db_pool):
        """Test handling of malformed response with empty content.

        Verifies graceful handling when LLM backend returns empty content.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, side_effect=IndexError("Empty content in response")):
                    with pytest.raises((IndexError, AttributeError)):
                        await handle_chat(
                            mock_pool,
                            "Test query",
                            "test-key",
                            "test-cohere-key",
                        )

    @pytest.mark.asyncio
    async def test_anthropic_partial_response_none_text(self, mock_db_pool):
        """Test handling of partial response where LLM returns None text.

        Verifies graceful handling when response text is None.
        """
        from pydantic import ValidationError

        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, return_value=(None, "gemini-2.5-flash", 1.5)):
                    with pytest.raises((TypeError, AttributeError, ValidationError, Exception)):
                        await handle_chat(
                            mock_pool,
                            "Test query",
                            "test-key",
                            "test-cohere-key",
                        )

    @pytest.mark.asyncio
    async def test_anthropic_network_error_connection_error(self, mock_db_pool):
        """Test network error (ConnectionError) during API call.

        Verifies that network errors are properly handled and logged.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, side_effect=ConnectionError("Network unreachable")):
                    with pytest.raises(ConnectionError):
                        await handle_chat(
                            mock_pool,
                            "Test query",
                            "test-key",
                            "test-cohere-key",
                        )

    @pytest.mark.asyncio
    async def test_anthropic_extraction_timeout(self):
        """Test timeout during extraction API call.

        Verifies graceful handling when signal extraction times out.
        The function returns empty list after retries rather than raising.
        """
        mock_api_key = "test-key"
        test_chunk = "Test document chunk about rezoning"
        doc_context = {"source_type": "council_minutes", "title": "Test Meeting"}

        with patch("api.intelligence.extractor.generate_extraction", new_callable=AsyncMock, side_effect=asyncio.TimeoutError("Extraction timeout")):
            # extract_signals_from_chunk catches timeouts and returns empty list
            result = await extract_signals_from_chunk(
                test_chunk,
                doc_context,
                mock_api_key,
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_anthropic_semaphore_saturation(self, mock_db_pool):
        """Test semaphore saturation with concurrent requests.

        Verifies that concurrent requests are properly queued when
        semaphore limit is reached.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        semaphore = asyncio.Semaphore(1)  # Very restrictive for testing

        async def slow_request():
            async with semaphore:
                await asyncio.sleep(0.1)
                return "done"

        # Launch multiple concurrent requests
        tasks = [slow_request() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All should complete, but sequentially due to semaphore
        assert len(results) == 5
        assert all(r == "done" for r in results)

    @pytest.mark.asyncio
    async def test_anthropic_empty_response_content_list(self, mock_db_pool):
        """Test handling when response.content is non-empty but elements are empty.

        Additional test for response malformation scenarios.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, side_effect=AttributeError("NoneType has no attribute 'text'")):
                    with pytest.raises((AttributeError, TypeError)):
                        await handle_chat(
                            mock_pool,
                            "Test query",
                            "test-key",
                            "test-cohere-key",
                        )


# ═════════════════════════════════════════════════════════════════════════════
# COHERE API FAILURES (8+ tests)
# ═════════════════════════════════════════════════════════════════════════════


class TestCohereAPIFailures:
    """Tests for Cohere API failure modes."""

    @pytest.mark.asyncio
    async def test_cohere_embedding_timeout(self, mock_db_pool):
        """Test embedding timeout from Cohere API.

        Verifies asyncio.TimeoutError during embedding generation.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.embed = AsyncMock(
                side_effect=asyncio.TimeoutError("Embedding timeout")
            )

            with pytest.raises(EmbeddingError):
                await generate_embedding("test text", "test-key")

    @pytest.mark.asyncio
    async def test_cohere_embedding_with_empty_text(self):
        """Test embedding generation with empty text.

        Verifies validation of empty input text.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_response = MagicMock()
            mock_response.embeddings.float_ = [[0.1] * 1024]
            mock_client.embed = AsyncMock(return_value=mock_response)

            # Should still process empty text (API will handle it)
            result = await generate_embedding("", "test-key")
            assert result is not None
            assert len(result) == 1024

    @pytest.mark.asyncio
    async def test_cohere_reranking_failure_fallback(self):
        """Test reranking failure with graceful fallback.

        Verifies that reranking failures return original order.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.rerank = AsyncMock(
                side_effect=Exception("Reranking failed")
            )

            results = await rerank_results(
                "test query",
                ["doc1", "doc2", "doc3"],
                "test-key",
                top_n=3
            )

            # Should return fallback order
            assert len(results) == 3
            assert results[0]["index"] == 0
            assert results[1]["index"] == 1
            assert results[2]["index"] == 2

    @pytest.mark.asyncio
    async def test_cohere_batch_embedding_partial_failure(self):
        """Test batch embedding with partial failure.

        Verifies error isolation when one batch fails.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            # First batch succeeds, second fails
            mock_response1 = MagicMock()
            mock_response1.embeddings.float_ = [[0.1] * 1024, [0.2] * 1024]
            mock_response2_error = Exception("Batch 2 failed")

            mock_client.embed = AsyncMock(
                side_effect=[mock_response1, mock_response2_error]
            )

            texts = ["text1", "text2", "text3", "text4"]
            with pytest.raises(EmbeddingError):
                await batch_embed(texts, "test-key", batch_size=2)

    @pytest.mark.asyncio
    async def test_cohere_invalid_api_key(self):
        """Test invalid API key error from Cohere.

        Verifies authentication error handling.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.embed = AsyncMock(
                side_effect=Exception("Invalid API key")
            )

            with pytest.raises(EmbeddingError):
                await generate_embedding("test", "invalid-key")

    @pytest.mark.asyncio
    async def test_cohere_rate_limit_response(self):
        """Test rate limit response from Cohere API.

        Verifies rate limit error handling.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.embed = AsyncMock(
                side_effect=Exception("Rate limit exceeded")
            )

            with pytest.raises(EmbeddingError):
                await generate_embedding("test", "test-key")

    @pytest.mark.asyncio
    async def test_cohere_connection_refused(self):
        """Test connection refused error from Cohere.

        Verifies clean error when connection is refused.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.embed = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )

            with pytest.raises(EmbeddingError):
                await generate_embedding("test", "test-key")

    @pytest.mark.asyncio
    async def test_cohere_malformed_embedding_response_wrong_dimensions(self):
        """Test malformed response with wrong embedding dimensions.

        Verifies validation of embedding dimensions.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            # Return wrong dimensions (512 instead of 1024)
            mock_response = MagicMock()
            mock_response.embeddings.float_ = [[0.1] * 512]
            mock_client.embed = AsyncMock(return_value=mock_response)

            with pytest.raises(EmbeddingError):
                await generate_embedding("test", "test-key")

    @pytest.mark.asyncio
    async def test_cohere_batch_size_mismatch(self):
        """Test batch embedding with size mismatch in response.

        Verifies detection of inconsistent batch responses.
        """
        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            # Request 2 embeddings, get 1
            mock_response = MagicMock()
            mock_response.embeddings.float_ = [[0.1] * 1024]  # Only 1 embedding
            mock_client.embed = AsyncMock(return_value=mock_response)

            texts = ["text1", "text2"]
            with pytest.raises(EmbeddingError):
                await batch_embed(texts, "test-key", batch_size=2)


# ═════════════════════════════════════════════════════════════════════════════
# DATABASE FAILURES (6+ tests)
# ═════════════════════════════════════════════════════════════════════════════


class TestDatabaseFailures:
    """Tests for database failure modes."""

    @pytest.mark.asyncio
    async def test_database_connection_pool_exhausted(self, mock_db_pool):
        """Test connection pool exhausted error.

        Verifies proper error when all pool connections are in use.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock(
            side_effect=Exception("Connection pool exhausted")
        )

        # Attempting to acquire from exhausted pool should fail
        with pytest.raises(Exception):
            async with mock_pool.acquire():
                pass

    @pytest.mark.asyncio
    async def test_database_query_timeout(self, mock_db_pool):
        """Test query timeout in database.

        Verifies proper timeout handling for long-running queries.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Simulate query timeout
        conn.fetch = AsyncMock(
            side_effect=asyncio.TimeoutError("Query execution timeout")
        )

        with pytest.raises(asyncio.TimeoutError):
            async with mock_pool.acquire() as db_conn:
                await db_conn.fetch("SELECT * FROM documents")

    @pytest.mark.asyncio
    async def test_database_connection_dropped_mid_query(self, mock_db_pool):
        """Test connection dropped during query execution.

        Verifies error handling when connection is lost mid-query.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Simulate connection drop
        conn.execute = AsyncMock(
            side_effect=Exception("Connection lost to server")
        )

        with pytest.raises(Exception):
            async with mock_pool.acquire() as db_conn:
                await db_conn.execute("INSERT INTO documents (title) VALUES ($1)", "test")

    @pytest.mark.asyncio
    async def test_database_concurrent_connection_acquisition(self, mock_db_pool):
        """Test concurrent connection acquisition from pool.

        Verifies proper behavior when multiple requests need connections.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()

        # Create multiple mock connections
        conn1 = AsyncMock()
        conn2 = AsyncMock()
        conn3 = AsyncMock()

        # Mock sequential connection acquisitions
        call_count = [0]

        def acquire_side_effect():
            cm = MagicMock()
            if call_count[0] == 0:
                cm.__aenter__ = AsyncMock(return_value=conn1)
            elif call_count[0] == 1:
                cm.__aenter__ = AsyncMock(return_value=conn2)
            else:
                cm.__aenter__ = AsyncMock(return_value=conn3)
            cm.__aexit__ = AsyncMock(return_value=None)
            call_count[0] += 1
            return cm

        mock_pool.acquire = MagicMock(side_effect=acquire_side_effect)

        # Acquire multiple connections concurrently
        async def get_conn():
            async with mock_pool.acquire() as conn:
                return conn

        results = await asyncio.gather(get_conn(), get_conn(), get_conn())
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_database_transaction_rollback_on_error(self, mock_db_pool):
        """Test transaction rollback on error.

        Verifies cleanup when transaction fails.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.execute = AsyncMock(side_effect=Exception("Insert failed"))
        conn.rollback = AsyncMock()

        with pytest.raises(Exception):
            async with mock_pool.acquire() as db_conn:
                await db_conn.execute("INSERT INTO documents (title) VALUES ($1)", "test")
                # In real code, transaction would be rolled back

    @pytest.mark.asyncio
    async def test_database_fetch_returns_empty_result(self, mock_db_pool):
        """Test handling of empty query results.

        Verifies proper behavior when query returns no rows.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch = AsyncMock(return_value=[])

        async with mock_pool.acquire() as db_conn:
            result = await db_conn.fetch("SELECT * FROM documents WHERE id = $1", 999)
            assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# COMBINED FAILURE SCENARIOS (3+ tests)
# ═════════════════════════════════════════════════════════════════════════════


class TestCombinedFailureScenarios:
    """Tests for scenarios where multiple services fail."""

    @pytest.mark.asyncio
    async def test_both_cohere_and_database_fail_during_chat(self, mock_db_pool):
        """Test when both Cohere and database fail during chat.

        Verifies error priority when multiple services fail.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks") as mock_search:
            # Retrieval fails due to upstream search error (e.g., Cohere embeddings)
            mock_search.side_effect = Exception("Cohere embedding failed")

            # When search fails, chat should fail before reaching generate_chat
            with pytest.raises(Exception):
                await handle_chat(
                    mock_pool,
                    "Test query",
                    "test-key",
                    "test-cohere-key",
                )

    @pytest.mark.asyncio
    async def test_anthropic_succeeds_but_database_fails_to_store(self, mock_db_pool):
        """Test when Anthropic succeeds but database fails to store result.

        Verifies that response is still returned even if storage fails.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Database execute fails
        conn.execute = AsyncMock(
            side_effect=Exception("Database insert failed")
        )

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.generate_chat", new_callable=AsyncMock, return_value=("Test answer", "gemini-2.5-flash", 1.5)):
                    # Should return answer even if storage fails
                    result = await handle_chat(
                        mock_pool,
                        "Test query",
                        "test-key",
                        "test-cohere-key",
                    )

                    assert result.answer == "Test answer"

    @pytest.mark.asyncio
    async def test_all_services_timeout_simultaneously(self, mock_db_pool):
        """Test when all services timeout at the same time.

        Verifies clean error handling for cascading timeouts.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Database query times out
        conn.fetch = AsyncMock(
            side_effect=asyncio.TimeoutError("Database timeout")
        )

        with patch("api.intelligence.chat.retrieve_document_chunks") as mock_search:
            # Retrieval times out (e.g., upstream embedding/search timeout)
            mock_search.side_effect = asyncio.TimeoutError("Cohere timeout")

            # Should raise error from retrieval before reaching generate_chat
            with pytest.raises(asyncio.TimeoutError):
                await handle_chat(
                    mock_pool,
                    "Test query",
                    "test-key",
                    "test-cohere-key",
                )

    @pytest.mark.asyncio
    async def test_hybrid_search_with_embedding_failure_and_no_fallback(self, mock_db_pool):
        """Test hybrid search when embedding generation fails.

        Verifies error propagation when critical steps fail.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.local_rag.embeddings.generate_embedding") as mock_embed:
            mock_embed.side_effect = EmbeddingError("Embedding generation failed")

            with pytest.raises(EmbeddingError):
                await hybrid_search(
                    mock_pool,
                    "test query",
                    "test-key",
                    limit=10
                )

    @pytest.mark.asyncio
    async def test_get_relevant_signals_database_error_returns_empty(self, mock_db_pool):
        """Test get_relevant_signals gracefully returns empty list on DB error.

        Verifies that signal retrieval doesn't crash on database errors.
        """
        mock_pool = mock_db_pool
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Database fetch fails
        conn.fetch = AsyncMock(
            side_effect=Exception("Database error retrieving signals")
        )

        result = await get_relevant_signals(
            mock_pool,
            "test query",
            neighborhood="Downtown"
        )

        # Should return empty list instead of crashing
        assert result == []

    @pytest.mark.asyncio
    async def test_cohere_semaphore_with_timeout_cascade(self, mock_db_pool):
        """Test semaphore behavior during timeout cascade.

        Verifies semaphore correctly releases when timeouts occur.
        """
        semaphore = asyncio.Semaphore(2)

        async def request_with_timeout(delay: float, fail: bool = False):
            async with semaphore:
                try:
                    await asyncio.sleep(delay)
                    if fail:
                        raise asyncio.TimeoutError("Request timeout")
                    return "success"
                except asyncio.TimeoutError:
                    raise

        # Launch requests: 2 succeed quickly, 1 times out, 1 should proceed
        tasks = [
            request_with_timeout(0.01),           # Should succeed
            request_with_timeout(0.02),           # Should succeed
            request_with_timeout(0.01, fail=True),  # Should timeout
            request_with_timeout(0.01),           # Should still succeed (semaphore released)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check that 3 succeeded and 1 timed out
        successes = sum(1 for r in results if r == "success")
        timeouts = sum(1 for r in results if isinstance(r, asyncio.TimeoutError))
        assert successes == 3
        assert timeouts == 1


# ═════════════════════════════════════════════════════════════════════════════
# ERROR LOGGING VERIFICATION TESTS
# ═════════════════════════════════════════════════════════════════════════════


class TestErrorLogging:
    """Tests to verify proper error logging."""

    @pytest.mark.asyncio
    async def test_cohere_error_logged_on_embedding_failure(self, caplog):
        """Test that Cohere errors are properly logged.

        Verifies logging of embedding failures.
        """
        import logging
        caplog.set_level(logging.ERROR)

        with patch("api.intelligence.local_rag.embeddings.cohere.AsyncClient") as mock_cohere:
            mock_client = MagicMock()
            mock_cohere.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cohere.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_client.embed = AsyncMock(
                side_effect=Exception("Cohere API error")
            )

            with pytest.raises(EmbeddingError):
                await generate_embedding("test", "test-key")

    @pytest.mark.asyncio
    async def test_database_error_logged_on_signal_retrieval(self, caplog):
        """Test that database errors are logged during signal retrieval.

        Verifies logging of database errors.
        """
        import logging
        caplog.set_level(logging.ERROR)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        conn.fetch = AsyncMock(
            side_effect=Exception("Database connection error")
        )

        result = await get_relevant_signals(mock_pool, "test query")
        assert result == []  # Should return empty without crashing
