"""
Tests for report indexing (backend/routers/copilot.py), covering:
  - report chunking (incl. empty sections that don't crash indexing)
  - indexing builds the right namespace and chunk count, idempotently
  - auth/ownership: 404 for a thread the caller doesn't own (matching
    research.py's convention -- see require_owned_thread)

Chatting over an indexed report is covered in test_chat_router.py -- chat
is one merged router now.

backend.rag.chat.build_index is a real, synchronous function: copilot.py
calls it via asyncio.to_thread, and tests mock it with plain Mock. Auth is
mocked at the copilot.get_thread/verify_thread_owner seam rather than
hitting a real database.

Run with: pytest backend/tests/test_copilot.py -v
"""

import logging

import pytest
from fastapi import HTTPException
from unittest.mock import Mock, patch

import backend.routers.copilot as copilot

MODULE = "backend.routers.copilot"

# thread_id -> owning user_id. A lightweight double for
# backend.research_threads, monkeypatched onto copilot.get_thread /
# copilot.verify_thread_owner below -- avoids needing a real sqlite DB for
# what is otherwise a pure auth-wiring concern.
_THREAD_OWNERS: dict[str, str] = {}

# thread_id -> stored report. Stands in for the Postgres-backed report store
# (its real round-trip is tested in test_postgres_stores.py).
_REPORTS: dict[str, dict] = {}


def register_report(thread_id: str, report: dict) -> None:
    _REPORTS[thread_id] = report


async def _fake_get_report(thread_id: str):
    return _REPORTS.get(thread_id)


async def _fake_get_thread(thread_id: str):
    return object() if thread_id in _THREAD_OWNERS else None


async def _fake_verify_thread_owner(thread_id: str, user_id: str) -> bool:
    return _THREAD_OWNERS.get(thread_id) == user_id


