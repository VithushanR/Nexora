"""
Chat router.

Responsibility:
- POST /chat: powers the Copilot sidebar (ChatSidebar.tsx). Supports two
  modes: "report" (retrieval over the faiss index built in report/assembly.py)
  and "web" (fresh live lookups via the source clients / LLM).
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    run_id: str
    message: str
    mode: str  # TODO: constrain to Literal["report", "web"]


# TODO: define ChatResponse model (reply, sources)


@router.post("")
async def chat(request: ChatRequest):
    # TODO: if mode == "report", retrieve from the faiss index and answer grounded in it
    # TODO: if mode == "web", run live source lookups + LLM synthesis
    raise NotImplementedError
