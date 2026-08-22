"""
Tests for Agent 2, covering the cases called out in the build reference:
  - dedup across sources
  - cap enforcement
  - unverifiable quote -> UNCERTAIN override
  - one source unreachable, others still succeed
Run with: pytest backend/tests/test_retrieval_screening.py -v
"""

import pytest
from typing import cast
from unittest.mock import AsyncMock, patch

from backend.agents.retrieval_screening import (
    dedupe, prerank_and_cap, screen_candidate, sort_by_verdict,
    retrieve_all_sources, run_retrieval_and_screening,
)
from backend.sources.base import SourceUnavailableError
from backend.graph.state import Candidate, Protocol


PROTOCOL: Protocol = {
    "domain": "test domain",
    "inclusion_criteria": ["Paper applies deep learning to the test domain"],
    "exclusion_criteria": ["Paper is a pure survey"],
    "queries": {"openalex": "q", "semantic_scholar": "q", "arxiv": "q", "europepmc": "q"},
}


def make_candidate(**overrides: object) -> Candidate:
    # **kwargs is inherently untyped, so pyright can't verify it matches
    # Partial[Candidate] structurally -- cast() is the standard idiom here:
    # it tells the type checker "trust this shape," which is legitimate
    # since this is a test factory constructing a known-valid Candidate,
    # not runtime-uncertain data.
    base: dict = {
        "title": "Sample Paper", "doi": "10.1/sample", "abstract": "x" * 80,
        "year": 2023, "source": "openalex", "arxiv_id": None, "pmcid": None,
        "known_oa_pdf_url": None,
    }
    base.update(overrides)
    return cast(Candidate, base)


# ------------------------------------------------------------------
# Dedup
# ------------------------------------------------------------------

def test_dedup_exact_doi_match():
    a = make_candidate(doi="10.1/x", title="Paper A", abstract="short")
    b = make_candidate(doi="10.1/x", title="Paper A (dup)", abstract="a much longer and richer abstract here")
    result = dedupe([a, b])
    assert len(result) == 1
    assert result[0].get("abstract") == b.get("abstract")  # keeps the richer one


def test_dedup_merges_fulltext_identifiers_across_duplicates():
    a = make_candidate(doi="10.1/x", abstract="x" * 100, arxiv_id="1234.5678", known_oa_pdf_url=None)
    b = make_candidate(doi="10.1/x", abstract="x" * 10, arxiv_id=None, known_oa_pdf_url="https://example.com/x.pdf")
    result = dedupe([a, b])
    assert len(result) == 1
    # richer abstract (a) wins as the base record, but b's OA link is merged in
    assert result[0].get("arxiv_id") == "1234.5678"
    assert result[0].get("known_oa_pdf_url") == "https://example.com/x.pdf"


def test_dedup_fuzzy_title_match_no_doi():
    a = make_candidate(doi=None, title="Deep Learning for Widget Detection")
    b = make_candidate(doi=None, title="Deep Learning for Widget Detection ")  # trivial diff
    result = dedupe([a, b])
    assert len(result) == 1


def test_dedup_keeps_genuinely_different_papers():
    a = make_candidate(doi=None, title="Deep Learning for Widget Detection")
    b = make_candidate(doi=None, title="Statistical Methods for Gadget Analysis")
    result = dedupe([a, b])
    assert len(result) == 2


# ------------------------------------------------------------------
# Cap enforcement
# ------------------------------------------------------------------

def test_cap_enforced_regardless_of_raw_candidate_count():
    candidates = [make_candidate(doi=f"10.1/{i}", title=f"Paper {i}", abstract="deep learning " * 10) for i in range(300)]
    capped = prerank_and_cap(candidates, PROTOCOL, cap=150)
    assert len(capped) == 150


def test_cap_orders_by_prerank_score_descending():
    candidates = [make_candidate(doi=f"10.1/{i}", abstract="irrelevant text " * 5) for i in range(5)]
    candidates[2]["abstract"] = "deep learning test domain deep learning test domain " * 5  # strong match
    capped = prerank_and_cap(candidates, PROTOCOL, cap=5)
    assert capped[0] is candidates[2]


def test_empty_candidate_list_returns_empty():
    assert prerank_and_cap([], PROTOCOL) == []


# ------------------------------------------------------------------
# Unverifiable quote -> UNCERTAIN override
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unverifiable_quote_downgrades_to_uncertain():
    candidate = make_candidate(abstract="This paper studies deep learning for the test domain in detail.")
    fake_response = {"verdict": "INCLUDE", "quote": "a quote that does not appear anywhere in the abstract",
                     "reason": "looked relevant"}
    with patch("backend.agents.retrieval_screening.llm_json_call", new=AsyncMock(return_value=fake_response)):
        result = await screen_candidate(candidate, PROTOCOL)
    assert result["verdict"] == "UNCERTAIN"
    assert "could not be verified" in result["reason"]


@pytest.mark.asyncio
async def test_verifiable_quote_keeps_original_verdict():
    abstract = "This paper studies deep learning for the test domain in great detail."
    candidate = make_candidate(abstract=abstract)
    fake_response = {"verdict": "INCLUDE", "quote": "deep learning for the test domain", "reason": "relevant"}
    with patch("backend.agents.retrieval_screening.llm_json_call", new=AsyncMock(return_value=fake_response)):
        result = await screen_candidate(candidate, PROTOCOL)
    assert result["verdict"] == "INCLUDE"


