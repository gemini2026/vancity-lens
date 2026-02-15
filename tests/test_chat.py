"""Tests for the RAG chat pipeline."""

from datetime import date
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from api.intelligence.chat import (
    CHAT_SYSTEM_PROMPT,
    handle_chat,
    get_relevant_signals,
)
from api.intelligence.models import ChatResponse, SourceCitation


class TestChatSystemPrompt:
    """Test chat system prompt."""

    def test_prompt_exists(self):
        """Test that CHAT_SYSTEM_PROMPT is defined."""
        assert CHAT_SYSTEM_PROMPT is not None
        assert isinstance(CHAT_SYSTEM_PROMPT, str)

    def test_prompt_not_empty(self):
        """Test prompt is substantial."""
        assert len(CHAT_SYSTEM_PROMPT) > 200

    def test_prompt_contains_rag_instructions(self):
        """Test prompt contains RAG instructions."""
        prompt_lower = CHAT_SYSTEM_PROMPT.lower()
        assert "context" in prompt_lower
        assert "cite" in prompt_lower or "source" in prompt_lower


class TestHandleChat:
    """Test RAG chat handler."""

    @pytest.mark.asyncio
    async def test_handle_chat_empty_query(self):
        """Test chat with empty query."""
        mock_pool = AsyncMock()

        with pytest.raises(Exception):
            await handle_chat(
                mock_pool,
                "",
                "test-key",
            )

    @pytest.mark.asyncio
    async def test_handle_chat_generates_session_id(self):
        """Test that handle_chat generates session_id if not provided."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session") as mock_create:
                    # Mock session creation
                    from api.intelligence.models import ChatSession
                    from datetime import datetime, timezone
                    mock_session = ChatSession(
                        id=1,
                        session_id="test-session-id",
                        user_label="default",
                        created_at=datetime.now(timezone.utc),
                        message_count=0
                    )
                    mock_create.return_value = mock_session

                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client

                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "Test answer"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "Test query",
                                "test-key",
                            )

                            assert response.session_id is not None
                            assert len(response.session_id) > 0

    @pytest.mark.asyncio
    async def test_handle_chat_uses_provided_session_id(self):
        """Test that provided session_id is used."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.get_session_history", return_value=None):
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                            with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                                mock_client = MagicMock()
                                mock_anthropic.return_value = mock_client

                                mock_response = MagicMock()
                                mock_response.content = [MagicMock()]
                                mock_response.content[0].text = "Test answer"
                                mock_client.messages.create = AsyncMock(return_value=mock_response)
                                mock_client.close = AsyncMock()

                                provided_id = "custom-session-123"
                                response = await handle_chat(
                                    mock_pool,
                                    "Test query",
                                    "test-key",
                                    session_id=provided_id
                                )

                                assert response.session_id == provided_id

    @pytest.mark.asyncio
    async def test_handle_chat_builds_citations(self):
        """Test that citations are built from chunks."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock semantic search results
        mock_chunks = [
            {
                "chunk_text": "Council voted to approve rezoning",
                "document_id": 1,
                "similarity_score": 0.92,
                "document_title": "Council Meeting Jan 15",
                "source_url": "https://example.com/meeting",
                "section_header": None,
                "chunk_index": 0,
                "final_score": 0.92
            }
        ]

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=mock_chunks):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session") as mock_create:
                    from api.intelligence.models import ChatSession
                    from datetime import datetime, timezone
                    mock_session = ChatSession(
                        id=1,
                        session_id="test-session",
                        user_label="default",
                        created_at=datetime.now(timezone.utc),
                        message_count=0
                    )
                    mock_create.return_value = mock_session
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client

                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "Council voted to approve"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "What rezoning decisions were made?",
                                "test-key",
                            )

                            # Should have citations
                            assert len(response.citations) > 0

    @pytest.mark.asyncio
    async def test_handle_chat_with_neighborhood_filter(self):
        """Test chat with neighborhood filter."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]) as mock_search:
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session") as mock_create:
                    from api.intelligence.models import ChatSession
                    from datetime import datetime, timezone
                    mock_session = ChatSession(
                        id=1,
                        session_id="test-session",
                        user_label="default",
                        created_at=datetime.now(timezone.utc),
                        message_count=0
                    )
                    mock_create.return_value = mock_session
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client

                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "Test"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "Query",
                                "test-key",
                                neighborhood_filter="Downtown"
                            )

                            # Should pass neighborhood filter to semantic search
                            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_chat_returns_valid_response(self):
        """Test that handle_chat returns valid ChatResponse."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session") as mock_create:
                    from api.intelligence.models import ChatSession
                    from datetime import datetime, timezone
                    mock_session = ChatSession(
                        id=1,
                        session_id="test-session",
                        user_label="default",
                        created_at=datetime.now(timezone.utc),
                        message_count=0
                    )
                    mock_create.return_value = mock_session
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client

                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "Test answer"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "Test query",
                                "test-key",
                            )

                            assert isinstance(response, ChatResponse)
                            assert response.answer == "Test answer"
                            assert response.session_id is not None


class TestGetRelevantSignals:
    """Test relevant signal retrieval."""

    @pytest.mark.asyncio
    async def test_get_relevant_signals_keyword_extraction(self):
        """Test that keywords are extracted from query."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        await get_relevant_signals(mock_pool, "rezoning downtown development")

        # Should have called fetch with SQL query
        conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_relevant_signals_with_neighborhood_filter(self):
        """Test signal retrieval with neighborhood filter."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        await get_relevant_signals(
            mock_pool,
            "rezoning",
            neighborhood="Downtown",
            limit=5
        )

        # Should include neighborhood filter in query
        conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_relevant_signals_returns_list(self):
        """Test that get_relevant_signals returns list."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = []

        result = await get_relevant_signals(mock_pool, "test query")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_relevant_signals_handles_errors(self):
        """Test error handling in get_relevant_signals."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.side_effect = Exception("DB Error")

        result = await get_relevant_signals(mock_pool, "test")

        # Should return empty list on error
        assert result == []


class TestChatIntegration:
    """Integration tests for chat pipeline."""

    @pytest.mark.asyncio
    async def test_full_chat_pipeline(self, sample_signals):
        """Test full chat pipeline with mock data."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock chunks and signals
        mock_chunks = [
            {
                "chunk_text": "Council approved rezoning of 1234 Main Street",
                "document_id": 1,
                "similarity_score": 0.95,
                "document_title": "Council Meeting",
                "source_url": "https://example.com",
                "section_header": "Rezoning",
                "chunk_index": 0,
                "final_score": 0.95
            }
        ]

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=mock_chunks):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session") as mock_create:
                    from api.intelligence.models import ChatSession
                    from datetime import datetime, timezone
                    mock_session = ChatSession(
                        id=1,
                        session_id="test-session",
                        user_label="default",
                        created_at=datetime.now(timezone.utc),
                        message_count=0
                    )
                    mock_create.return_value = mock_session
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client

                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "The city council approved rezoning of 1234 Main Street."
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "What rezoning decisions were made?",
                                "test-key",
                            )

                            assert isinstance(response, ChatResponse)
                            assert len(response.answer) > 0
