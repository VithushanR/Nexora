"""
Nexora pipeline graph assembly.

Topology (per the project doc):

    START -> protocol_planning -> retrieval_screening -> human_selection
                                                                |
                                              ------------------+------------------
                                              |                                   |
                                    synthesis_integrity                  gap_discovery
                                     (Agent 3 + 3b)                        (Agent 4)
                                              |                                   |
                                              ------------------+------------------
                                                                |
                                                        report_assembly -> END

All four agents and report assembly are wired. Agent 3 and Agent 4 fan out
from the human checkpoint and synchronise at report assembly.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.config import get_settings
from backend.graph.state import ResearchState
from backend.agents.protocol_planning import protocol_planning_node
from backend.agents.retrieval_screening import retrieval_screening_node
from backend.agents.human_selection import human_selection_node
from backend.agents.synthesis_integrity import synthesis_integrity_node
from backend.agents.gap_discovery import gap_discovery_node
from backend.agents.report_assembly import report_assembly_node


def build_graph() -> StateGraph:
    graph = StateGraph(ResearchState)

    # Agent 1 must create a validated protocol before Agent 2 can retrieve
    # papers, because Agent 2 reads protocol criteria and per-source queries.
    graph.add_node("protocol_planning", protocol_planning_node)
    graph.add_node("retrieval_screening", retrieval_screening_node)
    graph.add_node("human_selection", human_selection_node)
    graph.add_node("synthesis_integrity", synthesis_integrity_node)
    graph.add_node("gap_discovery", gap_discovery_node)
    graph.add_node("report_assembly", report_assembly_node)
    graph.add_edge(START, "protocol_planning")
    graph.add_edge("protocol_planning", "retrieval_screening")
    graph.add_edge("retrieval_screening", "human_selection")
    # Fan-out: both agents read the same checkpointed selected papers and
    # write disjoint state fields.
    graph.add_edge("human_selection", "synthesis_integrity")
    graph.add_edge("human_selection", "gap_discovery")
    # LangGraph's list-source edge is its explicit wait-for-all fan-in API.
    graph.add_edge(["synthesis_integrity", "gap_discovery"], "report_assembly")
    graph.add_edge("report_assembly", END)

    return graph


@asynccontextmanager
async def graph_context(
    sqlite_db_path: str | None = None,
    graph_builder: Callable[[], StateGraph] = build_graph,
) -> AsyncIterator[Any]:
    """Yield a compiled graph while its async SQLite checkpointer is open."""
    db_path = sqlite_db_path or get_settings().sqlite_db_path
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        yield graph_builder().compile(checkpointer=checkpointer)
