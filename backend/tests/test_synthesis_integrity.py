"""
Tests for Agent 3, covering the edge cases called out in the build reference:
  - no full text -> abstract-derived summaries, visibly tagged
  - no plausible contradiction pairs -> empty list reported as a finding
  - a shortlisted pair the LLM declines -> discarded, not forced through
  - a retracted paper -> flagged in its row, never dropped
  - Crossref down -> "unknown", never assumed clean
  - LLM budget exhausted -> reported as an error, not as "none found"
  - a paper that blows up mid-processing -> row survives, flagged

Run with: pytest backend/tests/test_synthesis_integrity.py -v
"""

import numpy as np
import pytest
from typing import cast
from unittest.mock import AsyncMock, patch

from backend.agents.synthesis_integrity import (
    split_sections, is_system_note, comparable_row_indices,
    shortlist_contradiction_pairs, confirm_contradiction, detect_contradictions,
    build_evidence_row, build_evidence_table, synthesis_integrity_node,
)
from backend.sources.crossref import check_retraction
from backend.graph.state import Candidate

AGENT = "backend.agents.synthesis_integrity"


def make_candidate(**overrides: object) -> Candidate:
    # **kwargs is inherently untyped, so pyright can't verify it matches
    # Partial[Candidate] structurally -- cast() is the standard idiom here.
    base: dict = {
        "title": "Deep Learning for Crop Disease Detection",
        "doi": "10.1/sample", "abstract": "x" * 200, "year": 2023,
        "source": "openalex", "arxiv_id": None, "pmcid": None,
        "known_oa_pdf_url": None,
    }
    base.update(overrides)
    return cast(Candidate, base)


