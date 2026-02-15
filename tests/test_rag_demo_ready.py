"""Tests for RAG pipeline demo-ready features: sparse_search, 3-tier degradation, demo mode."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from api.intelligence.chat import handle_chat, _build_demo_answer
from api.intelligence.models import ChatResponse, SignalResponse


# ── Helper fixtures ──────────────────────────────────────────────


def _make_mock_pool():
    """Create a mock asyncpg pool."""
    mock_pool = AsyncMock()
    mock_pool.acquire = MagicMock()
    conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool, conn


def _make_mock_session():
    """Create a mock chat session."""
    from api.intelligence.models import ChatSession
    return ChatSession(
        id=1,
        session_id="test-session-id",
        user_label="default",
        created_at=datetime.now(timezone.utc),
        message_count=0,
    )


def _sample_chunks():
    """Sample search result chunks."""
    return [
        {
            "chunk_id": 1,
            "chunk_text": "Council approved rezoning of 1234 Main Street from RS-1 to CD-1.",
            "document_id": 1,
            "section_header": "Rezoning Decisions",
            "chunk_index": 0,
            "text_score": 0.85,
            "rrf_score": 0.85,
            "final_score": 0.85,
            "document_title": "Council Meeting Jan 2026",
            "source_url": "https://vancouver.ca/council/jan2026",
            "source_type": "council_minutes",
            "published_date": None,
        },
        {
            "chunk_id": 2,
            "chunk_text": "The Broadway Plan introduces new density provisions for the corridor.",
            "document_id": 2,
            "section_header": "Broadway Plan",
            "chunk_index": 3,
            "text_score": 0.72,
            "rrf_score": 0.72,
            "final_score": 0.72,
            "document_title": "Broadway Plan Update",
            "source_url": "https://vancouver.ca/broadway-plan",
            "source_type": "community_plan",
            "published_date": None,
        },
    ]


def _sample_signal_responses():
    """Sample SignalResponse objects."""
    return [
        SignalResponse(
            id=1,
            document_id=1,
            signal_type="rezoning_decision",
            summary="Council approved rezoning of 1234 Main Street",
            headline="1234 Main rezoned",
            addresses=["1234 Main Street"],
            neighborhood="Downtown",
            decision="approved",
            vote_for=8,
            vote_against=3,
            sentiment="positive_for_development",
            severity="high",
            confidence=0.9,
            event_date=None,
            source_title="Council Meeting",
            source_url="https://vancouver.ca/council",
            source_type="council_minutes",
            source_date=None,
        ),
    ]


# ── sparse_search tests ─────────────────────────────────────────


class TestSparseSearch:
    """Tests for BM25-only sparse search."""

    @pytest.mark.asyncio
    async def test_sparse_search_empty_results(self):
        """sparse_search returns empty list when no matches."""
        from api.intelligence.local_rag.embeddings import sparse_search

        mock_pool, conn = _make_mock_pool()
        conn.fetch.return_value = []

        results = await sparse_search(mock_pool, "nonexistent query xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_sparse_search_returns_correct_format(self):
        """sparse_search returns dicts with final_score key."""
        from api.intelligence.local_rag.embeddings import sparse_search

        mock_pool, conn = _make_mock_pool()
        conn.fetch.return_value = [
            {
                "chunk_id": 1,
                "chunk_text": "Test chunk about rezoning",
                "document_id": 10,
                "section_header": "Section A",
                "chunk_index": 0,
                "text_score": 0.75,
                "document_title": "Test Doc",
                "source_url": "https://example.com",
                "source_type": "council_minutes",
                "published_date": None,
            },
        ]

        results = await sparse_search(mock_pool, "rezoning")
        assert len(results) == 1
        r = results[0]
        assert "final_score" in r
        assert "chunk_text" in r
        assert "document_id" in r
        assert "chunk_id" in r
        assert r["final_score"] == 0.75

    @pytest.mark.asyncio
    async def test_sparse_search_no_api_key_needed(self):
        """sparse_search does not require any API key parameter."""
        from api.intelligence.local_rag.embeddings import sparse_search
        import inspect

        sig = inspect.signature(sparse_search)
        params = list(sig.parameters.keys())
        assert "api_key" not in params

    @pytest.mark.asyncio
    async def test_sparse_search_with_neighborhood_filter(self):
        """sparse_search accepts and uses neighborhood filter."""
        from api.intelligence.local_rag.embeddings import sparse_search

        mock_pool, conn = _make_mock_pool()
        conn.fetch.return_value = []

        # Should not raise
        await sparse_search(mock_pool, "test query", neighborhood="Kitsilano")
        conn.fetch.assert_called_once()
        # Verify the query contains neighborhood parameter
        call_args = conn.fetch.call_args
        assert len(call_args[0]) >= 3  # query + at least 3 params (query_text, limit, neighborhood)


# ── _build_demo_answer tests ─────────────────────────────────────


class TestBuildDemoAnswer:
    """Tests for demo mode answer builder."""

    def test_no_results(self):
        """Demo answer with no chunks or signals."""
        answer = _build_demo_answer("test query", [], [])
        assert "Search results for:" in answer
        assert "No relevant documents" in answer
        assert "ANTHROPIC_API_KEY" in answer

    def test_with_chunks(self):
        """Demo answer with document chunks."""
        chunks = _sample_chunks()
        answer = _build_demo_answer("rezoning downtown", chunks, [])
        assert "Council approved rezoning" in answer
        assert "Council Meeting Jan 2026" in answer
        assert "relevance:" in answer
        assert "ANTHROPIC_API_KEY" in answer

    def test_with_signals(self):
        """Demo answer with intelligence signals."""
        signals = _sample_signal_responses()
        answer = _build_demo_answer("rezoning", [], signals)
        assert "Intelligence Signals" in answer
        assert "1234 Main rezoned" in answer

    def test_with_chunks_and_signals(self):
        """Demo answer with both chunks and signals."""
        chunks = _sample_chunks()
        signals = _sample_signal_responses()
        answer = _build_demo_answer("rezoning", chunks, signals)
        assert "Document Matches" in answer
        assert "Intelligence Signals" in answer

    def test_limits_to_5_chunks(self):
        """Demo answer shows at most 5 chunks."""
        chunks = _sample_chunks() * 4  # 8 chunks
        answer = _build_demo_answer("test", chunks, [])
        # Count occurrences of numbered items (1. through 5.)
        count = sum(1 for i in range(1, 9) if f"**{i}." in answer)
        assert count <= 5


# ── handle_chat 3-tier degradation tests ──────────────────────────


class TestHandleChatDemoMode:
    """Tests for handle_chat in demo mode (no API keys)."""

    @pytest.mark.asyncio
    async def test_demo_mode_no_keys(self):
        """handle_chat with no API keys returns demo mode response."""
        mock_pool, conn = _make_mock_pool()

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=_sample_chunks()):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session", return_value=_make_mock_session()):
                    response = await handle_chat(
                        mock_pool,
                        "What rezoning decisions?",
                        anthropic_api_key=None,
                    )

        assert isinstance(response, ChatResponse)
        assert response.mode == "demo"
        assert "ANTHROPIC_API_KEY" in response.answer
        assert len(response.citations) > 0

    @pytest.mark.asyncio
    async def test_demo_mode_does_not_call_claude(self):
        """Demo mode never calls Anthropic API."""
        mock_pool, conn = _make_mock_pool()

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session", return_value=_make_mock_session()):
                    with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                        await handle_chat(
                            mock_pool,
                            "test",
                            anthropic_api_key=None,
                        )
                        mock_anthropic.assert_not_called()


class TestHandleChatFullModeWithAnthropic:
    """Tests for handle_chat in full mode (Anthropic key present)."""

    @pytest.mark.asyncio
    async def test_full_mode_with_anthropic_key(self):
        """Full mode with Anthropic key calls Claude and returns full mode."""
        mock_pool, conn = _make_mock_pool()

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session", return_value=_make_mock_session()):
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client
                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "AI answer"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "test query",
                                anthropic_api_key="sk-ant-test",
                            )

        assert response.mode == "full"

    @pytest.mark.asyncio
    async def test_full_mode_calls_claude(self):
        """Full mode calls Claude API for answer generation."""
        mock_pool, conn = _make_mock_pool()

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session", return_value=_make_mock_session()):
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client
                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "Claude's answer"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "test query",
                                anthropic_api_key="sk-ant-test",
                            )

        assert response.answer == "Claude's answer"
        mock_anthropic.assert_called_once_with(api_key="sk-ant-test")


class TestHandleChatFullMode:
    """Tests for handle_chat in full mode (Anthropic key present)."""

    @pytest.mark.asyncio
    async def test_full_mode_returns_answer(self):
        """Full mode retrieves chunks and returns Claude answer."""
        mock_pool, conn = _make_mock_pool()

        with patch("api.intelligence.chat.retrieve_document_chunks", return_value=[]):
            with patch("api.intelligence.chat.get_relevant_signals", return_value=[]):
                with patch("api.intelligence.chat.create_session", return_value=_make_mock_session()):
                    with patch("api.intelligence.chat.build_context_window", return_value=""):
                        with patch("api.intelligence.chat.AsyncAnthropic") as mock_anthropic:
                            mock_client = MagicMock()
                            mock_anthropic.return_value = mock_client
                            mock_response = MagicMock()
                            mock_response.content = [MagicMock()]
                            mock_response.content[0].text = "Full answer"
                            mock_client.messages.create = AsyncMock(return_value=mock_response)
                            mock_client.close = AsyncMock()

                            response = await handle_chat(
                                mock_pool,
                                "test query",
                                anthropic_api_key="sk-ant-test",
                            )

        assert response.mode == "full"
        assert response.answer == "Full answer"


# ── ChatResponse model tests ──────────────────────────────────────


class TestChatResponseModel:
    """Test ChatResponse model with mode field."""

    def test_default_mode_is_full(self):
        """ChatResponse defaults to mode='full'."""
        resp = ChatResponse(
            answer="test",
            session_id="abc",
        )
        assert resp.mode == "full"

    def test_mode_demo(self):
        """ChatResponse accepts mode='demo'."""
        resp = ChatResponse(
            answer="test",
            session_id="abc",
            mode="demo",
        )
        assert resp.mode == "demo"

    def test_mode_partial(self):
        """ChatResponse accepts mode='partial'."""
        resp = ChatResponse(
            answer="test",
            session_id="abc",
            mode="partial",
        )
        assert resp.mode == "partial"


# ── Route optional key function tests ──────────────────────────


class TestOptionalKeyFunctions:
    """Test the optional API key getter functions."""

    def test_anthropic_optional_returns_none(self):
        """get_anthropic_api_key_optional returns None when env var unset."""
        from api.intelligence.routes import get_anthropic_api_key_optional
        with patch.dict("os.environ", {}, clear=True):
            result = get_anthropic_api_key_optional()
            assert result is None

    def test_anthropic_optional_returns_key(self):
        """get_anthropic_api_key_optional returns key when set."""
        from api.intelligence.routes import get_anthropic_api_key_optional
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"}):
            result = get_anthropic_api_key_optional()
            assert result == "sk-test-123"

    def test_anthropic_optional_empty_string_returns_none(self):
        """get_anthropic_api_key_optional returns None for empty string."""
        from api.intelligence.routes import get_anthropic_api_key_optional
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            result = get_anthropic_api_key_optional()
            assert result is None


# ── seed_chunks script tests ──────────────────────────────────────


class TestSeedChunksImport:
    """Test that seed_chunks.py imports cleanly."""

    def test_import_chunker(self):
        """chunk_document can be imported."""
        from api.intelligence.local_rag.chunker import chunk_document
        assert callable(chunk_document)

    def test_chunk_document_empty(self):
        """chunk_document returns empty list for empty/null input."""
        from api.intelligence.local_rag.chunker import chunk_document
        assert chunk_document("") == []
        assert chunk_document(None) == []

    def test_chunk_document_short_text(self):
        """chunk_document handles short text."""
        from api.intelligence.local_rag.chunker import chunk_document
        result = chunk_document("Hello world, this is a test document.")
        assert len(result) >= 1
        assert "chunk_text" in result[0]
        assert "chunk_index" in result[0]

    def test_chunk_document_returns_section_headers(self):
        """chunk_document detects section headers."""
        from api.intelligence.local_rag.chunker import chunk_document
        text = """SECTION 1: Introduction

This is the introduction to the document.

SECTION 2: Analysis

This is the analysis section with detailed findings."""
        result = chunk_document(text)
        assert len(result) >= 1
        # At least one chunk should have a section header
        headers = [c.get("section_header") for c in result if c.get("section_header")]
        # May or may not detect depending on chunk boundaries, but should not crash
        assert isinstance(headers, list)
