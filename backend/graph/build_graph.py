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

CURRENT STATE: only Agent 2 (retrieval_screening) is wired in. Everything
else is a TODO block below, in topology order -- uncomment as each node
lands. Owners: fill in your section, remove your TODO once your node is
real and tested.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from backend.graph.state import ResearchState
from backend.agents.retrieval_screening import retrieval_screening_node

# TODO(agent-1-owner): implement backend/agents/protocol_planning.py, then:
# from backend.agents.protocol_planning import protocol_planning_node

# TODO(human-checkpoint-owner): implement the interrupt()-based selection
# node. Requires the checkpointer already wired in below (MemorySaver for
# now -- swap to langgraph.checkpoint.sqlite.SqliteSaver so paused state
# survives across separate HTTP requests, not just this process's memory).
# from backend.agents.human_selection import human_selection_node

# TODO(agent-3-owner): implement backend/agents/synthesis_integrity.py.
# Writes evidence_table, contradictions, contradictions_status to state.
# from backend.agents.synthesis_integrity import synthesis_integrity_node

# TODO(agent-4-owner): implement backend/agents/gap_discovery.py. Writes
# gaps, gaps_status to state. Must run as a genuinely independent branch
# from Agent 3 -- do not read anything Agent 3 wrote.
# from backend.agents.gap_discovery import gap_discovery_node

# TODO(report-assembly-owner): implement backend/agents/report_assembly.py.
# NO LLM call here -- pure merge of evidence_table + contradictions + gaps
# into `report`.
# from backend.agents.report_assembly import report_assembly_node


def build_graph() -> StateGraph:
    graph = StateGraph(ResearchState)

    # --- Agent 2 (this PR) ---
    graph.add_node("retrieval_screening", retrieval_screening_node)
    graph.add_edge(START, "retrieval_screening")
    graph.add_edge("retrieval_screening", END)  # TODO: remove once human_selection exists

    # TODO(agent-1-owner): uncomment, then REMOVE the two START/END lines
    # above (retrieval_screening becomes the second node, not the entry).
    #
    # graph.add_node("protocol_planning", protocol_planning_node)
    # graph.add_edge(START, "protocol_planning")
    # graph.add_edge("protocol_planning", "retrieval_screening")

    # TODO(human-checkpoint-owner): uncomment, then REMOVE the
    # "retrieval_screening" -> END edge above.
    #
    # graph.add_node("human_selection", human_selection_node)
    # graph.add_edge("retrieval_screening", "human_selection")

    # TODO(agent-3-owner, agent-4-owner): fan-out -- both branches read
    # `selected_papers` and run independently; LangGraph runs them in the
    # same step automatically since neither depends on the other's output.
    #
    # graph.add_node("synthesis_integrity", synthesis_integrity_node)
    # graph.add_node("gap_discovery", gap_discovery_node)
    # graph.add_edge("human_selection", "synthesis_integrity")
    # graph.add_edge("human_selection", "gap_discovery")

    # TODO(report-assembly-owner): fan-in -- LangGraph automatically waits
    # for BOTH synthesis_integrity and gap_discovery before running this.
    #
    # graph.add_node("report_assembly", report_assembly_node)
    # graph.add_edge("synthesis_integrity", "report_assembly")
    # graph.add_edge("gap_discovery", "report_assembly")
    # graph.add_edge("report_assembly", END)

    return graph


# MemorySaver for local dev. Swap for SqliteSaver once human_selection's
# interrupt() lands, so paused state survives across separate requests.
checkpointer = MemorySaver()
app = build_graph().compile(checkpointer=checkpointer)
