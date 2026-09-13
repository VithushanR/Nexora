"""
Report Copilot router (Part B).

Responsibility:
- POST /research/{thread_id}/copilot/index         index a finished report for RAG chat
- POST /research/{thread_id}/copilot/chat          answer a question, grounded in the
                                                    report ("report" mode) or with live
                                                    tool-calling over report + web ("auto")
- POST /research/{thread_id}/copilot/add_to_evidence   promote a web-sourced answer into
                                                        the report's own retrieval index
- GET  /research/{thread_id}/copilot/history       chat history for the sidebar

Part B's only input is the `report` dict produced by the pipeline (see
backend/report/store.py for the exact contract shape) -- no other field is
assumed to exist. Everything this router imports but does not own (RAG
retrieval, auth, prompt sanitization, report persistence) is either already
built by a teammate or stubbed here with a loud "STUB -- replace with Part
D's real implementation" comment at the top of the file; see those files for
what exactly still needs replacing.
"""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional, Union, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth.deps import get_current_user, require_thread_ownership
from backend.auth.sanitize import sanitize_for_prompt
from backend.llm.client import llm_json_call
from backend.rag.chat import build_index, query, rag_chat
from backend.report.store import get_report

logger = logging.getLogger("nexora.copilot")

router = APIRouter(prefix="/research", tags=["copilot"])

MAX_MESSAGE_CHARS = 2000

ChatMode = Literal["report", "auto"]
AnswerMode = Literal["report", "web"]


# ============================================================
# Request / response models
# ============================================================


class IndexResponse(BaseModel):
    indexed: bool
    n_chunks: int


class ChatRequest(BaseModel):
    message: str
    mode: ChatMode


class SourceEvidenceRow(BaseModel):
    type: Literal["evidence_row"] = "evidence_row"
    paper_title: str


class SourceWeb(BaseModel):
    type: Literal["web"] = "web"
    url: str
    title: str


Source = Union[SourceEvidenceRow, SourceWeb]


class ChatResponse(BaseModel):
    message_id: str
    answer: str
    mode: AnswerMode
    sources: list[Source] = Field(default_factory=list)


class AddToEvidenceRequest(BaseModel):
    message_id: str


class AddToEvidenceResponse(BaseModel):
    added: bool


