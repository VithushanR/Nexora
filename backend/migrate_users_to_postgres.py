"""One-off, read-only SQLite users migration to PostgreSQL.

Run explicitly from the repository root:

    python -m backend.migrate_users_to_postgres path/to/users.db

The PostgreSQL ``users`` table must already exist. The source database is
opened read-only, inserts are idempotent on ``google_sub``, and every source
identity and field is verified after insertion.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.auth.users import users_table
from backend.db import async_session_factory
from backend.tiers import DEFAULT_TIER


@dataclass(frozen=True)
class LegacyUser:
    user_id: str
    google_sub: str
    email: str
    name: str | None
    created_at: datetime


def read_sqlite_users(source_path: Path) -> list[LegacyUser]:
    """Read legacy users without modifying or creating the SQLite file."""
    resolved_path = source_path.resolve(strict=True)
    connection = sqlite3.connect(f"file:{resolved_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT user_id, google_sub, email, name, created_at FROM users"
        ).fetchall()
    finally:
        connection.close()

    users: list[LegacyUser] = []
    for row in rows:
        created_at = datetime.fromisoformat(row["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        users.append(
            LegacyUser(
                user_id=row["user_id"],
                google_sub=row["google_sub"],
                email=row["email"],
                name=row["name"],
                created_at=created_at,
            )
        )
    return users


async def migrate_users(source_path: Path) -> int:
    """Insert and verify legacy users, returning the verified source count."""
    source_users = read_sqlite_users(source_path)

    async with async_session_factory() as session:
        async with session.begin():
            for user in source_users:
                await session.execute(
                    insert(users_table)
                    .values(
                        user_id=user.user_id,
                        google_sub=user.google_sub,
                        email=user.email,
                        name=user.name,
                        created_at=user.created_at,
                        tier=DEFAULT_TIER.value,
                    )
                    .on_conflict_do_nothing(index_elements=[users_table.c.google_sub])
                )

            google_subs = [user.google_sub for user in source_users]
            if google_subs:
                result = await session.execute(
                    select(users_table).where(users_table.c.google_sub.in_(google_subs))
                )
                target_by_sub = {
                    row["google_sub"]: row for row in result.mappings().all()
                }
            else:
                target_by_sub = {}

            if len(target_by_sub) != len(source_users):
                raise RuntimeError(
                    "Migration verification failed: PostgreSQL source-row count mismatch"
                )

            for source in source_users:
                target = target_by_sub[source.google_sub]
                target_created_at = target["created_at"]
                if target_created_at.tzinfo is None:
                    target_created_at = target_created_at.replace(tzinfo=timezone.utc)
                expected = (
                    source.user_id,
                    source.google_sub,
                    source.email,
                    source.name,
                    source.created_at.astimezone(timezone.utc),
                    DEFAULT_TIER.value,
                )
                actual = (
                    target["user_id"],
                    target["google_sub"],
                    target["email"],
                    target["name"],
                    target_created_at.astimezone(timezone.utc),
                    target["tier"],
                )
                if actual != expected:
                    raise RuntimeError(
                        "Migration verification failed for google_sub "
                        f"{source.google_sub!r}; existing PostgreSQL data differs"
                    )

    return len(source_users)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate a legacy SQLite users database to PostgreSQL"
    )
    parser.add_argument("sqlite_path", type=Path)
    args = parser.parse_args()
    migrated_count = asyncio.run(migrate_users(args.sqlite_path))
    print(f"Verified {migrated_count} migrated user row(s).")


if __name__ == "__main__":
    main()
