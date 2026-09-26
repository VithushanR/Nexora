"""PostgreSQL-backed chat history (the `chat_messages` table,
backend/sql/005_create_chat_messages.sql).

Every chat turn is stored as two rows -- the user message and the
assistant reply -- so a session or thread conversation survives restarts.
Reads are always scoped to the requesting user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, MetaData, Table, Text, Uuid, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from backend.db import async_session_factory

chat_messages_table = Table(
    "chat_messages",
    MetaData(),
    Column("message_id", Uuid(as_uuid=False), primary_key=True, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("thread_id", Text, ForeignKey("research_threads.thread_id", ondelete="SET NULL")),
    Column("document_id", Text, ForeignKey("documents.document_id", ondelete="SET NULL")),
    Column("session_id", Text),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("mode", Text),
    Column("sources", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class ChatMessageRecord:
    message_id: str
    role: str
    content: str
    mode: Optional[str]
    sources: list[dict[str, Any]]
    created_at: datetime


async def save_chat_turn(
    *,
    user_id: str,
    session_id: Optional[str],
    thread_id: Optional[str],
    document_id: Optional[str],
    user_content: str,
    assistant_message_id: str,
    assistant_content: str,
    mode: str,
    sources: list[dict[str, Any]],
) -> None:
    """Insert the user message and the assistant reply in one transaction.
    At least one of session_id / thread_id / document_id must be set (the
    table enforces it too)."""
    if not (session_id or thread_id or document_id):
        raise ValueError("A chat message must belong to a session, a thread, or a document.")

    now = datetime.now(timezone.utc)
    anchor = {"user_id": user_id, "session_id": session_id, "thread_id": thread_id, "document_id": document_id}
    rows = [
        {**anchor, "message_id": str(uuid4()), "role": "user", "content": user_content,
         "mode": None, "sources": [], "created_at": now},
        # A microsecond later so ordering by created_at keeps the user
        # message ahead of its reply.
        {**anchor, "message_id": assistant_message_id, "role": "assistant", "content": assistant_content,
         "mode": mode, "sources": sources, "created_at": now + timedelta(microseconds=1)},
    ]
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(chat_messages_table.insert(), rows)


async def list_chat_messages(
    user_id: str,
    *,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    limit: int = 500,
) -> list[ChatMessageRecord]:
    """The caller's messages in a session and/or thread, oldest first. With
    neither given the result is empty."""
    scopes = []
    if session_id:
        scopes.append(chat_messages_table.c.session_id == session_id)
    if thread_id:
        scopes.append(chat_messages_table.c.thread_id == thread_id)
    if not scopes:
        return []

    async with async_session_factory() as session:
        result = await session.execute(
            select(chat_messages_table)
            .where(chat_messages_table.c.user_id == user_id, or_(*scopes))
            .order_by(chat_messages_table.c.created_at.asc(), chat_messages_table.c.message_id.asc())
            .limit(limit)
        )
        return [
            ChatMessageRecord(
                message_id=str(row["message_id"]),
                role=row["role"],
                content=row["content"],
                mode=row["mode"],
                sources=row["sources"],
                created_at=row["created_at"],
            )
            for row in result.mappings().all()
        ]
