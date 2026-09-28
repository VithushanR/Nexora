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
        ),
        TierName.PRO: TierLimits(
            candidate_cap=150,
            concurrency=10,
            monthly_research_runs=50,
            synthesis_concurrency=4,
            max_contradiction_pairs=20,
        ),
        TierName.TEAM: TierLimits(
            candidate_cap=300,
            concurrency=20,
            synthesis_concurrency=8,
            max_contradiction_pairs=40,
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
