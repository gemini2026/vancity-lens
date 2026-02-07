-- Migration 009: Neighborhood Scorecards (Phase 5)
-- Madlan-style quality-of-life ratings for Vancouver's 22 local areas
-- Supports: metric ingestion, scoring, historical tracking, comparison

-- ============================================================
-- REFERENCE: Vancouver's 22 Official Local Areas
-- ============================================================
CREATE TABLE IF NOT EXISTS neighborhoods (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,              -- Official local area name
    slug TEXT UNIQUE NOT NULL,              -- URL-friendly slug
    centroid GEOMETRY(Point, 4326),         -- Center point for map
    boundary GEOMETRY(MultiPolygon, 4326),  -- Official boundary polygon
    population INT,                          -- Latest census population
    area_km2 NUMERIC,                       -- Area in square kilometers
    metadata JSONB DEFAULT '{}',            -- Flexible additional data
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Seed Vancouver's 22 local areas with approximate centroids
INSERT INTO neighborhoods (name, slug, centroid) VALUES
    ('Arbutus Ridge', 'arbutus-ridge', ST_SetSRID(ST_MakePoint(-123.1554, 49.2493), 4326)),
    ('Downtown', 'downtown', ST_SetSRID(ST_MakePoint(-123.1207, 49.2827), 4326)),
    ('Dunbar-Southlands', 'dunbar-southlands', ST_SetSRID(ST_MakePoint(-123.1855, 49.2440), 4326)),
    ('Fairview', 'fairview', ST_SetSRID(ST_MakePoint(-123.1300, 49.2650), 4326)),
    ('Grandview-Woodland', 'grandview-woodland', ST_SetSRID(ST_MakePoint(-123.0700, 49.2750), 4326)),
    ('Hastings-Sunrise', 'hastings-sunrise', ST_SetSRID(ST_MakePoint(-123.0400, 49.2810), 4326)),
    ('Kensington-Cedar Cottage', 'kensington-cedar-cottage', ST_SetSRID(ST_MakePoint(-123.0710, 49.2490), 4326)),
    ('Kerrisdale', 'kerrisdale', ST_SetSRID(ST_MakePoint(-123.1560, 49.2320), 4326)),
    ('Killarney', 'killarney', ST_SetSRID(ST_MakePoint(-123.0340, 49.2250), 4326)),
    ('Kitsilano', 'kitsilano', ST_SetSRID(ST_MakePoint(-123.1600, 49.2680), 4326)),
    ('Marpole', 'marpole', ST_SetSRID(ST_MakePoint(-123.1280, 49.2110), 4326)),
    ('Mount Pleasant', 'mount-pleasant', ST_SetSRID(ST_MakePoint(-123.1000, 49.2620), 4326)),
    ('Oakridge', 'oakridge', ST_SetSRID(ST_MakePoint(-123.1230, 49.2270), 4326)),
    ('Renfrew-Collingwood', 'renfrew-collingwood', ST_SetSRID(ST_MakePoint(-123.0340, 49.2460), 4326)),
    ('Riley Park', 'riley-park', ST_SetSRID(ST_MakePoint(-123.1020, 49.2430), 4326)),
    ('Shaughnessy', 'shaughnessy', ST_SetSRID(ST_MakePoint(-123.1410, 49.2470), 4326)),
    ('South Cambie', 'south-cambie', ST_SetSRID(ST_MakePoint(-123.1170, 49.2470), 4326)),
    ('Strathcona', 'strathcona', ST_SetSRID(ST_MakePoint(-123.0890, 49.2770), 4326)),
    ('Sunset', 'sunset', ST_SetSRID(ST_MakePoint(-123.0890, 49.2210), 4326)),
    ('Victoria-Fraserview', 'victoria-fraserview', ST_SetSRID(ST_MakePoint(-123.0610, 49.2180), 4326)),
    ('West End', 'west-end', ST_SetSRID(ST_MakePoint(-123.1370, 49.2870), 4326)),
    ('West Point Grey', 'west-point-grey', ST_SetSRID(ST_MakePoint(-123.2000, 49.2660), 4326))
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- RAW METRICS: Ingested from open data sources
-- One row per neighborhood per metric per period
-- ============================================================
CREATE TABLE IF NOT EXISTS neighborhood_metrics (
    id SERIAL PRIMARY KEY,
    neighborhood_id INT NOT NULL REFERENCES neighborhoods(id),
    category TEXT NOT NULL,                 -- 'safety', 'schools', 'transit', 'parks',
                                           -- 'development', 'air_quality', 'affordability', 'walkability'
    metric_name TEXT NOT NULL,              -- e.g., 'crimes_per_1000', 'avg_school_rating'
    metric_value NUMERIC NOT NULL,          -- raw numeric value
    period_start DATE NOT NULL,             -- measurement period start
    period_end DATE NOT NULL,               -- measurement period end
    source_name TEXT NOT NULL,              -- e.g., 'VPD GeoDASH', 'CoV Open Data'
    source_url TEXT,                        -- URL of the data source
    metadata JSONB DEFAULT '{}',           -- additional context
    ingested_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(neighborhood_id, category, metric_name, period_start)
);

CREATE INDEX IF NOT EXISTS idx_metrics_neighborhood ON neighborhood_metrics(neighborhood_id);
CREATE INDEX IF NOT EXISTS idx_metrics_category ON neighborhood_metrics(category);
CREATE INDEX IF NOT EXISTS idx_metrics_period ON neighborhood_metrics(period_start DESC);

-- ============================================================
-- COMPUTED SCORES: Normalized 0-10 ratings per dimension
-- Recomputed periodically from raw metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS neighborhood_scores (
    id SERIAL PRIMARY KEY,
    neighborhood_id INT NOT NULL REFERENCES neighborhoods(id),
    category TEXT NOT NULL,                 -- same categories as metrics
    score NUMERIC(3,1) NOT NULL CHECK (score >= 0 AND score <= 10),
    raw_value NUMERIC,                     -- the metric value this score was derived from
    percentile NUMERIC(4,1),               -- percentile rank among all neighborhoods
    trend TEXT,                             -- 'improving', 'stable', 'declining'
    trend_change NUMERIC,                  -- score change vs previous period
    computed_at TIMESTAMPTZ DEFAULT now(),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    UNIQUE(neighborhood_id, category, period_start)
);

CREATE INDEX IF NOT EXISTS idx_scores_neighborhood ON neighborhood_scores(neighborhood_id);
CREATE INDEX IF NOT EXISTS idx_scores_period ON neighborhood_scores(period_start DESC);

-- ============================================================
-- COMPOSITE SCORES: Overall neighborhood rating
-- Weighted average of category scores
-- ============================================================
CREATE TABLE IF NOT EXISTS neighborhood_composite_scores (
    id SERIAL PRIMARY KEY,
    neighborhood_id INT NOT NULL REFERENCES neighborhoods(id),
    overall_score NUMERIC(3,1) NOT NULL CHECK (overall_score >= 0 AND overall_score <= 10),
    rank INT,                              -- rank among 22 neighborhoods
    category_scores JSONB NOT NULL,        -- {"safety": 7.2, "schools": 8.1, ...}
    weights_used JSONB NOT NULL,           -- {"safety": 0.15, "schools": 0.15, ...}
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(neighborhood_id, period_start)
);

CREATE INDEX IF NOT EXISTS idx_composite_neighborhood ON neighborhood_composite_scores(neighborhood_id);
CREATE INDEX IF NOT EXISTS idx_composite_period ON neighborhood_composite_scores(period_start DESC);
CREATE INDEX IF NOT EXISTS idx_composite_rank ON neighborhood_composite_scores(rank);

-- ============================================================
-- SCORING WEIGHTS CONFIGURATION
-- Adjustable weights for composite score calculation
-- ============================================================
CREATE TABLE IF NOT EXISTS scoring_weights (
    id SERIAL PRIMARY KEY,
    category TEXT UNIQUE NOT NULL,
    weight NUMERIC(3,2) NOT NULL CHECK (weight >= 0 AND weight <= 1),
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Default weights (should sum to 1.0)
INSERT INTO scoring_weights (category, weight, description) VALUES
    ('safety', 0.15, 'Crime rate per 1000 residents (VPD GeoDASH)'),
    ('schools', 0.15, 'School quality and accessibility (VSB data)'),
    ('transit', 0.15, 'Transit stop density and walk-to-transit time (TransLink GTFS)'),
    ('parks', 0.10, 'Green space per capita and park proximity (CoV Open Data)'),
    ('development', 0.15, 'Active development pipeline and recent approvals (intelligence signals)'),
    ('air_quality', 0.05, 'Air quality index readings (Metro Vancouver AirMap)'),
    ('affordability', 0.15, 'Price per sqft trends and relative affordability (CoV Property Tax)'),
    ('walkability', 0.10, 'Walk Score and pedestrian infrastructure (UBC Walkability Index)')
ON CONFLICT (category) DO NOTHING;

-- Verify
DO $$
DECLARE
  hood_count INTEGER;
  weight_sum NUMERIC;
BEGIN
  SELECT COUNT(*) INTO hood_count FROM neighborhoods;
  SELECT SUM(weight) INTO weight_sum FROM scoring_weights;
  RAISE NOTICE 'Neighborhood scorecards: % neighborhoods, weight sum = %', hood_count, weight_sum;
END $$;
