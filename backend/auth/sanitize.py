# STUB -- replace with Part D's real implementation. Interface must not change.
"""
Minimal placeholder prompt-injection defense for backend/routers/copilot.py.

This is NOT a robust defense -- it strips control characters, hard-caps
length, and defuses a short list of common injection trigger phrases (e.g.
"ignore previous instructions") by replacing them with a visible
"[filtered]" marker before the text ever reaches a prompt. A determined
adversary can phrase around a fixed pattern list like this one. Part D's
real implementation should replace this with something more robust (e.g.
an LLM-based classifier or a maintained injection-pattern library) without
changing the function name/signature below.
"""

import re

MAX_PROMPT_CHARS = 2000

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# A short list of common prompt-injection trigger phrases. Matched
# case-insensitively; replaced rather than deleted so the resulting text
# still reads as a (neutered) sentence instead of leaving a confusing gap.
_INJECTION_PATTERNS_RE = re.compile(
    r"\b("
    r"ignore (all|any)? ?(previous|prior|above|earlier) instructions?"
    r"|disregard (all|any)? ?(previous|prior|above|earlier) instructions?"
    r"|forget (all|any)? ?(previous|prior|above|earlier) instructions?"
    r"|reveal (your|the) system prompt"
    r"|(show|print|output) (your|the) (system prompt|instructions)"
    r"|you are now (in )?[a-z ]+ mode"
    r"|act as (if you (are|were) )?(a|an) [a-z0-9 _-]+"
    r"|new instructions\s*:"
    r")\b",
    re.IGNORECASE,
)


def sanitize_for_prompt(text: str) -> str:
    """Caps length, strips control characters, and defuses recognizable
    prompt-injection phrases before `text` is ever interpolated into a
    system/user prompt. Callers should ALSO enforce a length limit at the
    HTTP layer with a 400 for oversized input -- this truncation is a
    defense-in-depth backstop, not the primary length check."""
    text = text[:MAX_PROMPT_CHARS]
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _INJECTION_PATTERNS_RE.sub("[filtered]", text)
    return text.strip()
