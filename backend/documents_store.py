"""PostgreSQL-backed metadata for uploaded documents (the `documents` table,
backend/sql/004_create_documents.sql).

Only metadata lives here: the encrypted PDF stays on disk at `file_path`
and its RAG index in rag/index_store. A document belongs to a chat session
(`session_id`, a client-generated id) and/or a Deep Search thread
(`thread_id`); listing by either restores a session's document panel after
a refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, Table, Text, delete, or_, select

from backend.db import async_session_factory

documents_table = Table(
    "documents",
    MetaData(),
    Column("document_id", Text, primary_key=True, nullable=False),
    Column("user_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("n_pages", Integer, nullable=False),
    Column("file_path", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("thread_id", Text, ForeignKey("research_threads.thread_id", ondelete="SET NULL")),
    Column("session_id", Text),
)


@dataclass(frozen=True)
class Document:
    document_id: str
    user_id: str
    title: str
    n_pages: int
    file_path: str
    created_at: datetime
    thread_id: Optional[str]
    session_id: Optional[str]


def _row_to_document(row) -> Document:
    created_at = row["created_at"]
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return Document(
        document_id=row["document_id"],
        user_id=row["user_id"],
        title=row["title"],
        n_pages=row["n_pages"],
        file_path=row["file_path"],
        created_at=created_at,
        thread_id=row["thread_id"],
        session_id=row["session_id"],
    )


async def create_document(
    *,
    document_id: str,
    user_id: str,
    title: str,
    n_pages: int,
    file_path: str,
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                documents_table.insert().values(
                    document_id=document_id,
                    user_id=user_id,
                    title=title,
                    n_pages=n_pages,
                    file_path=file_path,
                    created_at=datetime.now(timezone.utc),
                    thread_id=thread_id,
                    session_id=session_id,
                )
            )


async def get_document(document_id: str) -> Optional[Document]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(documents_table).where(documents_table.c.document_id == document_id)
        )
        row = result.mappings().one_or_none()
    return _row_to_document(row) if row is not None else None


async def list_documents(
    user_id: str,
    *,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> list[Document]:
    """The caller's documents in a session and/or thread, oldest first. With
    neither given there is nothing to scope to, so the result is empty (never
    "all of the user's documents")."""
    scopes = []
    if session_id:
        scopes.append(documents_table.c.session_id == session_id)
    if thread_id:
        scopes.append(documents_table.c.thread_id == thread_id)
    if not scopes:
        return []

    async with async_session_factory() as session:
        result = await session.execute(
            select(documents_table)
            .where(documents_table.c.user_id == user_id, or_(*scopes))
            .order_by(documents_table.c.created_at.asc(), documents_table.c.document_id.asc())
        )
        return [_row_to_document(row) for row in result.mappings().all()]


async def delete_document(document_id: str) -> None:
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(documents_table).where(documents_table.c.document_id == document_id)
            )
