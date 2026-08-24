from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.outcome_resolution_service import (
    REGRESSION_MARKET_RESOLVERS,
    MatchResult,
    OutcomeResolutionService,
    _away_clean_sheet,
    _away_team_total_goals_over_under_1_5,
    _away_win_to_nil,
    _both_teams_to_score,
    _correct_score,
    _first_half_both_teams_to_score,
    _first_half_goals_over_under_0_5,
    _first_half_points_over_under_109_5,
    _first_half_winner,
    _home_clean_sheet,
    _home_team_total_goals_over_under_1_5,
    _home_win_to_nil,
    _match_winner_home_draw_away,
    _moneyline_home_win,
    _second_half_winner,
    _total_goals_over_under_0_5,
    _total_goals_over_under_1_5,
    _total_goals_over_under_2_5,
    _total_goals_over_under_3_5,
    _total_goals_over_under_4_5,
    _total_points_over_under_199_5,
    _total_points_over_under_209_5,
    _total_points_over_under_219_5,
    _total_points_over_under_229_5,
    _total_points_over_under_239_5,
    _total_runs_over_under_6_5,
    _total_runs_over_under_7_5,
    _total_runs_over_under_8_5,
    _total_runs_over_under_9_5,
    _total_runs_over_under_10_5,
)
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    Prediction,
)
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    PredictionId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)

CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.8, feature_freshness=0.8, historical_accuracy=0.5, knowledge_graph_completeness=0.5,
    news_reliability=0.5, community_reliability=0.5, data_completeness=0.8, model_reliability=0.5,
    prediction_stability=1.0,
)


def _prediction(market_id: MarketId, value: str, status: PredictionStatus = PredictionStatus.PUBLISHED, subject_ref: str = "fx-1") -> Prediction:
    return Prediction(
        id=PredictionId(uuid4()), market_id=market_id, model_id=ModelId(uuid4()), subject_ref=subject_ref,
        value=value, probability=0.6, confidence=CONFIDENCE, explanation=ExplanationBundle(),
        feature_snapshot={}, model_version="1", status=status, generated_at=T0,
    )


def _market(market_key: str, market_kind: MarketKind = MarketKind.BINARY) -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code=market_key.split(".")[0], name=market_key,
        category="test", market_kind=market_kind, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


