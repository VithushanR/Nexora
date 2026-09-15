"""Human checkpoint between retrieval and later analysis agents."""

from typing import Any

from langgraph.types import interrupt

from backend.graph.state import Candidate, ResearchState


class HumanSelectionValidationError(ValueError):
    """Raised when a human-selection resume payload is invalid."""


def _validate_selected_indices(value: Any, candidate_count: int) -> list[int]:
    """Validate the client-provided indices before reading checkpointed papers."""
    if not isinstance(value, list):
        raise HumanSelectionValidationError("selected_indices must be a list.")
    if not value:
        raise HumanSelectionValidationError("At least one candidate must be selected.")

    validated: list[int] = []
    seen: set[int] = set()
    for index in value:
        if isinstance(index, bool) or not isinstance(index, int):
            raise HumanSelectionValidationError("Each selected index must be an integer.")
        if index < 0 or index >= candidate_count:
            raise HumanSelectionValidationError("Selected index is outside the candidate range.")
        if index in seen:
            raise HumanSelectionValidationError("Selected indices must be unique.")
        seen.add(index)
        validated.append(index)

    return validated


async def human_selection_node(state: ResearchState) -> dict:
    """Pause for a human to choose checkpointed Agent 2 candidates by index."""
    candidates = state.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise HumanSelectionValidationError(
            "human_selection_node requires a non-empty state['candidates'] list."
        )

    selection = interrupt(
        {
            "kind": "paper_selection",
            "candidates": candidates,
            "candidate_count": len(candidates),
        }
    )

    if not isinstance(selection, dict):
        raise HumanSelectionValidationError("Selection resume payload must be an object.")

    selected_indices = _validate_selected_indices(
        selection.get("selected_indices"), len(candidates)
    )
    selected_papers: list[Candidate] = [candidates[index] for index in selected_indices]
    return {"selected_papers": selected_papers}
