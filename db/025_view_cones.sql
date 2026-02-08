--
-- VCL-104 (VAL-001): View Cone Intersection (deal-killer)
-- Vancouver's 23 protected view corridors from CoV Open Data
-- Geometry-based parcel validation using PostGIS ST_Intersects
--

-- ────────────────────────────────────────────────────────────────────────────
-- View Cones Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS view_cones (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    max_height_m NUMERIC(8, 2),
    max_height_ft NUMERIC(8, 2),
    source_location VARCHAR(200),
    target_location VARCHAR(200),
    cone_type VARCHAR(50) DEFAULT 'protected_view',
    bylaw_reference VARCHAR(100),
    geom geometry(Polygon, 4326) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

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
