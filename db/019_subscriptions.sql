--
-- VCL-78 [BIZ-002] Tiered subscription model for VanCity Lens
-- Subscription tiers, user subscriptions, and usage tracking
--

-- ────────────────────────────────────────────────────────────────────────────
-- Subscription Tiers Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subscription_tiers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    price_monthly NUMERIC(10, 2),
    price_annual NUMERIC(10, 2),
    max_watchlists INTEGER NOT NULL,
    max_api_calls_daily INTEGER NOT NULL,
    max_signals_per_query INTEGER NOT NULL,
    features JSONB NOT NULL DEFAULT '{
        "chat_enabled": false,
        "digest_enabled": false,
        "export_enabled": false,
        "priority_support": false,
        "custom_branding": false
    }'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on name for quick tier lookups
CREATE INDEX IF NOT EXISTS idx_subscription_tiers_name ON subscription_tiers(name);

-- Index on is_active for filtering active tiers
CREATE INDEX IF NOT EXISTS idx_subscription_tiers_is_active ON subscription_tiers(is_active);


-- ────────────────────────────────────────────────────────────────────────────
-- User Subscriptions Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    tier_id INTEGER NOT NULL REFERENCES subscription_tiers(id),
    status TEXT NOT NULL DEFAULT 'active',
    trial_ends_at TIMESTAMP,
    current_period_start TIMESTAMP NOT NULL DEFAULT NOW(),
    current_period_end TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '30 days',
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on user_id for quick subscription lookup
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions(user_id);

-- Index on tier_id for finding users on a specific tier
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_tier_id ON user_subscriptions(tier_id);

-- Index on status for filtering by subscription status
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_status ON user_subscriptions(status);

-- Index on current_period_end for finding expiring subscriptions
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_period_end ON user_subscriptions(current_period_end);

-- Index on trial_ends_at for finding expiring trials
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_trial_ends_at ON user_subscriptions(trial_ends_at);


-- ────────────────────────────────────────────────────────────────────────────
-- Usage Tracking Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS usage_tracking (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL,
    api_calls INTEGER NOT NULL DEFAULT 0,
    signals_queried INTEGER NOT NULL DEFAULT 0,
    chat_messages INTEGER NOT NULL DEFAULT 0,
    exports INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Unique index on (user_id, usage_date) for one row per user per day
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_tracking_user_date ON usage_tracking(user_id, usage_date);

-- Index on user_id for finding usage by user
CREATE INDEX IF NOT EXISTS idx_usage_tracking_user_id ON usage_tracking(user_id);

-- Index on usage_date for finding usage by date
CREATE INDEX IF NOT EXISTS idx_usage_tracking_date ON usage_tracking(usage_date);


-- ────────────────────────────────────────────────────────────────────────────
-- Seed Subscription Tiers
-- ────────────────────────────────────────────────────────────────────────────

INSERT INTO subscription_tiers (
    name,
    display_name,
    price_monthly,
    price_annual,
    max_watchlists,
    max_api_calls_daily,
    max_signals_per_query,
    features,
    is_active
) VALUES
(
    'free',
    'Free',
    0.00,
    0.00,
    1,
    100,
    10,
    '{
        "chat_enabled": false,
        "digest_enabled": false,
        "export_enabled": false,
        "priority_support": false,
        "custom_branding": false
    }'::jsonb,
    true
),
(
    'starter',
    'Starter',
    29.99,
    299.99,
    5,
    1000,
    50,
    '{
        "chat_enabled": true,
        "digest_enabled": false,
        "export_enabled": true,
        "priority_support": false,
        "custom_branding": false
    }'::jsonb,
    true
),
(
    'professional',
    'Professional',
    99.99,
    999.99,
    20,
    10000,
    200,
    '{
        "chat_enabled": true,
        "digest_enabled": true,
        "export_enabled": true,
        "priority_support": true,
        "custom_branding": false
    }'::jsonb,
    true
),
(
    'enterprise',
    'Enterprise',
    499.99,
    4999.99,
    -1,
    -1,
    -1,
    '{
        "chat_enabled": true,
        "digest_enabled": true,
        "export_enabled": true,
        "priority_support": true,
        "custom_branding": true
    }'::jsonb,
    true
)
ON CONFLICT (name) DO NOTHING;
