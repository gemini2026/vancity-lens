-- Migration 023: VSB School Data Scraper (VCL-96)
-- Stores Vancouver School Board school data and computed metrics by neighborhood
-- Tables:
--   - school_data: Raw school information from VSB Open Data API
--   - school_metrics: Aggregated metrics by neighborhood

-- ============================================================
-- RAW SCHOOL DATA: Individual schools from VSB Open Data
-- ============================================================
CREATE TABLE IF NOT EXISTS school_data (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,                     -- School name (e.g., "Lord Byng Secondary")
    address TEXT NOT NULL,                  -- School address
    school_type TEXT NOT NULL,              -- 'elementary', 'secondary', 'middle'
    enrollment INT,                         -- Current enrollment count
    capacity INT,                           -- Maximum capacity
    student_teacher_ratio NUMERIC(4,2),     -- Student-to-teacher ratio
    latitude NUMERIC(10,6),                 -- School coordinates
    longitude NUMERIC(10,6),                -- School coordinates
    neighborhood TEXT NOT NULL,             -- Mapped Vancouver neighborhood
    source_url TEXT,                        -- VSB Open Data API URL
    metadata JSONB DEFAULT '{}',            -- Additional school data
    scraped_at TIMESTAMPTZ DEFAULT now(),   -- When this record was scraped
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(name, address)
);

CREATE INDEX IF NOT EXISTS idx_school_data_neighborhood ON school_data(neighborhood);
CREATE INDEX IF NOT EXISTS idx_school_data_school_type ON school_data(school_type);
CREATE INDEX IF NOT EXISTS idx_school_data_scraped_at ON school_data(scraped_at DESC);

-- ============================================================
-- AGGREGATED SCHOOL METRICS: Per neighborhood metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS school_metrics (
    id SERIAL PRIMARY KEY,
    neighborhood TEXT NOT NULL,             -- Vancouver neighborhood name
    school_count INT DEFAULT 0,             -- Number of schools in neighborhood
    elementary_count INT DEFAULT 0,         -- Number of elementary schools
    secondary_count INT DEFAULT 0,          -- Number of secondary/middle schools
    total_enrollment INT DEFAULT 0,         -- Total students across all schools
    total_capacity INT DEFAULT 0,           -- Total capacity across all schools
    avg_capacity_utilization NUMERIC(5,2),  -- Average % of capacity used (0-100)
    avg_student_teacher_ratio NUMERIC(4,2), -- Average student-to-teacher ratio
    quality_score NUMERIC(3,1),             -- Computed school quality score (0-10)
    period_start DATE NOT NULL,             -- Metric period start
    period_end DATE NOT NULL,               -- Metric period end
    computed_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(neighborhood, period_start)
);

CREATE INDEX IF NOT EXISTS idx_school_metrics_neighborhood ON school_metrics(neighborhood);
CREATE INDEX IF NOT EXISTS idx_school_metrics_period ON school_metrics(period_start DESC);

-- ============================================================
-- SCRAPER RUN TRACKING: Track each school scrape operation
-- ============================================================
CREATE TABLE IF NOT EXISTS scraper_schools_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    schools_found INT DEFAULT 0,
    schools_saved INT DEFAULT 0,
    neighborhoods_updated INT DEFAULT 0,
    errors TEXT[],                          -- Array of error messages
    status TEXT DEFAULT 'success',          -- 'success', 'partial', 'failed'
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scraper_schools_runs_started ON scraper_schools_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scraper_schools_runs_status ON scraper_schools_runs(status);
