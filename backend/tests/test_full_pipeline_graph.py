"""Focused no-I/O tests for the complete LangGraph pipeline topology."""

import asyncio

import pytest

from backend.graph import build_graph as graph_module


def _stubbed_graph(monkeypatch, *, synthesis_node, gap_node, report_node):
    """Build the production topology with deterministic node implementations."""

    async def protocol_node(state):
        return {
            "protocol": {
                "domain": state["domain"],
                "inclusion_criteria": ["include"],
                "exclusion_criteria": ["exclude"],
                "queries": {},
            }
        }

    async def retrieval_node(state):
        assert state["protocol"]["domain"] == state["domain"]
        return {"candidates": [{"title": "Candidate 0"}, {"title": "Candidate 1"}]}

    async def selection_node(state):
        return {"selected_papers": [state["candidates"][1]]}

    monkeypatch.setattr(graph_module, "protocol_planning_node", protocol_node)
    monkeypatch.setattr(graph_module, "retrieval_screening_node", retrieval_node)
    monkeypatch.setattr(graph_module, "human_selection_node", selection_node)
    monkeypatch.setattr(graph_module, "synthesis_integrity_node", synthesis_node)
    monkeypatch.setattr(graph_module, "gap_discovery_node", gap_node)
    monkeypatch.setattr(graph_module, "report_assembly_node", report_node)
    return graph_module.build_graph().compile()


def test_complete_topology_uses_langgraph_wait_for_all_fan_in():
    graph = graph_module.build_graph()

    assert ("__start__", "protocol_planning") in graph.edges
    assert ("protocol_planning", "retrieval_screening") in graph.edges
    assert ("retrieval_screening", "human_selection") in graph.edges
    assert ("human_selection", "synthesis_integrity") in graph.edges
    assert ("human_selection", "gap_discovery") in graph.edges
    assert (
        ("synthesis_integrity", "gap_discovery"),
        "report_assembly",
    ) in graph.waiting_edges
    assert ("report_assembly", "__end__") in graph.edges

    assert ("synthesis_integrity", "report_assembly") not in graph.edges
    assert ("gap_discovery", "report_assembly") not in graph.edges


@pytest.mark.asyncio
async def test_wired_graph_runs_both_branches_before_report_assembly(monkeypatch):
    completed_branches: set[str] = set()
    report_calls = 0

    async def synthesis_node(state):
        assert state["selected_papers"] == [{"title": "Candidate 1"}]
        await asyncio.sleep(0)
        completed_branches.add("synthesis_integrity")
        return {
            "evidence_table": [{"title": "Candidate 1", "method": "stub", "finding": "result"}],
            "contradictions": [],
            "contradictions_status": {"code": "none", "is_error": False},
        }

    async def gap_node(state):
        assert state["selected_papers"] == [{"title": "Candidate 1"}]
        completed_branches.add("gap_discovery")
        return {
            "gaps": [{"gap_id": "g1", "statement": "Stub gap"}],
            "gaps_status": {"code": "ok", "is_error": False},
        }

    async def report_node(state):
        nonlocal report_calls
        report_calls += 1
        assert completed_branches == {"synthesis_integrity", "gap_discovery"}
        assert state["evidence_table"][0]["title"] == "Candidate 1"
        assert state["contradictions_status"]["code"] == "none"
        assert state["gaps"][0]["gap_id"] == "g1"
        assert state["gaps_status"]["code"] == "ok"
        return {"report": "# Deterministic report"}

    app = _stubbed_graph(
        monkeypatch,
        synthesis_node=synthesis_node,
        gap_node=gap_node,
        report_node=report_node,
    )

    result = await app.ainvoke({"domain": "Deterministic graph test"})

    assert completed_branches == {"synthesis_integrity", "gap_discovery"}
    assert report_calls == 1
    assert result["report"] == "# Deterministic report"


@pytest.mark.asyncio
async def test_branch_failure_prevents_report_assembly(monkeypatch):
    report_called = False

    async def failing_synthesis_node(state):
        raise RuntimeError("controlled synthesis failure")

    async def gap_node(state):
        return {
            "gaps": [],
            "gaps_status": {"code": "no_statements", "is_error": False},
        }

    async def report_node(state):
        nonlocal report_called
        report_called = True
        return {"report": "must not be produced"}

    app = _stubbed_graph(
        monkeypatch,
        synthesis_node=failing_synthesis_node,
        gap_node=gap_node,
        report_node=report_node,
    )

    with pytest.raises(RuntimeError, match="controlled synthesis failure"):
        await app.ainvoke({"domain": "Deterministic graph test"})

    assert report_called is False
