"""Persistence tests for the SQLite-backed human-selection checkpoint."""

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from backend.agents.human_selection import HumanSelectionValidationError, human_selection_node
from backend.graph.build_graph import graph_context
from backend.graph.state import ResearchState


CANDIDATES = [
    {"title": "Paper zero", "abstract": "Abstract zero", "source": "openalex"},
    {"title": "Paper one", "abstract": "Abstract one", "source": "arxiv"},
    {"title": "Paper two", "abstract": "Abstract two", "source": "europepmc"},
]


def build_selection_graph() -> StateGraph:
    graph = StateGraph(ResearchState)
    graph.add_node("human_selection", human_selection_node)
    graph.add_edge(START, "human_selection")
    graph.add_edge("human_selection", END)
    return graph


@pytest.mark.asyncio
async def test_sqlite_checkpoint_survives_connection_reopen(tmp_path):
    db_path = tmp_path / "selection-checkpoints.sqlite"
    config = {"configurable": {"thread_id": "persistent-selection-test"}}

    async with graph_context(str(db_path), build_selection_graph) as first_app:
        paused = await first_app.ainvoke({"candidates": CANDIDATES}, config=config)

        interrupt_payload = paused["__interrupt__"][0].value
        assert interrupt_payload == {
            "kind": "paper_selection",
            "candidates": CANDIDATES,
            "candidate_count": len(CANDIDATES),
        }

    async with graph_context(str(db_path), build_selection_graph) as second_app:
        resumed = await second_app.ainvoke(
            Command(resume={"selected_indices": [0, 2]}),
            config=config,
        )

    assert resumed["selected_papers"] == [CANDIDATES[0], CANDIDATES[2]]


@pytest.mark.asyncio
async def test_sqlite_checkpoint_rejects_invalid_selection_after_reopen(tmp_path):
    db_path = tmp_path / "invalid-selection.sqlite"
    config = {"configurable": {"thread_id": "invalid-selection-test"}}

    async with graph_context(str(db_path), build_selection_graph) as first_app:
        await first_app.ainvoke({"candidates": CANDIDATES}, config=config)

    async with graph_context(str(db_path), build_selection_graph) as second_app:
        with pytest.raises(HumanSelectionValidationError, match="outside"):
            await second_app.ainvoke(
                Command(resume={"selected_indices": [3]}),
                config=config,
            )
