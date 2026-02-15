-- Migration 040: Sprint 7 — Political Risk Score Engine
-- Stores computed neighborhood-level political risk scores (1-10)
-- Supports FR-OPP-003, AC-OPP-001 through AC-OPP-003

CREATE TABLE IF NOT EXISTS political_risk_scores (
    id SERIAL PRIMARY KEY,
    neighborhood TEXT NOT NULL,

    -- Composite score (1-10)
    risk_score NUMERIC(3,1) NOT NULL CHECK (risk_score >= 1 AND risk_score <= 10),

    -- Component scores (each 0-10, weighted into composite)
    opposition_rate NUMERIC(5,2),        -- % of applications with opposition signals
    delay_score NUMERIC(3,1),            -- Average delay attribution (0-10)
    sentiment_intensity NUMERIC(3,1),    -- Recency-weighted negative sentiment (0-10)
    council_resistance NUMERIC(3,1),     -- Council voting pattern resistance (0-10)

    -- Raw data used
    total_applications INTEGER DEFAULT 0,
    opposed_applications INTEGER DEFAULT 0,
    total_signals INTEGER DEFAULT 0,
    negative_signals INTEGER DEFAULT 0,
    avg_delay_months NUMERIC(4,1),
    avg_vote_against_pct NUMERIC(5,2),

    -- Metadata
    period_months INTEGER DEFAULT 36,     -- Trailing period used for calculation
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(neighborhood, computed_at)
);

CREATE INDEX IF NOT EXISTS idx_political_risk_neighborhood ON political_risk_scores(neighborhood);
CREATE INDEX IF NOT EXISTS idx_political_risk_computed ON political_risk_scores(computed_at DESC);

-- Latest score per neighborhood view
CREATE OR REPLACE VIEW latest_political_risk AS
SELECT DISTINCT ON (neighborhood)
    neighborhood, risk_score, opposition_rate, delay_score,
    sentiment_intensity, council_resistance,
    total_applications, opposed_applications,
    total_signals, negative_signals,
    avg_delay_months, avg_vote_against_pct,
    period_months, computed_at
FROM political_risk_scores
ORDER BY neighborhood, computed_at DESC;
