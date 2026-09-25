"""PostgreSQL-backed metadata for research graph threads.

API-facing metadata remains separate from LangGraph checkpoint persistence.
Callers use this module without needing to manage SQLAlchemy sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    MetaData,
    Table,
    Text,
    insert,
    select,
    update,
)
from sqlalchemy.engine import CursorResult, RowMapping

from backend.db import async_session_factory


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

research_threads_metadata = MetaData()
research_threads_table = Table(
    "research_threads",
    research_threads_metadata,
    Column("thread_id", Text, primary_key=True, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("domain", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('running_agent2', 'paused_for_selection', "
        "'running_synthesis', 'done', 'error')",
        name="ck_research_threads_status",
    ),
)
Index(
    "idx_research_threads_user_created",
    research_threads_table.c.user_id.asc(),
    research_threads_table.c.created_at.desc(),
)


@dataclass(frozen=True)
class ResearchThread:
    """Application metadata for one research graph thread."""

    thread_id: str
    user_id: str
    domain: str
    status: str
    created_at: str


def _validate_status(status: str) -> None:
    if status not in VALID_THREAD_STATUSES:
        valid_statuses = ", ".join(sorted(VALID_THREAD_STATUSES))
        raise ValueError(f"Invalid research thread status: {status!r}. Valid statuses: {valid_statuses}")


def _row_to_research_thread(row: RowMapping) -> ResearchThread:
    created_at = row["created_at"]
    if not isinstance(created_at, datetime):
        raise TypeError("research_threads.created_at must be a datetime")
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)

    return ResearchThread(
        thread_id=row["thread_id"],
        user_id=row["user_id"],
        domain=row["domain"],
        status=row["status"],
        created_at=created_at.isoformat(),
    )


async def create_thread(user_id: object, domain: str) -> str:
    """Create a thread with an initial ``running_agent2`` API status."""
    thread_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                insert(research_threads_table).values(
                    thread_id=thread_id,
                    user_id=str(user_id),
                    domain=domain,
                    status=INITIAL_THREAD_STATUS,
                    created_at=created_at,
                )
            )

    return thread_id


async def get_thread(thread_id: str) -> ResearchThread | None:
    """Return metadata for a thread, or ``None`` when it does not exist."""
    statement = select(research_threads_table).where(
        research_threads_table.c.thread_id == thread_id
    )
    async with async_session_factory() as session:
        result = await session.execute(statement)
        row = result.mappings().one_or_none()

    return _row_to_research_thread(row) if row is not None else None


async def update_thread_status(thread_id: str, status: str) -> bool:
    """Update an existing thread status and report whether a row was changed."""
    _validate_status(status)

    statement = (
        update(research_threads_table)
        .where(research_threads_table.c.thread_id == thread_id)
        .values(status=status)
    )
    async with async_session_factory() as session:
        async with session.begin():
            result = cast(CursorResult[Any], await session.execute(statement))
            return result.rowcount == 1


async def verify_thread_owner(thread_id: str, user_id: object) -> bool:
    """Return whether the supplied user owns the requested thread."""
    statement = (
        select(research_threads_table.c.thread_id)
        .where(
            research_threads_table.c.thread_id == thread_id,
            research_threads_table.c.user_id == str(user_id),
        )
        .limit(1)
    )
    async with async_session_factory() as session:
        result = await session.execute(statement)
        return result.scalar_one_or_none() is not None
