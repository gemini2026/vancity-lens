-- Migration 042: Market benchmarks table
-- Replaces hardcoded REVENUE_PSF_BY_NEIGHBORHOOD with DB-driven values.

CREATE TABLE IF NOT EXISTS market_benchmarks (
    id SERIAL PRIMARY KEY,
    neighbourhood TEXT NOT NULL,
    product_type TEXT NOT NULL,
    revenue_per_sf NUMERIC(10,2) NOT NULL,
    hard_cost_per_sf NUMERIC(10,2) NOT NULL,
    source TEXT NOT NULL DEFAULT 'seed',
    effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(neighbourhood, product_type)
);

CREATE INDEX IF NOT EXISTS idx_market_benchmarks_neighbourhood
    ON market_benchmarks(neighbourhood);
CREATE INDEX IF NOT EXISTS idx_market_benchmarks_product_type
    ON market_benchmarks(product_type);
