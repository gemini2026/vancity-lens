-- Migration 033: Case Studies (preloaded showcase parcels)
-- Curated parcels with narrative descriptions to demonstrate Bill 47 opportunities.

CREATE TABLE IF NOT EXISTS case_studies (
    id SERIAL PRIMARY KEY,
    pid TEXT NOT NULL,
    title TEXT NOT NULL,
    narrative TEXT NOT NULL,
    highlight_metrics JSONB DEFAULT '{}',
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
