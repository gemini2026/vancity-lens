-- VCL-80 [DATA-004] Scraper Run Tracking Table
-- Stores execution history for all scheduled scraper runs with detailed metrics

CREATE TABLE IF NOT EXISTS scraper_runs (
    id SERIAL PRIMARY KEY,
    scraper_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    documents_found INT NOT NULL DEFAULT 0,
    documents_new INT NOT NULL DEFAULT 0,
    documents_skipped INT NOT NULL DEFAULT 0,
    errors JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_scraper_runs_name_started
    ON scraper_runs(scraper_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_status
    ON scraper_runs(status);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_created
    ON scraper_runs(created_at DESC);

-- Composite index for common queries (scraper + status + time)
CREATE INDEX IF NOT EXISTS idx_scraper_runs_name_status_created
    ON scraper_runs(scraper_name, status, created_at DESC);
