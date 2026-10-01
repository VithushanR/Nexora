"""Central account-tier names and limits for Nexora."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class TierName(StrEnum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


@dataclass(frozen=True, slots=True)
class TierLimits:
    candidate_cap: int
    concurrency: int
    monthly_research_runs: int | None = None
    # Agent 3 controls. Names match the canonical full-text cascade.
    synthesis_concurrency: int = 4
    max_contradiction_pairs: int = 20
    fulltext_strategies: tuple[str, ...] = (
        "known_oa_pdf",
        "arxiv",
        "europepmc_xml",
        "pmc_pdf",
        "unpaywall",
        "core_fulltext",
        "core_download",
    )
    # Appended, not inserted earlier: a positional TierLimits(...) call (see
    # test_tiers.py) only ever supplies candidate_cap/concurrency/
    # monthly_research_runs, so adding fields here can't shift what those
    # positions bind to. None means "no limit of its own" for the two upload
    # fields, matching monthly_research_runs' existing convention.
    upload_max_docs: int | None = None
    upload_max_size_mb: int | None = None
    pdf_export_enabled: bool = True
    # gap_max_papers scales by tier (a capacity limit, not an evidence-
    # standard change). gap_min_support deliberately does NOT scale -- it is
    # set to the same value on every tier below (see the TIER_CONFIG entries)
    # so what counts as a "gap" means the same thing regardless of plan.
    # This module can't import backend.agents.gap_discovery.MIN_SUPPORT
    # directly (gap_discovery.py already imports get_tier_config from here,
    # so that would be circular) -- the literal 2 here must be kept in sync
    # with that constant by hand; test_tiers.py asserts they match.
    gap_max_papers: int | None = None
    gap_min_support: int = 2


DEFAULT_TIER = TierName.FREE

TIER_CONFIG: Mapping[TierName, TierLimits] = MappingProxyType(
    {
        TierName.FREE: TierLimits(
            candidate_cap=50,
            concurrency=5,
            monthly_research_runs=3,
            synthesis_concurrency=2,
            max_contradiction_pairs=10,
            # A miss proceeds to Agent 3's labelled abstract fallback.
            fulltext_strategies=("arxiv",),
            upload_max_docs=1,
            upload_max_size_mb=5,
            # Matches the upgrade message already shown in
            # routers/research.py's PDF-export check ("available on Pro and
            # Team plans").
            pdf_export_enabled=False,
            gap_max_papers=10,
            gap_min_support=2,
        ),
        TierName.PRO: TierLimits(
            candidate_cap=150,
            concurrency=10,
            monthly_research_runs=50,
            synthesis_concurrency=4,
            max_contradiction_pairs=20,
            upload_max_docs=10,
            upload_max_size_mb=15,
            pdf_export_enabled=True,
            gap_max_papers=50,
            gap_min_support=2,
        ),
        TierName.TEAM: TierLimits(
            candidate_cap=300,
            concurrency=20,
            synthesis_concurrency=8,
            max_contradiction_pairs=40,
            upload_max_docs=None,
            upload_max_size_mb=None,
            pdf_export_enabled=True,
            gap_max_papers=None,
            gap_min_support=2,
        ),
    }
)


def get_tier_config(tier: TierName | str) -> TierLimits:
    """Return limits for a known account tier."""
    try:
        tier_name = TierName(tier)
    except ValueError as exc:
        raise ValueError(f"Unknown account tier: {tier!r}") from exc

    return TIER_CONFIG[tier_name]
