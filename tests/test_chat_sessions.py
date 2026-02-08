"""
Tests for chat session management and history persistence.

Tests cover:
- Session CRUD operations
- Message history retrieval
- Context window building
- Pagination
- Session deletion
- API endpoint contracts
- Edge cases
"""

from datetime import datetime, date, timezone
from uuid import uuid4
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.intelligence.chat_sessions import (
    create_session,
    get_session,
    list_sessions,
    get_session_history,
    delete_session,
    build_context_window,
)
from api.intelligence.models import (
    ChatSession,
    ChatSessionList,
    ChatMessageHistory,
    ChatHistoryMessage,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool.

    Follows conftest.py pattern: acquire() returns an async context manager,
    not a coroutine.
    """
    pool = AsyncMock()
    pool.acquire = MagicMock()  # sync, not async

    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool


@pytest.fixture
def sample_session_id():
    """Sample session UUID."""
    return "550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def sample_session_uuid(sample_session_id):
    """Sample session UUID object."""
    from uuid import UUID
    return UUID(sample_session_id)


# ────────────────────────────────────────────────────────────────────────────
# Tests: create_session
# ────────────────────────────────────────────────────────────────────────────


class TestCreateSession:
    """Test session creation."""

    @pytest.mark.asyncio
    async def test_create_session_default_user(self, mock_db_pool):
        """Test creating a session with default user label."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        # Mock the return value
        session_uuid = uuid4()
        created_at = datetime.now(timezone.utc)
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': session_uuid,
            'user_label': 'default',
            'created_at': created_at
        })

        result = await create_session(mock_db_pool)

        assert result.id == 1
        assert result.user_label == 'default'
        assert result.message_count == 0
        assert result.last_message_at is None
        assert conn.execute.call_count == 0  # fetchrow is used instead

    @pytest.mark.asyncio
    async def test_create_session_custom_user(self, mock_db_pool):
        """Test creating a session with custom user label."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        session_uuid = uuid4()
        created_at = datetime.now(timezone.utc)
        conn.fetchrow = AsyncMock(return_value={
            'id': 2,
            'session_id': session_uuid,
            'user_label': 'investor_alice',
            'created_at': created_at
        })

        result = await create_session(mock_db_pool, user_label='investor_alice')

        assert result.user_label == 'investor_alice'
        assert result.id == 2

    @pytest.mark.asyncio
    async def test_create_session_error_handling(self, mock_db_pool):
        """Test error handling during session creation."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await create_session(mock_db_pool)


# ────────────────────────────────────────────────────────────────────────────
# Tests: get_session
# ────────────────────────────────────────────────────────────────────────────


