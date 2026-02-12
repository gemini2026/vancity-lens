-- Migration 030: Utility Infrastructure Lines (Due Diligence Evidence)
-- Stores City of Vancouver open-data linear assets (e.g., water/sewer mains)
-- for proximity evidence in reports and the parcel UI.

CREATE TABLE IF NOT EXISTS utility_lines (
    id SERIAL PRIMARY KEY,
    utility_type TEXT NOT NULL,                 -- e.g. 'water', 'sewer'
    asset_id TEXT,
    line_type TEXT,                             -- optional subtype (e.g. sanitary/storm/combined)
    diameter_mm NUMERIC,
    material TEXT,
    source_dataset TEXT NOT NULL,               -- dataset id (e.g. 'water-distribution-mains')
    source_url TEXT,                            -- dataset page URL (human-friendly)
    geom GEOMETRY(Geometry, 4326) NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_utility_lines_geom ON utility_lines USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_utility_lines_type ON utility_lines (utility_type);
CREATE INDEX IF NOT EXISTS idx_utility_lines_dataset ON utility_lines (source_dataset);

