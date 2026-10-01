"""Tests for centralized Nexora account-tier configuration."""

from dataclasses import FrozenInstanceError

import pytest

from backend.agents.gap_discovery import MIN_SUPPORT
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
    assert limits.upload_max_docs == 1
    assert limits.upload_max_size_mb == 5
    assert limits.pdf_export_enabled is False
    assert limits.gap_max_papers == 10
    assert limits.gap_min_support == 2


def test_pro_tier_limits() -> None:
    limits = TIER_CONFIG[TierName.PRO]
    assert limits.candidate_cap == 150
    assert limits.concurrency == 10
    assert limits.monthly_research_runs == 50
    assert limits.upload_max_docs == 10
    assert limits.upload_max_size_mb == 15
    assert limits.pdf_export_enabled is True
    assert limits.gap_max_papers == 50
    assert limits.gap_min_support == 2


def test_team_tier_has_no_defined_monthly_research_limit() -> None:
    limits = TIER_CONFIG[TierName.TEAM]
    assert limits.candidate_cap == 300
    assert limits.concurrency == 20
    assert limits.monthly_research_runs is None
    assert limits.upload_max_docs is None
    assert limits.upload_max_size_mb is None
    assert limits.pdf_export_enabled is True
    assert limits.gap_max_papers is None
    assert limits.gap_min_support == 2


def test_gap_min_support_is_identical_across_every_tier_and_matches_the_module_constant() -> None:
    """gap_min_support must mean the same thing on every plan -- unlike
    gap_max_papers, which is deliberately tier-scaled, this one fails the
    test if anyone changes a single tier's value independently of the
    others, or lets it drift from gap_discovery.MIN_SUPPORT."""
    values = {tier: TIER_CONFIG[tier].gap_min_support for tier in TierName}
    assert len(set(values.values())) == 1, values
    assert TIER_CONFIG[TierName.FREE].gap_min_support == MIN_SUPPORT


def test_positional_tierlimits_construction_is_unaffected_by_appended_fields() -> None:
    """The appended fields all default -- a 3-positional-arg construction
    (candidate_cap, concurrency, monthly_research_runs), as already used
    elsewhere in this test file, must keep working unchanged."""
    limits = TierLimits(1, 1, 1)
    assert (limits.candidate_cap, limits.concurrency, limits.monthly_research_runs) == (1, 1, 1)
    assert (limits.upload_max_docs, limits.upload_max_size_mb, limits.pdf_export_enabled) == (None, None, True)
    assert (limits.gap_max_papers, limits.gap_min_support) == (None, 2)


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
