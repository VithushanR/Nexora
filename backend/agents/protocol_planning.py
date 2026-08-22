"""
Agent 1: Protocol Planning.

Responsibility:
- Take the user-supplied research domain and turn it into a structured
  search protocol: inclusion/exclusion criteria plus a set of query variants
  to run against each source in sources/.
"""

from llm.client import get_llm_client
from Nexora.backend.graph.state import ResearchState


async def protocol_planning(state: ResearchState) -> ResearchState:
    # TODO: prompt the LLM to produce criteria + query variants from state["domain"]
    # TODO: validate/structure the output (pydantic model) and write to state["protocol"]
    raise NotImplementedError