class TestResolverFunctions:
    def test_btts_both_scored(self):
        resolved = _both_teams_to_score(MatchResult(2, 1))
        assert resolved.matches_positive is True
        assert resolved.actual_value == "btts_yes"

    def test_btts_one_blanked(self):
        resolved = _both_teams_to_score(MatchResult(2, 0))
        assert resolved.matches_positive is False
        assert resolved.actual_value == "btts_no"

    def test_total_goals_over(self):
        resolved = _total_goals_over_under_2_5(MatchResult(2, 1))
        assert resolved.matches_positive is True

    def test_total_goals_under(self):
        resolved = _total_goals_over_under_2_5(MatchResult(1, 0))
        assert resolved.matches_positive is False

    def test_home_team_total_goals_over(self):
        resolved = _home_team_total_goals_over_under_1_5(MatchResult(2, 0))
        assert resolved.matches_positive is True

    def test_home_team_total_goals_under(self):
        resolved = _home_team_total_goals_over_under_1_5(MatchResult(1, 3))
        assert resolved.matches_positive is False

    def test_moneyline_home_win(self):
        resolved = _moneyline_home_win(MatchResult(5, 2))
        assert resolved.matches_positive is True
        assert resolved.actual_value == "home_win"

    def test_moneyline_away_win(self):
        resolved = _moneyline_home_win(MatchResult(2, 5))
        assert resolved.matches_positive is False
        assert resolved.actual_value == "away_win"

    def test_moneyline_tie_is_unresolved_not_fabricated(self):
        assert _moneyline_home_win(MatchResult(3, 3)) is None

    def test_correct_score_within_grid(self):
        assert _correct_score(MatchResult(2, 1)) == "2-1"

    def test_correct_score_outside_grid_is_other(self):
        assert _correct_score(MatchResult(7, 0)) == "OTHER"

    def test_match_winner_home_win(self):
        assert _match_winner_home_draw_away(MatchResult(2, 1)) == "HOME_WIN"

    @pytest.mark.parametrize(
        "resolver,line",
        [
            (_total_goals_over_under_0_5, 0.5),
            (_total_goals_over_under_1_5, 1.5),
            (_total_goals_over_under_2_5, 2.5),
            (_total_goals_over_under_3_5, 3.5),
            (_total_goals_over_under_4_5, 4.5),
        ],
    )
    def test_total_goals_over_under_lines_use_the_same_full_time_total(self, resolver, line):
        under_result = MatchResult(1, 0)  # 1 total goal
        over_result = MatchResult(3, 3)  # 6 total goals
        assert resolver(under_result).matches_positive is (1 > line)
        assert resolver(over_result).matches_positive is (6 > line)

    def test_away_team_total_goals_over(self):
        resolved = _away_team_total_goals_over_under_1_5(MatchResult(0, 2))
        assert resolved.matches_positive is True

    def test_away_team_total_goals_under(self):
        resolved = _away_team_total_goals_over_under_1_5(MatchResult(3, 1))
        assert resolved.matches_positive is False

    def test_home_clean_sheet_kept(self):
        resolved = _home_clean_sheet(MatchResult(2, 0))
        assert resolved.matches_positive is True
        assert resolved.actual_value == "home_clean_sheet_yes"

    def test_home_clean_sheet_conceded(self):
        resolved = _home_clean_sheet(MatchResult(2, 1))
        assert resolved.matches_positive is False
        assert resolved.actual_value == "home_clean_sheet_no"

    def test_away_clean_sheet_kept(self):
        resolved = _away_clean_sheet(MatchResult(0, 1))
        assert resolved.matches_positive is True

    def test_away_clean_sheet_conceded(self):
        resolved = _away_clean_sheet(MatchResult(1, 1))
        assert resolved.matches_positive is False

    def test_home_win_to_nil_true(self):
        resolved = _home_win_to_nil(MatchResult(2, 0))
        assert resolved.matches_positive is True
        assert resolved.actual_value == "home_win_to_nil_yes"

    def test_home_win_to_nil_false_when_away_scores(self):
        assert _home_win_to_nil(MatchResult(2, 1)).matches_positive is False

    def test_home_win_to_nil_false_when_home_does_not_win(self):
        assert _home_win_to_nil(MatchResult(0, 0)).matches_positive is False
        assert _home_win_to_nil(MatchResult(0, 2)).matches_positive is False

    def test_away_win_to_nil_true(self):
        resolved = _away_win_to_nil(MatchResult(0, 2))
        assert resolved.matches_positive is True
        assert resolved.actual_value == "away_win_to_nil_yes"

    def test_away_win_to_nil_false_when_home_scores(self):
        assert _away_win_to_nil(MatchResult(1, 2)).matches_positive is False

    def test_away_win_to_nil_false_when_away_does_not_win(self):
        assert _away_win_to_nil(MatchResult(0, 0)).matches_positive is False
        assert _away_win_to_nil(MatchResult(2, 0)).matches_positive is False

    def test_match_winner_away_win(self):
        assert _match_winner_home_draw_away(MatchResult(0, 3)) == "AWAY_WIN"

    def test_match_winner_draw_is_a_real_resolvable_outcome(self):
        """Unlike moneyline-style markets, a draw here is not an unmodeled edge case to skip — it's
        one of the market's three real allowed values."""
        assert _match_winner_home_draw_away(MatchResult(1, 1)) == "DRAW"


