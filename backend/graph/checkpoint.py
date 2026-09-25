"""Lifecycle-managed PostgreSQL checkpoint resources for LangGraph."""

from __future__ import annotations

import re

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from backend.config import get_settings


DEFAULT_CHECKPOINT_POOL_MIN_SIZE = 1
DEFAULT_CHECKPOINT_POOL_MAX_SIZE = 4
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def normalize_psycopg_url(database_url: str) -> str:
    """Convert a SQLAlchemy PostgreSQL URL into a psycopg-compatible URI."""
    try:
        url = make_url(database_url)
    except Exception:
        raise ValueError("DATABASE_URL is not a valid PostgreSQL URL.") from None

    if url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must use the PostgreSQL dialect.")
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("DATABASE_URL must use the psycopg PostgreSQL driver.")

    return url.set(drivername="postgresql").render_as_string(hide_password=False)


class PostgresCheckpointResource:
    """Own an explicitly opened psycopg pool and its LangGraph saver."""

    def __init__(
        self,
        database_url: str,
        *,
        checkpoint_schema: str,
        min_size: int = DEFAULT_CHECKPOINT_POOL_MIN_SIZE,
        max_size: int = DEFAULT_CHECKPOINT_POOL_MAX_SIZE,
    ) -> None:
        if (
            not _SCHEMA_NAME.fullmatch(checkpoint_schema)
            or checkpoint_schema == "public"
        ):
            raise ValueError(
                "Checkpoint schema must be a dedicated lowercase PostgreSQL "
                "identifier and cannot be public."
            )
        if min_size < 1:
            raise ValueError("Checkpoint pool min_size must be at least 1.")
        if max_size < min_size:
            raise ValueError("Checkpoint pool max_size must be at least min_size.")

        self._conninfo = normalize_psycopg_url(database_url)
        self._checkpoint_schema = checkpoint_schema
        self._min_size = min_size
        self._max_size = max_size
        self._pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None
        self._saver: AsyncPostgresSaver | None = None

    @classmethod
    def from_settings(
        cls,
        *,
        checkpoint_schema: str,
        min_size: int = DEFAULT_CHECKPOINT_POOL_MIN_SIZE,
        max_size: int = DEFAULT_CHECKPOINT_POOL_MAX_SIZE,
    ) -> PostgresCheckpointResource:
        """Create an unopened resource from the application's current settings."""
        return cls(
            get_settings().database_url,
            checkpoint_schema=checkpoint_schema,
            min_size=min_size,
            max_size=max_size,
        )

    @property
    def saver(self) -> AsyncPostgresSaver:
        """Return the saver after startup has opened the resource."""
        if self._saver is None:
            raise RuntimeError("PostgreSQL checkpoint resource is not open.")
        return self._saver

    async def open(self) -> None:
        """Open the pool and construct its saver without running schema setup."""
        if self._pool is not None:
            raise RuntimeError("PostgreSQL checkpoint resource is already open.")

        pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
            self._conninfo,
            min_size=self._min_size,
            max_size=self._max_size,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
                # AsyncPostgresSaver uses unqualified table names. Restricting
                # search_path to one validated schema prevents writes to public.
                "options": f"-c search_path={self._checkpoint_schema}",
            },
        )
        try:
            await pool.open(wait=True)
            saver = AsyncPostgresSaver(pool)
        except Exception:
            await pool.close()
            raise

        self._pool = pool
        self._saver = saver

    async def close(self) -> None:
        """Close the checkpoint pool; closing an unopened resource is harmless."""
        pool = self._pool
        self._saver = None
        self._pool = None
        if pool is not None:
            await pool.close()
