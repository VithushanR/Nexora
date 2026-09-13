# STUB -- replace with Part D's real implementation. Interface must not change.
"""
Placeholder RAG backend for the Report Copilot (backend/routers/copilot.py).

Part D owns the real implementation of this module (real embeddings, a real
vector index, real retrieval-augmented generation). Until that PR lands,
this stub keeps Part B runnable and testable end-to-end:

  - build_index()  stores chunks in a module-level dict keyed by namespace
                    (in-memory only -- nothing persists across process restarts,
                    and nothing is shared across workers/processes).
  - query()        does a naive lowercase word-overlap match instead of real
                    embeddings/ANN search.
  - rag_chat()      calls backend.llm.client.llm_json_call with the naive
                    query() results as context.

DO NOT let this become the permanent implementation. The interface below
(function names, parameters, return shapes) is frozen -- Part D's real
version must be a drop-in replacement with the same signatures.
"""

import logging
from typing import Optional

from backend.llm.client import llm_json_call

logger = logging.getLogger("nexora.rag.stub")

# namespace -> list of chunk strings. build_index() REPLACES this list
# wholesale on every call, which is what makes /copilot/index idempotent
# and what makes /copilot/add_to_evidence's "re-index instead of append"
# requirement meaningful (see copilot.py).
_INDEXES: dict[str, list[str]] = {}

RAG_SYSTEM_PROMPT = (
    "You are a research report assistant. Answer the user's question using "
    "ONLY the REPORT CONTEXT provided below. If the context does not contain "
    "the answer, say so plainly -- never invent information that is not "
    "present in the context."
)


def build_index(chunks: list[str], namespace: str) -> None:
    """Replace the indexed chunks for `namespace`. Idempotent: calling this
    twice with the same chunks leaves the namespace in the same state, it
    never appends duplicates."""
    _INDEXES[namespace] = list(chunks)


def query(namespace: str, question: str, top_k: int = 5) -> list[dict]:
    """Naive keyword-overlap "retrieval" -- good enough to exercise the
    Copilot's control flow in tests and local dev, not a real ANN search.
    Returns [] for an unknown namespace or when nothing overlaps at all."""
    chunks = _INDEXES.get(namespace, [])
    if not chunks:
        return []

    q_words = set(question.lower().split())
    scored: list[tuple[int, str]] = []
    for chunk in chunks:
        overlap = len(q_words & set(chunk.lower().split()))
        if overlap:
            scored.append((overlap, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"text": text, "score": float(score)} for score, text in scored[:top_k]]


async def rag_chat(namespace: str, question: str, system_prompt: Optional[str] = None) -> str:
    """One-shot grounded answer over `namespace`. Reuses the llm_json_call
    sentinel pattern (see backend/llm/client.py) so a degraded LLM call
    surfaces as an honest message instead of a fabricated-looking answer."""
    hits = query(namespace, question, top_k=5)
    context = "\n\n---\n\n".join(h["text"] for h in hits) if hits else "(no indexed report content)"

    result = await llm_json_call(
        system_prompt or RAG_SYSTEM_PROMPT,
        f"REPORT CONTEXT:\n{context}\n\nQUESTION: {question}\n\n"
        'Respond ONLY with valid JSON, no markdown fences: {"answer": "..."}',
        debug_label="rag.chat.stub.rag_chat",
    )

    if not result:
        return "I couldn't process that question right now (the model's response could not be parsed)."
    if result.get("_budget_exhausted"):
        return "I couldn't process that question right now (LLM budget exhausted)."
    if result.get("_blocked_or_empty"):
        return "I couldn't process that question right now (the model returned an empty response)."

    answer = (result.get("answer") or "").strip()
    return answer or "I couldn't process that question right now (no answer returned)."
