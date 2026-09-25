"""Focused tests for the human candidate-selection checkpoint."""

from typing import cast
from unittest.mock import patch

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from backend.agents.human_selection import (
    HumanSelectionValidationError,
    human_selection_node,
)
from backend.graph.state import Candidate, ResearchState


# cast() here, not a plain list[dict] literal, for the same reason as
# test_retrieval_screening.py's make_candidate(): this is a known-valid
# Candidate shape built by hand for tests, not runtime-uncertain data.
CANDIDATES = cast(list[Candidate], [
    {"title": "Paper zero", "abstract": "Abstract zero", "source": "openalex"},
    {"title": "Paper one", "abstract": "Abstract one", "source": "arxiv"},
    {"title": "Paper two", "abstract": "Abstract two", "source": "europepmc"},
])


@pytest.mark.asyncio
async def test_valid_selection_returns_checkpointed_candidates_in_requested_order():
    with patch(
        "backend.agents.human_selection.interrupt",
        return_value={"selected_indices": [0, 2]},
    ):
        result = await human_selection_node({"candidates": CANDIDATES})

    assert result == {"selected_papers": [CANDIDATES[0], CANDIDATES[2]]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selection", "message"),
    [
        ({"selected_indices": []}, "At least one"),
        ({"selected_indices": [0, 0]}, "unique"),
        ({"selected_indices": [-1]}, "outside"),
        ({"selected_indices": [3]}, "outside"),
        ({"selected_indices": ["0"]}, "integer"),
        ({"selected_indices": [True]}, "integer"),
    ],
)
async def test_invalid_selected_indices_are_rejected(selection, message):
    with patch("backend.agents.human_selection.interrupt", return_value=selection):
        with pytest.raises(HumanSelectionValidationError, match=message):
            await human_selection_node({"candidates": CANDIDATES})


@pytest.mark.asyncio
async def test_missing_or_empty_candidates_are_rejected_without_interrupting():
    with patch("backend.agents.human_selection.interrupt") as mock_interrupt:
        with pytest.raises(HumanSelectionValidationError, match="non-empty"):
            await human_selection_node({})
        with pytest.raises(HumanSelectionValidationError, match="non-empty"):
            await human_selection_node({"candidates": []})
    mock_interrupt.assert_not_called()


@pytest.mark.asyncio
async def test_interrupt_payload_contains_checkpointed_candidates_and_count():
    observed_payload = None

    def capture_payload(payload):
        nonlocal observed_payload
        observed_payload = payload
        return {"selected_indices": [1]}

    with patch("backend.agents.human_selection.interrupt", side_effect=capture_payload):
        await human_selection_node({"candidates": CANDIDATES})

    assert observed_payload == {
        "kind": "paper_selection",
        "candidates": CANDIDATES,
        "candidate_count": 3,
    }


@pytest.mark.asyncio
async def test_isolated_graph_pauses_and_resumes_with_selected_indices():
    graph = StateGraph(ResearchState)
    graph.add_node("human_selection", human_selection_node)
    graph.add_edge(START, "human_selection")
    graph.add_edge("human_selection", END)
    app = graph.compile(checkpointer=MemorySaver())
    config = cast(RunnableConfig, {"configurable": {"thread_id": "human-selection-test"}})

    paused = await app.ainvoke({"candidates": CANDIDATES}, config=config)
    interrupt_payload = paused["__interrupt__"][0].value
    assert interrupt_payload["kind"] == "paper_selection"
    assert interrupt_payload["candidates"] == CANDIDATES
    assert interrupt_payload["candidate_count"] == 3

    resumed = await app.ainvoke(
        Command(resume={"selected_indices": [2, 0]}),
        config=config,
    )
    assert resumed["selected_papers"] == [CANDIDATES[2], CANDIDATES[0]]
