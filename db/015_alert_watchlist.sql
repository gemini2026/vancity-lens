--
-- VCL-38 [INTEL-006] Alert system with watchlist
-- Watchlist rules, alerts, and alert management
--

-- ────────────────────────────────────────────────────────────────────────────
-- Watchlists Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on user_id for retrieving user's watchlists
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);

-- Index on is_active for filtering active watchlists
CREATE INDEX IF NOT EXISTS idx_watchlists_is_active ON watchlists(is_active);

-- Compound index for common queries
CREATE INDEX IF NOT EXISTS idx_watchlists_user_active ON watchlists(user_id, is_active);


-- ────────────────────────────────────────────────────────────────────────────
-- Watchlist Rules Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS watchlist_rules (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    rule_value TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index on watchlist_id for retrieving rules for a watchlist
CREATE INDEX IF NOT EXISTS idx_watchlist_rules_watchlist_id ON watchlist_rules(watchlist_id);

-- Index on rule_type for efficient rule matching
CREATE INDEX IF NOT EXISTS idx_watchlist_rules_type ON watchlist_rules(rule_type);

-- Compound index for common queries
CREATE INDEX IF NOT EXISTS idx_watchlist_rules_watchlist_type ON watchlist_rules(watchlist_id, rule_type);


-- ────────────────────────────────────────────────────────────────────────────
-- Alerts Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    signal_id INTEGER NOT NULL REFERENCES intelligence_signals(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    severity TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    read_at TIMESTAMP
);

-- Index on watchlist_id for retrieving alerts for a watchlist
CREATE INDEX IF NOT EXISTS idx_alerts_watchlist_id ON alerts(watchlist_id);

-- Index on signal_id for looking up alerts by signal
CREATE INDEX IF NOT EXISTS idx_alerts_signal_id ON alerts(signal_id);

-- Index on is_read for filtering unread alerts
CREATE INDEX IF NOT EXISTS idx_alerts_is_read ON alerts(is_read);

-- Index on created_at for chronological ordering
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);

-- Compound index for common queries (unread alerts for a watchlist)
CREATE INDEX IF NOT EXISTS idx_alerts_watchlist_read ON alerts(watchlist_id, is_read, created_at DESC);

-- Index for user-level queries (join through watchlists)
CREATE INDEX IF NOT EXISTS idx_alerts_watchlist_created ON alerts(watchlist_id, created_at DESC);

-- Unique constraint to prevent duplicate alerts for same signal+watchlist
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_unique_signal_watchlist
ON alerts(watchlist_id, signal_id);
