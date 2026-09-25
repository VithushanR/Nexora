"""JWT-authenticated research-pipeline HTTP endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from langgraph.types import Command

from backend.auth.jwt import get_current_user
from backend.auth.users import get_user_tier
# Kept importable as research.ResearchStartRateLimiter for backward
# compatibility with existing tests -- see backend/rate_limit.py.
from backend.rate_limit import RollingWindowRateLimiter as ResearchStartRateLimiter
from backend.research_threads import (
    MonthlyResearchQuotaExceeded,
    create_thread_with_monthly_quota,
    get_thread,
    update_thread_status,
    verify_thread_owner,
)
from backend.safety.nvidia_client import (
    NvidiaSafetyClientError,
    classify_research_topic,
)
from backend.safety.policy import (
    SafetyDecision,
    SafetyPolicyInputError,
    apply_safety_policy,
)
from backend.tiers import TierName, get_tier_config

logger = logging.getLogger("nexora.research_router")

router = APIRouter(prefix="/research", tags=["research"])

THREAD_CONFIG = lambda thread_id: {"configurable": {"thread_id": thread_id}}
_STATUS_DETAILS = {
    "running_agent2": "Research is planning the protocol and screening papers.",
    "paused_for_selection": "Research is waiting for paper selection.",
    "running_synthesis": "Research is synthesizing the selected papers.",
    "done": "Research is complete.",
    "error": "Research processing failed.",
}


class ResearchStartRequest(BaseModel):
    domain: str = Field(min_length=1, max_length=500)

    @field_validator("domain")
    @classmethod
    def reject_blank_domain(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Research topic must not be blank.")
        return value


class SelectionRequest(BaseModel):
    selected_indices: list[StrictInt]


class ResearchStartResponse(BaseModel):
    thread_id: str


class SafetyErrorDetail(BaseModel):
    code: Literal["SAFETY_UNSAFE", "SAFETY_NEEDS_CONTEXT", "SAFETY_UNAVAILABLE"]
    message: str


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
    paper_url: str | None = None
    prerank_score: float | None = None
    relevance_percent: float | None = None
    has_usable_abstract: bool | None = None


class CandidatesResponse(BaseModel):
    eligible_candidates: list[CandidateResponse]


class SelectionResponse(BaseModel):
    status: Literal["running_synthesis"]


class ReportResponse(BaseModel):
    report: str


_start_rate_limiter = ResearchStartRateLimiter()


def _safety_http_error(
    status_code: int,
    code: Literal["SAFETY_UNSAFE", "SAFETY_NEEDS_CONTEXT", "SAFETY_UNAVAILABLE"],
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=SafetyErrorDetail(code=code, message=message).model_dump(),
    )


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one candidate must be selected.")

    seen: set[int] = set()
    for index in selected_indices:
        if isinstance(index, bool) or not isinstance(index, int):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Each selected index must be an integer.")
        if index < 0 or index >= candidate_count:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected index is outside the candidate range.")
        if index in seen:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected indices must be unique.")
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


async def _start_initial_research(
    thread_id: str,
    user_id: str,
    tier: TierName,
    domain: str,
) -> None:
    """BackgroundTask body for the Agent 1/2 phase through selection pause."""
    config = THREAD_CONFIG(thread_id)
    try:
        async with graph_context() as app:
            await app.ainvoke(
                {
                    "user_id": user_id,
                    "tier": tier,
                    "domain": domain,
                },
                config=config,
            )
            snapshot = await app.aget_state(config)
        if not _has_selection_interrupt(snapshot):
            raise RuntimeError("Graph did not reach the paper-selection checkpoint.")
        await update_thread_status(thread_id, "paused_for_selection")
    except Exception:
        logger.exception("Initial research graph run failed for thread %s.", thread_id)
        await _mark_error(thread_id)


@router.post("", response_model=ResearchStartResponse, status_code=status.HTTP_201_CREATED)
async def start_research(
    request: ResearchStartRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
) -> ResearchStartResponse:
    if not await _start_rate_limiter.allow(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Research start limit exceeded. Try again later.",
        )

    # The hosted safety gateway must pass before any thread metadata or graph
    # checkpoint can be created. Agent 1 retains its own defense-in-depth check.
    try:
        classification = await classify_research_topic(request.domain)
        safety_result = apply_safety_policy(request.domain, classification)
    except (NvidiaSafetyClientError, SafetyPolicyInputError):
        raise _safety_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SAFETY_UNAVAILABLE",
            "The safety check is temporarily unavailable. Please try again later.",
        ) from None

    if safety_result.decision is SafetyDecision.UNSAFE:
        raise _safety_http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "SAFETY_UNSAFE",
            safety_result.message or "This request cannot be processed as a research topic.",
        )
    if safety_result.decision is SafetyDecision.UNCERTAIN:
        raise _safety_http_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "SAFETY_NEEDS_CONTEXT",
            safety_result.message
            or "Please provide clearer academic, prevention, policy, or research context.",
        )
    if safety_result.decision is not SafetyDecision.SAFE:
        raise _safety_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SAFETY_UNAVAILABLE",
            "The safety check is temporarily unavailable. Please try again later.",
        )

    tier = await get_user_tier(user_id)
    monthly_limit = get_tier_config(tier).monthly_research_runs
    try:
        thread_id = await create_thread_with_monthly_quota(
            user_id,
            request.domain,
            monthly_limit,
        )
    except MonthlyResearchQuotaExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RESEARCH_MONTHLY_QUOTA_EXCEEDED",
                "message": "Your monthly research-run limit has been reached.",
            },
        ) from None
    background_tasks.add_task(
        _start_initial_research,
        thread_id,
        user_id,
        tier,
        request.domain,
    )
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


@router.get("/{thread_id}/report/pdf")
async def research_report_pdf(thread_id: str, user_id: str = Depends(get_current_user)) -> Response:
    """Same report as GET /report, rendered as a downloadable PDF."""
    from backend.agents.report_assembly import render_pdf

    report_response = await research_report(thread_id, user_id)
    pdf_bytes = render_pdf(report_response.report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="nexora-report-{thread_id}.pdf"'},
    )
