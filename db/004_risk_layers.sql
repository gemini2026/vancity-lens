-- Migration: Add risk and validation data layers from Vancouver Open Data
-- Includes heritage sites, floodplain zones, property easements, and land/improvement value split

-- -----------------------------------------------------------
-- Heritage Sites (from Vancouver Open Data heritage-sites dataset)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS heritage_sites (
    id SERIAL PRIMARY KEY,
    name TEXT,
    address TEXT,
    category TEXT,       -- 'A', 'B', 'C' classification
    geom GEOMETRY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_heritage_geom ON heritage_sites USING GIST (geom);

-- -----------------------------------------------------------
-- Floodplain Zones (from Vancouver Open Data designated-floodplain dataset)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS floodplain_zones (
    id SERIAL PRIMARY KEY,
    zone_type TEXT,      -- 'coastal', 'still_creek', etc.
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_floodplain_geom ON floodplain_zones USING GIST (geom);

-- -----------------------------------------------------------
-- Property Easements (from Vancouver Open Data property-easements dataset)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS property_easements (
    id SERIAL PRIMARY KEY,
    easement_type TEXT,
    plan_number TEXT,
    geom GEOMETRY(Geometry, 4326),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_easements_geom ON property_easements USING GIST (geom);

-- -----------------------------------------------------------
-- Add land value and improvement value columns to parcels
-- Splits the total assessed value into land and improvement components
-- -----------------------------------------------------------
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS land_value BIGINT;
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS improvement_value BIGINT;
