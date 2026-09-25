CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    google_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    tier TEXT NOT NULL DEFAULT 'free',
    CONSTRAINT ck_users_tier CHECK (tier IN ('free', 'pro', 'team'))
);
