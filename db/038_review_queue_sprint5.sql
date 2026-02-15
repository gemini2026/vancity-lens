-- Migration 038: Sprint 5 — Review queue + regulatory intelligence enhancements

-- ── Signal Review Queue (DV-REG-002) ────────────────────────────
-- Signals with confidence < threshold get flagged for manual review

ALTER TABLE intelligence_signals ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT 'auto_approved';
-- Values: 'auto_approved' (confidence >= threshold), 'pending_review', 'approved', 'rejected'

ALTER TABLE intelligence_signals ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(id);
ALTER TABLE intelligence_signals ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE intelligence_signals ADD COLUMN IF NOT EXISTS review_notes TEXT;

CREATE INDEX IF NOT EXISTS idx_signals_review_status ON intelligence_signals(review_status)
    WHERE review_status = 'pending_review';

-- ── Digest Preferences (personalization) ────────────────────────
-- Additional personalization fields for digest subscriptions

ALTER TABLE digest_subscriptions ADD COLUMN IF NOT EXISTS severity_min TEXT DEFAULT 'info';
ALTER TABLE digest_subscriptions ADD COLUMN IF NOT EXISTS max_signals_per_digest INTEGER DEFAULT 20;
ALTER TABLE digest_subscriptions ADD COLUMN IF NOT EXISTS include_summary BOOLEAN DEFAULT true;

-- ── Valid Vancouver Neighborhoods Lookup ────────────────────────
CREATE TABLE IF NOT EXISTS vancouver_neighborhoods (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    alternate_names TEXT[] DEFAULT ARRAY[]::TEXT[],
    bbox_min_lat DOUBLE PRECISION,
    bbox_min_lng DOUBLE PRECISION,
    bbox_max_lat DOUBLE PRECISION,
    bbox_max_lng DOUBLE PRECISION
);

INSERT INTO vancouver_neighborhoods (name, alternate_names) VALUES
    ('Arbutus Ridge', ARRAY['Arbutus']),
    ('Downtown', ARRAY['Downtown Vancouver', 'CBD']),
    ('Dunbar-Southlands', ARRAY['Dunbar', 'Southlands']),
    ('Fairview', ARRAY['Fairview Slopes']),
    ('Grandview-Woodland', ARRAY['Grandview', 'Commercial Drive', 'The Drive']),
    ('Hastings-Sunrise', ARRAY['Hastings', 'Sunrise']),
    ('Kensington-Cedar Cottage', ARRAY['Kensington', 'Cedar Cottage']),
    ('Kerrisdale', ARRAY[]::TEXT[]),
    ('Killarney', ARRAY['Killarney-Victoria-Fraserview']),
    ('Kitsilano', ARRAY['Kits']),
    ('Marpole', ARRAY[]::TEXT[]),
    ('Mount Pleasant', ARRAY['Mt Pleasant']),
    ('Oakridge', ARRAY[]::TEXT[]),
    ('Renfrew-Collingwood', ARRAY['Renfrew', 'Collingwood']),
    ('Riley Park', ARRAY['Riley Park-Little Mountain']),
    ('Shaughnessy', ARRAY[]::TEXT[]),
    ('South Cambie', ARRAY['Cambie']),
    ('Strathcona', ARRAY[]::TEXT[]),
    ('Sunset', ARRAY[]::TEXT[]),
    ('Victoria-Fraserview', ARRAY['Victoria', 'Fraserview']),
    ('West End', ARRAY[]::TEXT[]),
    ('West Point Grey', ARRAY['Point Grey'])
ON CONFLICT (name) DO NOTHING;

-- ── Bylaw Amendment Signal Type ─────────────────────────────────
-- No schema change needed — signal_type is a free-text field.
-- We document the new type for reference:
-- signal_type = 'bylaw_amendment' for municipal bylaw change detection
