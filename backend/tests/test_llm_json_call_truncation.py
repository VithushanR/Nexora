"""
Tests for llm_json_call's MAX_TOKENS truncation handling (backend/llm/client.py).

A response cut off by max_output_tokens is a valid-JSON-prefix-but-no-
closing-bracket parse failure with finish_reason=MAX_TOKENS -- a distinct,
actionable problem (raise max_output_tokens) from a genuinely unparseable
response. distinguish_truncation=True surfaces it as {"_truncated": True,
"raw_length": ...} instead of collapsing it into a plain None; the default
(False) preserves the exact prior behavior for every other caller in the
pipeline (screening, gap discovery, contradiction detection, report
assembly, protocol planning), none of which opt in and none of which can
safely handle a truthy-but-incomplete dict here.

The Gemini client is mocked -- no network, no API key.

Run with: pytest backend/tests/test_llm_json_call_truncation.py -v
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import backend.llm.client as llm_client


@pytest.fixture(autouse=True)
def _reset_budget():
    llm_client.reset_budget_flag_for_tests()
    yield
    llm_client.reset_budget_flag_for_tests()


def _truncated_response():
    # Exactly the shape of the real production failure: a well-formed JSON
    # prefix with real content, cut off mid-sentence, no closing brace.
    text = (
        'Based on the provided context, the documents detail the design '
        'and planning specifications for the Waypoint Delivery Planning '
        'System... **Failure Handling:'
    )
    # A plain string stands in for the real SDK's FinishReason enum here --
    # str(enum_member) naturally contains "MAX_TOKENS" (confirmed against a
    # real truncated Gemini call: str(finish_reason) == "FinishReason.MAX_TOKENS"),
    # and assigning __str__ on a SimpleNamespace instance doesn't work since
    # dunder lookups bypass the instance dict.
    candidate = SimpleNamespace(finish_reason="FinishReason.MAX_TOKENS")
    return SimpleNamespace(text=text, candidates=[candidate])


def _patched_client(generate):
    return patch.object(llm_client, "_get_client", return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))


@pytest.mark.asyncio
async def test_truncated_response_is_a_distinct_sentinel_when_opted_in():
    generate = Mock(return_value=_truncated_response())
    with _patched_client(generate):
        result = await llm_client.llm_json_call(
            "system", "user", debug_label="grounded_chat", retries=0, distinguish_truncation=True,
        )

    assert result is not None
    assert result["_truncated"] is True
    assert result["raw_length"] > 0


@pytest.mark.asyncio
async def test_truncated_response_stays_plain_none_by_default():
    """Every existing pipeline caller (screening, gap discovery, etc.) never
    passes distinguish_truncation -- confirms they keep getting exactly the
    prior behavior, not a new truthy dict they don't know how to handle."""
    generate = Mock(return_value=_truncated_response())
    with _patched_client(generate):
        result = await llm_client.llm_json_call("system", "user", debug_label="screen: paper", retries=0)

    assert result is None


@pytest.mark.asyncio
async def test_a_genuinely_unparseable_non_truncated_response_is_still_none_even_with_opt_in():
    response = SimpleNamespace(text="not json at all", candidates=[SimpleNamespace(finish_reason="STOP")])
    with _patched_client(Mock(return_value=response)):
        result = await llm_client.llm_json_call(
            "system", "user", debug_label="grounded_chat", retries=0, distinguish_truncation=True,
        )

    assert result is None


@pytest.mark.asyncio
async def test_the_log_line_still_carries_the_max_tokens_hint():
    generate = Mock(return_value=_truncated_response())
    with _patched_client(generate):
        with patch.object(llm_client, "logger") as logger:
            await llm_client.llm_json_call(
                "system", "user", debug_label="grounded_chat", retries=0, distinguish_truncation=True,
            )

    [call] = [c for c in logger.error.call_args_list if "JSON parse failed" in c.args[0]]
    fmt, debug_label, hint, raw = call.args
    assert hint == " [MAX_TOKENS truncation]"
