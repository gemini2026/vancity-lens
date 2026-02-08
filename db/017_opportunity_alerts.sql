--
-- VCL-50 [INTEL-009] Proactive opportunity alerts
-- User-defined opportunity profiles and match tracking
--

-- ────────────────────────────────────────────────────────────────────────────
-- Opportunity Profiles Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS opportunity_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name TEXT NOT NULL,
    min_lot_area_sqm NUMERIC(12,2),
    max_price BIGINT,
    target_neighborhoods TEXT[],
    target_zoning_codes TEXT[],
    min_storey_uplift INTEGER,
    min_fsr_uplift NUMERIC(4,2),
    max_distance_m INTEGER DEFAULT 800,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on user_id for retrieving user's profiles
CREATE INDEX IF NOT EXISTS idx_opportunity_profiles_user_id
    ON opportunity_profiles(user_id);

-- Index on is_active for filtering active profiles
CREATE INDEX IF NOT EXISTS idx_opportunity_profiles_is_active
    ON opportunity_profiles(is_active);

-- Compound index for common queries (user's active profiles)
CREATE INDEX IF NOT EXISTS idx_opportunity_profiles_user_active
    ON opportunity_profiles(user_id, is_active);


-- ────────────────────────────────────────────────────────────────────────────
-- Opportunity Matches Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS opportunity_matches (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES opportunity_profiles(id) ON DELETE CASCADE,
    parcel_pid TEXT NOT NULL REFERENCES parcels(pid) ON DELETE CASCADE,
    match_score NUMERIC(5,2) NOT NULL,
    match_reasons JSONB,
    is_dismissed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    dismissed_at TIMESTAMP
);

-- Index on profile_id for retrieving matches for a profile
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_profile_id
    ON opportunity_matches(profile_id);

-- Index on parcel_pid for looking up matches for a parcel
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_parcel_pid
    ON opportunity_matches(parcel_pid);

-- Index on is_dismissed for filtering active matches
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_is_dismissed
    ON opportunity_matches(is_dismissed);

-- Index on match_score for ranking
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_score
    ON opportunity_matches(match_score DESC);

-- Compound index for common queries (active matches for a profile)
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_profile_active
    ON opportunity_matches(profile_id, is_dismissed, match_score DESC);

-- Compound index for timing queries
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_created
    ON opportunity_matches(created_at DESC);

-- Index for user-level queries (join through profiles)
CREATE INDEX IF NOT EXISTS idx_opportunity_matches_profile_dismissed_score
    ON opportunity_matches(profile_id, is_dismissed, match_score DESC);

-- Unique constraint to prevent duplicate matches for same parcel+profile
CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunity_matches_unique_profile_parcel
    ON opportunity_matches(profile_id, parcel_pid)
    WHERE is_dismissed = false;