def make_row(**overrides) -> dict:
    base = {
        "title": "Paper", "doi": "10.1/x", "year": 2023, "source": "openalex",
        "full_text_available": True, "full_text_strategy": "arxiv",
        "summary_source": "full_text (arxiv)",
        "abstract_summary": "An abstract summary.",
        "methodology_summary": "A CNN trained on PlantVillage.",
        "results_summary": "Reports 97% accuracy on PlantVillage.",
        "retracted": False, "retraction_status": "clean", "retraction_note": "checked",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# Section splitting (deterministic -- no mocks needed)
# ------------------------------------------------------------------

def test_split_sections_finds_numbered_headings():
    text = "\n".join([
        "Title and authors", "Abstract text here",
        "3. Methodology", "We trained a ResNet-50 on 10,000 images.",
        "4. Results", "Accuracy reached 97.2% on the held-out split.",
        "5. Discussion", "A limitation is the single-region dataset.",
    ])
    sections = split_sections(text)
    assert "ResNet-50" in sections["methodology"]
    assert "97.2%" in sections["results"]
    assert "single-region" in sections["discussion"]


def test_split_sections_ignores_keyword_inside_prose():
    """'our method' in a sentence is not a heading -- matching it would
    slice the section from the wrong offset."""
    text = "\n".join([
        "In this paper we describe our method for detecting disease early.",
        "That sentence is prose, not a heading, and should not be matched.",
    ])
    assert split_sections(text)["methodology"] == ""


def test_split_sections_on_empty_text():
    assert split_sections(None) == {}
    assert split_sections("") == {}


# ------------------------------------------------------------------
# Abstract fallback is tagged, not silently equivalent
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_full_text_produces_tagged_abstract_fallback():
    paper = make_candidate()

    with patch(f"{AGENT}.get_full_text", new=AsyncMock(return_value=(None, None))), \
         patch(f"{AGENT}.summarize_section", new=AsyncMock(return_value="A summary.")), \
         patch(f"{AGENT}.check_retraction", new=AsyncMock(return_value={
             "retracted": False, "status": "clean", "note": "checked"})):
        row = await build_evidence_row(AsyncMock(), paper)

    assert row["full_text_available"] is False
    assert row["summary_source"] == "abstract_fallback"
    assert row["full_text_strategy"] == "(none)"
    # The results summary must be an honest system note, not a summary
    # invented from the abstract.
    assert is_system_note(row["results_summary"])
    assert "Full text unavailable" in row["results_summary"]


@pytest.mark.asyncio
async def test_full_text_row_is_labelled_with_its_strategy():
    paper = make_candidate(arxiv_id="2301.00001")
    full_text = "3. Methodology\nA ResNet.\n4. Results\n97% accuracy.\n" + "x" * 600

    with patch(f"{AGENT}.get_full_text", new=AsyncMock(return_value=(full_text, "arxiv"))), \
         patch(f"{AGENT}.summarize_section", new=AsyncMock(return_value="A summary.")), \
         patch(f"{AGENT}.check_retraction", new=AsyncMock(return_value={
             "retracted": False, "status": "clean", "note": "checked"})):
        row = await build_evidence_row(AsyncMock(), paper)

    assert row["full_text_available"] is True
    assert row["summary_source"] == "full_text (arxiv)"
    assert not is_system_note(row["results_summary"])


# ------------------------------------------------------------------
# Integrity: retraction flags
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retracted_paper_is_flagged_and_kept():
    paper = make_candidate(title="A Retracted Study")

    with patch(f"{AGENT}.get_full_text", new=AsyncMock(return_value=(None, None))), \
         patch(f"{AGENT}.summarize_section", new=AsyncMock(return_value="A summary.")), \
         patch(f"{AGENT}.check_retraction", new=AsyncMock(return_value={
             "retracted": True, "status": "retracted", "note": "Crossref records a retraction."})):
        row = await build_evidence_row(AsyncMock(), paper)

    # The user chose this paper -- it stays in the table, visibly flagged.
    assert row["title"] == "A Retracted Study"
    assert row["retracted"] is True
    assert row["retraction_status"] == "retracted"


@pytest.mark.asyncio
async def test_crossref_failure_reports_unknown_not_clean():
    """The critical one: a dead Crossref must never launder into 'not retracted'."""
    from backend.sources.base import SourceUnavailableError

    with patch("backend.sources.crossref._fetch_work",
               new=AsyncMock(side_effect=SourceUnavailableError("crossref: timeout"))):
        status = await check_retraction(AsyncMock(), "10.1/x")

    assert status["retracted"] is None
    assert status["status"] == "unknown"
    assert status["retracted"] is not False


@pytest.mark.asyncio
async def test_crossref_no_record_reports_unknown():
    """A 404 means Crossref doesn't index the work -- that is not evidence
    of being clean."""
    with patch("backend.sources.crossref._fetch_work", new=AsyncMock(return_value=None)):
        status = await check_retraction(AsyncMock(), "10.1/not-indexed")
    assert status["status"] == "unknown"
    assert status["retracted"] is None


@pytest.mark.asyncio
async def test_missing_doi_reports_unknown():
    status = await check_retraction(AsyncMock(), None)
    assert status["status"] == "unknown"
    assert status["retracted"] is None


@pytest.mark.asyncio
async def test_crossref_clean_result():
    with patch("backend.sources.crossref._fetch_work",
               new=AsyncMock(return_value={"title": ["A Fine Paper"], "update-to": []})):
        status = await check_retraction(AsyncMock(), "10.1/x")
    assert status["retracted"] is False
    assert status["status"] == "clean"


@pytest.mark.asyncio
async def test_retraction_detected_via_updated_by():
    """Regression guard for the direction bug: on the ORIGINAL paper the
    retraction lives in `updated-by`, not `update-to`. Shape taken from the
    live Crossref record for the Wakefield 1998 Lancet paper, which checking
    only `update-to` reported as clean."""
    message = {
        "title": ["RETRACTED: Ileal-lymphoid-nodular hyperplasia, non-specific colitis"],
        "update-to": [],
        "updated-by": [
            {"type": "correction", "label": "Correction", "source": "retraction-watch"},
            {"type": "retraction", "label": "Retraction", "source": "retraction-watch"},
        ],
    }
    with patch("backend.sources.crossref._fetch_work", new=AsyncMock(return_value=message)):
        status = await check_retraction(AsyncMock(), "10.1016/S0140-6736(97)11096-0")

    assert status["retracted"] is True
    assert status["status"] == "retracted"


@pytest.mark.asyncio
async def test_retraction_detected_via_update_to():
    message = {"title": ["A Paper"], "update-to": [{"type": "retraction"}], "updated-by": []}
    with patch("backend.sources.crossref._fetch_work", new=AsyncMock(return_value=message)):
        status = await check_retraction(AsyncMock(), "10.1/x")
    assert status["retracted"] is True


@pytest.mark.asyncio
async def test_retraction_detected_via_title_prefix_alone():
    """Catches records where the relation hasn't propagated yet."""
    message = {"title": ["RETRACTED: Something Went Wrong"], "update-to": [], "updated-by": []}
    with patch("backend.sources.crossref._fetch_work", new=AsyncMock(return_value=message)):
        status = await check_retraction(AsyncMock(), "10.1/x")
    assert status["retracted"] is True


@pytest.mark.asyncio
async def test_correction_alone_is_not_a_retraction():
    """A correction is a real integrity signal but not a retraction --
    flagging it as one would overstate the finding."""
    message = {"title": ["A Paper"], "update-to": [],
               "updated-by": [{"type": "correction"}]}
    with patch("backend.sources.crossref._fetch_work", new=AsyncMock(return_value=message)):
        status = await check_retraction(AsyncMock(), "10.1/x")
    assert status["retracted"] is False


@pytest.mark.asyncio
async def test_arxiv_preprint_skips_crossref_entirely():
    """arXiv DOIs are registered with DataCite, so a synthesised
    10.48550/... lookup only ever 404s. Say why instead of pretending."""
    from backend.agents.synthesis_integrity import integrity_check

    paper = make_candidate(doi=None, arxiv_id="1706.03762")
    with patch(f"{AGENT}.check_retraction", new=AsyncMock()) as mock_check:
        status = await integrity_check(AsyncMock(), paper)

    mock_check.assert_not_awaited()
    assert status["status"] == "unknown"
    assert "arXiv" in status["note"]


# ------------------------------------------------------------------
# Contradiction shortlisting (embeddings, no LLM)
# ------------------------------------------------------------------

def test_comparable_rows_exclude_system_notes():
    rows = [
        make_row(results_summary="Reports 97% accuracy."),
        make_row(results_summary="(Full text unavailable -- results not extractable.)"),
        make_row(results_summary="Reports 62% accuracy on the same benchmark."),
    ]
    assert comparable_row_indices(rows) == [0, 2]


@pytest.mark.asyncio
async def test_shortlist_only_returns_pairs_above_threshold():
    rows = [make_row(title="A"), make_row(title="B"), make_row(title="C")]

    # A and B nearly identical; C orthogonal to both.
    vectors = np.array([[1.0, 0.0], [0.99, 0.14], [0.0, 1.0]], dtype=np.float32)
    with patch(f"{AGENT}.embed", new=AsyncMock(return_value=vectors)):
        pairs = await shortlist_contradiction_pairs(rows, threshold=0.55)

    assert [(i, j) for i, j, _ in pairs] == [(0, 1)]


@pytest.mark.asyncio
async def test_shortlist_respects_max_pairs_cap():
    rows = [make_row(title=str(n)) for n in range(6)]
    vectors = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (6, 1))  # all identical

    with patch(f"{AGENT}.embed", new=AsyncMock(return_value=vectors)):
        pairs = await shortlist_contradiction_pairs(rows, threshold=0.5, max_pairs=3)

    assert len(pairs) == 3


