--
-- VCL-42 [INTEL-007] Weekly digest generator for the VanCity Lens project
-- Digest subscriptions, templates, and delivery tracking
--

-- ────────────────────────────────────────────────────────────────────────────
-- Digest Subscriptions Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS digest_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    neighborhoods TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    frequency TEXT NOT NULL DEFAULT 'weekly' CHECK (frequency IN ('daily', 'weekly')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on user_id for retrieving user's subscriptions
CREATE INDEX IF NOT EXISTS idx_digest_subscriptions_user_id ON digest_subscriptions(user_id);

-- Index on is_active for filtering active subscriptions
CREATE INDEX IF NOT EXISTS idx_digest_subscriptions_is_active ON digest_subscriptions(is_active);

-- Compound index for common queries
CREATE INDEX IF NOT EXISTS idx_digest_subscriptions_user_active
    ON digest_subscriptions(user_id, is_active);

-- Index on frequency for digest cycle queries
CREATE INDEX IF NOT EXISTS idx_digest_subscriptions_frequency
    ON digest_subscriptions(frequency, is_active);


-- ────────────────────────────────────────────────────────────────────────────
-- Digest Deliveries Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS digest_deliveries (
    id SERIAL PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES digest_subscriptions(id) ON DELETE CASCADE,
    digest_date DATE NOT NULL,
    content_json JSONB NOT NULL,
    signal_count INTEGER NOT NULL DEFAULT 0,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        delivery_status IN ('pending', 'sent', 'failed')
    ),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMP
);

-- Index on subscription_id for retrieving deliveries for a subscription
CREATE INDEX IF NOT EXISTS idx_digest_deliveries_subscription_id
    ON digest_deliveries(subscription_id);

-- Index on digest_date for time-based queries
CREATE INDEX IF NOT EXISTS idx_digest_deliveries_digest_date
    ON digest_deliveries(digest_date DESC);

-- Index on delivery_status for filtering pending/failed deliveries
CREATE INDEX IF NOT EXISTS idx_digest_deliveries_status
    ON digest_deliveries(delivery_status);

-- Compound index for common queries (most recent delivery for each subscription)
CREATE INDEX IF NOT EXISTS idx_digest_deliveries_subscription_date
    ON digest_deliveries(subscription_id, digest_date DESC);

-- Index for status-based queries
CREATE INDEX IF NOT EXISTS idx_digest_deliveries_status_date
    ON digest_deliveries(delivery_status, created_at DESC);

-- Unique constraint to prevent duplicate digests for same subscription on same date
CREATE UNIQUE INDEX IF NOT EXISTS idx_digest_deliveries_unique_subscription_date
    ON digest_deliveries(subscription_id, digest_date);
