"""
Tests for backend.sources.base.strip_html_tags() and its application in
each source client -- covers the "raw HTML tags visible in abstract text"
bug (Europe PMC's abstractText and OpenAlex's abstract_inverted_index both
confirmed, against real API responses, to preserve embedded structural
markup like "<h4>Methods</h4>" verbatim).

Run with: pytest backend/tests/test_source_html_stripping.py -v
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from backend.sources.base import strip_html_tags
from backend.sources import openalex, europepmc, semantic_scholar, arxiv


# ------------------------------------------------------------------
# strip_html_tags() itself
# ------------------------------------------------------------------

def test_strips_structural_tags():
    raw = "<h4>Methods</h4>We used a GNN.<h4>Results</h4>It worked."
    assert "<" not in strip_html_tags(raw)
    assert ">" not in strip_html_tags(raw)
    assert "Methods" in strip_html_tags(raw)
    assert "We used a GNN." in strip_html_tags(raw)


def test_does_not_strip_math_inequality_notation():
    # The exact false-positive a blanket "<[^>]+>" regex would introduce --
    # a bare "<" or ">" in prose is not a tag, and must survive.
    raw = "We show convergence for x < 4 and y > 2 under mild conditions."
    assert strip_html_tags(raw) == raw


def test_unescapes_html_entities_after_stripping():
    raw = "<h4>Results</h4>p &lt; 0.05 was significant &amp; robust."
    result = strip_html_tags(raw)
    assert "<" not in result.replace("p < 0.05", "")  # the real inequality survives unescaped
    assert "p < 0.05" in result
    assert "&amp;" not in result
    assert "&" in result


def test_empty_and_none_safe():
    assert strip_html_tags("") == ""
    assert strip_html_tags(None) is None


# ------------------------------------------------------------------
# Per-source application -- each source's search() with a mocked API
# response containing embedded tags, asserting the returned abstract is
# tag-free.
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openalex_strips_tags_from_reconstructed_abstract():
    # abstract_inverted_index tokens can themselves be literal tag
    # fragments when the source publisher text was JATS-tagged.
    inverted_index = {
        "<h4>Methods</h4>We": [0],
        "used": [1],
        "a": [2],
        "GNN.": [3],
    }
    fake_response = {
        "results": [{
            "title": "A GNN paper",
            "doi": "https://doi.org/10.1/x",
            "abstract_inverted_index": inverted_index,
            "publication_year": 2023,
            "ids": {},
            "best_oa_location": {},
            "open_access": {},
        }]
    }
    with patch("backend.sources.openalex.get_json", new=AsyncMock(return_value=fake_response)):
        results = await openalex.search(AsyncMock(), "query")

    assert len(results) == 1
    assert "<" not in results[0]["abstract"]
    assert "Methods" in results[0]["abstract"]


@pytest.mark.asyncio
async def test_europepmc_strips_tags_from_abstract_text():
    fake_response = {
        "resultList": {
            "result": [{
                "title": "A clinical paper",
                "doi": "10.1/y",
                "abstractText": "<h4>Aims</h4>Diabetes and periodontal disease<h4>Methods</h4>We assessed glycemic control.",
                "pubYear": "2022",
                "pmcid": "PMC123",
                "inEPMC": "Y",
            }]
        }
    }
    with patch("backend.sources.europepmc.get_json", new=AsyncMock(return_value=fake_response)):
        results = await europepmc.search(AsyncMock(), "query")

    assert len(results) == 1
    assert "<" not in results[0]["abstract"]
    assert "Aims" in results[0]["abstract"]
    assert "Diabetes and periodontal disease" in results[0]["abstract"]


@pytest.mark.asyncio
async def test_semantic_scholar_strips_tags_from_abstract():
    fake_response = {
        "data": [{
            "title": "A paper",
            "abstract": "<p>Background</p>This study examines climate models.",
            "year": 2021,
            "externalIds": {},
            "openAccessPdf": None,
        }]
    }
    # httpx.Response.raise_for_status()/.json() are sync methods on a real
    # Response -- only client.get() itself is awaited, so the response mock
    # is a plain Mock, not AsyncMock.
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value=fake_response)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    results = await semantic_scholar.search(mock_client, "query")

    assert len(results) == 1
    assert "<" not in results[0]["abstract"]
    assert "Background" in results[0]["abstract"]


@pytest.mark.asyncio
async def test_arxiv_strips_tags_from_summary():
    raw_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678v1</id>
    <title>A paper</title>
    <summary>&lt;h4&gt;Background&lt;/h4&gt;We study transformers.</summary>
    <published>2023-01-01T00:00:00Z</published>
  </entry>
</feed>"""
    with patch("backend.sources.arxiv.get_text", new=AsyncMock(return_value=raw_xml)):
        results = await arxiv.search(AsyncMock(), "query")

    assert len(results) == 1
    assert "<" not in results[0]["abstract"]
    assert "Background" in results[0]["abstract"]
    assert "We study transformers." in results[0]["abstract"]
