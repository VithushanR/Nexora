"""Tests for required PostgreSQL configuration and shared DB primitives."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings
from backend.db import async_session_factory, engine, get_db_session


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        Settings()


def test_postgresql_engine_and_session_factory_are_constructed() -> None:
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"

    session = async_session_factory()
    assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_database_dependency_yields_async_session_without_connecting() -> None:
    dependency = get_db_session()
    session = await anext(dependency)

    try:
        assert isinstance(session, AsyncSession)
    finally:
        await dependency.aclose()
