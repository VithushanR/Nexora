"""
Agent 2 -- Retrieval & Screening

Node signature matches the LangGraph pattern used across the pipeline:

    async def retrieval_screening_node(state: ResearchState) -> dict:
        candidates = await run_retrieval_and_screening(state["protocol"])
        return {"candidates": candidates}

Pipeline (per the Agent Build Reference):
  1. Query execution -- one client per source, run concurrently, each
     wrapped in retry/backoff + rate pacing (see sources/base.py). A dead
     source is logged and skipped; it never fails the whole node.
  2. Deduplication -- deterministic, no LLM call. Exact DOI match, then
     fuzzy title match. Merges full-text identifiers (arxiv_id, pmcid,
     known_oa_pdf_url) across duplicate records so a paper found via two
     sources keeps whichever source found the better lead.
  3. Pre-rank -- BM25 against the inclusion criteria. No LLM call. Used
     for ordering only, never decides inclusion.
  4. Cap -- top N (SCREENING_CANDIDATE_CAP) by pre-rank score reach the
     LLM; everything below the cap is dropped before any LLM cost.
  5. LLM screening -- one call per capped candidate, via backend.llm.client.
     Every verdict must carry a quote that is verified as a real substring
     of the abstract (whitespace-normalized); an unverifiable quote is
     downgraded to UNCERTAIN rather than trusted.
  6. Sort -- INCLUDE, then UNCERTAIN, then EXCLUDE (EXCLUDE is kept, never
     silently dropped, in case a human wants to review it).
"""

import os
import re
import asyncio
import logging
from difflib import SequenceMatcher

import httpx
from rank_bm25 import BM25Okapi

from backend.sources import openalex, semantic_scholar, arxiv, europepmc
from backend.sources.base import SourceUnavailableError
from backend.llm.client import llm_json_call
from backend.graph.state import ResearchState, Candidate, Protocol

logger = logging.getLogger("nexora.agent2")

SCREENING_CANDIDATE_CAP = int(os.getenv("SCREENING_CANDIDATE_CAP", "150"))
MIN_ABSTRACT_CHARS = 50  # below this, skip the LLM call -- see screen_candidate

SCREENING_SYSTEM_PROMPT = """You are a literature screening assistant for a systematic research review.
Decide INCLUDE, EXCLUDE, or UNCERTAIN based only on the abstract given.
You MUST support your verdict with a quote copied EXACTLY from the abstract.
If ambiguous or the abstract is too short/thin, choose UNCERTAIN rather than guessing.
Never fabricate detail.

Respond ONLY with valid JSON, no markdown fences:
{"verdict": "INCLUDE|EXCLUDE|UNCERTAIN", "quote": "exact substring from abstract", "reason": "one sentence"}"""


# ------------------------------------------------------------------
# Step 1: concurrent retrieval across sources
# ------------------------------------------------------------------

SOURCE_CLIENTS = {
    "openalex": openalex.search,
    "semantic_scholar": semantic_scholar.search,
    "arxiv": arxiv.search,
    "europepmc": europepmc.search,
}


async def _run_source(client: httpx.AsyncClient, name: str, query: str) -> tuple[str, list[Candidate], str | None]:
    """Runs one source's search, returning (name, results, error_or_None).
    Never raises -- a source failure is captured, not propagated, so
    asyncio.gather can run all sources concurrently without one failure
    cancelling the others."""
    fn = SOURCE_CLIENTS[name]
    try:
        results = await fn(client, query)
        logger.info("%s: %d results", name, len(results))
        return name, results, None
    except SourceUnavailableError as e:
        logger.warning("%s unreachable: %s", name, e)
        return name, [], str(e)
    except Exception as e:
        logger.warning("%s failed unexpectedly: %s", name, e)
        return name, [], str(e)


async def retrieve_all_sources(protocol: Protocol) -> tuple[list[Candidate], list[str]]:
    """Runs every source concurrently. Returns (all_candidates, unreachable_source_names)."""
    queries = protocol["queries"]
    async with httpx.AsyncClient() as client:
        tasks = [
            _run_source(client, name, queries[name])
            for name in SOURCE_CLIENTS
            if name in queries
        ]
        results = await asyncio.gather(*tasks)

    all_candidates: list[Candidate] = []
    unreachable: list[str] = []
    for name, candidates, error in results:
        all_candidates.extend(candidates)
        if error:
            unreachable.append(name)
    return all_candidates, unreachable


# ------------------------------------------------------------------
# Step 2: deduplication (deterministic, no LLM)
# ------------------------------------------------------------------

def dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Exact DOI match, then fuzzy title match (ratio > 0.9) for records
    with no DOI. When two records merge, keep the richer abstract but
    carry forward any full-text identifiers (arxiv_id, pmcid,
    known_oa_pdf_url) either record had, so a paper found via both arXiv
    and Europe PMC keeps both leads for Agent 3's fetch cascade."""
    seen_dois: dict[str, Candidate] = {}
    no_doi: list[Candidate] = []

    for c in candidates:
        doi = (c.get("doi") or "").lower().strip()
        if not doi:
            no_doi.append(c)
            continue
        if doi not in seen_dois:
            seen_dois[doi] = c
            continue

        existing = seen_dois[doi]
        richer = c if len(c.get("abstract") or "") > len(existing.get("abstract") or "") else existing
        other = existing if richer is c else c
        for key in ("arxiv_id", "pmcid", "known_oa_pdf_url"):
            if not richer.get(key) and other.get(key):
                richer[key] = other.get(key)
        seen_dois[doi] = richer

    deduped = list(seen_dois.values())
    for c in no_doi:
        title = (c.get("title") or "").lower().strip()
        is_dup = any(
            title and SequenceMatcher(None, title, (e.get("title") or "").lower().strip()).ratio() > 0.9
            for e in deduped
        )
        if not is_dup:
            deduped.append(c)
    return deduped


