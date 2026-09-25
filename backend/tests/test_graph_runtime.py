"""Tests for application-scoped PostgreSQL LangGraph lifecycle."""

from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from backend.graph import runtime
from backend.graph.checkpoint import PRODUCTION_CHECKPOINT_SCHEMA


@pytest_asyncio.fixture(autouse=True)
async def reset_graph_runtime():
    await runtime.stop_graph_runtime()
    yield
    await runtime.stop_graph_runtime()


@pytest.mark.asyncio
async def test_runtime_opens_once_compiles_once_and_reuses_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saver = object()
    resource = Mock()
    resource.open = AsyncMock()
    resource.close = AsyncMock()
    resource.saver = saver
    resource_factory = Mock(return_value=resource)
    compiled_graph = object()
    graph_builder = Mock()
    graph_builder.compile.return_value = compiled_graph
    monkeypatch.setattr(
        runtime.PostgresCheckpointResource,
        "from_settings",
        resource_factory,
    )
    monkeypatch.setattr(runtime, "build_graph", Mock(return_value=graph_builder))

    await runtime.start_graph_runtime()

    resource_factory.assert_called_once_with(
        checkpoint_schema=PRODUCTION_CHECKPOINT_SCHEMA
    )
    resource.open.assert_awaited_once_with()
    graph_builder.compile.assert_called_once_with(checkpointer=saver)
    async with runtime.graph_context() as first_graph:
        pass
    async with runtime.graph_context() as second_graph:
        pass
    assert first_graph is second_graph is compiled_graph

    await runtime.stop_graph_runtime()

    resource.close.assert_awaited_once_with()
    with pytest.raises(RuntimeError, match="not started"):
        runtime.get_compiled_graph()


@pytest.mark.asyncio
async def test_runtime_closes_resource_when_graph_compilation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource = Mock()
    resource.open = AsyncMock()
    resource.close = AsyncMock()
    resource.saver = object()
    monkeypatch.setattr(
        runtime.PostgresCheckpointResource,
        "from_settings",
        Mock(return_value=resource),
    )
    graph_builder = Mock()
    graph_builder.compile.side_effect = RuntimeError("compile failed")
    monkeypatch.setattr(runtime, "build_graph", Mock(return_value=graph_builder))

    with pytest.raises(RuntimeError, match="compile failed"):
        await runtime.start_graph_runtime()

    resource.close.assert_awaited_once_with()
    with pytest.raises(RuntimeError, match="not started"):
        runtime.get_compiled_graph()


@pytest.mark.asyncio
async def test_runtime_fails_clearly_before_startup() -> None:
    with pytest.raises(RuntimeError, match="not started"):
        async with runtime.graph_context():
            pass
