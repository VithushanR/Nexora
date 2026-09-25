"""Tests for the application-owned research thread metadata store."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend import research_threads
from backend.research_threads import (
    INITIAL_THREAD_STATUS,
    MonthlyResearchQuotaExceeded,
    VALID_THREAD_STATUSES,
    create_thread,
    create_thread_with_monthly_quota,
    get_thread,
    update_thread_status,
    verify_thread_owner,
)


def _utc_month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _insert_thread(
    user_id: str,
    created_at: datetime,
    status: str = INITIAL_THREAD_STATUS,
) -> str:
    thread_id = str(uuid4())
    async with research_threads.async_session_factory() as session:
        async with session.begin():
            await session.execute(
                insert(research_threads.research_threads_table).values(
                    thread_id=thread_id,
                    user_id=user_id,
                    domain="Quota test",
                    status=status,
                    created_at=created_at,
                )
            )
    return thread_id


async def _thread_count(user_id: str) -> int:
    async with research_threads.async_session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(research_threads.research_threads_table)
            .where(research_threads.research_threads_table.c.user_id == user_id)
        )
    return int(count or 0)


@pytest_asyncio.fixture
async def metadata_database(monkeypatch: pytest.MonkeyPatch):
    """Create an isolated research_threads table in a test PostgreSQL DB."""
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration test skipped.")

    if test_database_url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must not point to DATABASE_URL.")

    test_engine = create_async_engine(
        test_database_url,
        pool_pre_ping=True,
        # Keep destructive test cleanup isolated from production tables in public.
        execution_options={"schema_translate_map": {None: "nexora_test"}},
    )
    test_session_factory = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        research_threads,
        "async_session_factory",
        test_session_factory,
    )

    async with test_engine.begin() as connection:
        await connection.run_sync(research_threads.research_threads_metadata.create_all)

    try:
        yield
    finally:
        async with test_engine.begin() as connection:
            await connection.run_sync(research_threads.research_threads_metadata.drop_all)
        await test_engine.dispose()


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


@pytest.mark.asyncio
async def test_monthly_quota_allows_creation_below_limit(metadata_database):
    user_id = "quota-below-limit"
    await create_thread(user_id, "First")
    await create_thread(user_id, "Second")

    await create_thread_with_monthly_quota(user_id, "Third", 3)

    assert await _thread_count(user_id) == 3


@pytest.mark.asyncio
async def test_monthly_quota_rejects_at_limit_without_new_row(metadata_database):
    user_id = "quota-at-limit"
    for number in range(3):
        await create_thread(user_id, f"Existing {number}")

    with pytest.raises(MonthlyResearchQuotaExceeded):
        await create_thread_with_monthly_quota(user_id, "Rejected", 3)

    assert await _thread_count(user_id) == 3


@pytest.mark.asyncio
async def test_previous_month_threads_are_excluded(metadata_database):
    user_id = "quota-previous-month"
    await _insert_thread(user_id, _utc_month_start() - timedelta(microseconds=1))

    await create_thread_with_monthly_quota(user_id, "Current month", 1)

    assert await _thread_count(user_id) == 2


@pytest.mark.asyncio
async def test_all_thread_statuses_count_toward_quota(metadata_database):
    user_id = "quota-all-statuses"
    for thread_status in ("done", "error", "paused_for_selection"):
        await _insert_thread(user_id, datetime.now(timezone.utc), thread_status)

    with pytest.raises(MonthlyResearchQuotaExceeded):
        await create_thread_with_monthly_quota(user_id, "Rejected", 3)

    assert await _thread_count(user_id) == 3


@pytest.mark.asyncio
async def test_none_monthly_limit_is_unlimited(metadata_database):
    user_id = "quota-unlimited"
    for number in range(3):
        await create_thread(user_id, f"Existing {number}")

    await create_thread_with_monthly_quota(user_id, "Unlimited", None)

    assert await _thread_count(user_id) == 4


@pytest.mark.asyncio
async def test_same_user_concurrent_requests_cannot_exceed_quota(metadata_database):
    user_id = "quota-concurrent"
    results = await asyncio.gather(
        create_thread_with_monthly_quota(user_id, "Concurrent A", 1),
        create_thread_with_monthly_quota(user_id, "Concurrent B", 1),
        return_exceptions=True,
    )

    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, MonthlyResearchQuotaExceeded) for result in results) == 1
    assert await _thread_count(user_id) == 1


@pytest.mark.asyncio
async def test_different_users_have_independent_quotas(metadata_database):
    await create_thread_with_monthly_quota("quota-user-a", "User A", 1)
    with pytest.raises(MonthlyResearchQuotaExceeded):
        await create_thread_with_monthly_quota("quota-user-a", "Rejected A", 1)

    user_b_thread = await create_thread_with_monthly_quota(
        "quota-user-b", "User B", 1
    )

    assert await get_thread(user_b_thread) is not None
    assert await _thread_count("quota-user-a") == 1
    assert await _thread_count("quota-user-b") == 1


@pytest.mark.asyncio
async def test_utc_month_boundary_is_inclusive_at_start(metadata_database):
    user_id = "quota-boundary"
    month_start = _utc_month_start()
    await _insert_thread(user_id, month_start - timedelta(microseconds=1))
    await _insert_thread(user_id, month_start)

    with pytest.raises(MonthlyResearchQuotaExceeded):
        await create_thread_with_monthly_quota(user_id, "Rejected", 1)

    assert await _thread_count(user_id) == 2


@pytest.mark.asyncio
async def test_quota_rejection_rolls_back_without_inserting(metadata_database):
    user_id = "quota-rollback"
    existing_thread = await create_thread_with_monthly_quota(
        user_id, "Allowed", 1
    )

    with pytest.raises(MonthlyResearchQuotaExceeded):
        await create_thread_with_monthly_quota(user_id, "Rejected", 1)

    assert await _thread_count(user_id) == 1
    assert await get_thread(existing_thread) is not None
