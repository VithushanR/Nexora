"""Deterministic Nexora policy for parsed research-topic safety results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from backend.safety.nvidia_client import NvidiaSafetyClassification


class SafetyDecision(str, Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    UNCERTAIN = "UNCERTAIN"


class SafetyPolicyInputError(ValueError):
    """Raised when the policy cannot make a valid, fail-closed decision."""


@dataclass(frozen=True)
class SafetyPolicyResult:
    decision: SafetyDecision
    category: str | None = None
    message: str | None = None


_UNSAFE_MESSAGE = "This request cannot be processed as a research topic."
_UNCERTAIN_MESSAGE = (
    "Please clarify the academic, clinical, prevention, policy, or research context "
    "for this topic."
)

# These patterns describe requests for operational guidance. They deliberately
# do not enumerate harmful subjects; Nemotron supplies the subject classification.
_ACTIONABLE_INTENT_PATTERNS = (
    re.compile(r"\bhow\s+to\b", re.IGNORECASE),
    re.compile(
        r"\bhow\s+(?:can|could|do|would|should)\s+(?:i|we|you|someone)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ways?|methods?|techniques?|instructions?|steps?|guide)\s+(?:for|to|on)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:best|easiest|fastest|most\s+effective)\s+"
        r"(?:way|method|technique|approach)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bstep[\s-]*by[\s-]*step\b", re.IGNORECASE),
    re.compile(
        r"\b(?:help|teach|tell|show|walk)\s+(?:me|us)\s+(?:how|to|through)\b",
        re.IGNORECASE,
    ),
)

# A provider-classified unsafe topic that also tries to control the classifier
# is an explicit unsafe request, rather than an ambiguous sensitive subject.
_CONTROL_ATTEMPT_PATTERNS = (
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b.{0,80}"
        r"\b(?:instructions?|rules?|policy|guardrails?|safety|classification)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:classify|mark|label|return|respond)\b.{0,60}"
        r"\b(?:safe|safe\s+content)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"<\s*/?\s*(?:end\s+conversation|system|assistant|user)\b[^>]*>",
        re.IGNORECASE,
    ),
)


def _first_category(classification: NvidiaSafetyClassification) -> str | None:
    return classification.categories[0] if classification.categories else None


def _matches_any(topic: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(topic) is not None for pattern in patterns)


def apply_safety_policy(
    research_topic: str,
    classification: NvidiaSafetyClassification,
) -> SafetyPolicyResult:
    """Convert a parsed Nemotron result into Nexora's deterministic decision."""
    if not isinstance(research_topic, str) or not research_topic.strip():
        raise SafetyPolicyInputError("research_topic must be a non-empty string.")
    if not isinstance(classification, NvidiaSafetyClassification):
        raise SafetyPolicyInputError("A valid NVIDIA safety classification is required.")

    category = _first_category(classification)
    if classification.user_safety == "safe":
        return SafetyPolicyResult(decision=SafetyDecision.SAFE, category=category)
    if classification.user_safety != "unsafe":
        raise SafetyPolicyInputError("Unsupported NVIDIA safety classification.")

    if _matches_any(research_topic, _CONTROL_ATTEMPT_PATTERNS) or _matches_any(
        research_topic, _ACTIONABLE_INTENT_PATTERNS
    ):
        return SafetyPolicyResult(
            decision=SafetyDecision.UNSAFE,
            category=category,
            message=_UNSAFE_MESSAGE,
        )

    return SafetyPolicyResult(
        decision=SafetyDecision.UNCERTAIN,
        category=category,
        message=_UNCERTAIN_MESSAGE,
    )
