-- Migration 032: Saved Parcels (bookmark/quick-save feature)
-- Complements the rule-based watchlist system with a simple one-click save.

CREATE TABLE IF NOT EXISTS saved_parcels (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pid TEXT NOT NULL,
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, pid)
);

CREATE INDEX IF NOT EXISTS idx_saved_parcels_user ON saved_parcels(user_id);
