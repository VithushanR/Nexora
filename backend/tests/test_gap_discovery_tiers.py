"""
Tests for Agent 4's tier limits:
  - free tier mines only the first gap_max_papers selected papers
  - pro/team (gap_max_papers=None) mine every selected paper
  - gap_min_support from the tier drives the support threshold
  - free tier still returns paper_limitations, never an empty section
  - missing state["tier"] fails loud
  - tiers without the gap fields fall back to today's behaviour

extract_limitations, cluster_limitations and pick_representative are
mocked, so no network request is made and no embedding model is loaded.
get_tier_config is patched with fake limits, so these tests don't depend on
the final numbers in backend/tiers.py.

Run with: pytest backend/tests/test_gap_discovery_tiers.py -v
"""

from types import SimpleNamespace

import pytest

from backend.agents import gap_discovery
from backend.agents.gap_discovery import MIN_SUPPORT, gap_discovery_node, tier_gap_limits


FREE_LIMITS = SimpleNamespace(gap_max_papers=3, gap_min_support=2)
PRO_LIMITS = SimpleNamespace(gap_max_papers=None, gap_min_support=2)


def make_papers(n):
    return [{"title": f"Paper {i}", "abstract": "abstract"} for i in range(1, n + 1)]


@pytest.fixture
def mined(monkeypatch):
    """Patch the expensive pipeline steps and record which papers were mined.

    Every mined paper reports the same limitation, and clustering puts all
    statements in one cluster, so the support count equals the number of
    papers mined.
    """
    seen = {}

    async def fake_extract_limitations(papers):
        seen["papers"] = list(papers)
        return [(paper["title"], "The sample size was small.") for paper in papers]

    monkeypatch.setattr(gap_discovery, "extract_limitations", fake_extract_limitations)
    monkeypatch.setattr(
        gap_discovery, "cluster_limitations", lambda limitations: {0: list(limitations)} if limitations else {}
    )
    monkeypatch.setattr(gap_discovery, "pick_representative", lambda cluster: cluster[0][1])
    return seen


def use_limits(monkeypatch, limits):
    monkeypatch.setattr(gap_discovery, "get_tier_config", lambda tier: limits)


@pytest.mark.asyncio
async def test_free_tier_mines_only_first_gap_max_papers(monkeypatch, mined):
    use_limits(monkeypatch, FREE_LIMITS)
    papers = make_papers(5)

    result = await gap_discovery_node({"tier": "free", "selected_papers": papers})  # type: ignore[typeddict-item]

    assert mined["papers"] == papers[:3]
    assert result["gaps"][0]["total_papers"] == 3
    assert "first 3 of 5 selected papers" in result["gaps_status"]["message"]


@pytest.mark.asyncio
async def test_pro_tier_mines_every_selected_paper(monkeypatch, mined):
    use_limits(monkeypatch, PRO_LIMITS)
    papers = make_papers(5)

    result = await gap_discovery_node({"tier": "pro", "selected_papers": papers})  # type: ignore[typeddict-item]

    assert mined["papers"] == papers
    assert result["gaps"][0]["support_count"] == 5
    assert "upgrade" not in result["gaps_status"]["message"]


@pytest.mark.asyncio
async def test_no_cap_note_when_selection_fits_the_free_cap(monkeypatch, mined):
    use_limits(monkeypatch, FREE_LIMITS)
    papers = make_papers(2)

    result = await gap_discovery_node({"tier": "free", "selected_papers": papers})  # type: ignore[typeddict-item]

    assert mined["papers"] == papers
    assert result["gaps_status"]["code"] == "ok"
    assert "upgrade" not in result["gaps_status"]["message"]


@pytest.mark.asyncio
async def test_tier_min_support_withholds_weaker_gaps(monkeypatch, mined):
    use_limits(monkeypatch, SimpleNamespace(gap_max_papers=None, gap_min_support=4))

    result = await gap_discovery_node({"tier": "free", "selected_papers": make_papers(3)})  # type: ignore[typeddict-item]

    assert result["gaps"] == []
    assert result["gaps_status"]["code"] == "none_met_threshold"
    assert "at least 4 independent papers" in result["gaps_status"]["message"]


@pytest.mark.asyncio
async def test_free_tier_still_returns_paper_limitations(monkeypatch, mined):
    use_limits(monkeypatch, FREE_LIMITS)

    result = await gap_discovery_node({"tier": "free", "selected_papers": make_papers(5)})  # type: ignore[typeddict-item]

    assert len(result["paper_limitations"]) == 3
    assert result["gaps"], "free tier must still surface gaps, not an empty section"


@pytest.mark.asyncio
async def test_missing_tier_fails_loud(mined):
    with pytest.raises(ValueError, match="state\\['tier'\\]"):
        await gap_discovery_node({"selected_papers": make_papers(2)})  # type: ignore[typeddict-item]


def test_tier_without_gap_fields_keeps_current_behaviour(monkeypatch):
    use_limits(monkeypatch, SimpleNamespace(candidate_cap=50, concurrency=5))

    assert tier_gap_limits("free") == (None, MIN_SUPPORT)
