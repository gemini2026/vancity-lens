"""
Session and history management for VanCity Lens chat.

Provides functions to:
- Create and retrieve chat sessions
- List sessions for a user
- Retrieve full conversation history
- Build context windows for multi-turn chat
- Manage session lifecycle (delete)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from .models import (
    ChatSession,
    ChatSessionList,
    ChatMessageHistory,
    ChatHistoryMessage,
)

logger = logging.getLogger(__name__)


async def create_session(
    db_pool: asyncpg.Pool, user_label: str = "default"
) -> ChatSession:
    """
    Create a new chat session.

    Args:
        db_pool: AsyncPG connection pool
        user_label: Label/identifier for the user (for analytics)

    Returns:
        ChatSession object with generated session_id
    """
    session_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)

    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO chat_sessions (session_id, user_label, created_at)
                VALUES ($1, $2, $3)
                RETURNING id, session_id, user_label, created_at
            """,
                session_id,
                user_label,
                created_at,
            )

        return ChatSession(
            id=result["id"],
            session_id=str(result["session_id"]),
            user_label=result["user_label"],
            created_at=result["created_at"],
            message_count=0,
            last_message_at=None,
        )

    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise


async def get_session(db_pool: asyncpg.Pool, session_id: str) -> Optional[ChatSession]:
    """
    Get a session by ID with message count and last message timestamp.

    Args:
        db_pool: AsyncPG connection pool
        session_id: UUID string of the session

    Returns:
        ChatSession with message_count and last_message_at, or None if not found
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        logger.error(f"Invalid session_id format: {session_id}")
        return None

    try:
        async with db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT
                    cs.id,
                    cs.session_id,
                    cs.user_label,
                    cs.created_at,
                    COUNT(cm.id)::INT as message_count,
                    MAX(cm.created_at) as last_message_at
                FROM chat_sessions cs
                LEFT JOIN chat_messages cm ON cs.session_id = cm.session_id
                WHERE cs.session_id = $1
                GROUP BY cs.id, cs.session_id, cs.user_label, cs.created_at
            """,
                session_uuid,
            )

        if not result:
            return None

        return ChatSession(
            id=result["id"],
            session_id=str(result["session_id"]),
            user_label=result["user_label"],
            created_at=result["created_at"],
            message_count=result["message_count"] or 0,
            last_message_at=result["last_message_at"],
        )

    except Exception as e:
        logger.error(f"Error retrieving session {session_id}: {e}")
        raise


async def list_sessions(
    db_pool: asyncpg.Pool, user_label: str, limit: int = 20, offset: int = 0
) -> ChatSessionList:
    """
    List all sessions for a user with pagination.

    Args:
        db_pool: AsyncPG connection pool
        user_label: User label to filter by
        limit: Number of sessions per page
        offset: Pagination offset

    Returns:
        ChatSessionList with paginated sessions and total count
    """
    if limit < 1 or limit > 100:
        limit = 20
    if offset < 0:
        offset = 0

    try:
        async with db_pool.acquire() as conn:
            # Get total count
            count_result = await conn.fetchval(
                "SELECT COUNT(*) FROM chat_sessions WHERE user_label = $1", user_label
            )

            # Get paginated results
            rows = await conn.fetch(
                """
                SELECT
                    cs.id,
                    cs.session_id,
                    cs.user_label,
                    cs.created_at,
                    COUNT(cm.id)::INT as message_count,
                    MAX(cm.created_at) as last_message_at
                FROM chat_sessions cs
                LEFT JOIN chat_messages cm ON cs.session_id = cm.session_id
                WHERE cs.user_label = $1
                GROUP BY cs.id, cs.session_id, cs.user_label, cs.created_at
                ORDER BY cs.created_at DESC
                LIMIT $2 OFFSET $3
            """,
                user_label,
                limit,
                offset,
            )

        sessions = [
            ChatSession(
                id=row["id"],
                session_id=str(row["session_id"]),
                user_label=row["user_label"],
                created_at=row["created_at"],
                message_count=row["message_count"] or 0,
                last_message_at=row["last_message_at"],
            )
            for row in rows
        ]

        has_more = (offset + limit) < count_result

        return ChatSessionList(
            sessions=sessions, total_count=count_result, has_more=has_more
        )

    except Exception as e:
        logger.error(f"Error listing sessions for {user_label}: {e}")
        raise


