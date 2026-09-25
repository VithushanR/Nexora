"""PostgreSQL-backed application users and account-tier lookup."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, MetaData, Table, Text, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import text

from backend.db import async_session_factory
from backend.tiers import DEFAULT_TIER, TierName


users_metadata = MetaData()
users_table = Table(
    "users",
    users_metadata,
    Column("user_id", Text, primary_key=True, nullable=False),
    Column("google_sub", Text, nullable=False, unique=True),
    Column("email", Text, nullable=False),
    Column("name", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("tier", Text, nullable=False, server_default=text(f"'{DEFAULT_TIER.value}'")),
    CheckConstraint("tier IN ('free', 'pro', 'team')", name="ck_users_tier"),
)


async def find_or_create_user(
    google_sub: str,
    email: str,
    name: str | None = None,
) -> str:
    """Return the stable internal ID for a verified Google account.

    First login creates a user with the default account tier. Later logins
    refresh email and name while preserving both the internal ID and tier.
    """
    if not google_sub:
        raise ValueError("google_sub must be a non-empty string")
    if not email:
        raise ValueError("email must be a non-empty string")

    statement = (
        insert(users_table)
        .values(
            user_id=str(uuid4()),
            google_sub=google_sub,
            email=email,
            name=name,
            created_at=datetime.now(timezone.utc),
            tier=DEFAULT_TIER.value,
        )
        .on_conflict_do_update(
            index_elements=[users_table.c.google_sub],
            set_={"email": email, "name": name},
        )
        .returning(users_table.c.user_id)
    )

    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(statement)
            return result.scalar_one()


async def get_user_tier(user_id: str) -> TierName:
    """Return a user's tier, raising for an unknown user or invalid value."""
    statement = select(users_table.c.tier).where(users_table.c.user_id == user_id)
    async with async_session_factory() as session:
        result = await session.execute(statement)
        stored_tier = result.scalar_one_or_none()

    if stored_tier is None:
        raise LookupError(f"Unknown user_id: {user_id!r}")

    return TierName(stored_tier)
