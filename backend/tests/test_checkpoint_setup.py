"""Tests for the explicit PostgreSQL checkpoint setup command."""

from unittest.mock import AsyncMock, Mock

import pytest

from backend import setup_checkpoints


DATABASE_URL = "postgresql+psycopg://setup_user:safe-password@db.example.test/nexora"
SCHEMA = "nexora_checkpoints"


@pytest.mark.asyncio
async def test_setup_invokes_langgraph_setup_and_closes_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saver = Mock()
    saver.setup = AsyncMock()
    resource = Mock()
    resource.open = AsyncMock()
    resource.close = AsyncMock()
    resource.saver = saver
    resource_factory = Mock(return_value=resource)
    monkeypatch.setattr(
        setup_checkpoints,
        "PostgresCheckpointResource",
        resource_factory,
    )

    await setup_checkpoints.setup_checkpoint_schema(DATABASE_URL, SCHEMA)

    resource_factory.assert_called_once_with(
        DATABASE_URL,
        checkpoint_schema=SCHEMA,
        min_size=1,
        max_size=1,
    )
    resource.open.assert_awaited_once_with()
    saver.setup.assert_awaited_once_with()
    resource.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_setup_closes_resource_when_langgraph_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saver = Mock()
    saver.setup = AsyncMock(side_effect=RuntimeError("setup failed"))
    resource = Mock()
    resource.open = AsyncMock()
    resource.close = AsyncMock()
    resource.saver = saver
    monkeypatch.setattr(
        setup_checkpoints,
        "PostgresCheckpointResource",
        Mock(return_value=resource),
    )

    with pytest.raises(RuntimeError, match="setup failed"):
        await setup_checkpoints.setup_checkpoint_schema(DATABASE_URL, SCHEMA)

    resource.close.assert_awaited_once_with()


def test_main_requires_explicit_checkpoint_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHECKPOINT_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    run_setup = Mock()
    monkeypatch.setattr(setup_checkpoints, "_run_setup", run_setup)

    with pytest.raises(SystemExit) as error:
        setup_checkpoints.main(["--schema", SCHEMA])

    assert error.value.code == 2
    run_setup.assert_not_called()


def test_main_returns_nonzero_without_exposing_failure_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "never-print-this-password"
    database_url = f"postgresql+psycopg://user:{secret}@db.example.test/nexora"
    monkeypatch.setenv("CHECKPOINT_DATABASE_URL", database_url)
    monkeypatch.setattr(
        setup_checkpoints,
        "_run_setup",
        Mock(side_effect=RuntimeError(f"connection failed for {database_url}")),
    )

    result = setup_checkpoints.main(["--schema", SCHEMA])

    captured = capsys.readouterr()
    assert result == 1
    assert secret not in captured.err
    assert database_url not in captured.err
