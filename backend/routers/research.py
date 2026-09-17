"""JWT-authenticated research-pipeline HTTP endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StrictInt
from langgraph.types import Command

from backend.auth.jwt import get_current_user
from backend.research_threads import (
    create_thread,
    get_thread,
    update_thread_status,
    verify_thread_owner,
)

logger = logging.getLogger("nexora.research_router")

router = APIRouter(prefix="/research", tags=["research"])

THREAD_CONFIG = lambda thread_id: {"configurable": {"thread_id": thread_id}}
_STATUS_DETAILS = {
    "running_agent2": "Research is retrieving and screening papers.",
    "paused_for_selection": "Research is waiting for paper selection.",
    "running_synthesis": "Research is synthesizing the selected papers.",
    "done": "Research is complete.",
    "error": "Research processing failed.",
}


class ResearchStartRequest(BaseModel):
    domain: str


class SelectionRequest(BaseModel):
    selected_indices: list[StrictInt]


class ResearchStartResponse(BaseModel):
    thread_id: str


class ResearchStatusResponse(BaseModel):
    status: Literal[
        "running_agent2",
        "paused_for_selection",
        "running_synthesis",
        "done",
        "error",
    ]
    detail: str


class CandidateResponse(BaseModel):
    """Public projection of a checkpointed Agent 2 candidate."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    doi: str | None = None
    abstract: str | None = None
    year: int | None = None
    source: Literal["openalex", "semantic_scholar", "arxiv", "europepmc"] | None = None
    verdict: Literal["INCLUDE", "EXCLUDE", "UNCERTAIN"] | None = None
    quote: str | None = None
    reason: str | None = None
    prerank_score: float | None = None
    has_usable_abstract: bool | None = None


class CandidatesResponse(BaseModel):
    eligible_candidates: list[CandidateResponse]


class SelectionResponse(BaseModel):
    status: Literal["running_synthesis"]


class ReportResponse(BaseModel):
    report: str


class ResearchStartRateLimiter:
    """Small process-local rolling-window limiter for research starts.

    It intentionally does not attempt distributed enforcement: timestamps are
    lost after restart and are not shared across worker processes.
    """

    def __init__(self, limit: int = 10, window_seconds: float = 3600) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._starts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            starts = self._starts[user_id]
            while starts and now - starts[0] >= self.window_seconds:
                starts.popleft()
            if len(starts) >= self.limit:
                return False
            starts.append(now)
            return True

    def reset(self) -> None:
        """Clear process-local state; used only by isolated tests."""
        self._starts.clear()


_start_rate_limiter = ResearchStartRateLimiter()


@asynccontextmanager
async def graph_context() -> AsyncIterator[Any]:
    """Lazily load graph dependencies after the FastAPI app has started.

    This avoids importing source clients merely to import the HTTP app. Tests
    replace this seam with a deterministic context manager.
    """
    from backend.graph.build_graph import graph_context as production_graph_context

    async with production_graph_context() as app:
        yield app


async def _owned_thread_or_404(thread_id: str, user_id: str):
    thread = await get_thread(thread_id)
    if thread is None or not await verify_thread_owner(thread_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research thread not found.")
    return thread


def _has_selection_interrupt(snapshot: Any) -> bool:
    return any(
        isinstance(getattr(interrupt, "value", None), dict)
        and interrupt.value.get("kind") == "paper_selection"
        for interrupt in getattr(snapshot, "interrupts", ())
    )


def _checkpointed_candidates(snapshot: Any) -> list[dict[str, Any]]:
    if not _has_selection_interrupt(snapshot):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Research is not waiting for paper selection.",
        )
    values = getattr(snapshot, "values", {})
    candidates = values.get("candidates") if isinstance(values, dict) else None
    if not isinstance(candidates, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Research selection checkpoint is unavailable.",
        )
    return candidates


def _validate_selected_indices(selected_indices: list[int], candidate_count: int) -> None:
    """Mirror human_selection_node validation before a background resume."""
    if not selected_indices:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="At least one candidate must be selected.")

    seen: set[int] = set()
    for index in selected_indices:
        if isinstance(index, bool) or not isinstance(index, int):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Each selected index must be an integer.")
        if index < 0 or index >= candidate_count:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Selected index is outside the candidate range.")
        if index in seen:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Selected indices must be unique.")
        seen.add(index)


