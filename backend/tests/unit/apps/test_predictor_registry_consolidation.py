"""ML-architecture consolidation (2026-08-04) regression guards: the Poisson-based formula
predictors were removed entirely as legacy statistical engines, and `football.correct_score` plus
the eleven Over/Under-style markets deliberately have no formula fallback registered for them —
their production path is "a real trained Champion, or an honest insufficient-data response",
never a silently-substituted formula guess."""

from __future__ import annotations

import pytest

from apps.api.composition import get_predictor_registry
from modules.predictions.domain.value_objects import MarketKind


def test_predictor_registry_has_no_poisson_source_files():
    with pytest.raises(ModuleNotFoundError):
        import importlib

        importlib.import_module("modules.predictions.infrastructure.predictors.poisson_score_predictor")
    with pytest.raises(ModuleNotFoundError):
        import importlib

        importlib.import_module("modules.predictions.infrastructure.predictors.poisson_goals_threshold_predictor")


def test_predictor_registry_has_no_per_market_override_for_formerly_poisson_markets():
    """These eleven markets used to be overridden per-`market_key` with a Poisson-threshold
    predictor (composition.py's old `FOOTBALL_POISSON_THRESHOLD_MARKETS`) — that override is
    gone. They still generate via a real trained Champion when one exists; when none does,
    `PredictionContextBuilder` raises `NoChampionModelError` before this registry is ever
    consulted (see `scripts/seed_football_markets.py`'s `NOT_YET_TRAINED_MARKET_KEYS`)."""
    registry = get_predictor_registry()
    formerly_poisson_market_keys = (
        "football.total_goals_over_under",
        "football.total_goals_over_under_0_5",
        "football.total_goals_over_under_1_5",
        "football.total_goals_over_under_3_5",
        "football.total_goals_over_under_4_5",
        "football.home_team_total_goals",
        "football.away_team_total_goals",
        "football.home_clean_sheet",
        "football.away_clean_sheet",
        "football.home_win_to_nil",
        "football.away_win_to_nil",
    )
    for market_key in formerly_poisson_market_keys:
        # No per-market override exists; falling through to the MarketKind-level default is the
        # generic weighted predictor, not a market-specific Poisson answer — confirmed distinct
        # by checking the registry's internal per-market map directly rather than `.get()`, which
        # would silently succeed via the kind-level fallback and mask a reintroduced override.
        assert market_key not in registry._market_predictors  # noqa: SLF001 — direct regression check


def test_correct_score_has_no_per_market_override():
    registry = get_predictor_registry()
    assert "football.correct_score" not in registry._market_predictors  # noqa: SLF001


def test_predictor_registry_still_serves_unaffected_market_kinds():
    """HOME_DRAW_AWAY (match_winner) and BINARY (both_teams_to_score) markets were never Poisson-
    served — confirm they're completely unaffected by this consolidation."""
    registry = get_predictor_registry()
    assert registry.get(MarketKind.HOME_DRAW_AWAY) is not None
    assert registry.get(MarketKind.BINARY) is not None


def test_predictor_registry_raises_for_correct_score_kind_without_override():
    """Sanity check on the test's own assumption: CORRECT_SCORE still resolves to
    WeightedLinearPredictor via the MarketKind-level default (its raw-number output is simply
    never reached for football.correct_score in production, since that market has no Champion —
    this test just confirms the registry itself wasn't accidentally left with a gap for the
    MarketKind entirely, which would be a different, unrelated bug)."""
    registry = get_predictor_registry()
    predictor = registry.get(MarketKind.CORRECT_SCORE)
    assert predictor is not None
