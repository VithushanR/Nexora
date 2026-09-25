"""Integration tests for the one-off SQLite users migration."""

import os
import sqlite3
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.auth import users as users_module
from backend import migrate_users_to_postgres as migration_module
from backend.migrate_users_to_postgres import migrate_users
from backend.tiers import TierName


@pytest_asyncio.fixture
async def migration_database(monkeypatch: pytest.MonkeyPatch):
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration test skipped.")
    if test_database_url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must not point to DATABASE_URL.")

    test_engine = create_async_engine(test_database_url, pool_pre_ping=True)
    test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(migration_module, "async_session_factory", test_session_factory)

    async with test_engine.begin() as connection:
        await connection.run_sync(users_module.users_metadata.create_all)
    try:
        yield test_session_factory
    finally:
        async with test_engine.begin() as connection:
            await connection.run_sync(users_module.users_metadata.drop_all)
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_migration_preserves_users_and_is_idempotent(tmp_path, migration_database):
    source_path = tmp_path / "users.db"
    connection = sqlite3.connect(source_path)
    try:
        connection.execute(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                google_sub TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        created_at = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
            (
                "legacy-opaque-user-id",
                "legacy-google-sub",
                "legacy@example.com",
                "Legacy User",
                created_at.isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert await migrate_users(source_path) == 1
    assert await migrate_users(source_path) == 1

    async with migration_database() as session:
        row = (
            await session.execute(select(users_module.users_table))
        ).mappings().one()
        count = await session.scalar(select(func.count()).select_from(users_module.users_table))

    assert count == 1
    assert row["user_id"] == "legacy-opaque-user-id"
    assert row["google_sub"] == "legacy-google-sub"
    assert row["email"] == "legacy@example.com"
    assert row["name"] == "Legacy User"
    assert row["created_at"] == created_at
    assert row["tier"] == TierName.FREE.value
