"""
Agent 3: Synthesis & Integrity.

Responsibility:
- Given state["selected_papers"], build a structured evidence table
  (claims, methods, sample sizes, findings per paper).
- Cross-check papers for contradictions and flag retractions/integrity
  concerns.
- Write results to state["evidence_table"] and state["contradictions"].
"""

from llm.client import get_llm_client
from state import ResearchState


async def synthesis_integrity(state: ResearchState) -> ResearchState:
    # TODO: extract structured evidence rows per selected paper via LLM
    # TODO: cross-compare evidence rows to detect contradictions
    # TODO: check retraction status (e.g. via Crossref/OpenAlex metadata)
    raise NotImplementedError
