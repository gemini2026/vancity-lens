-- Migration 045: Retrieval audit log (DI-005)

CREATE TABLE IF NOT EXISTS retrieval_log (
    id SERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    query_params JSONB,
    retrieval_timestamp TIMESTAMPTZ DEFAULT NOW(),
    http_status INT,
    record_count INT,
    duration_ms INT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_retrieval_log_source
    ON retrieval_log(source_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_log_timestamp
    ON retrieval_log(retrieval_timestamp DESC);
