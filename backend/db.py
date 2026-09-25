"""Shared asynchronous SQLAlchemy foundation for PostgreSQL access."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import get_settings


settings = get_settings()

# Engine construction is lazy with respect to network I/O: SQLAlchemy does not
# open a PostgreSQL connection until the first database operation is executed.
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield one async session for a FastAPI request or application helper."""
    async with async_session_factory() as session:
        yield session
