-- ============================================================
-- VanCity Lens — Background Job Queue (VCL-95 / PERF-015)
-- ============================================================
-- Celery task tracking table with status, retry logic, and results
-- ============================================================

-- -----------------------------------------------------------
-- Background Jobs Table
-- -----------------------------------------------------------
-- Tracks status of all background tasks (scraping, processing, email, etc.)
-- job_id = Celery task ID (UUID)
-- status = pending, running, success, failed, retrying
-- params = Input parameters (JSON)
-- result = Task result/output (JSON)
-- error = Error message if failed
-- retries = Number of retry attempts
-- progress = Task progress percentage (0-100)

CREATE TABLE IF NOT EXISTS background_jobs (
    id                  TEXT PRIMARY KEY,                          -- Celery task ID (UUID)
    job_type            TEXT NOT NULL,                             -- Task type (scraper, document_processing, etc.)
    status              TEXT NOT NULL DEFAULT 'pending',           -- pending, running, success, failed, retrying
    params              JSONB,                                     -- Input parameters for the task
    result              JSONB,                                     -- Task result/output
    error               TEXT,                                      -- Error message if task failed
    progress            NUMERIC(5,2) DEFAULT 0,                    -- Progress percentage (0-100)
    retries             INTEGER DEFAULT 0,                         -- Number of retry attempts
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),        -- Job creation time
    started_at          TIMESTAMPTZ,                               -- Task execution start time
    completed_at        TIMESTAMPTZ,                               -- Task completion time
    updated_at          TIMESTAMPTZ DEFAULT now()                  -- Last update time
);

-- -----------------------------------------------------------
-- Indexes for Common Queries
-- -----------------------------------------------------------
-- Status lookup (list jobs by status)
CREATE INDEX IF NOT EXISTS idx_background_jobs_status
    ON background_jobs(status);

-- Job type lookup (count jobs by type)
CREATE INDEX IF NOT EXISTS idx_background_jobs_job_type
    ON background_jobs(job_type);

-- Time-based queries (cleanup old jobs)
CREATE INDEX IF NOT EXISTS idx_background_jobs_created_at
    ON background_jobs(created_at DESC);

-- Compound index for common filter: (status, created_at)
CREATE INDEX IF NOT EXISTS idx_background_jobs_status_created
    ON background_jobs(status, created_at DESC);

-- Compound index for job type + status
CREATE INDEX IF NOT EXISTS idx_background_jobs_type_status
    ON background_jobs(job_type, status);

-- -----------------------------------------------------------
-- Functions and Triggers
-- -----------------------------------------------------------

-- Update updated_at timestamp on row modification
CREATE OR REPLACE FUNCTION update_background_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for updated_at
DROP TRIGGER IF EXISTS trigger_background_jobs_updated_at
    ON background_jobs;

CREATE TRIGGER trigger_background_jobs_updated_at
    BEFORE UPDATE ON background_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_background_jobs_updated_at();

-- -----------------------------------------------------------
-- Comments
-- -----------------------------------------------------------

COMMENT ON TABLE background_jobs IS
    'Celery background task tracking. Stores job status, parameters, results, and retry counts.';

COMMENT ON COLUMN background_jobs.id IS
    'Celery task ID (UUID). Primary key for identifying tasks.';

COMMENT ON COLUMN background_jobs.job_type IS
    'Type of background job (scraper, document_processing, email, embeddings, etc.)';

COMMENT ON COLUMN background_jobs.status IS
    'Current job status: pending, running, success, failed, retrying';

COMMENT ON COLUMN background_jobs.params IS
    'JSON input parameters passed to the task';

COMMENT ON COLUMN background_jobs.result IS
    'JSON result/output returned by the task after completion';

COMMENT ON COLUMN background_jobs.error IS
    'Error message if task failed (null if successful)';

COMMENT ON COLUMN background_jobs.progress IS
    'Task progress as percentage (0-100) for long-running tasks';

COMMENT ON COLUMN background_jobs.retries IS
    'Number of retry attempts made so far';

COMMENT ON COLUMN background_jobs.created_at IS
    'When the job was created (queued)';

COMMENT ON COLUMN background_jobs.started_at IS
    'When task execution started (null until running)';

COMMENT ON COLUMN background_jobs.completed_at IS
    'When task completed (success or failed)';

COMMENT ON COLUMN background_jobs.updated_at IS
    'Last row modification timestamp (auto-updated)';
