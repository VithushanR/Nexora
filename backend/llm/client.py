"""
Gemini LLM wrapper shared by every agent that needs a language-understanding
call. Reserved for tasks that genuinely need it (screening verdicts,
contradiction confirmation, gap clustering) -- per the project's cost
principles, everything else (retrieval, dedup, BM25, retraction lookups)
stays deterministic and never touches this module.

LLM_BUDGET_EXHAUSTED flag: once quota/credits run out, calls short-circuit
instantly instead of hitting the API again, so a long pipeline run degrades
gracefully instead of crashing partway through. This is a COOLDOWN, not a
permanent kill switch: Gemini's RPM/TPM quotas reset on a rolling ~1-minute
window, so a flag that stayed True forever would mean one transient 429 --
tripped by, say, a raised screening concurrency -- silently degrades every
future request in this process (across all users, not just the one that
hit the limit) until the process is restarted. `LLM_BUDGET_EXHAUSTED` is
exposed as a plain module attribute (module __getattr__, PEP 562) so
existing direct reads like `llm_client.LLM_BUDGET_EXHAUSTED` keep working
unchanged, but it now clears itself once the cooldown elapses.
"""

import os
import json
import time
import asyncio
import logging
from typing import Optional

from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("nexora.llm")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# How long to short-circuit LLM calls after a quota/budget error before
# trying the API again. Matches Gemini's rolling per-minute RPM/TPM window --
# long enough that we don't hammer an API that just told us to back off,
# short enough that one transient limit hit doesn't degrade the rest of an
# unrelated later request.
BUDGET_EXHAUSTED_COOLDOWN_SECONDS = float(os.getenv("LLM_BUDGET_COOLDOWN_SECONDS", "60"))

_client: Optional[genai.Client] = None
_budget_exhausted_until: Optional[float] = None


def _is_budget_exhausted() -> bool:
    return _budget_exhausted_until is not None and time.monotonic() < _budget_exhausted_until


def _trip_budget_exhausted() -> None:
    global _budget_exhausted_until
    _budget_exhausted_until = time.monotonic() + BUDGET_EXHAUSTED_COOLDOWN_SECONDS


def __getattr__(name: str):
    # PEP 562 module-level dynamic attribute. Only fires for names not set
    # as real module globals -- LLM_BUDGET_EXHAUSTED is deliberately never
    # assigned as a plain global below, so every external read (e.g.
    # synthesis_integrity.py's `llm_client.LLM_BUDGET_EXHAUSTED`) resolves
    # live off the cooldown timer instead of a stale True/False snapshot.
    if name == "LLM_BUDGET_EXHAUSTED":
        return _is_budget_exhausted()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Use the typed HarmCategory/HarmBlockThreshold enums, not raw strings --
# the SDK's stubs are strict about this (Pylance: "Literal[...] is not
# assignable to HarmCategory | None" when passed as plain strings).
SAFETY_SETTINGS = [
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=genai_types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def reset_budget_flag_for_tests():
    """Test-only helper -- production code should never reset this mid-run."""
    global _budget_exhausted_until
    _budget_exhausted_until = None


async def llm_json_call(system_prompt: str, user_prompt: str, *,
                         retries: int = 1, debug_label: str = "",
                         max_output_tokens: int = 4096) -> Optional[dict]:
    """
    Returns:
      - a parsed dict on success
      - None if the model's output could not be parsed after retries
      - {"_budget_exhausted": True} if quota/credits are exhausted
      - {"_blocked_or_empty": True, "finish_reason": ...} if the model
        returned nothing (commonly a safety-filter false-positive on
        clinical/academic text -- see SAFETY_SETTINGS above)

    Callers MUST check for these sentinels and degrade honestly (e.g.
    escalate a screening verdict to UNCERTAIN) rather than treating a
    failure as a clean empty result. See gaps_status / contradictions_status
    in the synthesis and gap-discovery agents for the pattern to follow.

    max_output_tokens defaults to 4096 (the pipeline steps' report/
    screening-sized budget) -- pass a smaller value for short, cheap calls
    like casual chat (see routers/chat.py) rather than paying for headroom
    a one-sentence reply will never use.
    """
    if _is_budget_exhausted():
        return {"_budget_exhausted": True}

    client = _get_client()

    # Build the typed config object once, not a plain dict -- the SDK's
    # generate_content() expects GenerateContentConfig | dict, but with
    # strict type checking a raw dict of mixed-type values fails Pylance
    # ("dict[str, str | int | ...] is not assignable to
    # GenerateContentConfigOrDict"). The typed object is unambiguous.
    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        safety_settings=SAFETY_SETTINGS,
    )

    for attempt in range(retries + 1):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=config,
            )

            # response.candidates is typed Optional[list[...]] -- guard
            # explicitly rather than relying on a bare try/except to hide
            # the None case (Pylance: "Object of type None is not
            # subscriptable").
            finish_reason = None
            if response.candidates:
                finish_reason = response.candidates[0].finish_reason

            raw = (response.text or "").strip()
            if not raw:
                logger.warning("Empty LLM response (finish_reason=%s) for [%s]", finish_reason, debug_label)
                if attempt == retries:
                    return {"_blocked_or_empty": True, "finish_reason": str(finish_reason)}
                await asyncio.sleep(1)
                continue

        except Exception as e:
            msg = str(e)
            if any(tok in msg for tok in ("RESOURCE_EXHAUSTED", "429", "402")) or "quota" in msg.lower():
                logger.error(
                    "LLM budget/quota exhausted: %s -- backing off for %.0fs",
                    msg[:200], BUDGET_EXHAUSTED_COOLDOWN_SECONDS,
                )
                _trip_budget_exhausted()
                return {"_budget_exhausted": True}
            if attempt == retries:
                logger.error("LLM call raised an exception for [%s]: %s", debug_label, msg[:300])
                return None
            await asyncio.sleep(2)
            continue

        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()

        try:
            return json.loads(raw)
        except Exception:
            if attempt == retries:
                truncated = finish_reason and "MAX_TOKENS" in str(finish_reason).upper()
                hint = " [MAX_TOKENS truncation]" if truncated else ""
                logger.error("JSON parse failed for [%s]%s. Raw: %r", debug_label, hint, raw[:1000])
                return None
            await asyncio.sleep(1)

    return None