"""SQLite-backed metadata for research graph threads.

This module deliberately stores API-facing metadata separately from the
LangGraph checkpoint database.  Future routers use these functions without
needing to know how SQLite connections or schema setup are handled.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4

import aiosqlite

from backend.config import get_settings


VALID_THREAD_STATUSES = frozenset(
    {
        "running_agent2",
        "paused_for_selection",
        "running_synthesis",
        "done",
        "error",
    }
)
INITIAL_THREAD_STATUS = "running_agent2"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_threads (
    thread_id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'running_agent2',
            'paused_for_selection',
            'running_synthesis',
            'done',
            'error'
        )
    ),
    created_at TEXT NOT NULL
)
"""
_USER_CREATED_INDEX = """
CREATE INDEX IF NOT EXISTS idx_research_threads_user_created
ON research_threads (user_id, created_at DESC)
"""


@dataclass(frozen=True)
class ResearchThread:
    """Application metadata for one research graph thread."""

    thread_id: str
    user_id: str
    domain: str
    status: str
    created_at: str


@asynccontextmanager
async def _metadata_connection() -> AsyncIterator[aiosqlite.Connection]:
    """Open one short-lived, initialized metadata database connection."""
    database_path = get_settings().thread_metadata_db_path
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("PRAGMA busy_timeout = 5000")
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute(_SCHEMA)
        await connection.execute(_USER_CREATED_INDEX)
        await connection.commit()
        yield connection


def _validate_status(status: str) -> None:
    if status not in VALID_THREAD_STATUSES:
        valid_statuses = ", ".join(sorted(VALID_THREAD_STATUSES))
        raise ValueError(f"Invalid research thread status: {status!r}. Valid statuses: {valid_statuses}")


def _row_to_research_thread(row: aiosqlite.Row) -> ResearchThread:
    return ResearchThread(
        thread_id=row["thread_id"],
        user_id=row["user_id"],
        domain=row["domain"],
        status=row["status"],
        created_at=row["created_at"],
    )


async def create_thread(user_id: object, domain: str) -> str:
    """Create a thread with an initial ``running_agent2`` API status."""
    thread_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    async with _metadata_connection() as connection:
        await connection.execute(
            """
            INSERT INTO research_threads (thread_id, user_id, domain, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, str(user_id), domain, INITIAL_THREAD_STATUS, created_at),
        )
        await connection.commit()

    return thread_id


async def get_thread(thread_id: str) -> ResearchThread | None:
    """Return metadata for a thread, or ``None`` when it does not exist."""
    async with _metadata_connection() as connection:
        connection.row_factory = aiosqlite.Row
        async with connection.execute(
            """
            SELECT thread_id, user_id, domain, status, created_at
            FROM research_threads
            WHERE thread_id = ?
            """,
            (thread_id,),
        ) as cursor:
            row = await cursor.fetchone()

    return _row_to_research_thread(row) if row is not None else None


async def update_thread_status(thread_id: str, status: str) -> bool:
    """Update an existing thread status and report whether a row was changed."""
    _validate_status(status)

    async with _metadata_connection() as connection:
        cursor = await connection.execute(
            "UPDATE research_threads SET status = ? WHERE thread_id = ?",
            (status, thread_id),
        )
        await connection.commit()
        return cursor.rowcount == 1


async def verify_thread_owner(thread_id: str, user_id: object) -> bool:
    """Return whether the supplied user owns the requested thread."""
    async with _metadata_connection() as connection:
        async with connection.execute(
            """
            SELECT 1
            FROM research_threads
            WHERE thread_id = ? AND user_id = ?
            """,
            (thread_id, str(user_id)),
        ) as cursor:
            return await cursor.fetchone() is not None
