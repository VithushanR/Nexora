"""One-off, read-only SQLite documents migration to PostgreSQL.

Run explicitly from the repository root:

    python -m backend.migrate_documents_to_postgres backend/uploads/documents.db

The PostgreSQL ``documents`` and ``chat_messages`` tables must already exist
(backend/sql/004 and 005). The source database is opened read-only and every
insert is idempotent (re-running is safe). Migrated documents have no
session_id/thread_id (that association did not exist before), so they belong
to the user but appear in no session's panel. The old per-document chat
history is carried over into ``chat_messages`` anchored to its document.

The encrypted PDFs themselves are not moved: ``file_path`` keeps pointing at
the same file on disk.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from backend.chat_store import chat_messages_table
from backend.db import async_session_factory
from backend.documents_store import documents_table


@dataclass(frozen=True)
class LegacyDocument:
    document_id: str
    user_id: str
    title: str
    n_pages: int
    file_path: str
    created_at: datetime


@dataclass(frozen=True)
class LegacyMessage:
    message_id: str
    document_id: str
    role: str
    content: str
    created_at: datetime


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_sqlite(source_path: Path) -> tuple[list[LegacyDocument], list[LegacyMessage]]:
    """Read legacy rows without modifying or creating the SQLite file."""
    resolved_path = source_path.resolve(strict=True)
    connection = sqlite3.connect(f"file:{resolved_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        document_rows = connection.execute(
            "SELECT document_id, user_id, title, n_pages, file_path, created_at FROM documents"
        ).fetchall()
        message_rows = connection.execute(
            "SELECT message_id, document_id, role, content, timestamp FROM document_chat_history"
        ).fetchall()
    finally:
        connection.close()

    documents = [
        LegacyDocument(
            document_id=row["document_id"],
            user_id=row["user_id"],
            title=row["title"],
            n_pages=row["n_pages"],
            file_path=row["file_path"],
            created_at=_parse_timestamp(row["created_at"]),
        )
        for row in document_rows
    ]
    messages = [
        LegacyMessage(
            message_id=row["message_id"],
            document_id=row["document_id"],
            role=row["role"],
            content=row["content"],
            created_at=_parse_timestamp(row["timestamp"]),
        )
        for row in message_rows
    ]
    return documents, messages


async def migrate_documents(source_path: Path) -> tuple[int, int]:
    """Insert and verify legacy documents and their chat history, returning
    the verified (document, message) counts."""
    documents, messages = read_sqlite(source_path)
    owner_by_document = {d.document_id: d.user_id for d in documents}

    async with async_session_factory() as session:
        async with session.begin():
            for doc in documents:
                await session.execute(
                    insert(documents_table)
                    .values(
                        document_id=doc.document_id,
                        user_id=doc.user_id,
                        title=doc.title,
                        n_pages=doc.n_pages,
                        file_path=doc.file_path,
                        created_at=doc.created_at,
                    )
                    .on_conflict_do_nothing(index_elements=[documents_table.c.document_id])
                )

            for message in messages:
                await session.execute(
                    insert(chat_messages_table)
                    .values(
                        message_id=message.message_id,
                        user_id=owner_by_document[message.document_id],
                        document_id=message.document_id,
                        role=message.role,
                        content=message.content,
                        mode="grounded" if message.role == "assistant" else None,
                        sources=[],
                        created_at=message.created_at,
                    )
                    .on_conflict_do_nothing(index_elements=[chat_messages_table.c.message_id])
                )

            document_ids = [d.document_id for d in documents]
            stored_documents = {}
            if document_ids:
                result = await session.execute(
                    select(documents_table).where(documents_table.c.document_id.in_(document_ids))
                )
                stored_documents = {row["document_id"]: row for row in result.mappings().all()}
            if len(stored_documents) != len(documents):
                raise RuntimeError("Migration verification failed: PostgreSQL document count mismatch")

            for doc in documents:
                stored = stored_documents[doc.document_id]
                expected = (doc.user_id, doc.title, doc.n_pages, doc.file_path)
                actual = (stored["user_id"], stored["title"], stored["n_pages"], stored["file_path"])
                if actual != expected:
                    raise RuntimeError(
                        f"Migration verification failed for document {doc.document_id!r}; "
                        "existing PostgreSQL data differs"
                    )

            message_ids = [m.message_id for m in messages]
            stored_message_count = 0
            if message_ids:
                stored_message_count = await session.scalar(
                    select(func.count())
                    .select_from(chat_messages_table)
                    .where(chat_messages_table.c.message_id.in_(message_ids))
                ) or 0
            if stored_message_count != len(messages):
                raise RuntimeError("Migration verification failed: PostgreSQL message count mismatch")

    return len(documents), len(messages)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate a legacy SQLite documents database to PostgreSQL"
    )
    parser.add_argument("sqlite_path", type=Path)
    args = parser.parse_args()
    document_count, message_count = asyncio.run(migrate_documents(args.sqlite_path))
    print(f"Verified {document_count} migrated document(s) and {message_count} chat message(s).")


if __name__ == "__main__":
    main()
