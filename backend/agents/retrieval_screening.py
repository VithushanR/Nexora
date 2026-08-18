"""
Agent 2: Retrieval & Screening.

Responsibility:
- Run the protocol's query variants against every configured source client
  (openalex, semantic_scholar, crossref, arxiv, doaj).
- Deduplicate results (rapidfuzz on titles/DOIs), rank (rank-bm25 /
  sentence-transformers similarity), and screen against inclusion criteria.
- Populate state["candidates"] for the human selection step.
"""

from rapidfuzz import fuzz
from rank_bm25 import BM25Okapi

from sources import openalex, semantic_scholar, crossref, arxiv, doaj
from state import ResearchState


async def retrieval_screening(state: ResearchState) -> ResearchState:
    # TODO: fan out queries to each source client concurrently
    # TODO: dedupe candidates via rapidfuzz title/DOI matching
    # TODO: rank via BM25 / embedding similarity against the protocol criteria
    # TODO: write screened, ranked candidates to state["candidates"]
    raise NotImplementedError
