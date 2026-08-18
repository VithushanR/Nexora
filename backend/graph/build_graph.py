"""
LangGraph StateGraph assembly.

Responsibility:
- Wire the pipeline: protocol_planning -> retrieval_screening -> human
  interrupt() checkpoint (paper selection) -> parallel fan-out to
  synthesis_integrity + gap_discovery -> fan-in to report_assembly.
- Use a SQLite checkpointer (langgraph.checkpoint.sqlite) so the interrupt
  can be resumed later via the /select endpoint.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from state import ResearchState
from agents import protocol_planning, retrieval_screening, synthesis_integrity, gap_discovery
from report import assembly


def build_graph():
    # TODO: instantiate the SqliteSaver against a real db path (from config)
    # TODO: add nodes for each agent function
    # TODO: add sequential edges: START -> protocol_planning -> retrieval_screening
    # TODO: add interrupt() checkpoint after retrieval_screening for human paper selection
    # TODO: add parallel fan-out edges to synthesis_integrity and gap_discovery
    # TODO: add fan-in edges from both into report_assembly -> END
    # TODO: compile the graph with the checkpointer and return it
    graph = StateGraph(ResearchState)
    raise NotImplementedError
