--
-- VCL-86 [BIZ-004] Usage analytics dashboard for VanCity Lens
-- Analytics events tracking table and indexes
--

-- ────────────────────────────────────────────────────────────────────────────
-- Analytics Events Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on user_id for finding events by user
CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON analytics_events(user_id);

-- Index on event_type for aggregating by event type
CREATE INDEX IF NOT EXISTS idx_analytics_events_event_type ON analytics_events(event_type);

-- Index on created_at for time-range queries
CREATE INDEX IF NOT EXISTS idx_analytics_events_created_at ON analytics_events(created_at DESC);

-- Composite index for common queries: user + event type + time
CREATE INDEX IF NOT EXISTS idx_analytics_events_user_type_time
ON analytics_events(user_id, event_type, created_at DESC);

-- Composite index for time range aggregation queries
CREATE INDEX IF NOT EXISTS idx_analytics_events_time_user
ON analytics_events(created_at DESC, user_id);
