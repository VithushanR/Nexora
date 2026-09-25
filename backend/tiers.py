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


DEFAULT_TIER = TierName.FREE

TIER_CONFIG: Mapping[TierName, TierLimits] = MappingProxyType(
    {
        TierName.FREE: TierLimits(
            candidate_cap=50,
            concurrency=5,
            monthly_research_runs=3,
        ),
        TierName.PRO: TierLimits(
            candidate_cap=150,
            concurrency=10,
            monthly_research_runs=50,
        ),
        TierName.TEAM: TierLimits(
            candidate_cap=300,
            concurrency=20,
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
