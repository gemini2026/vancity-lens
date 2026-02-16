-- Migration 048: Email preferences for weekly undervalued parcel alerts (F06-002)
-- Adds opt-in email alert columns to users table

ALTER TABLE users ADD COLUMN IF NOT EXISTS email_alerts BOOLEAN DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS alert_email TEXT;

-- Index for efficient subscriber lookup when sending weekly digests
CREATE INDEX IF NOT EXISTS idx_users_email_alerts
    ON users(email_alerts) WHERE email_alerts = true;
