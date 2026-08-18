"""
Search router.

Responsibility:
- POST /search: accepts a research domain from the frontend SearchPage,
  starts a new graph run (protocol_planning -> retrieval_screening), and
  returns the run id + candidate papers once the run hits the human
  interrupt() checkpoint.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from graph.build_graph import build_graph

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    domain: str


# TODO: define SearchResponse model (run_id, candidates)


@router.post("")
async def start_search(request: SearchRequest):
    # TODO: invoke the compiled graph up to the interrupt() checkpoint
    # TODO: return run_id (thread_id for the checkpointer) + candidates
    raise NotImplementedError
