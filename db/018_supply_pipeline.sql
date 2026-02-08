-- Migration 018: Supply Pipeline Tracking
-- Tracks residential development supply from rezoning through completion
-- Supports analysis of unit supply pipeline by stage and neighborhood

-- ============================================================
-- SUPPLY PIPELINE TABLE
-- Main table for tracking development projects through stages
-- ============================================================
CREATE TABLE IF NOT EXISTS supply_pipeline (
    id SERIAL PRIMARY KEY,
    parcel_pid TEXT NOT NULL UNIQUE,        -- BC Land Title PID (dedupe key)
    address TEXT NOT NULL,                  -- Street address for display
    neighborhood TEXT,                      -- Vancouver neighborhood

    -- Pipeline stage
    pipeline_stage TEXT NOT NULL,           -- rezoning_application, public_hearing, council_decision,
                                            -- development_permit, building_permit, under_construction, completed

    -- Zoning details
    current_zoning TEXT,                    -- e.g., 'RS-1'
    proposed_zoning TEXT,                   -- e.g., 'CD-1'

    -- Development specifications
    proposed_storeys INT,                   -- number of storeys in proposed project
    proposed_units INT,                     -- total residential units (nullable for non-residential)
    proposed_sqft NUMERIC,                  -- total floor space in square feet

    -- Project metadata
    developer TEXT,                         -- developer/company name
    estimated_completion DATE,              -- when project expected to complete (nullable)

    -- Linked intelligence signals
    signal_ids INT[],                       -- array of intelligence_signals.id referenced

    -- Flexible metadata storage
    metadata JSONB DEFAULT '{}',            -- project notes, amenities, conditions, etc.

    -- Bookkeeping
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supply_pipeline_parcel_pid ON supply_pipeline(parcel_pid);
CREATE INDEX IF NOT EXISTS idx_supply_pipeline_neighborhood ON supply_pipeline(neighborhood);
CREATE INDEX IF NOT EXISTS idx_supply_pipeline_stage ON supply_pipeline(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_supply_pipeline_created ON supply_pipeline(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supply_pipeline_signal_ids ON supply_pipeline USING gin(signal_ids);

-- ============================================================
-- PIPELINE STAGE HISTORY TABLE
-- Audit trail for pipeline stage transitions
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_stage_history (
    id SERIAL PRIMARY KEY,
    pipeline_id INT NOT NULL REFERENCES supply_pipeline(id) ON DELETE CASCADE,

    from_stage TEXT,                        -- previous stage (nullable for first entry)
    to_stage TEXT NOT NULL,                 -- new stage
    changed_at TIMESTAMPTZ DEFAULT now(),

    -- Optional linkage to triggering intelligence signal
    signal_id INT REFERENCES intelligence_signals(id) ON DELETE SET NULL,

    -- Optional notes about transition
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stage_history_pipeline ON pipeline_stage_history(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_stage_history_changed ON pipeline_stage_history(changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_stage_history_from_to ON pipeline_stage_history(from_stage, to_stage);

-- ============================================================
-- AUTO-UPDATE TRIGGER
-- Sets updated_at timestamp when supply_pipeline record changes
-- ============================================================
CREATE OR REPLACE FUNCTION update_supply_pipeline_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_supply_pipeline_timestamp ON supply_pipeline;
CREATE TRIGGER trg_supply_pipeline_timestamp
    BEFORE UPDATE ON supply_pipeline
    FOR EACH ROW
    EXECUTE FUNCTION update_supply_pipeline_timestamp();
