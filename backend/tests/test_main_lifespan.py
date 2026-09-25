"""Focused tests for FastAPI ownership of the production graph lifecycle."""

from unittest.mock import AsyncMock

import pytest

from backend import main


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_graph_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start = AsyncMock()
    stop = AsyncMock()
    monkeypatch.setattr(main, "start_graph_runtime", start)
    monkeypatch.setattr(main, "stop_graph_runtime", stop)

    async with main.lifespan(main.app):
        start.assert_awaited_once_with()
        stop.assert_not_awaited()

    stop.assert_awaited_once_with()