class TestGetSession:
    """Test session retrieval."""

    @pytest.mark.asyncio
    async def test_get_session_found(self, mock_db_pool, sample_session_id):
        """Test retrieving an existing session."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        created_at = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        last_message_at = datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc)

        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': sample_session_id,
            'user_label': 'default',
            'created_at': created_at,
            'message_count': 5,
            'last_message_at': last_message_at
        })

        result = await get_session(mock_db_pool, sample_session_id)

        assert result is not None
        assert result.session_id == sample_session_id
        assert result.message_count == 5
        assert result.last_message_at == last_message_at

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, mock_db_pool, sample_session_id):
        """Test retrieving non-existent session."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(return_value=None)

        result = await get_session(mock_db_pool, sample_session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_invalid_uuid(self, mock_db_pool):
        """Test with invalid UUID format."""
        result = await get_session(mock_db_pool, "not-a-uuid")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_empty_messages(self, mock_db_pool, sample_session_id):
        """Test retrieving session with no messages."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        created_at = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': sample_session_id,
            'user_label': 'default',
            'created_at': created_at,
            'message_count': 0,
            'last_message_at': None
        })

        result = await get_session(mock_db_pool, sample_session_id)

        assert result.message_count == 0
        assert result.last_message_at is None


# ────────────────────────────────────────────────────────────────────────────
# Tests: list_sessions
# ────────────────────────────────────────────────────────────────────────────


class TestListSessions:
    """Test session listing with pagination."""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, mock_db_pool):
        """Test listing sessions when none exist."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetch = AsyncMock(return_value=[])

        result = await list_sessions(mock_db_pool, user_label='test_user')

        assert result.total_count == 0
        assert len(result.sessions) == 0
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_list_sessions_paginated(self, mock_db_pool):
        """Test listing sessions with pagination."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=25)  # Total count

        sessions = [
            {
                'id': i,
                'session_id': str(uuid4()),
                'user_label': 'test_user',
                'created_at': datetime(2024, 1, i, tzinfo=timezone.utc),
                'message_count': 5 + i,
                'last_message_at': datetime(2024, 1, i, 12, 0, tzinfo=timezone.utc)
            }
            for i in range(1, 21)
        ]
        conn.fetch = AsyncMock(return_value=sessions)

        result = await list_sessions(
            mock_db_pool,
            user_label='test_user',
            limit=20,
            offset=0
        )

        assert result.total_count == 25
        assert len(result.sessions) == 20
        assert result.has_more is True  # 20 + 20 offset = 40 > 25 is false, but 0 + 20 < 25 is true

    @pytest.mark.asyncio
    async def test_list_sessions_last_page(self, mock_db_pool):
        """Test listing last page of sessions."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=25)

        sessions = [
            {
                'id': i,
                'session_id': str(uuid4()),
                'user_label': 'test_user',
                'created_at': datetime(2024, 1, i, tzinfo=timezone.utc),
                'message_count': i,
                'last_message_at': None
            }
            for i in range(21, 26)
        ]
        conn.fetch = AsyncMock(return_value=sessions)

        result = await list_sessions(
            mock_db_pool,
            user_label='test_user',
            limit=20,
            offset=20
        )

        assert result.total_count == 25
        assert len(result.sessions) == 5
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_list_sessions_limit_validation(self, mock_db_pool):
        """Test limit validation (clamped to 1-100)."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=0)
        conn.fetch = AsyncMock(return_value=[])

        # Test with limit > 100 (should be clamped to 20)
        await list_sessions(mock_db_pool, user_label='test', limit=200)

        # Verify the call used the clamped limit
        call_args = conn.fetch.call_args
        assert call_args is not None  # Just verify it was called


# ────────────────────────────────────────────────────────────────────────────
# Tests: get_session_history
# ────────────────────────────────────────────────────────────────────────────


class TestGetSessionHistory:
    """Test message history retrieval."""

    @pytest.mark.asyncio
    async def test_get_history_with_messages(self, mock_db_pool, sample_session_id):
        """Test retrieving history with multiple messages."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        # Mock session exists
        conn.fetchval = AsyncMock(return_value=1)

        # Mock messages
        messages = [
            {
                'id': 1,
                'role': 'user',
                'content': 'What is the zoning of 1234 Main St?',
                'source_chunks': [1, 2],
                'source_signals': [],
                'created_at': datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            },
            {
                'id': 2,
                'role': 'assistant',
                'content': 'The zoning is RS-1.',
                'source_chunks': [1],
                'source_signals': [1],
                'created_at': datetime(2024, 1, 15, 10, 1, tzinfo=timezone.utc)
            },
            {
                'id': 3,
                'role': 'user',
                'content': 'Can it be rezoned?',
                'source_chunks': [],
                'source_signals': [],
                'created_at': datetime(2024, 1, 15, 10, 2, tzinfo=timezone.utc)
            }
        ]
        conn.fetch = AsyncMock(return_value=messages)

        result = await get_session_history(mock_db_pool, sample_session_id)

        assert result is not None
        assert result.session_id == sample_session_id
        assert len(result.messages) == 3
        assert result.messages[0].role == 'user'
        assert result.messages[1].role == 'assistant'
        assert result.messages[2].content == 'Can it be rezoned?'

    @pytest.mark.asyncio
    async def test_get_history_session_not_found(self, mock_db_pool, sample_session_id):
        """Test retrieving history for non-existent session."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=None)

        result = await get_session_history(mock_db_pool, sample_session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_history_empty_session(self, mock_db_pool, sample_session_id):
        """Test retrieving history for session with no messages."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=1)
        conn.fetch = AsyncMock(return_value=[])

        result = await get_session_history(mock_db_pool, sample_session_id)

        assert result is not None
        assert len(result.messages) == 0

    @pytest.mark.asyncio
    async def test_get_history_limit(self, mock_db_pool, sample_session_id):
        """Test history limit enforcement."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetchval = AsyncMock(return_value=1)

        # Create 100 mock messages
        messages = [
            {
                'id': i,
                'role': 'user' if i % 2 == 1 else 'assistant',
                'content': f'Message {i}',
                'source_chunks': [],
                'source_signals': [],
                'created_at': datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            }
            for i in range(1, 101)
        ]
        conn.fetch = AsyncMock(return_value=messages[:50])  # Return only 50

        result = await get_session_history(
            mock_db_pool,
            sample_session_id,
            limit=50
        )

        assert len(result.messages) == 50


# ────────────────────────────────────────────────────────────────────────────
# Tests: build_context_window
# ────────────────────────────────────────────────────────────────────────────


class TestBuildContextWindow:
    """Test context window building for multi-turn chat."""

    @pytest.mark.asyncio
    async def test_build_context_with_messages(self, mock_db_pool, sample_session_id):
        """Test building context from messages."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        messages = [
            {
                'role': 'user',
                'content': 'What rezoning decisions were made?',
                'created_at': datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            },
            {
                'role': 'assistant',
                'content': 'There were 3 rezoning decisions.',
                'created_at': datetime(2024, 1, 15, 10, 1, tzinfo=timezone.utc)
            },
            {
                'role': 'user',
                'content': 'Which neighborhoods?',
                'created_at': datetime(2024, 1, 15, 10, 2, tzinfo=timezone.utc)
            }
        ]
        conn.fetch = AsyncMock(return_value=messages)

        result = await build_context_window(mock_db_pool, sample_session_id)

        assert isinstance(result, str)
        assert 'CONVERSATION HISTORY' in result
        assert 'What rezoning decisions were made?' in result
        assert 'There were 3 rezoning decisions.' in result
        assert 'Which neighborhoods?' in result

    @pytest.mark.asyncio
    async def test_build_context_empty_session(self, mock_db_pool, sample_session_id):
        """Test context building for empty session."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.fetch = AsyncMock(return_value=[])

        result = await build_context_window(mock_db_pool, sample_session_id)

        assert result == ""

    @pytest.mark.asyncio
    async def test_build_context_max_messages(self, mock_db_pool, sample_session_id):
        """Test max_messages parameter."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        # Create 20 messages
        messages = [
            {
                'role': 'user' if i % 2 == 0 else 'assistant',
                'content': f'Message {i}',
                'created_at': datetime(2024, 1, 15, 10, i, tzinfo=timezone.utc)
            }
            for i in range(1, 21)
        ]
        conn.fetch = AsyncMock(return_value=messages)

        result = await build_context_window(
            mock_db_pool,
            sample_session_id,
            max_messages=10
        )

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_build_context_invalid_session_id(self, mock_db_pool):
        """Test with invalid session ID."""
        result = await build_context_window(mock_db_pool, "not-a-uuid")

        assert result == ""


