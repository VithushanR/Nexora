"""
Report assembly (fan-in node).

Responsibility:
- Merge state["evidence_table"], state["contradictions"], and state["gaps"]
  (outputs of Agent 3 + Agent 4) into a single human-readable report.
- Chunk the report/evidence content, embed it (sentence-transformers), and
  index it (faiss) so the Copilot "Report mode" chat can retrieve over it.
"""

import faiss
from sentence_transformers import SentenceTransformer

from Nexora.backend.graph.state import ResearchState


async def assemble_report(state: ResearchState) -> ResearchState:
    # TODO: render evidence_table + contradictions + gaps into report markdown
    # TODO: chunk the report text
    # TODO: embed chunks and build/update a faiss index for retrieval
    # TODO: write final markdown to state["report"]
    raise NotImplementedError
