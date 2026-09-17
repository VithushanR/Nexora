"""Tests for the application-owned research thread metadata store."""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.config import get_settings
from backend.research_threads import (
    INITIAL_THREAD_STATUS,
    VALID_THREAD_STATUSES,
    create_thread,
    get_thread,
    update_thread_status,
    verify_thread_owner,
)


@pytest.fixture
def metadata_database(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Point each test to an isolated metadata SQLite database."""
    monkeypatch.setenv("THREAD_METADATA_DB_PATH", str(tmp_path / "threads.sqlite"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_create_thread_stores_metadata_with_expected_initial_values(metadata_database):
    thread_id = await create_thread(42, "Effects of sleep on academic performance")

    assert UUID(thread_id).version == 4
    thread = await get_thread(thread_id)
    assert thread is not None
    assert thread.thread_id == thread_id
    assert thread.user_id == "42"
    assert thread.domain == "Effects of sleep on academic performance"
    assert thread.status == INITIAL_THREAD_STATUS == "running_agent2"

    created_at = datetime.fromisoformat(thread.created_at)
    assert created_at.tzinfo is not None
    assert created_at.utcoffset() == timezone.utc.utcoffset(created_at)


@pytest.mark.asyncio
async def test_get_thread_returns_none_for_unknown_thread(metadata_database):
    assert await get_thread("does-not-exist") is None


@pytest.mark.asyncio
async def test_update_thread_status_accepts_all_valid_statuses(metadata_database):
    thread_id = await create_thread("student-7", "AI safety policy")

    for status in VALID_THREAD_STATUSES:
        assert await update_thread_status(thread_id, status) is True
        thread = await get_thread(thread_id)
        assert thread is not None
        assert thread.status == status


@pytest.mark.asyncio
async def test_update_thread_status_rejects_invalid_status_before_writing(metadata_database):
    thread_id = await create_thread("student-7", "AI safety policy")

    with pytest.raises(ValueError, match="Invalid research thread status"):
        await update_thread_status(thread_id, "paused")

    thread = await get_thread(thread_id)
    assert thread is not None
    assert thread.status == INITIAL_THREAD_STATUS


@pytest.mark.asyncio
async def test_update_thread_status_returns_false_for_unknown_thread(metadata_database):
    assert await update_thread_status("does-not-exist", "error") is False


@pytest.mark.asyncio
async def test_verify_thread_owner_matches_normalized_user_id(metadata_database):
    thread_id = await create_thread(17, "Software engineering education")

    assert await verify_thread_owner(thread_id, "17") is True
    assert await verify_thread_owner(thread_id, 18) is False
    assert await verify_thread_owner("does-not-exist", 17) is False


@pytest.mark.asyncio
async def test_thread_metadata_persists_across_independent_connections(metadata_database):
    thread_id = await create_thread("student-9", "Climate adaptation")

    thread = await get_thread(thread_id)

    assert thread is not None
    assert thread.thread_id == thread_id
    assert thread.user_id == "student-9"
