"""Tests for centralized Nexora account-tier configuration."""

from dataclasses import FrozenInstanceError

import pytest

from backend.tiers import (
    DEFAULT_TIER,
    TIER_CONFIG,
    TierLimits,
    TierName,
    get_tier_config,
)


def test_all_canonical_tier_names_exist() -> None:
    assert {tier.value for tier in TierName} == {"free", "pro", "team"}
    assert DEFAULT_TIER is TierName.FREE


def test_free_tier_limits() -> None:
    limits = TIER_CONFIG[TierName.FREE]
    assert limits.candidate_cap == 50
    assert limits.concurrency == 5
    assert limits.monthly_research_runs == 3


def test_pro_tier_limits() -> None:
    limits = TIER_CONFIG[TierName.PRO]
    assert limits.candidate_cap == 150
    assert limits.concurrency == 10
    assert limits.monthly_research_runs == 50


def test_team_tier_has_no_defined_monthly_research_limit() -> None:
    limits = TIER_CONFIG[TierName.TEAM]
    assert limits.candidate_cap == 300
    assert limits.concurrency == 20
    assert limits.monthly_research_runs is None


def test_get_tier_config_accepts_equivalent_enum_and_string() -> None:
    by_enum = get_tier_config(TierName.FREE)
    by_string = get_tier_config("free")

    assert by_enum is by_string
    assert by_enum is TIER_CONFIG[TierName.FREE]


def test_get_tier_config_uses_tier_config_as_single_source_of_truth() -> None:
    for tier in TierName:
        assert get_tier_config(tier) is TIER_CONFIG[tier]


def test_unknown_tier_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown account tier"):
        get_tier_config("enterprise")


def test_tier_limits_are_frozen() -> None:
    limits = TIER_CONFIG[TierName.FREE]

    with pytest.raises(FrozenInstanceError):
        limits.candidate_cap = 999  # type: ignore[misc]


def test_tier_config_mapping_is_immutable() -> None:
    with pytest.raises(TypeError):
        TIER_CONFIG[TierName.FREE] = TierLimits(1, 1, 1)  # type: ignore[index]
