"""
Shared LangGraph state definition.

Responsibility:
- Define the ResearchState TypedDict that flows through every node in the
  graph (protocol planning -> retrieval/screening -> human interrupt ->
  synthesis/integrity + gap discovery -> report assembly).
"""

from typing import Any, TypedDict


class ResearchState(TypedDict):
    # TODO: refine each field's type as the real agent contracts solidify
    domain: str
    protocol: dict[str, Any]
    candidates: list[dict[str, Any]]
    selected_papers: list[dict[str, Any]]
    evidence_table: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    report: str