@pytest.mark.asyncio
async def test_quote_verification_is_whitespace_tolerant():
    abstract = "This paper studies\ndeep   learning for the test domain."
    candidate = make_candidate(abstract=abstract)
    fake_response = {"verdict": "INCLUDE", "quote": "deep learning for the test domain", "reason": "relevant"}
    with patch("backend.agents.retrieval_screening.llm_json_call", new=AsyncMock(return_value=fake_response)):
        result = await screen_candidate(candidate, PROTOCOL)
    assert result["verdict"] == "INCLUDE"


@pytest.mark.asyncio
async def test_short_abstract_skips_llm_call_entirely():
    candidate = make_candidate(abstract="too short")
    mock_llm = AsyncMock(return_value={"verdict": "INCLUDE", "quote": "too short", "reason": "x"})
    with patch("backend.agents.retrieval_screening.llm_json_call", new=mock_llm):
        result = await screen_candidate(candidate, PROTOCOL)
    mock_llm.assert_not_called()
    assert result["verdict"] == "UNCERTAIN"


@pytest.mark.asyncio
async def test_budget_exhausted_escalates_to_uncertain_not_crash():
    candidate = make_candidate(abstract="x" * 80)
    with patch("backend.agents.retrieval_screening.llm_json_call",
               new=AsyncMock(return_value={"_budget_exhausted": True})):
        result = await screen_candidate(candidate, PROTOCOL)
    assert result["verdict"] == "UNCERTAIN"
    assert "budget" in result["reason"].lower()


# ------------------------------------------------------------------
# One source unreachable, others succeed
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_source_down_others_still_return_results():
    good_result = [make_candidate(doi="10.1/ok", title="A Working Result")]

    async def fake_openalex(client, query, **kw):
        return good_result

    async def fake_arxiv(client, query, **kw):
        raise SourceUnavailableError("arxiv: simulated outage")

    async def fake_s2(client, query, **kw):
        return []

    async def fake_epmc(client, query, **kw):
        return []

    with patch("backend.agents.retrieval_screening.SOURCE_CLIENTS", {
        "openalex": fake_openalex, "arxiv": fake_arxiv,
        "semantic_scholar": fake_s2, "europepmc": fake_epmc,
    }):
        candidates, unreachable = await retrieve_all_sources(PROTOCOL)

    assert unreachable == ["arxiv"]
    assert len(candidates) == 1
    assert candidates[0].get("title") == "A Working Result"


@pytest.mark.asyncio
async def test_all_sources_down_returns_empty_not_exception():
    async def always_fails(client, query, **kw):
        raise SourceUnavailableError("simulated")

    with patch("backend.agents.retrieval_screening.SOURCE_CLIENTS", {
        name: always_fails for name in ("openalex", "arxiv", "semantic_scholar", "europepmc")
    }):
        candidates, unreachable = await retrieve_all_sources(PROTOCOL)

    assert candidates == []
    assert set(unreachable) == {"openalex", "arxiv", "semantic_scholar", "europepmc"}


# ------------------------------------------------------------------
# Sort order
# ------------------------------------------------------------------

def test_sort_by_verdict_include_then_uncertain_then_exclude():
    candidates = [
        make_candidate(verdict="EXCLUDE", prerank_score=99),
        make_candidate(verdict="INCLUDE", prerank_score=1),
        make_candidate(verdict="UNCERTAIN", prerank_score=50),
    ]
    result = sort_by_verdict(candidates)
    assert [c.get("verdict") for c in result] == ["INCLUDE", "UNCERTAIN", "EXCLUDE"]


def test_exclude_candidates_are_kept_not_dropped():
    candidates = [make_candidate(verdict="EXCLUDE"), make_candidate(verdict="INCLUDE")]
    result = sort_by_verdict(candidates)
    assert len(result) == 2  # EXCLUDE is ranked last, never removed


# ------------------------------------------------------------------
# End-to-end orchestration (fully mocked)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_retrieval_and_screening_end_to_end():
    raw_candidates = [
        make_candidate(doi=f"10.1/{i}", title=f"Paper {i}",
                       abstract="This paper studies deep learning for the test domain in detail. " * 3)
        for i in range(5)
    ]

    async def fake_retrieve(protocol):
        return raw_candidates, []

    async def fake_screen_all(candidates, protocol, concurrency=5):
        for c in candidates:
            c.update({"verdict": "INCLUDE", "quote": "deep learning for the test domain", "reason": "matches"})
        return candidates

    with patch("backend.agents.retrieval_screening.retrieve_all_sources", new=AsyncMock(side_effect=fake_retrieve)), \
         patch("backend.agents.retrieval_screening.screen_all", new=AsyncMock(side_effect=fake_screen_all)):
        result = await run_retrieval_and_screening(PROTOCOL)

    assert len(result) == 5
    assert all(c.get("verdict") == "INCLUDE" for c in result)
    assert all("has_usable_abstract" in c for c in result)