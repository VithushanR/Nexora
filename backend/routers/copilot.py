"""
Report indexing for chat (Part B).

Responsibility:
- POST /research/{thread_id}/copilot/index   index a finished report so the
  merged chat router (routers/chat.py) can ground answers in it

Chatting itself -- report-grounded, document-grounded, general and web
search -- no longer lives here: it is one code path in routers/chat.py,
keyed off the thread's state. This module only turns a finished report into
a searchable RAG namespace.

Part B's only input is the `report` dict produced by the pipeline (see
backend/report/store.py for the exact contract shape). Auth
(backend.auth.jwt.get_current_user) and thread ownership
(backend.research_threads.get_thread/verify_thread_owner) are the same real,
shared implementation backend/routers/research.py uses.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth.jwt import get_current_user
from backend.rag.chat import build_index
from backend.report.store import get_report
from backend.research_threads import get_thread, verify_thread_owner

logger = logging.getLogger("nexora.copilot")

router = APIRouter(prefix="/research", tags=["copilot"])


class IndexResponse(BaseModel):
    indexed: bool
    n_chunks: int


def report_namespace(thread_id: str) -> str:
    return f"report:{thread_id}"


async def require_owned_thread(thread_id: str, user_id: str) -> None:
    """Raises 404 (not 403) if the thread doesn't exist or isn't owned by
    user_id -- matching backend/routers/research.py's _owned_thread_or_404
    exactly, so a non-owner can't distinguish "doesn't exist" from "exists,
    not yours"."""
    thread = await get_thread(thread_id)
    if thread is None or not await verify_thread_owner(thread_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research thread not found.")


# ============================================================
# Report chunking (for /index)
# ============================================================


def chunk_report(report: dict) -> list[str]:
    """One chunk per evidence row, per contradiction, per gap.

    An empty section is simply skipped -- it contributes zero chunks. A
    section whose *_status shows is_error=True is still handled this way
    (skip what's empty, index what's real); the caller logs a warning so
    the incomplete analysis isn't silently invisible, but nothing here
    fabricates content to fill the gap.
    """
    chunks: list[str] = []

    for row in report.get("evidence_table") or []:
        title = row.get("title", "")
        methodology = row.get("methodology_summary", "")
        results = row.get("results_summary", "")
        chunks.append(f"{title}\n\nMethodology: {methodology}\n\nResults: {results}")

    for item in report.get("contradictions") or []:
        description = item.get("description", "")
        paper_a_title = item.get("paper_a_title", "")
        paper_a_claim = item.get("paper_a_claim", "")
        paper_b_title = item.get("paper_b_title", "")
        paper_b_claim = item.get("paper_b_claim", "")
        chunks.append(
            f"{description}\n\n"
            f'"{paper_a_title}" claims: {paper_a_claim}\n\n'
            f'"{paper_b_title}" claims: {paper_b_claim}'
        )

    for gap in report.get("gaps") or []:
        theme = gap.get("theme", "")
        supporting_titles = gap.get("supporting_paper_titles") or []
        chunks.append(f"{theme}\n\nSupporting papers: {', '.join(supporting_titles)}")

    return chunks


def _warn_if_incomplete(thread_id: str, report: dict) -> None:
    """Logs (does not raise) when a section is empty or was reported as a
    processing failure, so an incomplete analysis is visible in logs
    without ever blocking indexing of whatever real content does exist."""
    if not report.get("evidence_table"):
        logger.warning("copilot/index thread=%s: evidence_table is empty", thread_id)

    contradictions_status = report.get("contradictions_status") or {}
    if not report.get("contradictions") and contradictions_status.get("is_error"):
        logger.warning(
            "copilot/index thread=%s: contradictions analysis incomplete (%s): %s",
            thread_id, contradictions_status.get("code"), contradictions_status.get("message"),
        )

    gaps_status = report.get("gaps_status") or {}
    if not report.get("gaps") and gaps_status.get("is_error"):
        logger.warning(
            "copilot/index thread=%s: gap analysis incomplete (%s): %s",
            thread_id, gaps_status.get("code"), gaps_status.get("message"),
        )



# ============================================================
# Endpoint
# ============================================================


@router.post("/{thread_id}/copilot/index", response_model=IndexResponse)
async def index_report(thread_id: str, user_id: str = Depends(get_current_user)) -> IndexResponse:
    await require_owned_thread(thread_id, user_id)

    report = await get_report(thread_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No finished report exists for this research thread yet.",
        )
    _warn_if_incomplete(thread_id, report)

    chunks = chunk_report(report)
    # rag.chat.build_index() raises ValueError on an empty list -- indexing
    # nothing is a no-op here, not an error (see chunk_report's docstring:
    # an empty/incomplete report is still indexed for whatever real content
    # it does have, which can legitimately be zero chunks).
    if chunks:
        await asyncio.to_thread(build_index, chunks, namespace=report_namespace(thread_id))

    return IndexResponse(indexed=True, n_chunks=len(chunks))
