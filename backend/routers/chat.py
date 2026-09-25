"""
General conversational chat -- no uploaded document, no research thread
required.

Backs the frontend's Chat mode when there's nothing to ground a response
in yet (no document uploaded, no completed Deep Search report in this
thread). Replaces the earlier client-side pattern-matched canned-reply
logic: this is a real, scoped LLM call through the existing Gemini
integration (backend/llm/client.py) -- same model/budget-cooldown
machinery the rest of the app already uses, no new provider.

Endpoint:
    POST /chat  ->  {"reply": "string"}
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth.jwt import get_current_user
from backend.auth.sanitize import sanitize_for_prompt
from backend.llm.client import llm_json_call
from backend.rate_limit import RollingWindowRateLimiter

logger = logging.getLogger("nexora.chat_router")

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_MESSAGE_CHARS = 2000

# Casual chat is cheap per-call (short prompt, capped output) but is also
# the kind of traffic that can spike unpredictably (unlike POST /research,
# which a user only fires occasionally) -- a higher ceiling than research's
# 10/hour, but still bounded. Process-local, same caveats as
# ResearchStartRateLimiter (research.py) -- not distributed, resets on restart.
_chat_rate_limiter = RollingWindowRateLimiter(limit=30, window_seconds=3600)

FALLBACK_REPLY = "I'm having trouble responding right now. Please try again in a moment."

SYSTEM_PROMPT = """You are Nexora's assistant. Respond naturally and briefly to greetings and general conversation.
If the user asks a question that requires searching academic literature or reading a specific document to answer accurately, do NOT attempt to answer it from general knowledge -- instead, tell them to use Deep Search (for academic research topics) or upload a document (to chat about a specific paper).
Keep responses to one or two short sentences -- this is casual chat, not a research report.

Respond ONLY with valid JSON, no markdown fences:
{"reply": "your short response here"}"""


class GeneralChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class GeneralChatResponse(BaseModel):
    reply: str


@router.post("", response_model=GeneralChatResponse)
async def general_chat(
    request: GeneralChatRequest,
    user_id: str = Depends(get_current_user),
) -> GeneralChatResponse:
    if not await _chat_rate_limiter.allow(user_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many chat messages. Please wait and try again later.",
        )

    safe_message = sanitize_for_prompt(request.message) or ""

    # Short and cheap on purpose (see llm_json_call's max_output_tokens
    # docstring) -- this is a sentence or two of small talk, not report
    # synthesis, and shouldn't pay for 4096 tokens of headroom it will
    # never use.
    result = await llm_json_call(
        SYSTEM_PROMPT,
        safe_message,
        debug_label="general_chat",
        max_output_tokens=200,
    )

    if result is None or result.get("_budget_exhausted") or result.get("_blocked_or_empty"):
        if result is not None:
            logger.warning("general_chat degraded to fallback: %s", {k: v for k, v in result.items()})
        return GeneralChatResponse(reply=FALLBACK_REPLY)

    reply = result.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return GeneralChatResponse(reply=FALLBACK_REPLY)

    return GeneralChatResponse(reply=reply.strip())