async def get_session_history(
    db_pool: asyncpg.Pool, session_id: str, limit: int = 50
) -> Optional[ChatMessageHistory]:
    """
    Get the full message history for a session.

    Args:
        db_pool: AsyncPG connection pool
        session_id: UUID string of the session
        limit: Maximum number of messages to retrieve (most recent first)

    Returns:
        ChatMessageHistory with messages, or None if session not found
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        logger.error(f"Invalid session_id format: {session_id}")
        return None

    if limit < 1 or limit > 500:
        limit = 50

    try:
        async with db_pool.acquire() as conn:
            # Verify session exists
            session_exists = await conn.fetchval(
                "SELECT id FROM chat_sessions WHERE session_id = $1", session_uuid
            )

            if not session_exists:
                return None

            # Get messages ordered by creation (oldest first for context building)
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    role,
                    content,
                    source_chunks,
                    source_signals,
                    created_at
                FROM chat_messages
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT $2
            """,
                session_uuid,
                limit,
            )

        messages = [
            ChatHistoryMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                source_chunks=row["source_chunks"] or [],
                source_signals=row["source_signals"] or [],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return ChatMessageHistory(session_id=session_id, messages=messages)

    except Exception as e:
        logger.error(f"Error retrieving history for session {session_id}: {e}")
        raise


async def delete_session(
    db_pool: asyncpg.Pool, session_id: str, soft_delete: bool = False
) -> bool:
    """
    Delete a chat session and all its messages.

    Args:
        db_pool: AsyncPG connection pool
        session_id: UUID string of the session
        soft_delete: If True, would implement soft delete (not implemented yet)

    Returns:
        True if deletion was successful, False otherwise
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        logger.error(f"Invalid session_id format: {session_id}")
        return False

    try:
        async with db_pool.acquire() as conn:
            # Delete messages first (they reference the session)
            await conn.execute(
                "DELETE FROM chat_messages WHERE session_id = $1", session_uuid
            )

            # Delete session
            result = await conn.execute(
                "DELETE FROM chat_sessions WHERE session_id = $1", session_uuid
            )

        # Check if anything was deleted
        return result == "DELETE 1"

    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise


async def build_context_window(
    db_pool: asyncpg.Pool, session_id: str, max_messages: int = 10
) -> str:
    """
    Build a formatted context window from recent conversation history.

    This function retrieves the most recent messages from a session
    and formats them as a multi-turn context string suitable for
    passing to Claude for continued conversation.

    Args:
        db_pool: AsyncPG connection pool
        session_id: UUID string of the session
        max_messages: Maximum number of messages to include (most recent first)

    Returns:
        Formatted context string ready for Claude API, or empty string if no history
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        logger.error(f"Invalid session_id format: {session_id}")
        return ""

    if max_messages < 1 or max_messages > 100:
        max_messages = 10

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    role,
                    content,
                    created_at
                FROM chat_messages
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """,
                session_uuid,
                max_messages,
            )

        if not rows:
            return ""

        # Reverse to get chronological order (oldest first)
        rows = list(reversed(rows))

        context_parts = ["## CONVERSATION HISTORY:\n", "Recent messages for context:\n"]

        for row in rows:
            role = row["role"].upper()
            context_parts.append(f"\n**{role}:** {row['content']}\n")

        context_parts.append("\n---\n")

        return "".join(context_parts)

    except Exception as e:
        logger.error(f"Error building context window for session {session_id}: {e}")
        return ""
