CREATE TABLE IF NOT EXISTS research_threads (
    thread_id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_research_threads_status CHECK (
        status IN (
            'running_agent2',
            'paused_for_selection',
            'running_synthesis',
            'done',
            'error'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_research_threads_user_created
ON research_threads (user_id ASC, created_at DESC);
