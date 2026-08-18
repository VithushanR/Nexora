"""
Selection router.

Responsibility:
- POST /select: accepts the user's ticked paper selection from
  SelectionPage, resumes the graph's interrupt() checkpoint with
  selected_papers, and lets the parallel synthesis/gap-discovery branch
  run through to report assembly.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from graph.build_graph import build_graph

router = APIRouter(prefix="/select", tags=["selection"])


class SelectionRequest(BaseModel):
    run_id: str
    selected_paper_ids: list[str]


# TODO: define SelectionResponse model (report, evidence_table, contradictions, gaps)


@router.post("")
async def submit_selection(request: SelectionRequest):
    # TODO: resume the graph run identified by run_id via the checkpointer
    # TODO: return the assembled report once the fan-in completes
    raise NotImplementedError
