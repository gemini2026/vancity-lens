-- Migration 041: Sprint 9 — Undervalued Parcel Alerts
-- Stores parcel-level undervaluation scores and weekly opportunity rankings

CREATE TABLE IF NOT EXISTS undervalued_scores (
    id SERIAL PRIMARY KEY,
    pid TEXT NOT NULL,
    neighborhood TEXT,

    -- Value metrics
    assessed_value BIGINT,
    implied_value BIGINT,                  -- From buildable SF x avg comp $/SF
    buildable_sqft NUMERIC(12,1),
    avg_comp_per_bsf NUMERIC(10,2),        -- Avg comparable $ per buildable sqft
    comp_count INTEGER DEFAULT 0,          -- Number of comparables used

    -- Scoring
    discount_pct NUMERIC(6,2),             -- (implied - assessed) / implied * 100
    is_undervalued BOOLEAN DEFAULT FALSE,  -- discount_pct > 25%
    repeat_signal BOOLEAN DEFAULT FALSE,   -- Was flagged in previous period too

    -- Exclusions / caveats
    has_active_application BOOLEAN DEFAULT FALSE,  -- Exclude from alerts
    has_contamination BOOLEAN DEFAULT FALSE,
    has_heritage BOOLEAN DEFAULT FALSE,
    caveats TEXT[],

    -- Metadata
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pid, computed_at)
);

CREATE INDEX IF NOT EXISTS idx_undervalued_pid ON undervalued_scores(pid);
CREATE INDEX IF NOT EXISTS idx_undervalued_discount ON undervalued_scores(discount_pct DESC);
CREATE INDEX IF NOT EXISTS idx_undervalued_computed ON undervalued_scores(computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_undervalued_flagged ON undervalued_scores(is_undervalued)
    WHERE is_undervalued = TRUE;
