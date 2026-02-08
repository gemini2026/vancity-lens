-- Migration 011: Chat Session Indexes
-- Add useful indexes for chat session and message queries

-- Index for listing sessions by user (most common query)
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_label_created
    ON chat_sessions(user_label, created_at DESC);

-- Index for session lookup by session_id (fast retrieval)
CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id_unique
    ON chat_sessions(session_id);

-- Composite index for message queries with ordering
-- Used by: get_session_history, build_context_window
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages(session_id, created_at ASC);

-- Index for reverse order (getting most recent messages first)
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_desc
    ON chat_messages(session_id, created_at DESC);

-- Index for message counting and pagination
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
    ON chat_messages(session_id);

-- Index for source chunks search (for finding related messages)
CREATE INDEX IF NOT EXISTS idx_chat_messages_source_chunks
    ON chat_messages USING gin(source_chunks);

-- Index for source signals search (for finding related messages)
CREATE INDEX IF NOT EXISTS idx_chat_messages_source_signals
    ON chat_messages USING gin(source_signals);

-- Stats: Help query planner for better performance
ANALYZE chat_sessions;
ANALYZE chat_messages;
