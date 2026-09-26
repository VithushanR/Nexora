"""
Tests for llm_web_search_call (backend/llm/client.py): the google_search
grounded call that backs Web Search mode. The Gemini client is mocked --
no network, no API key.

Run with: pytest backend/tests/test_llm_web_search.py -v
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


def _response(text="Answer.", chunks=(), finish_reason="STOP"):
    grounding_chunks = [SimpleNamespace(web=SimpleNamespace(uri=u, title=t)) for u, t in chunks]
    candidate = SimpleNamespace(
        finish_reason=finish_reason,
        grounding_metadata=SimpleNamespace(grounding_chunks=grounding_chunks),
    )
    return SimpleNamespace(text=text, candidates=[candidate])


def _patched_client(generate):
    return patch.object(llm_client, "_get_client", return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))


@pytest.mark.asyncio
async def test_returns_text_and_deduplicated_web_sources():
    generate = Mock(return_value=_response(chunks=[("https://a", "A"), ("https://a", "A again"), ("https://b", "B")]))
    with _patched_client(generate):
        result = await llm_client.llm_web_search_call("news?")

    assert result == {"text": "Answer.", "sources": [{"url": "https://a", "title": "A"}, {"url": "https://b", "title": "B"}]}


@pytest.mark.asyncio
async def test_uses_the_google_search_tool_and_no_json_mode():
    generate = Mock(return_value=_response())
    with _patched_client(generate):
        await llm_client.llm_web_search_call("news?")

    config = generate.call_args.kwargs["config"]
    assert config.tools and config.tools[0].google_search is not None
    # google_search cannot be combined with a JSON response mime type.
    assert config.response_mime_type is None


@pytest.mark.asyncio
async def test_empty_response_is_reported_not_returned_as_an_answer():
    with _patched_client(Mock(return_value=_response(text="  ", finish_reason="SAFETY"))):
        result = await llm_client.llm_web_search_call("news?")

    assert result and result["_blocked_or_empty"] is True


@pytest.mark.asyncio
async def test_quota_error_trips_the_shared_cooldown():
    with _patched_client(Mock(side_effect=Exception("429 RESOURCE_EXHAUSTED"))):
        result = await llm_client.llm_web_search_call("news?")

    assert result == {"_budget_exhausted": True}
    # ...and the very next call short-circuits without touching the API.
    untouched = Mock()
    with _patched_client(untouched):
        assert await llm_client.llm_web_search_call("again") == {"_budget_exhausted": True}
    untouched.assert_not_called()


@pytest.mark.asyncio
async def test_other_errors_return_none():
    with _patched_client(Mock(side_effect=Exception("boom"))):
        assert await llm_client.llm_web_search_call("news?") is None


@pytest.mark.asyncio
async def test_missing_grounding_metadata_yields_no_sources():
    response = SimpleNamespace(
        text="Answer.", candidates=[SimpleNamespace(finish_reason="STOP", grounding_metadata=None)]
    )
    with _patched_client(Mock(return_value=response)):
        result = await llm_client.llm_web_search_call("news?")

    assert result == {"text": "Answer.", "sources": []}
