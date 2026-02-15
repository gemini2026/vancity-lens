-- Migration 039: Sprint 6 — External retrieval audit log (DI-005)
-- Tracks every external data retrieval for compliance and debugging

CREATE TABLE IF NOT EXISTS external_retrieval_log (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,           -- e.g., 'statscan_wds', 'cmhc_open_canada', 'bclaws'
    operation TEXT NOT NULL,             -- e.g., 'fetch', 'search', 'scrape', 'ingest'
    endpoint_url TEXT,                   -- The URL or API endpoint queried
    request_params JSONB DEFAULT '{}',   -- Query parameters sent
    response_status INTEGER,             -- HTTP status code (200, 404, 500, etc.)
    records_returned INTEGER DEFAULT 0,  -- Number of records in response
    records_stored INTEGER DEFAULT 0,    -- Number of records actually stored/updated
    error_message TEXT,                  -- Error details if failed
    duration_ms INTEGER,                 -- Request duration in milliseconds
    triggered_by TEXT,                   -- 'scheduler', 'api', 'manual', 'report'
    user_id INTEGER,                     -- User who triggered (if via API)
    pid TEXT,                            -- Related parcel PID (if parcel-scoped)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_log_source ON external_retrieval_log(source_name);
CREATE INDEX IF NOT EXISTS idx_retrieval_log_created ON external_retrieval_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_retrieval_log_pid ON external_retrieval_log(pid);
CREATE INDEX IF NOT EXISTS idx_retrieval_log_status ON external_retrieval_log(response_status);
