"""
backend/auth/users.py

Part D — Security Core: internal user table, mapping a verified Google
identity to this application's own user_id.

Owned by: Part D
Used by: backend/routers/auth.py (the POST /auth/google endpoint)

Public surface:
    find_or_create_user(google_sub: str, email: str, name: str | None = None) -> str

Why this table exists: everything else in the system (Part A's
thread_id -> user_id table, Part D's documents table, get_current_user())
was built around an opaque internal user_id string. This table is the
one place that maps "this specific Google account" to "this specific
internal user_id" -- once that mapping is made, ownership checks
elsewhere in the app (owns_thread, _get_owned_document_or_404, etc.)
continue to work completely unchanged, since they only ever cared about
the internal user_id.

google_sub (the "sub" claim from the verified Google ID token) is used
as the durable lookup key, NOT email -- a Google account's "sub" is a
stable, permanent identifier, whereas the associated email address can
change over time. Using email as the primary key would silently break
a returning user's account history if they ever changed their Google
account's email.

internal user_id is a fresh UUID, deliberately NOT the Google sub
directly -- this keeps the rest of the system's user_id format
consistent regardless of which identity provider was used to
authenticate (relevant if, e.g., a different login method is ever added
alongside Google Sign-In later).
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

_DB_PATH = os.environ.get(
    "USERS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "uploads", "users.db"),
)
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                google_sub TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL
            )
            """)
        conn.commit()
    finally:
        conn.close()


_init_db()


def find_or_create_user(google_sub: str, email: str, name: str | None = None) -> str:
    """
    Looks up the internal user_id for a given verified Google account,
    creating a new user row on first login.

    Args:
        google_sub: the "sub" claim from a verified Google ID token
            (see auth/google_auth.py). This is the durable lookup key.
        email: the Google account's email, stored for reference/display.
            Updated on every login in case the user's email changed on
            Google's side, but never used as the lookup key.
        name: optional display name from the Google account.

    Returns:
        The internal user_id (a UUID string) for this Google account --
        the same string every time for the same google_sub, across every
        future login.

    Raises:
        ValueError: if google_sub or email is empty.
    """
    if not google_sub:
        raise ValueError("google_sub must be a non-empty string")
    if not email:
        raise ValueError("email must be a non-empty string")

    new_user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_db()
    try:
        # Atomic upsert: avoids a check-then-act race where two concurrent
        # first-time logins for the same brand-new google_sub (e.g. a
        # double-click, or two browser tabs) could otherwise both pass a
        # SELECT finding no existing row, then both attempt an INSERT --
        # the second would crash on the UNIQUE constraint on google_sub.
        # ON CONFLICT makes "find or create" a single atomic operation.
        #
        # If this is a genuinely new google_sub, new_user_id is inserted
        # and becomes THE user_id for this account from now on. If
        # google_sub already exists, the conflict clause fires instead:
        # user_id is deliberately left untouched (excluded.user_id is
        # never assigned to the user_id column), so the existing,
        # already-established internal user_id is preserved -- only
        # email/name are refreshed.
        conn.execute(
            """
            INSERT INTO users (user_id, google_sub, email, name, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(google_sub) DO UPDATE SET
                email = excluded.email,
                name = excluded.name
            """,
            (new_user_id, google_sub, email, name, now),
        )
        conn.commit()

        row = conn.execute(
            "SELECT user_id FROM users WHERE google_sub = ?", (google_sub,)
        ).fetchone()
        return row["user_id"]
    finally:
        conn.close()
