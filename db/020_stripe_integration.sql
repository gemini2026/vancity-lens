--
-- VCL-82 [BIZ-003] Stripe payment integration for VanCity Lens
-- Adds Stripe customer and subscription tracking, plus webhook audit log
--

-- ────────────────────────────────────────────────────────────────────────────
-- Add Stripe columns to subscription_tiers
-- ────────────────────────────────────────────────────────────────────────────

ALTER TABLE IF EXISTS subscription_tiers
    ADD COLUMN IF NOT EXISTS stripe_price_id TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS stripe_product_id TEXT,
    ADD COLUMN IF NOT EXISTS is_stripe_managed BOOLEAN NOT NULL DEFAULT false;

-- Index for Stripe price lookups
CREATE INDEX IF NOT EXISTS idx_subscription_tiers_stripe_price_id
    ON subscription_tiers(stripe_price_id);

-- Index for Stripe product lookups
CREATE INDEX IF NOT EXISTS idx_subscription_tiers_stripe_product_id
    ON subscription_tiers(stripe_product_id);


-- ────────────────────────────────────────────────────────────────────────────
-- Add Stripe columns to user_subscriptions
-- ────────────────────────────────────────────────────────────────────────────

ALTER TABLE IF EXISTS user_subscriptions
    ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
    ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
    ADD COLUMN IF NOT EXISTS grace_period_ends_at TIMESTAMP;

-- Index for Stripe customer lookups
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_stripe_customer_id
    ON user_subscriptions(stripe_customer_id);

-- Index for Stripe subscription lookups
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_stripe_subscription_id
    ON user_subscriptions(stripe_subscription_id);

-- Index for grace period checking
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_grace_period
    ON user_subscriptions(grace_period_ends_at);


-- ────────────────────────────────────────────────────────────────────────────
-- Payment Events Audit Log Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS payment_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    stripe_event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL,
    processed BOOLEAN NOT NULL DEFAULT false,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- Index for event ID lookups (Stripe webhook idempotency)
CREATE INDEX IF NOT EXISTS idx_payment_events_stripe_event_id
    ON payment_events(stripe_event_id);

-- Index for user lookup
CREATE INDEX IF NOT EXISTS idx_payment_events_user_id
    ON payment_events(user_id);

-- Index for event type filtering
CREATE INDEX IF NOT EXISTS idx_payment_events_event_type
    ON payment_events(event_type);

-- Index for processing status
CREATE INDEX IF NOT EXISTS idx_payment_events_processed
    ON payment_events(processed);

-- Index for created_at (for audit trail)
CREATE INDEX IF NOT EXISTS idx_payment_events_created_at
    ON payment_events(created_at);