async def _mark_error(thread_id: str) -> None:
    try:
        await update_thread_status(thread_id, "error")
    except Exception:
        logger.exception("Could not mark research thread %s as errored.", thread_id)


async def _resume_research(thread_id: str, selected_indices: list[int]) -> None:
    """BackgroundTask body for the long Agent 3/4/report phase."""
    config = THREAD_CONFIG(thread_id)
    try:
        async with graph_context() as app:
            await app.ainvoke(Command(resume={"selected_indices": selected_indices}), config=config)
            snapshot = await app.aget_state(config)
        values = getattr(snapshot, "values", {})
        report = values.get("report") if isinstance(values, dict) else None
        if not isinstance(report, str):
            raise RuntimeError("Graph completed without a Markdown report.")
        await update_thread_status(thread_id, "done")
    except Exception:
        logger.exception("Research synthesis failed for thread %s.", thread_id)
        await _mark_error(thread_id)


@router.post("", response_model=ResearchStartResponse, status_code=status.HTTP_201_CREATED)
async def start_research(
    request: ResearchStartRequest,
    user_id: str = Depends(get_current_user),
) -> ResearchStartResponse:
    if not await _start_rate_limiter.allow(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Research start limit exceeded. Try again later.",
        )

    thread_id = await create_thread(user_id, request.domain)
    config = THREAD_CONFIG(thread_id)
    try:
        async with graph_context() as app:
            await app.ainvoke({"domain": request.domain}, config=config)
            snapshot = await app.aget_state(config)
        if not _has_selection_interrupt(snapshot):
            raise RuntimeError("Graph did not reach the paper-selection checkpoint.")
        await update_thread_status(thread_id, "paused_for_selection")
    except Exception:
        logger.exception("Initial research graph run failed for thread %s.", thread_id)
        await _mark_error(thread_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Research processing failed.",
        ) from None

    return ResearchStartResponse(thread_id=thread_id)


@router.get("/{thread_id}/status", response_model=ResearchStatusResponse)
async def research_status(thread_id: str, user_id: str = Depends(get_current_user)) -> ResearchStatusResponse:
    thread = await _owned_thread_or_404(thread_id, user_id)
    return ResearchStatusResponse(
        status=thread.status,
        detail=_STATUS_DETAILS[thread.status],
    )


@router.get("/{thread_id}/candidates", response_model=CandidatesResponse)
async def research_candidates(thread_id: str, user_id: str = Depends(get_current_user)) -> CandidatesResponse:
    thread = await _owned_thread_or_404(thread_id, user_id)
    if thread.status != "paused_for_selection":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Research is not waiting for paper selection.",
        )

    async with graph_context() as app:
        snapshot = await app.aget_state(THREAD_CONFIG(thread_id))
    candidates = _checkpointed_candidates(snapshot)
    return CandidatesResponse(
        eligible_candidates=[CandidateResponse.model_validate(candidate) for candidate in candidates]
    )


@router.post("/{thread_id}/select", response_model=SelectionResponse)
async def select_papers(
    thread_id: str,
    request: SelectionRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
) -> SelectionResponse:
    thread = await _owned_thread_or_404(thread_id, user_id)
    if thread.status != "paused_for_selection":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Research is not waiting for paper selection.",
        )

    async with graph_context() as app:
        snapshot = await app.aget_state(THREAD_CONFIG(thread_id))
    candidates = _checkpointed_candidates(snapshot)
    _validate_selected_indices(request.selected_indices, len(candidates))

    await update_thread_status(thread_id, "running_synthesis")
    background_tasks.add_task(_resume_research, thread_id, list(request.selected_indices))
    return SelectionResponse(status="running_synthesis")


@router.get("/{thread_id}/report", response_model=ReportResponse)
async def research_report(thread_id: str, user_id: str = Depends(get_current_user)) -> ReportResponse:
    thread = await _owned_thread_or_404(thread_id, user_id)
    if thread.status != "done":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research report not found.")

    async with graph_context() as app:
        snapshot = await app.aget_state(THREAD_CONFIG(thread_id))
    values = getattr(snapshot, "values", {})
    report = values.get("report") if isinstance(values, dict) else None
    if not isinstance(report, str):
        logger.error("Thread %s is marked done without a Markdown report.", thread_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Research report is unavailable.",
        )
    return ReportResponse(report=report)