class HistoryEntry(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    mode: Optional[AnswerMode] = None
    timestamp: str


# ============================================================
# Per-thread chat history store
# ============================================================
# STUB -- replace with a real per-thread DB table (e.g. SQLite). Using an
# in-memory dict keyed by thread_id since there is no DB wiring yet. This
# does not persist across process restarts and is not shared across
# worker processes.

_HISTORY: dict[str, list[HistoryEntry]] = {}

# thread_id -> the exact chunk list last handed to build_index(). Needed
# because rag.chat.build_index() REPLACES a namespace's chunks wholesale
# (it has no incremental-append operation), so appending one new chunk
# (add_to_evidence) requires resending the full set.
_LAST_CHUNKS: dict[str, list[str]] = {}


def _namespace(thread_id: str) -> str:
    return f"report:{thread_id}"


def _append_history(thread_id: str, entry: HistoryEntry) -> None:
    _HISTORY.setdefault(thread_id, []).append(entry)


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
# "auto" mode tool-calling
# ============================================================
# The shared LLM client (backend/llm/client.py) only exposes a plain
# JSON-in-JSON-out call, not a native function-calling API. Tool-calling
# here is therefore a manual two-step loop, matching the JSON-prompting
# pattern already used throughout backend/agents/: (1) ask the model which
# tool(s) apply, (2) execute those tools, (3) ask the model to synthesize
# an answer from what came back.

TOOL_DECISION_SYSTEM_PROMPT = """You are a research copilot deciding which tools to use to answer a user's question.

Two tools are available:
- "search_report": searches the already-completed research report (its evidence table, contradictions and research gaps).
- "search_web": performs a live web search for information the report does not cover.

Use "search_report" when the question is about the analysed papers, their findings, contradictions, or gaps.
Use "search_web" when the question asks about something outside the report -- recent developments, background facts, anything not among the analysed papers.
Use both if genuinely useful for the question.

Respond ONLY with valid JSON, no markdown fences:
{"tools": ["search_report"]}"""

SYNTHESIS_SYSTEM_PROMPT = """You answer the user's question using ONLY the CONTEXT provided below, which was gathered by tools called on their behalf.
Never invent information that is not present in the CONTEXT. If the CONTEXT is insufficient to answer, say so plainly.

Respond ONLY with valid JSON, no markdown fences:
{"answer": "..."}"""

VALID_TOOLS = ("search_report", "search_web")


def _degrade_reason(result: Optional[dict]) -> str:
    if not result:
        return "the model's response could not be parsed"
    if result.get("_budget_exhausted"):
        return "LLM budget exhausted"
    if result.get("_blocked_or_empty"):
        return "the model returned an empty response"
    return "an unknown error"


def _is_degraded(result: Optional[dict]) -> bool:
    return not result or bool(result.get("_budget_exhausted")) or bool(result.get("_blocked_or_empty"))


def _chunk_title(chunk_text: str) -> str:
    """Recovers a display title from a chunk built by chunk_report().
    rag.chat.build_index() only accepts plain strings (no metadata), so the
    title has to be pulled back out of the chunk's own text -- this mirrors
    the "{title}\\n\\n..." format chunk_report() writes for evidence rows.
    Good enough for a citation label; not meant to be exact for
    contradiction/gap chunks, which don't have a single "title" concept.
    """
    first_line = chunk_text.split("\n\n", 1)[0].strip()
    return first_line or "(untitled)"


async def _web_search(search_query: str) -> list[dict]:
    """search_web tool implementation.

    STUB -- no real web search provider (Bing/SerpAPI/etc.) is wired into
    this repo yet. This placeholder returns a single canned result so the
    "auto" mode control flow (tool selection -> tool execution ->
    synthesis -> mode="web" tagging) can be built and tested end-to-end.
    A real implementation MUST keep safe-search explicitly enabled in its
    request parameters (e.g. `safe=active` / `safesearch=strict`) -- do not
    drop that when wiring in a real provider.
    """
    logger.warning("copilot: using stub web search (no provider wired) for query=%r", search_query[:80])
    return [
        {
            "title": f"Stub web result for: {search_query[:60]}",
            "url": "https://example.com/search-stub",
            "snippet": (
                "This is placeholder content from the web-search stub -- no real "
                "search provider is wired into this repo yet."
            ),
        }
    ]


async def _run_report_mode(namespace: str, question: str) -> tuple[str, list[dict]]:
    hits = query(namespace, question, top_k=5)
    sources = [{"type": "evidence_row", "paper_title": _chunk_title(h.get("text", ""))} for h in hits]
    answer = await rag_chat(namespace, question)
    return answer, sources


async def _run_auto_mode(namespace: str, question: str) -> tuple[str, AnswerMode, list[dict]]:
    decision = await llm_json_call(
        TOOL_DECISION_SYSTEM_PROMPT, question, debug_label="copilot.decide_tools",
    )
    if _is_degraded(decision):
        reason = _degrade_reason(decision)
        return f"I couldn't process that question right now ({reason}).", "report", []

    assert decision is not None
    requested = decision.get("tools")
    tools = [t for t in requested if t in VALID_TOOLS] if isinstance(requested, list) else []
    if not tools:
        tools = ["search_report"]  # safe default: always at least check the report

    sources: list[dict] = []
    context_parts: list[str] = []

    if "search_report" in tools:
        for hit in query(namespace, question, top_k=5):
            text = hit.get("text", "")
            sources.append({"type": "evidence_row", "paper_title": _chunk_title(text)})
            context_parts.append(text)

    if "search_web" in tools:
        for hit in await _web_search(question):
            sources.append({"type": "web", "url": hit["url"], "title": hit["title"]})
            context_parts.append(f"{hit['title']}: {hit.get('snippet', '')}")

    mode: AnswerMode = "web" if "search_web" in tools else "report"
    context = "\n\n---\n\n".join(context_parts) if context_parts else "(no context retrieved)"

    synthesis = await llm_json_call(
        SYNTHESIS_SYSTEM_PROMPT,
        f"CONTEXT:\n{context}\n\nQUESTION: {question}",
        debug_label="copilot.synthesize",
    )
    if _is_degraded(synthesis):
        reason = _degrade_reason(synthesis)
        return f"I couldn't process that question right now ({reason}).", mode, sources

    assert synthesis is not None
    answer = (synthesis.get("answer") or "").strip()
    if not answer:
        return "I couldn't process that question right now (no answer returned).", mode, sources

    return answer, mode, sources


# ============================================================
# Endpoints
# ============================================================


@router.post("/{thread_id}/copilot/index", response_model=IndexResponse)
async def index_report(thread_id: str, user_id: str = Depends(get_current_user)) -> IndexResponse:
    require_thread_ownership(user_id, thread_id)

    report = get_report(thread_id)
    _warn_if_incomplete(thread_id, report)

    chunks = chunk_report(report)
    build_index(chunks, namespace=_namespace(thread_id))
    _LAST_CHUNKS[thread_id] = chunks

    return IndexResponse(indexed=True, n_chunks=len(chunks))


@router.post("/{thread_id}/copilot/chat", response_model=ChatResponse)
async def chat(
    thread_id: str, request: ChatRequest, user_id: str = Depends(get_current_user),
) -> ChatResponse:
    require_thread_ownership(user_id, thread_id)

    if len(request.message) > MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"message must be {MAX_MESSAGE_CHARS} characters or fewer",
        )

    sanitized = sanitize_for_prompt(request.message)
    namespace = _namespace(thread_id)

    if request.mode == "report":
        answer, sources = await _run_report_mode(namespace, sanitized)
        mode: AnswerMode = "report"
    else:
        answer, mode, sources = await _run_auto_mode(namespace, sanitized)

    now = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid4())

    _append_history(thread_id, HistoryEntry(
        message_id=str(uuid4()), role="user", content=sanitized, mode=None, timestamp=now,
    ))
    _append_history(thread_id, HistoryEntry(
        message_id=message_id, role="assistant", content=answer, mode=mode, timestamp=now,
    ))

    return ChatResponse(
        message_id=message_id,
        answer=answer,
        mode=mode,
        sources=cast(list[Source], sources),
    )


@router.post("/{thread_id}/copilot/add_to_evidence", response_model=AddToEvidenceResponse)
async def add_to_evidence(
    thread_id: str, request: AddToEvidenceRequest, user_id: str = Depends(get_current_user),
) -> AddToEvidenceResponse:
    require_thread_ownership(user_id, thread_id)

    entries = _HISTORY.get(thread_id, [])
    entry = next(
        (e for e in entries if e.message_id == request.message_id and e.role == "assistant"),
        None,
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
    if entry.mode != "web":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only web-mode answers can be added to evidence",
        )

    existing_chunks = list(_LAST_CHUNKS.get(thread_id, []))
    existing_chunks.append(entry.content)
    build_index(existing_chunks, namespace=_namespace(thread_id))
    _LAST_CHUNKS[thread_id] = existing_chunks

    return AddToEvidenceResponse(added=True)


@router.get("/{thread_id}/copilot/history", response_model=list[HistoryEntry])
async def get_history(thread_id: str, user_id: str = Depends(get_current_user)) -> list[HistoryEntry]:
    require_thread_ownership(user_id, thread_id)
    return _HISTORY.get(thread_id, [])
