from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.outcome_resolution_service import (
    MatchResult,
    OutcomeResolutionService,
    _away_clean_sheet,
    _away_team_total_goals_over_under_1_5,
    _away_win_to_nil,
    _both_teams_to_score,
    _correct_score,
    _home_clean_sheet,
    _home_team_total_goals_over_under_1_5,
    _home_win_to_nil,
    _match_winner_home_draw_away,
    _moneyline_home_win,
    _total_goals_over_under_0_5,
    _total_goals_over_under_1_5,
    _total_goals_over_under_2_5,
    _total_goals_over_under_3_5,
    _total_goals_over_under_4_5,
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

    async def test_skips_markets_without_a_registered_resolver(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.first_half_winner")  # no resolver — no first-half score data available
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="positive"))
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

    async def test_resolves_away_win_to_nil(self, prediction_repo, market_repo, prediction_outcome_repo):
        market = _market("football.away_win_to_nil")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="NO"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=0, away_score=2, now=T0)

        # Away won to nil (true), but the prediction claimed NO — mismatched, error=1.0.
        assert recorded[0].actual_value == "away_win_to_nil_yes"
        assert recorded[0].error == 1.0

    async def test_still_skips_first_half_markets_with_no_resolver(self, prediction_repo, market_repo, prediction_outcome_repo):
        """first_half_goals is seeded PRODUCTION (2026-08-02) but has no resolver — no sub-match
        score data exists to evaluate it against, and it must never be silently fabricated."""
        market = _market("football.first_half_goals")
        await market_repo.upsert(market)
        await prediction_repo.record(_prediction(market.id, value="OVER"))
        service = OutcomeResolutionService(predictions=prediction_repo, markets=market_repo, outcomes=prediction_outcome_repo)

        recorded = await service.resolve_for_fixture("fx-1", home_score=1, away_score=1, now=T0)

        assert recorded == []


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
        market = _market("football.first_half_goals")  # no registered resolver
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
