"""Tests for the RAG chat pipeline."""

from datetime import date
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from api.intelligence.chat import (
    CHAT_SYSTEM_PROMPT,
    handle_chat,
    get_relevant_signals,
)
from api.intelligence.models import ChatResponse, SourceCitation, SignalResponse


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


def _mock_generate_chat():
    """Return a patched generate_chat that returns a standard response tuple."""
    return patch(
        "api.intelligence.chat.generate_chat",
        new_callable=AsyncMock,
        return_value=("Test answer", "gemini-2.5-flash", 1.5),
    )


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
                        with _mock_generate_chat():
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
                        with _mock_generate_chat():
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
                        with _mock_generate_chat():
                            response = await handle_chat(
                                mock_pool,
                                "What rezoning decisions were made?",
                                "test-key",
                            )

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
                        with _mock_generate_chat():
                            response = await handle_chat(
                                mock_pool,
                                "Query",
                                "test-key",
                                neighborhood_filter="Downtown"
                            )

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
                        with _mock_generate_chat():
                            response = await handle_chat(
                                mock_pool,
                                "Test query",
                                "test-key",
                            )

                            assert isinstance(response, ChatResponse)
                            assert response.answer == "Test answer"
                            assert response.session_id is not None

    @pytest.mark.asyncio
    async def test_handle_chat_prefers_structured_signal_context_and_citations(self):
        """Structured rezoning decision queries should lead with signal context."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_chunks = [
            {
                "chunk_text": "Generic rezoning process guidance",
                "document_id": None,
                "document_title": "Zoning District Change Process",
                "source_url": "https://vancouver.ca/home-property-development/zoning-district-change.aspx",
                "section_header": None,
                "chunk_index": 0,
                "final_score": 0.78,
            }
        ]
        mock_signals = [
            SignalResponse(
                id=10179,
                document_id=10301,
                signal_type="rezoning_decision",
                summary="3055 Grandview Highway was approved on February 4, 2026 for 275 units.",
                headline="Renfrew Station Area: 22-Storey with 275 Units Approved",
                addresses=["3055 Grandview Highway"],
                neighborhood="Renfrew-Collingwood",
                decision="approved",
                vote_for=8,
                vote_against=2,
                sentiment="positive_for_development",
                severity="medium",
                confidence=0.91,
                event_date=date(2026, 2, 4),
                source_title="Regular Council Meeting Minutes - February 4, 2026",
                source_url="https://vancouver.ca/your-government/council-minutes-2026-02-04.aspx",
                source_type="council_minutes",
                source_date=date(2026, 2, 4),
            )
        ]
        captured: dict[str, str] = {}

        async def fake_generate_chat(**kwargs):
            captured["user_message"] = kwargs["user_message"]
            return ("Test answer", "gemini-2.5-flash", 1.1)

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=mock_chunks):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=mock_signals):
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
                        with patch(
                            "api.intelligence.chat.generate_chat",
                            new_callable=AsyncMock,
                            side_effect=fake_generate_chat,
                        ):
                            response = await handle_chat(
                                mock_pool,
                                "What rezoning applications were approved recently?",
                                "test-key",
                            )

        user_message = captured["user_message"]
        assert user_message.index("## INTELLIGENCE SIGNALS") < user_message.index("## RETRIEVED DOCUMENT CHUNKS")
        assert response.citations[0].document_title == "Regular Council Meeting Minutes - February 4, 2026"
        assert response.citations[0].document_id == 10301

    @pytest.mark.asyncio
    async def test_handle_chat_uses_archive_fallback_for_dead_signal_links(self):
        """Dead signal source URLs should fall back to the archived document URL."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = [
            {
                "id": 10301,
                "url_status": "dead",
                "archive_url": "https://web.archive.org/web/https://vancouver.ca/your-government/council-minutes-2026-02-04.aspx",
            }
        ]

        mock_signals = [
            SignalResponse(
                id=10179,
                document_id=10301,
                signal_type="rezoning_decision",
                summary="3055 Grandview Highway was approved on February 4, 2026 for 275 units.",
                headline="Renfrew Station Area: 22-Storey with 275 Units Approved",
                addresses=["3055 Grandview Highway"],
                neighborhood="Renfrew-Collingwood",
                decision="approved",
                vote_for=8,
                vote_against=2,
                sentiment="positive_for_development",
                severity="medium",
                confidence=0.91,
                event_date=date(2026, 2, 4),
                source_title="Regular Council Meeting Minutes - February 4, 2026",
                source_url="https://vancouver.ca/your-government/council-minutes-2026-02-04.aspx",
                source_type="council_minutes",
                source_date=date(2026, 2, 4),
            )
        ]

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=mock_signals):
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
                        with _mock_generate_chat():
                            response = await handle_chat(
                                mock_pool,
                                "What rezoning applications were approved recently?",
                                "test-key",
                            )

        assert response.citations[0].document_url == "https://web.archive.org/web/https://vancouver.ca/your-government/council-minutes-2026-02-04.aspx"
        assert response.citations[0].url_status == "dead"
        assert response.citations[0].archive_url == "https://web.archive.org/web/https://vancouver.ca/your-government/council-minutes-2026-02-04.aspx"


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

        assert result == []

    @pytest.mark.asyncio
    async def test_get_relevant_signals_prefers_structured_recent_approved_rezonings(self):
        """Approved recent rezoning queries should use explicit signal filters."""
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock()
        conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        conn.fetch.return_value = [
            {
                "id": 1,
                "document_id": 10,
                "signal_type": "rezoning_decision",
                "summary": "3055 Grandview Highway approved.",
                "headline": "Renfrew Station Area: 22-Storey with 275 Units Approved",
                "addresses": ["3055 Grandview Highway"],
                "neighborhood": "Renfrew-Collingwood",
                "decision": "approved",
                "vote_for": 8,
                "vote_against": 2,
                "sentiment": "positive_for_development",
                "severity": "medium",
                "confidence": 0.91,
                "event_date": date(2026, 2, 4),
                "source_title": "Regular Council Meeting Minutes - February 4, 2026",
                "source_url": "https://vancouver.ca/your-government/council-minutes-2026-02-04.aspx",
                "source_type": "council_minutes",
                "source_date": date(2026, 2, 4),
            },
            {
                "id": 2,
                "document_id": 11,
                "signal_type": "rezoning_decision",
                "summary": "3055 Grandview Highway approved.",
                "headline": "Renfrew Station Area: 22-Storey with 275 Units Approved",
                "addresses": ["3055 Grandview Highway"],
                "neighborhood": "Renfrew-Collingwood",
                "decision": "approved",
                "vote_for": 8,
                "vote_against": 2,
                "sentiment": "positive_for_development",
                "severity": "medium",
                "confidence": 0.88,
                "event_date": date(2026, 2, 4),
                "source_title": "Regular Council Meeting Minutes - February 4, 2026",
                "source_url": "https://vancouver.ca/your-government/vancouver-city-council.aspx#doc-10179",
                "source_type": "council_minutes",
                "source_date": date(2026, 2, 4),
            },
        ]

        result = await get_relevant_signals(
            mock_pool,
            "What rezoning applications were approved recently?",
            limit=5,
        )

        assert len(result) == 1
        assert conn.fetch.called
        query_call = conn.fetch.call_args
        query_string = query_call[0][0]
        params = query_call[0][1:]
        assert "isig.signal_type = $1" in query_string
        assert "isig.decision = $2" in query_string
        assert params[0] == "rezoning_decision"
        assert params[1] == "approved"


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
                        with patch(
                            "api.intelligence.chat.generate_chat",
                            new_callable=AsyncMock,
                            return_value=("The city council approved rezoning of 1234 Main Street.", "gemini-2.5-flash", 1.2),
                        ):
                            response = await handle_chat(
                                mock_pool,
                                "What rezoning decisions were made?",
                                "test-key",
                            )

                            assert isinstance(response, ChatResponse)
                            assert len(response.answer) > 0
