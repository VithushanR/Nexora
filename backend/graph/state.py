"""
Shared LangGraph state for the Nexora research pipeline.

One object, overwrite-per-field merge semantics. Each node reads/writes
only the fields it owns:
  Agent 1 -> protocol
  Agent 2 -> candidates
  [human]  -> selected_papers  (via interrupt())
  Agent 3 -> evidence_table, contradictions
  Agent 4 -> gaps
  Report Assembly -> report  (no LLM call, merges 3 + 4)
"""

from typing import TypedDict, Optional, Literal


class ScreeningVerdict(TypedDict):
    verdict: Literal["INCLUDE", "EXCLUDE", "UNCERTAIN"]
    quote: str
    reason: str


class Candidate(TypedDict, total=False):
    title: str
    doi: Optional[str]
    abstract: str
    year: Optional[int]
    source: str                     # "openalex" | "semantic_scholar" | "arxiv" | "europepmc"
    arxiv_id: Optional[str]
    pmcid: Optional[str]
    known_oa_pdf_url: Optional[str]
    prerank_score: float
    verdict: str
    quote: str
    reason: str
    has_usable_abstract: bool


class Protocol(TypedDict):
    domain: str
    inclusion_criteria: list[str]
    exclusion_criteria: list[str]
    queries: dict[str, str]         # per-source query string


class ResearchState(TypedDict, total=False):
    domain: str
    protocol: Optional[Protocol]
    candidates: Optional[list[Candidate]]
    selected_papers: Optional[list[Candidate]]
    evidence_table: Optional[list[dict]]
    contradictions: Optional[list[dict]]
    contradictions_status: Optional[dict]
    gaps: Optional[list[dict]]
    gaps_status: Optional[dict]
    report: Optional[dict]