@pytest.mark.asyncio
async def test_shortlist_needs_two_comparable_rows():
    rows = [
        make_row(results_summary="Real content here."),
        make_row(results_summary="(Full text unavailable.)"),
    ]
    assert await shortlist_contradiction_pairs(rows) == []


# ------------------------------------------------------------------
# Contradiction confirmation
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_declining_a_pair_discards_it():
    """Topical similarity alone is not a contradiction."""
    with patch(f"{AGENT}.llm_json_call", new=AsyncMock(return_value={
            "is_contradiction": False, "description": "Different datasets, no conflict.",
            "paper_a_claim": "", "paper_b_claim": ""})):
        result = await confirm_contradiction(make_row(title="A"), make_row(title="B"), 0.81)

    assert result is None


@pytest.mark.asyncio
async def test_confirmed_pair_becomes_a_record():
    with patch(f"{AGENT}.llm_json_call", new=AsyncMock(return_value={
            "is_contradiction": True, "description": "Opposite accuracy rankings.",
            "paper_a_claim": "CNN beats ViT", "paper_b_claim": "ViT beats CNN"})):
        result = await confirm_contradiction(make_row(title="A"), make_row(title="B"), 0.81)

    assert result is not None
    assert result["paper_a_title"] == "A"
    assert result["paper_b_title"] == "B"
    assert result["shortlist_similarity"] == 0.81


@pytest.mark.asyncio
async def test_unparseable_llm_output_discards_the_pair():
    with patch(f"{AGENT}.llm_json_call", new=AsyncMock(return_value=None)):
        assert await confirm_contradiction(make_row(), make_row(), 0.7) is None


# ------------------------------------------------------------------
# detect_contradictions: empty vs. broken
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fewer_than_two_papers_is_not_an_error():
    contradictions, status = await detect_contradictions([make_row()])
    assert contradictions == []
    assert status["code"] == "too_few_papers"
    assert status["is_error"] is False


