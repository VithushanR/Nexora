"""Application-scoped lifecycle for the production LangGraph runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from backend.graph.build_graph import build_graph
from backend.graph.checkpoint import (
    PRODUCTION_CHECKPOINT_SCHEMA,
    PostgresCheckpointResource,
)


_checkpoint_resource: PostgresCheckpointResource | None = None
_compiled_graph: Any | None = None


async def start_graph_runtime() -> None:
    """Open PostgreSQL checkpointing and compile the production graph once."""
    global _checkpoint_resource, _compiled_graph
    if _checkpoint_resource is not None or _compiled_graph is not None:
        raise RuntimeError("Production graph runtime is already started.")

    resource = PostgresCheckpointResource.from_settings(
        checkpoint_schema=PRODUCTION_CHECKPOINT_SCHEMA
    )
    try:
        await resource.open()
        compiled_graph = build_graph().compile(checkpointer=resource.saver)
    except Exception:
        await resource.close()
        raise

    _checkpoint_resource = resource
    _compiled_graph = compiled_graph


async def stop_graph_runtime() -> None:
    """Discard the compiled graph and close its PostgreSQL checkpoint pool."""
    global _checkpoint_resource, _compiled_graph
    resource = _checkpoint_resource
    _compiled_graph = None
    _checkpoint_resource = None
    if resource is not None:
        await resource.close()


def get_compiled_graph() -> Any:
    """Return the shared graph, failing clearly before startup or after shutdown."""
    if _compiled_graph is None:
        raise RuntimeError("Production graph runtime is not started.")
    return _compiled_graph


@asynccontextmanager
async def graph_context() -> AsyncIterator[Any]:
    """Preserve the router context-manager seam while reusing one graph."""
    yield get_compiled_graph()
