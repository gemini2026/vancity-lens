-- Migration 037: Sprint 4 — New data source tables
-- BC Contaminated Sites, StatsCan demographics, CMHC housing, census geography lookup

-- ── BC Contaminated Sites Registry ──────────────────────────────
CREATE TABLE IF NOT EXISTS contaminated_sites (
    id SERIAL PRIMARY KEY,
    site_id TEXT UNIQUE NOT NULL,          -- BC registry site ID
    site_name TEXT,
    address TEXT,
    city TEXT DEFAULT 'Vancouver',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geom GEOMETRY(Point, 4326),
    classification TEXT,                    -- e.g., 'Independent Remediation', 'Detailed Risk Assessment'
    status TEXT,                            -- e.g., 'Active', 'Closed', 'Under Review'
    contamination_type TEXT,                -- e.g., 'Petroleum', 'Heavy Metals', 'Mixed'
    date_reported DATE,
    date_updated DATE,
    legal_description TEXT,
    associated_pid TEXT,                    -- Matched PID if available
    raw_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contaminated_sites_geom ON contaminated_sites USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_contaminated_sites_pid ON contaminated_sites(associated_pid);
CREATE INDEX IF NOT EXISTS idx_contaminated_sites_status ON contaminated_sites(status);

-- ── StatsCan Census Demographics (census tract level) ───────────
CREATE TABLE IF NOT EXISTS statscan_demographics (
    id SERIAL PRIMARY KEY,
    census_tract TEXT NOT NULL,            -- e.g., '9330001.00'
    census_year INTEGER NOT NULL,          -- e.g., 2021
    population INTEGER,
    population_5yr_growth NUMERIC(6,2),    -- Percentage
    median_household_income INTEGER,
    avg_household_size NUMERIC(4,2),
    owner_pct NUMERIC(5,2),               -- Owner-occupied %
    renter_pct NUMERIC(5,2),              -- Renter-occupied %
    dominant_dwelling_type TEXT,            -- e.g., 'Single-detached', 'Apartment'
    total_dwellings INTEGER,
    median_age NUMERIC(4,1),
    raw_data JSONB DEFAULT '{}',
    data_source TEXT DEFAULT 'statscan_wds',
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(census_tract, census_year)
);

CREATE INDEX IF NOT EXISTS idx_statscan_census_tract ON statscan_demographics(census_tract);

-- ── StatsCan Population Estimates (CSD level) ───────────────────
CREATE TABLE IF NOT EXISTS statscan_population (
    id SERIAL PRIMARY KEY,
    geo_code TEXT NOT NULL,                -- Census subdivision code
    geo_name TEXT,                          -- e.g., 'Vancouver (CY)'
    ref_date TEXT NOT NULL,                -- e.g., '2025-Q3'
    population INTEGER,
    raw_data JSONB DEFAULT '{}',
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(geo_code, ref_date)
);

-- ── StatsCan Building Permits (CMA level) ───────────────────────
CREATE TABLE IF NOT EXISTS statscan_building_permits (
    id SERIAL PRIMARY KEY,
    geo_code TEXT NOT NULL,
    geo_name TEXT,
    ref_date TEXT NOT NULL,                -- e.g., '2025-01'
    permit_type TEXT,                       -- 'residential', 'commercial', 'industrial'
    num_permits INTEGER,
    value_thousands NUMERIC(12,1),
    raw_data JSONB DEFAULT '{}',
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(geo_code, ref_date, permit_type)
);

-- ── CMHC Housing Market Data (CMA level) ────────────────────────
CREATE TABLE IF NOT EXISTS cmhc_housing (
    id SERIAL PRIMARY KEY,
    cma_code TEXT NOT NULL DEFAULT '933',   -- Vancouver CMA = 933
    cma_name TEXT DEFAULT 'Vancouver',
    ref_date TEXT NOT NULL,                 -- e.g., '2025-01'
    metric TEXT NOT NULL,                   -- 'starts', 'completions', 'under_construction', 'absorptions'
    dwelling_type TEXT DEFAULT 'total',     -- 'single', 'semi', 'row', 'apartment', 'total'
    value INTEGER,
    raw_data JSONB DEFAULT '{}',
    data_source TEXT DEFAULT 'cmhc_open_canada',
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cma_code, ref_date, metric, dwelling_type)
);

CREATE INDEX IF NOT EXISTS idx_cmhc_cma_metric ON cmhc_housing(cma_code, metric);

-- ── PID → Census Geography Lookup (DI-008) ──────────────────────
CREATE TABLE IF NOT EXISTS parcel_census_lookup (
    pid TEXT PRIMARY KEY REFERENCES parcels(pid),
    census_tract TEXT,                     -- StatsCan census tract code
    census_subdivision TEXT,               -- StatsCan CSD code (Vancouver = 5915022)
    census_subdivision_name TEXT,           -- e.g., 'Vancouver (CY)'
    distance_to_tract_boundary_m NUMERIC(8,1),  -- For boundary proximity note
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parcel_census_tract ON parcel_census_lookup(census_tract);
CREATE INDEX IF NOT EXISTS idx_parcel_census_csd ON parcel_census_lookup(census_subdivision);
