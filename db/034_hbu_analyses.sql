-- Migration 034: HBU Analyses cache table
-- Caches LLM-powered Highest & Best Use analysis results per parcel.

CREATE TABLE IF NOT EXISTS hbu_analyses (
    id SERIAL PRIMARY KEY,
    pid TEXT NOT NULL REFERENCES parcels(pid),
    analysis JSONB NOT NULL,
    narrative TEXT,
    confidence_score NUMERIC(3,2),
    llm_model TEXT,
    llm_cost_cents INTEGER DEFAULT 0,
    sources JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_hbu_analyses_pid ON hbu_analyses(pid);
CREATE INDEX IF NOT EXISTS idx_hbu_analyses_expires ON hbu_analyses(expires_at);