class TestHalfResultResolvers:
    """Post-M24: first/second-half winner, first-half goals, first-half BTTS. Every resolver here
    must return None (never a fabricated result) whenever the half-time score isn't present on
    MatchResult — that's the honest, currently-universal state for every real fixture in this
    codebase (no provider adapter parses football's half-time score yet)."""

    # -- First half winner (HOME_WIN/DRAW/AWAY_WIN from HT score alone) -------------------------
    def test_first_half_winner_home(self):
        assert _first_half_winner(MatchResult(2, 1, home_score_ht=1, away_score_ht=0)) == "HOME_WIN"

    def test_first_half_winner_away(self):
        assert _first_half_winner(MatchResult(1, 2, home_score_ht=0, away_score_ht=1)) == "AWAY_WIN"

    def test_first_half_winner_draw_0_0(self):
        assert _first_half_winner(MatchResult(1, 1, home_score_ht=0, away_score_ht=0)) == "DRAW"

    def test_first_half_winner_draw_2_2(self):
        assert _first_half_winner(MatchResult(3, 2, home_score_ht=2, away_score_ht=2)) == "DRAW"

    def test_first_half_winner_unresolved_without_half_time_score(self):
        assert _first_half_winner(MatchResult(2, 1)) is None

    # -- Second half winner (derived: FT - HT) ---------------------------------------------------
    def test_second_half_winner_home_ft_3_1_ht_1_1(self):
        assert _second_half_winner(MatchResult(3, 1, home_score_ht=1, away_score_ht=1)) == "HOME_WIN"

    def test_second_half_winner_away_ft_1_3_ht_1_1(self):
        assert _second_half_winner(MatchResult(1, 3, home_score_ht=1, away_score_ht=1)) == "AWAY_WIN"

    def test_second_half_winner_draw_ft_2_2_ht_1_1(self):
        assert _second_half_winner(MatchResult(2, 2, home_score_ht=1, away_score_ht=1)) == "DRAW"

    def test_second_half_winner_draw_ft_1_1_ht_0_0(self):
        assert _second_half_winner(MatchResult(1, 1, home_score_ht=0, away_score_ht=0)) == "DRAW"

    def test_second_half_winner_unresolved_without_half_time_score(self):
        assert _second_half_winner(MatchResult(3, 1)) is None

    def test_second_half_winner_unresolved_when_derived_goals_would_be_negative(self):
        """Impossible/inconsistent data (e.g. a half-time score that's higher than the recorded
        full-time score, from a provider correction race) must never be fabricated or clamped —
        fail closed to unresolved."""
        assert _second_half_winner(MatchResult(1, 1, home_score_ht=2, away_score_ht=0)) is None

    def test_second_half_winner_unresolved_for_malformed_away_side(self):
        assert _second_half_winner(MatchResult(1, 1, home_score_ht=0, away_score_ht=2)) is None

    # -- First half BTTS (binary) -----------------------------------------------------------------
    def test_first_half_btts_yes(self):
        resolved = _first_half_both_teams_to_score(MatchResult(2, 1, home_score_ht=1, away_score_ht=1))
        assert resolved.matches_positive is True
        assert resolved.actual_value == "first_half_btts_yes"

    def test_first_half_btts_no(self):
        resolved = _first_half_both_teams_to_score(MatchResult(2, 0, home_score_ht=1, away_score_ht=0))
        assert resolved.matches_positive is False
        assert resolved.actual_value == "first_half_btts_no"

    def test_first_half_btts_unresolved_without_half_time_score(self):
        assert _first_half_both_teams_to_score(MatchResult(2, 1)) is None

    # -- First half goals over/under 0.5 -----------------------------------------------------------
    def test_first_half_goals_over(self):
        resolved = _first_half_goals_over_under_0_5(MatchResult(2, 1, home_score_ht=1, away_score_ht=0))
        assert resolved.matches_positive is True

    def test_first_half_goals_under(self):
        resolved = _first_half_goals_over_under_0_5(MatchResult(2, 1, home_score_ht=0, away_score_ht=0))
        assert resolved.matches_positive is False

    def test_first_half_goals_unresolved_without_half_time_score(self):
        assert _first_half_goals_over_under_0_5(MatchResult(2, 1)) is None

    # -- Basketball game total points over/under 219.5 --------------------------------------------
    def test_game_total_points_over(self):
        resolved = _total_points_over_under_219_5(MatchResult(115, 110))
        assert resolved.matches_positive is True

    def test_game_total_points_under(self):
        resolved = _total_points_over_under_219_5(MatchResult(105, 100))
        assert resolved.matches_positive is False

    # -- Basketball game total points, four more lines bracketing the median ------------------------
    def test_game_total_points_199_5_over(self):
        assert _total_points_over_under_199_5(MatchResult(105, 100)).matches_positive is True

    def test_game_total_points_199_5_under(self):
        assert _total_points_over_under_199_5(MatchResult(95, 90)).matches_positive is False

    def test_game_total_points_209_5_over(self):
        assert _total_points_over_under_209_5(MatchResult(108, 105)).matches_positive is True

    def test_game_total_points_209_5_under(self):
        assert _total_points_over_under_209_5(MatchResult(100, 100)).matches_positive is False

    def test_game_total_points_229_5_over(self):
        assert _total_points_over_under_229_5(MatchResult(118, 115)).matches_positive is True

    def test_game_total_points_229_5_under(self):
        assert _total_points_over_under_229_5(MatchResult(112, 110)).matches_positive is False

    def test_game_total_points_239_5_over(self):
        assert _total_points_over_under_239_5(MatchResult(125, 120)).matches_positive is True

    def test_game_total_points_239_5_under(self):
        assert _total_points_over_under_239_5(MatchResult(118, 115)).matches_positive is False

    # -- Basketball first half total points over/under 109.5 ---------------------------------------
    def test_first_half_points_over(self):
        resolved = _first_half_points_over_under_109_5(MatchResult(115, 110, home_score_ht=58, away_score_ht=55))
        assert resolved.matches_positive is True

    def test_first_half_points_under(self):
        resolved = _first_half_points_over_under_109_5(MatchResult(105, 100, home_score_ht=50, away_score_ht=50))
        assert resolved.matches_positive is False

    def test_first_half_points_unresolved_without_half_time_score(self):
        assert _first_half_points_over_under_109_5(MatchResult(115, 110)) is None

    # -- Baseball total runs over/under 8.5 ---------------------------------------------------------
    def test_total_runs_over(self):
        resolved = _total_runs_over_under_8_5(MatchResult(5, 4))
        assert resolved.matches_positive is True

    def test_total_runs_under(self):
        resolved = _total_runs_over_under_8_5(MatchResult(3, 2))
        assert resolved.matches_positive is False

    # -- Baseball total runs, four more lines bracketing the median ---------------------------------
    def test_total_runs_6_5_over(self):
        assert _total_runs_over_under_6_5(MatchResult(4, 3)).matches_positive is True

    def test_total_runs_6_5_under(self):
        assert _total_runs_over_under_6_5(MatchResult(3, 3)).matches_positive is False

    def test_total_runs_7_5_over(self):
        assert _total_runs_over_under_7_5(MatchResult(4, 4)).matches_positive is True

    def test_total_runs_7_5_under(self):
        assert _total_runs_over_under_7_5(MatchResult(4, 3)).matches_positive is False

    def test_total_runs_9_5_over(self):
        assert _total_runs_over_under_9_5(MatchResult(5, 5)).matches_positive is True

    def test_total_runs_9_5_under(self):
        assert _total_runs_over_under_9_5(MatchResult(5, 4)).matches_positive is False

    def test_total_runs_10_5_over(self):
        assert _total_runs_over_under_10_5(MatchResult(6, 5)).matches_positive is True

    def test_total_runs_10_5_under(self):
        assert _total_runs_over_under_10_5(MatchResult(5, 5)).matches_positive is False


