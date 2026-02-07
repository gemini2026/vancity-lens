-- Migration 005: V2 Validation Engine — Additional risk layers
-- View cones, protected trees, non-market housing, community gardens,
-- building permit activity, and parcel enrichment (year_built, neighborhood)

-- -----------------------------------------------------------
-- View Cones (23 protected view corridors)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS view_cones (
    id SERIAL PRIMARY KEY,
    view_number TEXT,
    view_cone_name TEXT,
    description TEXT,
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_view_cones_geom ON view_cones USING GIST (geom);

-- -----------------------------------------------------------
-- Protected Trees (large trees >30cm diameter from public-trees)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS protected_trees (
    id SERIAL PRIMARY KEY,
    asset_id TEXT,
    common_name TEXT,
    diameter_cm NUMERIC,
    height_m NUMERIC,
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_protected_trees_geom ON protected_trees USING GIST (geom);

-- -----------------------------------------------------------
-- Non-Market Housing (641 social/co-op housing locations)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS non_market_housing (
    id SERIAL PRIMARY KEY,
    name TEXT,
    address TEXT,
    project_status TEXT,
    total_units INT,
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_nmh_geom ON non_market_housing USING GIST (geom);

-- -----------------------------------------------------------
-- Community Gardens (170 locations)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS community_gardens (
    id SERIAL PRIMARY KEY,
    name TEXT,
    address TEXT,
    number_of_plots INT,
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_community_gardens_geom ON community_gardens USING GIST (geom);

-- -----------------------------------------------------------
-- Issued Building Permits (for competing supply analysis)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS issued_building_permits (
    id SERIAL PRIMARY KEY,
    permit_number TEXT,
    type_of_work TEXT,
    specific_use TEXT,
    project_value BIGINT,
    issue_year INT,
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_permits_geom ON issued_building_permits USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_permits_year_value ON issued_building_permits (issue_year, project_value);

-- -----------------------------------------------------------
-- Zoning districts (for CD-1 detection)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS zoning_districts (
    id SERIAL PRIMARY KEY,
    zoning_classification TEXT,
    zoning_category TEXT,
    cd_1_number TEXT,
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_zoning_geom ON zoning_districts USING GIST (geom);

-- -----------------------------------------------------------
-- Add enrichment columns to parcels
-- -----------------------------------------------------------
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS year_built INT;
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS geo_local_area TEXT;
