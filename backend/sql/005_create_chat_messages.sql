-- Every chat turn (one row for the user's message, one for the assistant's
-- reply). A message is anchored to a Deep Search thread, a document, and/or
-- a chat session -- at least one must be set (enforced below).
--
-- user_id is stored on every row so history reads are owner-scoped without
-- joining through threads/documents. Deleting a document or thread only
-- detaches the message (SET NULL); the conversation itself is kept, which
-- is why session_id is set on every message the app writes.
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    thread_id TEXT
        REFERENCES research_threads (thread_id) ON DELETE SET NULL,
    document_id TEXT
        REFERENCES documents (document_id) ON DELETE SET NULL,
    session_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mode TEXT,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_chat_messages_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT ck_chat_messages_mode CHECK (
        mode IS NULL OR mode IN ('general', 'grounded', 'web')
    ),
    CONSTRAINT ck_chat_messages_anchor CHECK (
        thread_id IS NOT NULL
        OR document_id IS NOT NULL
        OR session_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user_session
ON chat_messages (user_id, session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user_thread
ON chat_messages (user_id, thread_id, created_at);
