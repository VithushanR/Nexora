"""
Integration test for the report_assembly -> report/store -> copilot/index
connection point.

Before this wiring, backend/agents/report_assembly.py never called
register_report(), so backend/report/store.py's get_report(thread_id)
always fell back to the hardcoded two-fake-papers SAMPLE_REPORT for every
real thread -- POST /research/{thread_id}/copilot/index silently indexed
sample data instead of that thread's actual evidence table, contradictions
and gaps, regardless of report format (markdown vs structured). This test
runs a minimal but realistic multi-paper state through the REAL
report_assembly_node (inside a real, minimal LangGraph run, so
get_config() resolves a real thread_id the way it would in production),
then calls copilot.index_report() for that same thread and asserts the
indexed chunks contain that thread's own content -- not SAMPLE_REPORT's.

Run with: pytest backend/tests/test_report_pipeline_to_copilot.py -v
"""

import pytest
from typing import cast
from unittest.mock import Mock, patch

from langgraph.graph import StateGraph, START, END

import backend.routers.copilot as copilot
from backend.agents.report_assembly import report_assembly_node
from backend.graph.state import ResearchState
from backend.report.store import get_report, SAMPLE_REPORT

MODULE = "backend.routers.copilot"

THREAD_ID = "thread-integration-gnn"
USER_ID = "u1"

# A hand-built but realistic multi-paper state, standing in for what
# synthesis_integrity_node + gap_discovery_node would actually produce.
# Distinctive strings here (never present in SAMPLE_REPORT) are what the
# assertions below check for.
FAKE_STATE: dict = {
    "domain": "graph neural networks for molecular property prediction",
    "selected_papers": [{"title": "GNN-Mol"}, {"title": "MolFormer"}, {"title": "ChemBERT"}],
    "evidence_table": [
        {
            "title": "GNN-Mol", "doi": "10.9999/gnn-mol", "year": 2023, "source": "arxiv",
            "full_text_available": True, "full_text_strategy": "arxiv",
            "summary_source": "full_text",
            "methodology_summary": "A message-passing GNN trained on QM9.",
            "results_summary": "Achieves 0.09 mean absolute error on HOMO-LUMO gap prediction.",
            "method": "A message-passing GNN trained on QM9.",
            "finding": "Achieves 0.09 mean absolute error on HOMO-LUMO gap prediction.",
            "retracted": False, "retraction_status": "clean", "retraction_note": "checked",
        },
        {
            "title": "MolFormer", "doi": "10.9999/molformer", "year": 2022, "source": "openalex",
            "full_text_available": True, "full_text_strategy": "unpaywall",
            "summary_source": "full_text",
            "methodology_summary": "A transformer pretrained on one billion SMILES strings.",
            "results_summary": "Reports no significant improvement over GNN baselines.",
            "method": "A transformer pretrained on one billion SMILES strings.",
            "finding": "Reports no significant improvement over GNN baselines.",
            "retracted": False, "retraction_status": "clean", "retraction_note": "checked",
        },
    ],
    "contradictions": [
        {
            "description": "GNN-Mol and MolFormer disagree on whether transformers beat GNNs.",
            "paper_a_title": "GNN-Mol", "paper_a_claim": "GNNs outperform transformer baselines.",
            "paper_b_title": "MolFormer", "paper_b_claim": "Transformers show no improvement over GNNs.",
            "summary": "GNN-Mol and MolFormer disagree on whether transformers beat GNNs.",
        }
    ],
    "contradictions_status": {"code": "ok", "message": "1 contradiction found.", "is_error": False},
    "gaps": [
        {
            "gap_id": "g1",
            "statement": "Generalisation to molecules outside the training distribution is rarely evaluated.",
            "support_count": 3,
            "total_papers": 3,
            "supporting_paper_ids": ["GNN-Mol", "MolFormer", "ChemBERT"],
            "quotes": [{"paper_id": "GNN-Mol", "text": "We do not evaluate out-of-distribution generalisation."}],
            "support_weight": None,
        }
    ],
    "gaps_status": {"code": "ok", "message": "1 candidate gap(s) surfaced.", "is_error": False},
}


def _build_report_assembly_only_graph():
    """A minimal graph running just the REAL report_assembly_node, fed a
    hand-built upstream state -- exercises the exact register_report()
    connection point without needing Agent 1/2/3/4's LLM/source calls."""
    graph = StateGraph(ResearchState)
    graph.add_node("report_assembly", report_assembly_node)
    graph.add_edge(START, "report_assembly")
    graph.add_edge("report_assembly", END)
    return graph.compile()


async def _fake_get_thread(thread_id: str):
    return object() if thread_id == THREAD_ID else None


async def _fake_verify_thread_owner(thread_id: str, user_id: str) -> bool:
    return thread_id == THREAD_ID and user_id == USER_ID


@pytest.fixture(autouse=True)
def _reset_copilot_state(monkeypatch):
    copilot._HISTORY.clear()
    copilot._LAST_CHUNKS.clear()
    monkeypatch.setattr(copilot, "get_thread", _fake_get_thread)
    monkeypatch.setattr(copilot, "verify_thread_owner", _fake_verify_thread_owner)
    yield
    copilot._HISTORY.clear()
    copilot._LAST_CHUNKS.clear()


@pytest.mark.asyncio
async def test_report_assembly_registers_real_report_for_copilot_indexing():
    app = _build_report_assembly_only_graph()

    result = await app.ainvoke(
        cast(ResearchState, dict(FAKE_STATE)), config={"configurable": {"thread_id": THREAD_ID}},
    )

    # The markdown path (GET /research/{thread_id}/report) still works.
    assert isinstance(result["report"], str)
    assert "graph neural networks for molecular property prediction" in result["report"]

    # register_report() ran for THIS thread_id with THIS thread's data --
    # not the sample.
    registered = get_report(THREAD_ID)
    assert registered is not SAMPLE_REPORT
    assert registered["domain"] == "graph neural networks for molecular property prediction"

    # The gaps field-mapping (statement/supporting_paper_ids ->
    # theme/supporting_paper_titles) actually happened.
    assert registered["gaps"][0]["theme"] == FAKE_STATE["gaps"][0]["statement"]
    assert registered["gaps"][0]["supporting_paper_titles"] == ["GNN-Mol", "MolFormer", "ChemBERT"]

    # Now index this thread through the real copilot endpoint.
    mock_build_index = Mock()
    with patch(f"{MODULE}.build_index", mock_build_index):
        index_result = await copilot.index_report(THREAD_ID, user_id=USER_ID)

    assert index_result.indexed is True
    mock_build_index.assert_called_once()
    chunks, kwargs = mock_build_index.call_args
    indexed_text = "\n".join(chunks[0])

    assert kwargs["namespace"] == f"report:{THREAD_ID}"

    # The indexed content came from THIS thread's real evidence/gaps/
    # contradictions...
    assert "A message-passing GNN trained on QM9." in indexed_text
    assert "Achieves 0.09 mean absolute error on HOMO-LUMO gap prediction." in indexed_text
    assert "A transformer pretrained on one billion SMILES strings." in indexed_text
    assert "GNN-Mol and MolFormer disagree on whether transformers beat GNNs." in indexed_text
    assert "Generalisation to molecules outside the training distribution" in indexed_text
    assert "GNN-Mol" in indexed_text and "MolFormer" in indexed_text and "ChemBERT" in indexed_text

    # ...and NOT from the old SAMPLE_REPORT fallback. This is the
    # assertion that would have caught the original bug.
    assert "Sample Paper One" not in indexed_text
    assert "Sample Paper Two" not in indexed_text
    assert "sample domain" not in indexed_text