def register_thread_owner(thread_id: str, user_id: str) -> None:
    _THREAD_OWNERS[thread_id] = user_id


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Every store here is a plain module-level dict -- clear them between
    tests so nothing leaks across test cases. get_thread/verify_thread_owner
    are monkeypatched to the fake thread registry above for every test."""
    _THREAD_OWNERS.clear()
    _REPORTS.clear()
    monkeypatch.setattr(copilot, "get_thread", _fake_get_thread)
    monkeypatch.setattr(copilot, "verify_thread_owner", _fake_verify_thread_owner)
    monkeypatch.setattr(copilot, "get_report", _fake_get_report)
    yield
    _THREAD_OWNERS.clear()
    _REPORTS.clear()


def make_report(**overrides) -> dict:
    base: dict = {
        "domain": "test domain",
        "evidence_table": [
            {
                "title": "Paper One", "doi": "10.1/1", "year": 2023, "source": "arxiv",
                "full_text_available": True, "full_text_strategy": "arxiv",
                "summary_source": "full_text",
                "methodology_summary": "M1", "results_summary": "R1",
                "retracted": False, "retraction_note": "", "related_gap_indices": [0],
            },
            {
                "title": "Paper Two", "doi": "10.1/2", "year": 2022, "source": "europepmc",
                "full_text_available": False, "full_text_strategy": "none",
                "summary_source": "abstract_fallback",
                "methodology_summary": "M2", "results_summary": "R2",
                "retracted": False, "retraction_note": "", "related_gap_indices": [],
            },
        ],
        "contradictions": [
            {
                "description": "They disagree.", "paper_a_title": "Paper One",
                "paper_a_claim": "Claim A", "paper_b_title": "Paper Two", "paper_b_claim": "Claim B",
            }
        ],
        "contradictions_status": {"code": "ok", "message": "ok", "is_error": False},
        "gaps": [
            {"theme": "Long-term follow-up is understudied.", "support_count": 2,
             "supporting_paper_titles": ["Paper One", "Paper Two"]}
        ],
        "gaps_status": {"code": "ok", "message": "ok", "n_statements": 4, "is_error": False},
        "meta": {"n_papers": 2, "n_full_text": 1, "n_abstract_fallback": 1,
                  "n_contradictions": 1, "n_gaps": 1, "strategy_counts": {"arxiv": 1},
                  "analysis_incomplete": False},
    }
    base.update(overrides)
    return base


def setup_thread(thread_id: str, user_id: str = "u1", report: dict | None = None) -> None:
    register_thread_owner(thread_id, user_id)
    register_report(thread_id, report if report is not None else make_report())


# ------------------------------------------------------------------
# chunk_report / /index
# ------------------------------------------------------------------

def test_chunk_report_produces_one_chunk_per_row_contradiction_and_gap():
    report = make_report()
    chunks = copilot.chunk_report(report)
    assert len(chunks) == 4  # 2 evidence rows + 1 contradiction + 1 gap
    assert chunks[0] == "Paper One\n\nMethodology: M1\n\nResults: R1"
    assert "Paper Two" in chunks[1]
    assert "They disagree." in chunks[2]
    assert "Long-term follow-up is understudied." in chunks[3]
    assert "Paper One" in chunks[3] and "Paper Two" in chunks[3]


@pytest.mark.asyncio
async def test_index_calls_build_index_with_correct_namespace_and_chunk_count():
    thread_id = "thread-index-1"
    setup_thread(thread_id)

    mock_build_index = Mock()
    with patch(f"{MODULE}.build_index", mock_build_index):
        result = await copilot.index_report(thread_id, user_id="u1")

    assert result.indexed is True
    assert result.n_chunks == 4
    mock_build_index.assert_called_once()
    called_chunks, kwargs = mock_build_index.call_args
    assert kwargs["namespace"] == f"report:{thread_id}"
    assert len(called_chunks[0]) == 4


@pytest.mark.asyncio
async def test_index_empty_evidence_table_does_not_crash(caplog):
    thread_id = "thread-index-empty"
    empty_report = make_report(
        evidence_table=[],
        contradictions=[], contradictions_status={"code": "llm_failed", "message": "boom", "is_error": True},
        gaps=[], gaps_status={"code": "llm_failed", "message": "boom", "is_error": True, "n_statements": 0},
    )
    setup_thread(thread_id, report=empty_report)

    mock_build_index = Mock()
    with caplog.at_level(logging.WARNING, logger="nexora.copilot"):
        with patch(f"{MODULE}.build_index", mock_build_index):
            result = await copilot.index_report(thread_id, user_id="u1")

    assert result.indexed is True
    assert result.n_chunks == 0
    # rag.chat.build_index() raises ValueError on an empty chunk list, so
    # copilot.py must skip the call entirely rather than call it with [].
    mock_build_index.assert_not_called()
    assert "evidence_table is empty" in caplog.text
    assert "contradictions analysis incomplete" in caplog.text
    assert "gap analysis incomplete" in caplog.text


@pytest.mark.asyncio
async def test_index_is_idempotent_reindexing_does_not_duplicate():
    thread_id = "thread-index-idempotent"
    setup_thread(thread_id)

    mock_build_index = Mock()
    with patch(f"{MODULE}.build_index", mock_build_index):
        first = await copilot.index_report(thread_id, user_id="u1")
        second = await copilot.index_report(thread_id, user_id="u1")

    assert first.n_chunks == second.n_chunks == 4
    # build_index() itself overwrites a namespace wholesale (frozen
    # interface contract) -- copilot.py's part of "idempotent" is calling
    # it again with the same full chunk list, not an accumulated one.
    assert mock_build_index.call_count == 2
    first_chunks = mock_build_index.call_args_list[0][0][0]
    second_chunks = mock_build_index.call_args_list[1][0][0]
    assert first_chunks == second_chunks
    assert len(second_chunks) == 4


@pytest.mark.asyncio
async def test_non_owner_gets_404():
    thread_id = "thread-not-yours"
    register_thread_owner(thread_id, "owner-user")
    register_report(thread_id, make_report())

    with pytest.raises(HTTPException) as exc_info:
        await copilot.index_report(thread_id, user_id="attacker")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_thread_id_also_gets_404():
    """A thread_id nobody ever registered is indistinguishable from one
    that exists but belongs to someone else -- both are a plain 404."""
    with pytest.raises(HTTPException) as exc_info:
        await copilot.index_report("no-such-thread", user_id="u1")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_index_for_a_thread_with_no_report_is_a_404_not_fake_data():
    """A real, owned thread whose report does not exist yet (still running)
    must not be indexed with made-up content."""
    thread_id = "thread-still-running"
    register_thread_owner(thread_id, "u1")  # owned, but no report registered

    mock_build_index = Mock()
    with patch(f"{MODULE}.build_index", mock_build_index):
        with pytest.raises(HTTPException) as exc_info:
            await copilot.index_report(thread_id, user_id="u1")

    assert exc_info.value.status_code == 404
    mock_build_index.assert_not_called()
