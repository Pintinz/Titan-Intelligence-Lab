from __future__ import annotations

import pytest

from modules.predictions.domain.market_outcome_registry import (
    MARKET_OUTCOME_CATALOG,
    get_outcome_spec,
)
from modules.predictions.domain.value_objects import OutcomeType

EXPECTED_MARKETS_BY_SPORT: dict[str, set[str]] = {
    "football": {
        "football.match_winner", "football.match_result", "football.double_chance",
        "football.both_teams_to_score", "football.total_goals_over_under_0_5",
        "football.total_goals_over_under_1_5", "football.total_goals_over_under_2_5",
        "football.total_goals_over_under_3_5", "football.total_goals_over_under",
        "football.home_team_total_0_5", "football.home_team_total_1_5", "football.home_team_total_goals",
        "football.away_team_total_0_5", "football.away_team_total_1_5", "football.correct_score",
    },
    "basketball": {
        "basketball.winner", "basketball.moneyline", "basketball.spread", "basketball.totals",
        "basketball.quarter_winner", "basketball.half_winner",
    },
    "baseball": {"baseball.winner", "baseball.run_line", "baseball.totals"},
    "table_tennis": {"table_tennis.winner", "table_tennis.correct_sets"},
}

# Every catalog entry pointing (directly, or via a brief-named alias like "baseball.winner") at a
# real resolver — outcome_resolution_service.MARKET_OUTCOME_RESOLVERS (binary-polarity),
# football.match_winner in THREE_WAY_MARKET_RESOLVERS (direct 3-way label equality, Phase 3), and
# football.correct_score in GRID_MARKET_RESOLVERS (direct N-way label equality, 2026-08-06 audit
# fix — same mechanics as THREE_WAY, just a 37-cell label space instead of 3).
MARKETS_WITH_REAL_RESOLVER = {
    "football.both_teams_to_score", "football.total_goals_over_under", "football.home_team_total_goals",
    "football.match_winner", "football.correct_score",
    # 2026-08-02 football market catalog expansion — nine more real resolvers, all computable
    # from the final score alone.
    "football.total_goals_over_under_0_5", "football.total_goals_over_under_1_5",
    "football.total_goals_over_under_3_5", "football.total_goals_over_under_4_5",
    "football.away_team_total_goals",
    "football.home_clean_sheet", "football.away_clean_sheet",
    "football.home_win_to_nil", "football.away_win_to_nil",
    "basketball.moneyline", "baseball.winner", "baseball.moneyline",
    "table_tennis.winner", "table_tennis.match_winner",
}


def test_catalog_covers_every_market_the_brief_names_per_sport():
    for sport, expected_keys in EXPECTED_MARKETS_BY_SPORT.items():
        catalog_keys_for_sport = {k for k, spec in MARKET_OUTCOME_CATALOG.items() if spec.sport_code == sport}
        missing = expected_keys - catalog_keys_for_sport
        assert not missing, f"{sport} catalog is missing: {missing}"


def test_every_spec_market_key_matches_its_dict_key():
    for key, spec in MARKET_OUTCOME_CATALOG.items():
        assert spec.market_key == key


def test_every_spec_has_at_least_two_allowed_values():
    for key, spec in MARKET_OUTCOME_CATALOG.items():
        assert len(spec.allowed_values) >= 2, f"{key} has fewer than 2 allowed values"


def test_allowed_values_are_unique_per_market():
    for key, spec in MARKET_OUTCOME_CATALOG.items():
        assert len(spec.allowed_values) == len(set(spec.allowed_values)), f"{key} has duplicate allowed values"


@pytest.mark.parametrize("market_key", sorted(MARKETS_WITH_REAL_RESOLVER))
def test_markets_with_real_resolver_have_a_resolver_key_set(market_key):
    """These six are the only markets `OutcomeResolutionService` can actually evaluate today —
    the catalog must say so explicitly, not leave every entry looking equally "ready"."""
    spec = get_outcome_spec(market_key)
    assert spec is not None
    assert spec.resolver_key is not None


def test_markets_without_a_real_resolver_have_resolver_key_none():
    """Every other catalog entry is specification-only (Phase 1) — asserting resolver_key is None
    documents, in a running test, that no resolver silently exists for it yet."""
    unresolved = {k for k, spec in MARKET_OUTCOME_CATALOG.items() if k not in MARKETS_WITH_REAL_RESOLVER}
    for key in unresolved:
        assert get_outcome_spec(key).resolver_key is None, f"{key} unexpectedly has a resolver_key"


def test_home_draw_away_markets_have_exactly_three_values():
    for key, spec in MARKET_OUTCOME_CATALOG.items():
        if spec.outcome_type is OutcomeType.HOME_DRAW_AWAY:
            assert set(spec.allowed_values) == {"HOME_WIN", "DRAW", "AWAY_WIN"}, key


def test_over_under_markets_have_exactly_over_and_under():
    for key, spec in MARKET_OUTCOME_CATALOG.items():
        if spec.outcome_type is OutcomeType.OVER_UNDER:
            assert set(spec.allowed_values) == {"OVER", "UNDER"}, key


def test_correct_score_grid_includes_an_other_catch_all():
    spec = get_outcome_spec("football.correct_score")
    assert "OTHER" in spec.allowed_values
    assert "0-0" in spec.allowed_values
    assert "2-1" in spec.allowed_values


def test_table_tennis_correct_sets_matches_brief_exact_values():
    spec = get_outcome_spec("table_tennis.correct_sets")
    assert spec.allowed_values == ("3-0", "3-1", "3-2", "0-3", "1-3", "2-3")


def test_get_outcome_spec_returns_none_for_unknown_market():
    assert get_outcome_spec("football.nonexistent_market") is None