class TestRegressionMarketResolvers:
    def test_total_score_regression_basketball(self):
        resolved = REGRESSION_MARKET_RESOLVERS["basketball.game_total_points_prediction"](MatchResult(115, 110))
        assert resolved == 225.0

    def test_total_score_regression_baseball(self):
        resolved = REGRESSION_MARKET_RESOLVERS["baseball.total_runs_prediction"](MatchResult(5, 4))
        assert resolved == 9.0


@pytest.mark.asyncio
class TestOutcomeResolutionService:
    async def test_records_correct_outcome_for_matching_positive_prediction(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        prediction = _prediction(market.id, value="positive")
        await prediction_repo.record(prediction)
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "btts_yes"
        assert recorded[0].error == 0.0

    async def test_records_correct_outcome_for_real_domain_label_prediction(self, prediction_repo, market_repo, prediction_outcome_repo):
        """Milestone 9.2 Phase 2: PredictionEngine now stores "YES"/"NO" for this market, not the
        generic "positive"/"negative" — evaluation must score these exactly the same way."""
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="YES"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "btts_yes"
        assert recorded[0].error == 0.0

    async def test_records_incorrect_outcome_for_mismatched_real_domain_label(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="NO"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert recorded[0].actual_value == "btts_yes"
        assert recorded[0].error == 1.0

    async def test_records_incorrect_outcome_for_mismatched_prediction(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        prediction = _prediction(market.id, value="positive")
        await prediction_repo.record(prediction)
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=0, now=T0)

        assert recorded[0].actual_value == "btts_no"
        assert recorded[0].error == 1.0

    async def test_skips_draft_predictions(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="positive", status=PredictionStatus.DRAFT))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert recorded == []

    async def test_skips_markets_whose_resolver_cannot_resolve_this_pass(self, prediction_repo, market_repo, prediction_outcome_repo):
        """football.first_half_winner has a real resolver (post-M24) but no half-time score was
        passed here — the resolver correctly returns None (not "DRAW"), and the service must skip
        it rather than record a fabricated outcome."""
        market = _market("football.first_half_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert recorded == []

    async def test_skips_ties_for_moneyline_style_markets(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("basketball.moneyline")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="positive"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=100, away_score=100, now=T0)

        assert recorded == []

    async def test_is_idempotent_across_repeated_calls(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="positive"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        first = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)
        second = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert len(first) == 1
        assert len(second) == 0

    async def test_only_evaluates_predictions_for_the_given_fixture(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="positive", subject_ref="fx-other"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert recorded == []


@pytest.mark.asyncio
class TestFootballMarketCatalogExpansionResolution:
    """End-to-end resolve_for_fixture coverage for the 2026-08-02 expansion's real resolvers —
    the same fixture completion must correctly resolve several new markets at once."""

    async def test_resolves_a_new_total_goals_line(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.total_goals_over_under_0_5")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="OVER"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=1, away_score=0, now=T0)

        assert len(recorded) == 1
        assert recorded[0].error == 0.0  # 1 total goal is over the 0.5 line — the OVER claim matched

    async def test_resolves_home_clean_sheet(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.home_clean_sheet")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="YES"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=3, away_score=0, now=T0)

        assert recorded[0].actual_value == "home_clean_sheet_yes"
        assert recorded[0].error == 0.0
        # Statistical-baseline charter, Phase 3 — real goal counts populated at the binary branch,
        # for FootballGoalsPoissonAdapter to fit λ_home/λ_away against later.
        assert recorded[0].raw_home_goals == 3
        assert recorded[0].raw_away_goals == 0

    async def test_resolves_away_win_to_nil(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.away_win_to_nil")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="NO"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=0, away_score=2, now=T0)

        # Away won to nil (true), but the prediction claimed NO — mismatched, error=1.0.
        assert recorded[0].actual_value == "away_win_to_nil_yes"
        assert recorded[0].error == 1.0

    async def test_still_skips_first_half_markets_without_half_time_data(self, prediction_repo, market_repo, prediction_outcome_repo):
        """football.first_half_goals has a real resolver (post-M24) but no half-time score is
        available for this fixture (the default/universal state today — no provider adapter
        parses one yet) — must still resolve to unresolved, never fabricated."""
        market = _market("football.first_half_goals")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="OVER"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=1, away_score=1, now=T0)

        assert recorded == []

    async def test_resolves_first_half_goals_when_half_time_score_is_available(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        """The forward-looking case: once a caller genuinely has a half-time score (passed via
        resolve_for_fixture's optional kwargs), the market resolves for real."""
        market = _market("football.first_half_goals")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="OVER"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=2, away_score=1, now=T0, home_score_ht=1, away_score_ht=0
        )

        assert len(recorded) == 1
        assert recorded[0].error == 0.0  # 1 first-half goal is over the 0.5 line — OVER matched

    async def test_resolves_first_half_winner_three_way_when_half_time_score_is_available(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        market = _market("football.first_half_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="DRAW"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=2, away_score=1, now=T0, home_score_ht=1, away_score_ht=1
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "DRAW"
        assert recorded[0].error == 0.0

    async def test_resolves_second_half_winner_derived_from_full_and_half_time_scores(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        market = _market("football.second_half_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=3, away_score=1, now=T0, home_score_ht=1, away_score_ht=1
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "HOME_WIN"  # 2nd half: 2-0
        assert recorded[0].error == 0.0

    async def test_skips_second_half_winner_when_derived_goals_are_impossible(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        """Fail-closed on inconsistent data (e.g. a stale/incorrect half-time score from a
        provider correction race) rather than fabricating or clamping a derived negative."""
        market = _market("football.second_half_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=1, away_score=1, now=T0, home_score_ht=2, away_score_ht=0
        )

        assert recorded == []


@pytest.mark.asyncio
class TestSecondarySportResolvers:
    """POST-M24 Phase 5A — basketball/baseball's real resolvers. Moneyline (all three secondary
    sports) reuses `_moneyline_home_win`; basketball's first-half-winner reuses football's own
    `_first_half_winner` unchanged (basketball's halftime genuinely is quarters 1+2); baseball's
    first-five-innings-winner is new (`_first_five_innings_winner`)."""

    async def test_basketball_moneyline_resolves_home_win(self, prediction_repo, market_repo, prediction_outcome_repo):
        """`MARKET_OUTCOME_LABELS["basketball.moneyline"]` real label pair is ("HOME", "AWAY") —
        distinct from baseball/table_tennis's ("HOME_WIN", "AWAY_WIN"), a pre-existing convention
        this test asserts against exactly, not a normalization this phase introduces."""
        market = _market("basketball.moneyline")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=101, away_score=98, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "home_win"
        assert recorded[0].error == 0.0

    async def test_baseball_moneyline_resolves_away_win(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("baseball.moneyline")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=5, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "away_win"
        assert recorded[0].error == 1.0

    async def test_table_tennis_match_winner_resolves(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("table_tennis.match_winner")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=3, away_score=1, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "home_win"

    async def test_basketball_first_half_winner_reuses_football_resolver_unchanged(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        """Basketball halftime = quarters 1+2 combined — a real rule of the sport, resolved via
        the exact same `_first_half_winner` function football's own first-half market uses."""
        market = _market("basketball.first_half_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=101, away_score=98, now=T0, home_score_ht=54, away_score_ht=50,
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "HOME_WIN"
        assert recorded[0].error == 0.0

    async def test_baseball_first_five_innings_winner_resolves_from_period_scores(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        market = _market("baseball.first_five_innings_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="AWAY_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=3, away_score=4, now=T0, home_score_first5=1, away_score_first5=4,
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "AWAY_WIN"
        assert recorded[0].error == 0.0

    async def test_baseball_first_five_innings_winner_allows_a_real_tie(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        market = _market("baseball.first_five_innings_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="DRAW"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=5, away_score=5, now=T0, home_score_first5=2, away_score_first5=2,
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "DRAW"
        assert recorded[0].error == 0.0

    async def test_baseball_first_five_innings_winner_unresolved_without_segment_data(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        """Never derived from the full-game final score — a game whose first-five-innings segment
        score isn't available must resolve to unresolved, not a guess."""
        market = _market("baseball.first_five_innings_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=5, away_score=2, now=T0)

        assert recorded == []


@pytest.mark.asyncio
class TestBasketballPeriodWinners:
    """POST-M24 Phase 5B — Q1-Q4 and second-half winner markets, backed by real per-quarter
    `Fixture.period_scores` (confirmed via dev.db audit: all 1,708 completed basketball fixtures
    carry complete 4-quarter data). `_quarter_winner` is a factory (one shape, four indices);
    second-half reuses `_second_half_winner` (full-time minus half-time) unchanged."""

    async def test_q1_winner_resolves_home_win(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("basketball.q1_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=101, away_score=98, now=T0,
            home_quarters=(26, 31, 20, 24), away_quarters=(20, 25, 28, 25),
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "HOME_WIN"
        assert recorded[0].error == 0.0

    async def test_q4_winner_resolves_from_the_last_index(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("basketball.q4_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="AWAY_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=101, away_score=98, now=T0,
            home_quarters=(26, 31, 20, 24), away_quarters=(20, 25, 28, 25),
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "AWAY_WIN"
        assert recorded[0].error == 0.0

    async def test_quarter_winner_allows_a_real_tie(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("basketball.q2_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="DRAW"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=100, away_score=100, now=T0,
            home_quarters=(25, 25, 25, 25), away_quarters=(20, 25, 25, 30),
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "DRAW"
        assert recorded[0].error == 0.0

    async def test_quarter_winner_unresolved_without_quarter_data(self, prediction_repo, market_repo, prediction_outcome_repo):
        """Never inferred from the half-time or full-time score — a fixture with no quarter
        breakdown must resolve to unresolved, not a guess."""
        market = _market("basketball.q3_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=101, away_score=98, now=T0)

        assert recorded == []

    async def test_quarter_winner_unresolved_when_fewer_than_four_quarters_recorded(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        market = _market("basketball.q4_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=75, away_score=70, now=T0,
            home_quarters=(26, 31, 18), away_quarters=(20, 25, 25),  # game abandoned before Q4
        )

        assert recorded == []

    async def test_second_half_winner_reuses_the_existing_generic_resolver(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        """`_second_half_winner` (full-time minus half-time) is unchanged — this asserts basketball
        genuinely composes with it via home_score_ht = Q1+Q2, not a duplicate function."""
        market = _market("basketball.second_half_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="AWAY_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture(
            "fx-1", home_score=90, away_score=98, now=T0, home_score_ht=50, away_score_ht=40,
        )

        assert len(recorded) == 1
        assert recorded[0].actual_value == "AWAY_WIN"  # 2H: home 40, away 58
        assert recorded[0].error == 0.0


@pytest.mark.asyncio
class TestThreeWayResolution:
    """Milestone 9.2 Phase 3: football.match_winner is evaluated by direct label equality against
    HOME_WIN/DRAW/AWAY_WIN — WeightedOrdinalPredictor already emits the real label, so there's no
    "positive"/"negative" polarity mapping involved, unlike every other resolved market."""

    async def test_records_correct_outcome_for_matching_home_win_prediction(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.match_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=0, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "HOME_WIN"
        assert recorded[0].error == 0.0

    async def test_records_correct_outcome_for_matching_draw_prediction(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.match_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="DRAW"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=1, away_score=1, now=T0)

        assert recorded[0].actual_value == "DRAW"
        assert recorded[0].error == 0.0

    async def test_records_incorrect_outcome_when_predicted_label_does_not_match(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.match_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="AWAY_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=1, away_score=1, now=T0)

        assert recorded[0].actual_value == "DRAW"
        assert recorded[0].error == 1.0

    async def test_never_skips_a_draw_as_unresolved(self, prediction_repo, market_repo, prediction_outcome_repo):
        """Contrast with basketball.moneyline/table_tennis.match_winner, where an equal score is an
        unmodeled edge case that's silently skipped — for match_winner, a draw is always a real,
        fully-resolvable outcome, never a tie to be discarded."""
        market = _market("football.match_winner", market_kind=MarketKind.HOME_DRAW_AWAY)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=0, away_score=0, now=T0)

        assert len(recorded) == 1
        assert recorded[0].actual_value == "DRAW"


@pytest.mark.asyncio
class TestGridResolution:
    """(2026-08-06) football.correct_score's grid resolver — same direct-label-equality mechanics
    as TestThreeWayResolution, but the real answer is one of 37 labels rather than 3. This is the
    resolver football.correct_score never had before (its resolver_key was None from the market's
    original addition), which was the reason its outcomes never resolved even before the Poisson
    predictor removal."""

    async def test_records_correct_scoreline(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.correct_score", market_kind=MarketKind.CORRECT_SCORE)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="2-1"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert recorded[0].actual_value == "2-1"
        assert recorded[0].error == 0.0
        # Statistical-baseline charter, Phase 3 — real goal counts populated at the GRID branch too.
        assert recorded[0].raw_home_goals == 2
        assert recorded[0].raw_away_goals == 1

    async def test_records_incorrect_scoreline(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.correct_score", market_kind=MarketKind.CORRECT_SCORE)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="1-0"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        assert recorded[0].actual_value == "2-1"
        assert recorded[0].error == 1.0

    async def test_out_of_grid_score_resolves_to_other(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.correct_score", market_kind=MarketKind.CORRECT_SCORE)
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="OTHER"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=8, away_score=0, now=T0)

        assert recorded[0].actual_value == "OTHER"
        assert recorded[0].error == 0.0


@pytest.mark.asyncio
class TestReviewForFixture:
    """The AI Review read path — real predicted-vs-actual per market, never guessed at."""

    async def test_resolved_market_reports_correctness(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="YES"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)
        await service.resolve_for_fixture("fx-1", home_score=2, away_score=1, now=T0)

        rows = await service.review_for_fixture("fx-1")

        assert len(rows) == 1
        assert rows[0].market_key == "football.both_teams_to_score"
        assert rows[0].predicted_value == "YES"
        assert rows[0].actual_value == "YES"
        assert rows[0].is_correct is True
        assert rows[0].evaluated_at == T0

    async def test_unresolved_market_reports_none_rather_than_guessing(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        # football.first_half_goals has a real resolver (post-M24) but resolve_for_fixture was
        # never called here at all — no PredictionOutcome exists for this prediction yet, and this
        # test verifies review_for_fixture reports that honestly rather than resolving anything itself.
        market = _market("football.first_half_goals")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="OVER"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        rows = await service.review_for_fixture("fx-1")

        assert len(rows) == 1
        assert rows[0].actual_value is None
        assert rows[0].is_correct is None
        assert rows[0].evaluated_at is None

    async def test_skips_draft_predictions(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="YES", status=PredictionStatus.DRAFT))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        rows = await service.review_for_fixture("fx-1")

        assert rows == []

    async def test_only_reviews_the_given_fixture(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.both_teams_to_score")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="YES", subject_ref="fx-other"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        rows = await service.review_for_fixture("fx-1")

        assert rows == []

    async def test_correct_score_sorts_last_regardless_of_prediction_order(
        self, prediction_repo, market_repo, prediction_outcome_repo
    ):
        # Correct Score is the hardest market to call exactly right and is already excluded from
        # the landing page's hero carousel for the same reason — the actual-vs-predicted list
        # should lead with higher-signal markets, never let Correct Score sit first by accident of
        # insertion order. Display order only: it's still a normal row, just sorted last.
        correct_score_market = _market("football.correct_score", market_kind=MarketKind.CORRECT_SCORE)
        winner_market = _market("football.match_winner")
        await market_repo.upsert(correct_score_market)
        await market_repo.upsert(winner_market)
        await prediction_repo.record(_prediction(correct_score_market.id, value="1-1"))
        await prediction_repo.record(_prediction(winner_market.id, value="HOME_WIN"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        rows = await service.review_for_fixture("fx-1")

        assert [row.market_key for row in rows] == ["football.match_winner", "football.correct_score"]
