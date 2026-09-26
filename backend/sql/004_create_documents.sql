-- Uploaded PDFs (metadata only; the encrypted file stays on disk at
-- file_path). Moved here from a local SQLite file so the list survives
-- restarts and can be queried per chat session / research thread.
--
-- A document belongs to a chat session (session_id, a client-generated id
-- kept in the browser) and/or a Deep Search thread (thread_id). Rows
-- migrated from the old SQLite table have neither.
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    n_pages INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    thread_id TEXT
        REFERENCES research_threads (thread_id) ON DELETE SET NULL,
    session_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_user_session
ON documents (user_id, session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_documents_user_thread
ON documents (user_id, thread_id, created_at);
