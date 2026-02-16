-- Migration 044: Enable pg_trgm for fuzzy developer name matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_developer_entities_trgm
    ON developer_entities USING gin (canonical_name gin_trgm_ops);
