-- Migration 047: Regulatory change records (F02-A)
-- Tracks policy/zoning/regulatory changes extracted from documents
-- Links to intelligence_signals for source attribution

CREATE TABLE IF NOT EXISTS change_records (
    change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id INT REFERENCES intelligence_signals(id) ON DELETE SET NULL,

    -- Change classification
    change_type TEXT NOT NULL,

    -- Source attribution
    source_url TEXT NOT NULL,
    source_document_title TEXT NOT NULL,
    publication_date TIMESTAMPTZ,
    effective_date TIMESTAMPTZ,

    -- Geographic scope
    geographic_scope TEXT NOT NULL,
    affected_areas TEXT[] DEFAULT '{}',

    -- Entitlement impact (JSONB for flexibility)
    entitlement_change JSONB DEFAULT '{}',

    -- AI-extracted summary and confidence
    plain_english_summary TEXT,
    nlp_confidence_score NUMERIC(3,2),

    -- Timestamps and review flag
    extraction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    requires_manual_review BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_change_records_change_type ON change_records(change_type);
CREATE INDEX IF NOT EXISTS idx_change_records_pub_date ON change_records(publication_date DESC);
CREATE INDEX IF NOT EXISTS idx_change_records_geo_scope ON change_records(geographic_scope);
CREATE INDEX IF NOT EXISTS idx_change_records_affected_areas ON change_records USING GIN(affected_areas);

-- Full-text search index for summary and title
CREATE INDEX IF NOT EXISTS idx_change_records_fts
    ON change_records USING GIN(to_tsvector('english', coalesce(plain_english_summary, '') || ' ' || source_document_title));
