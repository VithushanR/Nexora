"""PostgreSQL integration tests for application users."""

import os

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.auth import users as users_module
from backend.auth.users import find_or_create_user, get_user_tier
from backend.tiers import DEFAULT_TIER, TierName


@pytest_asyncio.fixture
async def users_database(monkeypatch: pytest.MonkeyPatch):
    """Create an isolated users table in the configured test PostgreSQL DB."""
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration test skipped.")
    if test_database_url == os.environ.get("DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must not point to DATABASE_URL.")

    test_engine = create_async_engine(test_database_url, pool_pre_ping=True)
    test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(users_module, "async_session_factory", test_session_factory)

    async with test_engine.begin() as connection:
        await connection.run_sync(users_module.users_metadata.create_all)
    try:
        yield test_session_factory
    finally:
        async with test_engine.begin() as connection:
            await connection.run_sync(users_module.users_metadata.drop_all)
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_new_google_account_creates_free_user(users_database):
    user_id = await find_or_create_user("google-sub-123", "alice@example.com", "Alice")
    assert isinstance(user_id, str)
    assert await get_user_tier(user_id) is DEFAULT_TIER is TierName.FREE


@pytest.mark.asyncio
async def test_same_google_sub_preserves_user_id_tier_and_updates_profile(users_database):
    user_id = await find_or_create_user("google-sub-456", "old@example.com", "Old")
    async with users_database() as session:
        async with session.begin():
            await session.execute(
                update(users_module.users_table)
                .where(users_module.users_table.c.user_id == user_id)
                .values(tier=TierName.PRO.value)
            )

    repeated_user_id = await find_or_create_user(
        "google-sub-456", "new@example.com", "New"
    )
    assert repeated_user_id == user_id
    assert await get_user_tier(user_id) is TierName.PRO

    async with users_database() as session:
        row = (
            await session.execute(
                select(users_module.users_table).where(
                    users_module.users_table.c.user_id == user_id
                )
            )
        ).mappings().one()
    assert row["email"] == "new@example.com"
    assert row["name"] == "New"


@pytest.mark.asyncio
async def test_different_google_accounts_get_different_user_ids(users_database):
    user_a = await find_or_create_user("sub-a", "a@example.com")
    user_b = await find_or_create_user("sub-b", "b@example.com")
    assert user_a != user_b


@pytest.mark.asyncio
async def test_missing_identity_fields_raise_value_error(users_database):
    with pytest.raises(ValueError):
        await find_or_create_user("", "x@example.com")
    with pytest.raises(ValueError):
        await find_or_create_user("sub-x", "")


@pytest.mark.asyncio
async def test_get_user_tier_raises_for_unknown_user(users_database):
    with pytest.raises(LookupError, match="Unknown user_id"):
        await get_user_tier("does-not-exist")


@pytest.mark.asyncio
async def test_get_user_tier_raises_for_invalid_stored_tier():
    class InvalidTierResult:
        def scalar_one_or_none(self):
            return "enterprise"

    class InvalidTierSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def execute(self, statement):
            return InvalidTierResult()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(users_module, "async_session_factory", InvalidTierSession)

    try:
        with pytest.raises(ValueError):
            await get_user_tier("corrupt-user")
    finally:
        monkeypatch.undo()
