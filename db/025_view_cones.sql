--
-- VCL-104 (VAL-001): View Cone Intersection (deal-killer)
-- Vancouver's 23 protected view corridors from CoV Open Data
-- Geometry-based parcel validation using PostGIS ST_Intersects
--
-- Note: view_cones table base was created in 005_v2_risk_layers.sql
-- This migration adds additional columns needed by the API layer
--

-- Add columns that the API expects (safe if they already exist)
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS name VARCHAR(200);
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS max_height_m NUMERIC(8, 2);
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS max_height_ft NUMERIC(8, 2);
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS source_location VARCHAR(200);
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS target_location VARCHAR(200);
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS cone_type VARCHAR(50) DEFAULT 'protected_view';
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS bylaw_reference VARCHAR(100);
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE view_cones ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill name from view_cone_name if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'view_cones' AND column_name = 'view_cone_name') THEN
        UPDATE view_cones SET name = view_cone_name WHERE name IS NULL AND view_cone_name IS NOT NULL;
    END IF;
END $$;

-- GIST index for spatial queries (ST_Intersects, etc.)
CREATE INDEX IF NOT EXISTS idx_view_cones_geom ON view_cones USING GIST(geom);

-- Index for filtering active view cones
CREATE INDEX IF NOT EXISTS idx_view_cones_active ON view_cones(is_active) WHERE is_active = TRUE;

-- Composite index for active geometry queries
CREATE INDEX IF NOT EXISTS idx_view_cones_active_geom
    ON view_cones USING GIST(geom) WHERE is_active = TRUE;

-- Index for lookups by name or corridor
CREATE INDEX IF NOT EXISTS idx_view_cones_name ON view_cones(name);

-- Index for bylaw reference searches
CREATE INDEX IF NOT EXISTS idx_view_cones_bylaw ON view_cones(bylaw_reference);
