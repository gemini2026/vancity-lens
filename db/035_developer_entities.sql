-- Migration 035: Developer Entity Resolution
-- Normalizes developer names for accurate pipeline filtering and analytics
-- Addresses DV-PIPE-006: Developer entity resolution

CREATE TABLE IF NOT EXISTS developer_entities (
    id SERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,   -- normalized canonical name
    aliases TEXT[] DEFAULT '{}',           -- alternate spellings, abbreviations
    bc_corp_number TEXT,                   -- BC Corporate Registry number (future)
    metadata JSONB DEFAULT '{}',           -- website, contact, portfolio size, etc.
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_developer_entities_canonical ON developer_entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_developer_entities_aliases ON developer_entities USING gin(aliases);

-- Add developer_entity_id FK to supply_pipeline
ALTER TABLE supply_pipeline
    ADD COLUMN IF NOT EXISTS developer_entity_id INTEGER
    REFERENCES developer_entities(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_supply_pipeline_developer_entity
    ON supply_pipeline(developer_entity_id);