@pytest.mark.asyncio
async def test_no_shortlisted_pairs_is_a_finding_not_an_error():
    rows = [make_row(title="A"), make_row(title="B")]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    with patch(f"{AGENT}.embed", new=AsyncMock(return_value=vectors)):
        contradictions, status = await detect_contradictions(rows)

    assert contradictions == []
    assert status["code"] == "none_shortlisted"
    assert status["is_error"] is False


@pytest.mark.asyncio
async def test_all_pairs_rejected_is_a_finding_not_an_error():
    rows = [make_row(title="A"), make_row(title="B")]
    vectors = np.array([[1.0, 0.0], [0.99, 0.14]], dtype=np.float32)

    with patch(f"{AGENT}.embed", new=AsyncMock(return_value=vectors)), \
         patch(f"{AGENT}.llm_json_call", new=AsyncMock(return_value={"is_contradiction": False})):
        contradictions, status = await detect_contradictions(rows)

    assert contradictions == []
    assert status["code"] == "none_confirmed"
    assert status["is_error"] is False
    assert status["shortlisted_pairs"] == 1


@pytest.mark.asyncio
async def test_exhausted_budget_is_an_error_not_an_empty_finding():
    """The distinction the whole status object exists for: 'we checked and
    found nothing' must never be conflated with 'we could not check'."""
    rows = [make_row(title="A"), make_row(title="B")]
    vectors = np.array([[1.0, 0.0], [0.99, 0.14]], dtype=np.float32)

    with patch(f"{AGENT}.embed", new=AsyncMock(return_value=vectors)), \
         patch(f"{AGENT}.llm_client") as mock_llm_client:
        mock_llm_client.LLM_BUDGET_EXHAUSTED = True
        contradictions, status = await detect_contradictions(rows)

    assert contradictions == []
    assert status["code"] == "llm_budget_exhausted"
    assert status["is_error"] is True


@pytest.mark.asyncio
async def test_embedding_model_unavailable_is_an_error():
    from backend.llm.embeddings import EmbeddingUnavailableError

    rows = [make_row(title="A"), make_row(title="B")]
    with patch(f"{AGENT}.embed",
               new=AsyncMock(side_effect=EmbeddingUnavailableError("no weights"))):
        contradictions, status = await detect_contradictions(rows)

    assert contradictions == []
    assert status["code"] == "embedding_unavailable"
    assert status["is_error"] is True


@pytest.mark.asyncio
async def test_all_abstract_only_reports_nothing_to_compare():
    rows = [
        make_row(title="A", full_text_available=False,
                 results_summary="(Full text unavailable.)"),
        make_row(title="B", full_text_available=False,
                 results_summary="(Full text unavailable.)"),
    ]
    contradictions, status = await detect_contradictions(rows)

    assert contradictions == []
    assert status["code"] == "no_comparable_summaries"
    assert status["is_error"] is False


# ------------------------------------------------------------------
# Table assembly + node contract
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_failing_paper_does_not_lose_the_others():
    papers = [make_candidate(title="Good A"), make_candidate(title="Bad"),
              make_candidate(title="Good B")]

    async def _row(client, paper):
        if paper["title"] == "Bad":
            raise RuntimeError("boom")
        return make_row(title=paper["title"])

    with patch(f"{AGENT}.build_evidence_row", new=AsyncMock(side_effect=_row)):
        table = await build_evidence_table(papers, concurrency=3)

    assert [r["title"] for r in table] == ["Good A", "Bad", "Good B"]  # order preserved
    bad = table[1]
    assert bad["summary_source"] == "error"
    assert bad["retraction_status"] == "unknown"     # never assumed clean
    assert is_system_note(bad["results_summary"])


@pytest.mark.asyncio
async def test_node_writes_only_the_three_fields_it_owns():
    state = {"domain": "d", "protocol": {}, "candidates": [],
             "selected_papers": [make_candidate()], "gaps": ["should not be touched"]}

    with patch(f"{AGENT}.build_evidence_table", new=AsyncMock(return_value=[make_row()])), \
         patch(f"{AGENT}.detect_contradictions",
               new=AsyncMock(return_value=([], {"code": "too_few_papers", "is_error": False,
                                                "message": "m"}))):
        result = await synthesis_integrity_node(cast(dict, state))

    assert set(result) == {"evidence_table", "contradictions", "contradictions_status"}


@pytest.mark.asyncio
async def test_node_refuses_to_run_without_a_selection():
    with pytest.raises(ValueError, match="selected_papers"):
        await synthesis_integrity_node(cast(dict, {"domain": "d", "selected_papers": []}))