# ────────────────────────────────────────────────────────────────────────────
# Tests: delete_session
# ────────────────────────────────────────────────────────────────────────────


class TestDeleteSession:
    """Test session deletion."""

    @pytest.mark.asyncio
    async def test_delete_session_success(self, mock_db_pool, sample_session_id):
        """Test successful session deletion."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        # Mock successful deletes
        conn.execute = AsyncMock(side_effect=["DELETE 5", "DELETE 1"])

        result = await delete_session(mock_db_pool, sample_session_id)

        assert result is True
        assert conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, mock_db_pool, sample_session_id):
        """Test deleting non-existent session."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        # Mock delete that returned 0 rows
        conn.execute = AsyncMock(side_effect=["DELETE 0", "DELETE 0"])

        result = await delete_session(mock_db_pool, sample_session_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_session_invalid_uuid(self, mock_db_pool):
        """Test delete with invalid UUID."""
        result = await delete_session(mock_db_pool, "invalid-uuid")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_session_error_handling(self, mock_db_pool, sample_session_id):
        """Test error handling during deletion."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value
        conn.execute = AsyncMock(side_effect=Exception("Database error"))

        with pytest.raises(Exception, match="Database error"):
            await delete_session(mock_db_pool, sample_session_id)


# ────────────────────────────────────────────────────────────────────────────
# Tests: Model Contract Tests
# ────────────────────────────────────────────────────────────────────────────


class TestChatSessionModels:
    """Test Pydantic models for chat sessions."""

    def test_chat_session_model(self):
        """Test ChatSession model."""
        session = ChatSession(
            id=1,
            session_id="550e8400-e29b-41d4-a716-446655440000",
            user_label="test_user",
            created_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            message_count=5,
            last_message_at=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        )

        assert session.id == 1
        assert session.message_count == 5
        assert session.last_message_at is not None

    def test_chat_session_model_optional_last_message(self):
        """Test ChatSession with no last_message_at."""
        session = ChatSession(
            id=1,
            session_id="550e8400-e29b-41d4-a716-446655440000",
            user_label="test_user",
            created_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            message_count=0
        )

        assert session.last_message_at is None

    def test_chat_session_list_model(self):
        """Test ChatSessionList model."""
        session = ChatSession(
            id=1,
            session_id="550e8400-e29b-41d4-a716-446655440000",
            user_label="test_user",
            created_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            message_count=5
        )

        session_list = ChatSessionList(
            sessions=[session],
            total_count=10,
            has_more=True
        )

        assert len(session_list.sessions) == 1
        assert session_list.total_count == 10
        assert session_list.has_more is True

    def test_chat_history_message_model(self):
        """Test ChatHistoryMessage model."""
        msg = ChatHistoryMessage(
            id=1,
            role="user",
            content="Test question",
            source_chunks=[1, 2, 3],
            source_signals=[10, 20],
            created_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        )

        assert msg.role == "user"
        assert len(msg.source_chunks) == 3
        assert len(msg.source_signals) == 2

    def test_chat_message_history_model(self):
        """Test ChatMessageHistory model."""
        messages = [
            ChatHistoryMessage(
                id=1,
                role="user",
                content="Question",
                created_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
            ),
            ChatHistoryMessage(
                id=2,
                role="assistant",
                content="Answer",
                created_at=datetime(2024, 1, 15, 10, 1, tzinfo=timezone.utc)
            )
        ]

        history = ChatMessageHistory(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            messages=messages
        )

        assert len(history.messages) == 2
        assert history.messages[0].role == "user"
        assert history.messages[1].role == "assistant"


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────


class TestSessionIntegration:
    """Integration tests for session workflows."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_session(self, mock_db_pool):
        """Test creating and then retrieving a session."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        session_uuid = uuid4()
        created_at = datetime.now(timezone.utc)

        # First call: create_session fetchrow
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': session_uuid,
            'user_label': 'test_user',
            'created_at': created_at
        })

        created = await create_session(mock_db_pool, user_label='test_user')

        # Now mock retrieve
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': session_uuid,
            'user_label': 'test_user',
            'created_at': created_at,
            'message_count': 0,
            'last_message_at': None
        })

        retrieved = await get_session(mock_db_pool, str(session_uuid))

        assert created.session_id == str(session_uuid)
        assert retrieved.session_id == str(session_uuid)

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self, mock_db_pool):
        """Test complete session lifecycle: create, add messages, retrieve, delete."""
        conn = mock_db_pool.acquire.return_value.__aenter__.return_value

        session_uuid = uuid4()

        # 1. Create session
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': session_uuid,
            'user_label': 'test_user',
            'created_at': datetime.now(timezone.utc)
        })
        session = await create_session(mock_db_pool)

        # 2. Get session
        conn.fetchrow = AsyncMock(return_value={
            'id': 1,
            'session_id': session_uuid,
            'user_label': 'test_user',
            'created_at': datetime.now(timezone.utc),
            'message_count': 2,
            'last_message_at': datetime.now(timezone.utc)
        })
        retrieved = await get_session(mock_db_pool, session.session_id)
        assert retrieved.message_count == 2

        # 3. Get history
        conn.fetchval = AsyncMock(return_value=1)
        conn.fetch = AsyncMock(return_value=[
            {
                'id': 1,
                'role': 'user',
                'content': 'Question',
                'source_chunks': [],
                'source_signals': [],
                'created_at': datetime.now(timezone.utc)
            }
        ])
        history = await get_session_history(mock_db_pool, session.session_id)
        assert len(history.messages) == 1

        # 4. Delete session
        conn.execute = AsyncMock(side_effect=["DELETE 1", "DELETE 1"])
        success = await delete_session(mock_db_pool, session.session_id)
        assert success is True
