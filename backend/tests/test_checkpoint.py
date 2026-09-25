"""Focused tests for the future PostgreSQL LangGraph checkpoint resource."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from backend.graph import checkpoint


DATABASE_URL = "postgresql+psycopg://checkpoint_user:safe-password@db.example.test:5432/nexora"
CHECKPOINT_SCHEMA = "nexora_checkpoints"


def test_normalize_psycopg_url_removes_only_sqlalchemy_driver() -> None:
    normalized = checkpoint.normalize_psycopg_url(DATABASE_URL)
    parsed = make_url(normalized)

    assert parsed.drivername == "postgresql"
    assert parsed.username == "checkpoint_user"
    assert parsed.password == "safe-password"
    assert parsed.host == "db.example.test"
    assert parsed.port == 5432
    assert parsed.database == "nexora"


def test_normalize_psycopg_url_rejects_other_dialects_without_exposing_credentials() -> None:
    secret = "never-show-this-password"

    with pytest.raises(ValueError) as error:
        checkpoint.normalize_psycopg_url(f"sqlite://user:{secret}@localhost/database")

    assert secret not in str(error.value)


def test_malformed_url_error_does_not_chain_credential_bearing_parser_error() -> None:
    secret = "never-show-this-password"

    with pytest.raises(ValueError) as error:
        checkpoint.normalize_psycopg_url(f"not a URL containing {secret}")

    assert secret not in str(error.value)
    assert error.value.__cause__ is None


def test_resource_construction_does_not_create_or_open_a_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool_factory = Mock()
    monkeypatch.setattr(checkpoint, "AsyncConnectionPool", pool_factory)

    resource = checkpoint.PostgresCheckpointResource(
        DATABASE_URL,
        checkpoint_schema=CHECKPOINT_SCHEMA,
    )

    pool_factory.assert_not_called()
    with pytest.raises(RuntimeError, match="not open"):
        _ = resource.saver


def test_resource_can_read_database_url_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        checkpoint,
        "get_settings",
        lambda: SimpleNamespace(checkpoint_database_url=DATABASE_URL),
    )

    resource = checkpoint.PostgresCheckpointResource.from_settings(
        checkpoint_schema=CHECKPOINT_SCHEMA,
        min_size=2,
        max_size=3,
    )

    assert resource._min_size == 2
    assert resource._max_size == 3


@pytest.mark.asyncio
async def test_open_constructs_configured_pool_and_saver_without_schema_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = Mock()
    pool.open = AsyncMock()
    pool.close = AsyncMock()
    pool_factory = Mock(return_value=pool)
    saver = Mock()
    saver.setup = AsyncMock()
    saver_factory = Mock(return_value=saver)
    monkeypatch.setattr(checkpoint, "AsyncConnectionPool", pool_factory)
    monkeypatch.setattr(checkpoint, "AsyncPostgresSaver", saver_factory)
    resource = checkpoint.PostgresCheckpointResource(
        DATABASE_URL,
        checkpoint_schema=CHECKPOINT_SCHEMA,
        min_size=2,
        max_size=3,
    )

    await resource.open()

    _, pool_kwargs = pool_factory.call_args
    assert make_url(pool_factory.call_args.args[0]).drivername == "postgresql"
    assert pool_kwargs == {
        "min_size": 2,
        "max_size": 3,
        "open": False,
        "kwargs": {
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": "-c search_path=nexora_checkpoints",
        },
    }
    pool.open.assert_awaited_once_with(wait=True)
    saver_factory.assert_called_once_with(pool)
    saver.setup.assert_not_awaited()
    assert resource.saver is saver

    await resource.close()

    pool.close.assert_awaited_once_with()
    with pytest.raises(RuntimeError, match="not open"):
        _ = resource.saver


@pytest.mark.asyncio
async def test_failed_open_closes_pool_and_leaves_resource_unopened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = Mock()
    pool.open = AsyncMock(side_effect=RuntimeError("connection failed"))
    pool.close = AsyncMock()
    monkeypatch.setattr(checkpoint, "AsyncConnectionPool", Mock(return_value=pool))
    resource = checkpoint.PostgresCheckpointResource(
        DATABASE_URL,
        checkpoint_schema=CHECKPOINT_SCHEMA,
    )

    with pytest.raises(RuntimeError, match="connection failed"):
        await resource.open()

    pool.close.assert_awaited_once_with()
    with pytest.raises(RuntimeError, match="not open"):
        _ = resource.saver


@pytest.mark.asyncio
async def test_close_before_open_is_harmless() -> None:
    resource = checkpoint.PostgresCheckpointResource(
        DATABASE_URL,
        checkpoint_schema=CHECKPOINT_SCHEMA,
    )

    await resource.close()


@pytest.mark.parametrize(
    "schema",
    [
        "",
        "public",
        "public, nexora_checkpoints",
        "Public",
        "nexora-checkpoints",
        'bad"schema',
    ],
)
def test_checkpoint_schema_must_be_one_safe_explicit_identifier(schema: str) -> None:
    with pytest.raises(ValueError, match="dedicated lowercase PostgreSQL identifier"):
        checkpoint.PostgresCheckpointResource(
            DATABASE_URL,
            checkpoint_schema=schema,
        )