# ------------------------------------------------------------------
# Step 3-4: BM25 pre-rank + cap (deterministic, no LLM)
# ------------------------------------------------------------------

def prerank_and_cap(candidates: list[Candidate], protocol: Protocol, cap: int = SCREENING_CANDIDATE_CAP) -> list[Candidate]:
    if not candidates:
        return []

    criteria_text = " ".join(protocol["inclusion_criteria"])
    corpus = [((c.get("title") or "") + " " + (c.get("abstract") or "")).lower().split() for c in candidates]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(criteria_text.lower().split())

    for c, s in zip(candidates, scores):
        c["prerank_score"] = float(s)

    ranked = sorted(candidates, key=lambda c: c.get("prerank_score", 0.0), reverse=True)
    return ranked[:cap]


# ------------------------------------------------------------------
# Step 5: LLM screening with quote verification
# ------------------------------------------------------------------

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


async def screen_candidate(candidate: Candidate, protocol: Protocol) -> dict:
    abstract = candidate.get("abstract") or ""

    if len(abstract.strip()) < MIN_ABSTRACT_CHARS:
        return {"verdict": "UNCERTAIN", "quote": "", "reason": "Abstract missing or too short to screen reliably."}

    user_prompt = f"""INCLUSION CRITERIA:
{chr(10).join('- ' + c for c in protocol['inclusion_criteria'])}

EXCLUSION CRITERIA:
{chr(10).join('- ' + c for c in protocol['exclusion_criteria'])}

PAPER TITLE:
{candidate.get('title')}

PAPER ABSTRACT:
{abstract}"""

    result = await llm_json_call(
        SCREENING_SYSTEM_PROMPT, user_prompt,
        debug_label=f"screen: {(candidate.get('title') or '')[:40]}",
    )

    if result is None:
        return {"verdict": "UNCERTAIN", "quote": "", "reason": "Could not parse model output as valid JSON."}
    if result.get("_budget_exhausted"):
        return {"verdict": "UNCERTAIN", "quote": "", "reason": "LLM budget/quota exhausted -- escalated to UNCERTAIN."}
    if result.get("_blocked_or_empty"):
        return {"verdict": "UNCERTAIN", "quote": "",
                "reason": f"Model returned empty response (finish_reason={result.get('finish_reason')})."}

    if _normalize(result.get("quote", "")) not in _normalize(abstract):
        result["verdict"] = "UNCERTAIN"
        result["reason"] = (result.get("reason") or "") + " [quote could not be verified against abstract]"

    return {"verdict": result["verdict"], "quote": result.get("quote", ""), "reason": result.get("reason", "")}


async def screen_all(candidates: list[Candidate], protocol: Protocol, concurrency: int = 5) -> list[Candidate]:
    """Screens the capped candidate list. Bounded concurrency (not full
    fan-out) so screening 150 candidates doesn't slam the Gemini rate
    limit -- adjust `concurrency` against your account's actual per-minute
    quota."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _screen_one(c: Candidate) -> Candidate:
        async with semaphore:
            verdict = await screen_candidate(c, protocol)
            c.update(verdict)
            return c

    return list(await asyncio.gather(*(_screen_one(c) for c in candidates)))


# ------------------------------------------------------------------
# Step 6: sort
# ------------------------------------------------------------------

_VERDICT_ORDER = {"INCLUDE": 0, "UNCERTAIN": 1, "EXCLUDE": 2}


def sort_by_verdict(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda c: (_VERDICT_ORDER.get(c.get("verdict", ""), 3), -c.get("prerank_score", 0.0)),
    )


# ------------------------------------------------------------------
# Orchestration + LangGraph node
# ------------------------------------------------------------------

async def run_retrieval_and_screening(protocol: Protocol) -> list[Candidate]:
    raw, unreachable = await retrieve_all_sources(protocol)
    if unreachable:
        logger.warning("Sources unreachable this run: %s", unreachable)

    deduped = dedupe(raw)
    logger.info("Deduped: %d -> %d", len(raw), len(deduped))

    capped = prerank_and_cap(deduped, protocol)
    logger.info("Capped to top %d of %d for LLM screening", len(capped), len(deduped))

    screened = await screen_all(capped, protocol)

    for c in screened:
        c["has_usable_abstract"] = len((c.get("abstract") or "").strip()) >= MIN_ABSTRACT_CHARS

    return sort_by_verdict(screened)


async def retrieval_screening_node(state: ResearchState) -> dict:
    """LangGraph node. Writes only `candidates`, per the state-ownership
    rule -- Agent 2 must not touch protocol, selected_papers, or anything
    downstream."""
    protocol = state.get("protocol")
    if protocol is None:
        # A real guard, not just a type-checker workaround: this means
        # Agent 1 hasn't run yet or didn't write `protocol` -- fail with a
        # clear message here rather than letting a confusing AttributeError
        # surface deep inside retrieve_all_sources().
        raise ValueError(
            "retrieval_screening_node requires state['protocol'] to already "
            "be set -- Agent 1 (protocol_planning_node) must run before Agent 2."
        )
    candidates = await run_retrieval_and_screening(protocol)
    return {"candidates": candidates}