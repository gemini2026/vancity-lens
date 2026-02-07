-- ============================================================
-- VanCity Lens — Bill 47 (TOA) PostGIS Schema
-- Housing Statutes (Transit-Oriented Areas) Amendment Act, 2023
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- -----------------------------------------------------------
-- ENUM: Transit station type determines buffer radii & tiers
-- -----------------------------------------------------------
CREATE TYPE station_type AS ENUM ('skytrain', 'bus_exchange');

-- -----------------------------------------------------------
-- Transit Stations
-- -----------------------------------------------------------
CREATE TABLE transit_stations (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    line            TEXT NOT NULL,
    type            station_type NOT NULL DEFAULT 'skytrain',
    geom            GEOMETRY(Point, 4326) NOT NULL,
    opened_date     DATE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_stations_geom ON transit_stations USING GIST (geom);

-- -----------------------------------------------------------
-- Parcels (Vancouver Parcel Fabric)
-- -----------------------------------------------------------
CREATE TABLE parcels (
    id              SERIAL PRIMARY KEY,
    pid             TEXT UNIQUE NOT NULL,
    civic_address   TEXT,
    current_zoning  TEXT,
    current_fsr     NUMERIC(4,2),
    current_height  INTEGER,
    lot_area_sqm    NUMERIC(12,2),
    assessed_value  BIGINT,                -- BC Assessment land value (dollars)
    asking_price    BIGINT,                -- current listing price if any (dollars)
    rew_url         TEXT,                  -- direct REW.ca listing URL for price verification
    geom            GEOMETRY(Geometry, 4326) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_parcels_geom ON parcels USING GIST (geom);
CREATE INDEX idx_parcels_pid  ON parcels (pid);

-- -----------------------------------------------------------
-- Bill 47 Tier Definitions (reference table)
-- -----------------------------------------------------------
CREATE TABLE bill47_tiers (
    id              SERIAL PRIMARY KEY,
    tier            INTEGER NOT NULL,
    station_type    station_type NOT NULL,
    min_distance_m  INTEGER NOT NULL,
    max_distance_m  INTEGER NOT NULL,
    max_storeys     INTEGER NOT NULL,
    max_fsr         NUMERIC(4,2) NOT NULL,
    UNIQUE (tier, station_type)
);

-- Seed the tier rules per Bill 47
INSERT INTO bill47_tiers (tier, station_type, min_distance_m, max_distance_m, max_storeys, max_fsr) VALUES
    (1, 'skytrain',   0,  200, 20, 5.5),
    (2, 'skytrain', 201,  400, 12, 4.0),
    (3, 'skytrain', 401,  800,  8, 3.0),
    (1, 'bus_exchange',   0,  200, 12, 4.0),
    (2, 'bus_exchange', 201,  400,  8, 3.0);

-- -----------------------------------------------------------
-- Materialized View: Pre-computed TOA Buffer Zones
-- Uses ST_Transform to project to BC Albers (EPSG:3005)
-- for accurate metre-based buffers, then back to 4326
-- -----------------------------------------------------------
CREATE MATERIALIZED VIEW toa_buffers AS
SELECT
    s.id AS station_id,
    s.name AS station_name,
    s.type AS station_type,
    t.tier,
    t.max_storeys,
    t.max_fsr,
    t.min_distance_m,
    t.max_distance_m,
    ST_Transform(
        ST_Buffer(
            ST_Transform(s.geom, 3005),
            t.max_distance_m
        ),
        4326
    ) AS geom
FROM transit_stations s
CROSS JOIN bill47_tiers t
WHERE s.type = t.station_type;

CREATE INDEX idx_toa_buffers_geom ON toa_buffers USING GIST (geom);

-- -----------------------------------------------------------
-- Function: Get Bill 47 entitlement for a single parcel
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION get_parcel_entitlement(p_pid TEXT)
RETURNS TABLE (
    parcel_pid          TEXT,
    station_name        TEXT,
    distance_m          NUMERIC,
    tier                INTEGER,
    entitled_storeys    INTEGER,
    entitled_fsr        NUMERIC,
    current_storeys     INTEGER,
    current_fsr         NUMERIC,
    storey_uplift       INTEGER,
    fsr_uplift          NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH parcel AS (
        SELECT p.pid, p.geom, p.current_height, p.current_fsr
        FROM parcels p
        WHERE p.pid = p_pid
    ),
    intersections AS (
        SELECT
            par.pid,
            b.station_name,
            b.tier,
            b.max_storeys,
            b.max_fsr,
            par.current_height,
            par.current_fsr,
            ST_Distance(
                ST_Transform(ST_Centroid(par.geom), 3005),
                ST_Transform(
                    (SELECT s.geom FROM transit_stations s WHERE s.id = b.station_id),
                    3005
                )
            ) AS dist_m
        FROM parcel par
        CROSS JOIN toa_buffers b
        WHERE ST_Intersects(par.geom, b.geom)
    )
    SELECT DISTINCT ON (i.station_name)
        i.pid,
        i.station_name,
        ROUND(i.dist_m::numeric, 1),
        i.tier,
        i.max_storeys,
        i.max_fsr,
        i.current_height,
        i.current_fsr,
        (i.max_storeys - COALESCE(i.current_height, 0)),
        (i.max_fsr - COALESCE(i.current_fsr, 0))
    FROM intersections i
    ORDER BY i.station_name, i.max_storeys DESC;
END;
$$ LANGUAGE plpgsql STABLE;

-- -----------------------------------------------------------
-- Function: Estimate land value based on entitlement
-- -----------------------------------------------------------
CREATE OR REPLACE FUNCTION estimate_entitled_value(
    p_pid TEXT,
    p_price_per_sqft NUMERIC DEFAULT 800
)
RETURNS TABLE (
    parcel_pid          TEXT,
    lot_area_sqm        NUMERIC,
    entitled_fsr        NUMERIC,
    buildable_sqft      NUMERIC,
    estimated_value     BIGINT,
    current_assessed    BIGINT,
    asking_price        BIGINT,
    value_delta         BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH best_entitlement AS (
        SELECT *
        FROM get_parcel_entitlement(p_pid)
        ORDER BY entitled_storeys DESC
        LIMIT 1
    ),
    parcel_info AS (
        SELECT p.pid, p.lot_area_sqm, p.assessed_value, p.asking_price
        FROM parcels p
        WHERE p.pid = p_pid
    )
    SELECT
        pi.pid,
        pi.lot_area_sqm,
        be.entitled_fsr,
        ROUND((pi.lot_area_sqm * be.entitled_fsr * 10.7639)::numeric, 0),
        (pi.lot_area_sqm * be.entitled_fsr * 10.7639 * p_price_per_sqft)::BIGINT,
        pi.assessed_value,
        pi.asking_price,
        (pi.lot_area_sqm * be.entitled_fsr * 10.7639 * p_price_per_sqft)::BIGINT
            - COALESCE(pi.asking_price, pi.assessed_value, 0)
    FROM parcel_info pi
    CROSS JOIN best_entitlement be;
END;
$$ LANGUAGE plpgsql STABLE;
