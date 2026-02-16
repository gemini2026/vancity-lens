-- Migration 043: Pipeline schema enhancement for PRD F04

ALTER TABLE supply_pipeline
    ADD COLUMN IF NOT EXISTS application_id TEXT,
    ADD COLUMN IF NOT EXISTS application_type TEXT;

CREATE INDEX IF NOT EXISTS idx_supply_pipeline_application_id
    ON supply_pipeline(application_id);
CREATE INDEX IF NOT EXISTS idx_supply_pipeline_application_type
    ON supply_pipeline(application_type);

COMMENT ON COLUMN supply_pipeline.pipeline_stage IS
    'One of: enquiry, application_submitted, under_staff_review, '
    'referred_to_public_hearing, approved, under_construction, '
    'completed, refused, withdrawn';

COMMENT ON COLUMN supply_pipeline.application_type IS
    'One of: rezoning, development_permit, building_permit';
