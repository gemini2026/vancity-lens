--
-- VCL-74 [BIZ-001] User authentication and accounts
-- User accounts, sessions, API keys, and authentication tables
--

-- ────────────────────────────────────────────────────────────────────────────
-- Users Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP
);

-- Index on email for quick lookups during login
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Index on is_active for filtering active users
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);


-- ────────────────────────────────────────────────────────────────────────────
-- User Sessions Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

-- Index on session_token for quick lookup during validation
CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);

-- Index on user_id for finding sessions by user
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);

-- Index on expires_at for cleanup queries
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);


-- ────────────────────────────────────────────────────────────────────────────
-- API Keys Table
-- ────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash TEXT UNIQUE NOT NULL,
    label TEXT,
    permissions TEXT[] DEFAULT '{"read"}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT true
);

-- Index on key_hash for quick validation during API calls
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);

-- Index on user_id for listing user's API keys
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);

-- Index on is_active for filtering active keys
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active);

-- Index on expires_at for cleanup queries
CREATE INDEX IF NOT EXISTS idx_api_keys_expires_at ON api_keys(expires_at);


-- ────────────────────────────────────────────────────────────────────────────
-- Roles Enum (for consistency)
-- ────────────────────────────────────────────────────────────────────────────

CREATE TYPE user_role AS ENUM ('user', 'admin', 'moderator');

-- Alter users table to use the enum (comment out if you want to keep it flexible)
-- ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::user_role;
