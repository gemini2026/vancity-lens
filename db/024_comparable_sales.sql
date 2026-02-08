-- VCL-100: Comparable Sales Data Pipeline
-- Migration: Create comparable_sales table with PostGIS support and calculated fields

CREATE TABLE IF NOT EXISTS comparable_sales (
    id SERIAL PRIMARY KEY,
    address TEXT NOT NULL,
    pid VARCHAR(20),
    sale_price NUMERIC(15, 2) NOT NULL,
    sale_date DATE NOT NULL,
    lot_area_sqft NUMERIC(12, 2),
    lot_area_sqm NUMERIC(12, 2),
    zoning VARCHAR(20),
    building_type VARCHAR(50),
    bedrooms INTEGER,
    bathrooms INTEGER,
    year_built INTEGER,
    floor_area_sqft NUMERIC(12, 2),
    price_per_lot_sqft NUMERIC(10, 2) GENERATED ALWAYS AS (
        CASE WHEN lot_area_sqft > 0 THEN sale_price / lot_area_sqft ELSE NULL END
    ) STORED,
    price_per_floor_sqft NUMERIC(10, 2) GENERATED ALWAYS AS (
        CASE WHEN floor_area_sqft > 0 THEN sale_price / floor_area_sqft ELSE NULL END
    ) STORED,
    geom geometry(Point, 4326),
    neighborhood VARCHAR(100),
    data_source VARCHAR(50) DEFAULT 'bc_assessment',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index for efficient spatial queries
CREATE INDEX idx_comparable_sales_geom ON comparable_sales USING GIST(geom);

-- Attribute indexes for filtering and sorting
CREATE INDEX idx_comparable_sales_zoning ON comparable_sales(zoning);
CREATE INDEX idx_comparable_sales_date ON comparable_sales(sale_date DESC);
CREATE INDEX idx_comparable_sales_pid ON comparable_sales(pid);
CREATE INDEX idx_comparable_sales_neighborhood ON comparable_sales(neighborhood);

-- Composite index for common filter patterns
CREATE INDEX idx_comparable_sales_zoning_date ON comparable_sales(zoning, sale_date DESC);
