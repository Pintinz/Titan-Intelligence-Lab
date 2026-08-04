"""Closes the self-learning loop's missing first link: turning a completed fixture's real final
score into `PredictionOutcome` records.

Audit finding (2026-08-02): `PredictionOutcomeRepositoryPort.record()` had zero production call
sites — evaluation, calibration fitting, concept/feature drift, and dataset building all read
`PredictionOutcome` history correctly, but nothing ever wrote it, so every one of those real
subsystems ran permanently starved. This service is the write side.

A second, deeper gap made a naive "just call record()" fix dishonest: the generic predictors
(`weighted_scoring.py`) persist `Prediction.value` as the bare strings "positive"/"negative" (for
`MarketKind.BINARY`) with no stored mapping onto a market's real-world outcome label. Guessing at
a hidden pre-existing convention would risk silently scoring every outcome backwards.

`MARKET_OUTCOME_RESOLVERS` below is that missing mapping, added deliberately and narrowly: one
resolver per market_key where (a) the market's own name states an unambiguous real-world question
("Both Teams To Score", "Total Goals Over/Under 2.5") and (b) the answer is fully computable from
a `Fixture`'s final score alone. "Positive" is defined, per resolver, as the market's own named
affirmative side (BTTS/clean sheet/win-to-nil: yes; Over markets: over; Moneyline/Match Winner:
home team wins — the standard quotation convention when no other line is specified). Every other
currently-seeded market (spreads/handicaps needing a stored line, segment/first-half/second-half
winners and first-half goals/BTTS needing sub-match score data this platform doesn't ingest yet,
race-to/set markets needing point-by-point or set-by-set data, player props needing player-level
statistics, correct-score markets whose predictor output isn't yet a real scoreline) has no
resolver and is silently skipped — never fabricated.

Milestone 9.2 Phase 2 (`modules.predictions.application.outcome_label_mapper`) closed the second
gap for the markets with a resolver above (six originally; nine more added in the 2026-08-02
football market catalog expansion): `PredictionEngine` now stores the market's real label (e.g.
"YES"/"OVER"/"HOME_WIN") instead of the generic "positive"/"negative" for them. This module's
`predicted_positive` check goes through `real_label_is_positive`, which recognizes both the real
label and (for safety across a rolling deploy) the legacy generic value — so this module didn't
need to change *what* it resolves, only how it reads a prediction's stored value.

Milestone 9.2 Phase 3 adds a second, genuinely different resolution shape: `THREE_WAY_MARKET_RESOLVERS`
for markets whose real answer is one of three unambiguous labels (`football.match_winner`'s
HOME_WIN/DRAW/AWAY_WIN) rather than an affirmative/negative pair. There's no "positive side" to a
draw, so `real_label_is_positive`'s binary polarity check doesn't apply here — `WeightedOrdinalPredictor`
already emits the exact real label (never "positive"/"negative"), so this path is direct label
equality against the resolved actual result, nothing to map.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.application.outcome_label_mapper import real_label_is_positive
from modules.predictions.domain.entities import PredictionOutcome
from modules.predictions.domain.value_objects import PredictionOutcomeId
from modules.predictions.ports.repositories import (
    MarketRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)


@dataclass(frozen=True)
class MatchResult:
    home_score: int
    away_score: int


@dataclass(frozen=True)
class ResolvedOutcome:
    actual_value: str  # human-readable real-world fact, stored on PredictionOutcome
    matches_positive: bool  # whether this fact is the market's own-named affirmative side


def _both_teams_to_score(result: MatchResult) -> ResolvedOutcome:
    scored_both = result.home_score >= 1 and result.away_score >= 1
    return ResolvedOutcome("btts_yes" if scored_both else "btts_no", matches_positive=scored_both)


def _total_goals_over_under(line: float) -> Callable[[MatchResult], ResolvedOutcome]:
    """Factory for a fixed-line total-goals resolver — every line is computed identically from
    the same `home_score + away_score` sum, only the threshold differs, so one shape serves all
    of them rather than duplicating near-identical functions per line."""

    def _resolve(result: MatchResult) -> ResolvedOutcome:
        total = result.home_score + result.away_score
        over = total > line
        return ResolvedOutcome(f"total_goals_{total}_{'over' if over else 'under'}_{line}", matches_positive=over)

    return _resolve


_total_goals_over_under_0_5 = _total_goals_over_under(0.5)
_total_goals_over_under_1_5 = _total_goals_over_under(1.5)
_total_goals_over_under_2_5 = _total_goals_over_under(2.5)
_total_goals_over_under_3_5 = _total_goals_over_under(3.5)
_total_goals_over_under_4_5 = _total_goals_over_under(4.5)


def _home_team_total_goals_over_under_1_5(result: MatchResult) -> ResolvedOutcome:
    over = result.home_score > 1.5
    return ResolvedOutcome(f"home_goals_{result.home_score}_{'over' if over else 'under'}_1.5", matches_positive=over)


def _away_team_total_goals_over_under_1_5(result: MatchResult) -> ResolvedOutcome:
    over = result.away_score > 1.5
    return ResolvedOutcome(f"away_goals_{result.away_score}_{'over' if over else 'under'}_1.5", matches_positive=over)


def _home_clean_sheet(result: MatchResult) -> ResolvedOutcome:
    kept = result.away_score == 0
    return ResolvedOutcome("home_clean_sheet_yes" if kept else "home_clean_sheet_no", matches_positive=kept)


def _away_clean_sheet(result: MatchResult) -> ResolvedOutcome:
    kept = result.home_score == 0
    return ResolvedOutcome("away_clean_sheet_yes" if kept else "away_clean_sheet_no", matches_positive=kept)


def _home_win_to_nil(result: MatchResult) -> ResolvedOutcome:
    won_to_nil = result.home_score > result.away_score and result.away_score == 0
    return ResolvedOutcome("home_win_to_nil_yes" if won_to_nil else "home_win_to_nil_no", matches_positive=won_to_nil)


def _away_win_to_nil(result: MatchResult) -> ResolvedOutcome:
    won_to_nil = result.away_score > result.home_score and result.home_score == 0
    return ResolvedOutcome("away_win_to_nil_yes" if won_to_nil else "away_win_to_nil_no", matches_positive=won_to_nil)


def _moneyline_home_win(result: MatchResult) -> ResolvedOutcome | None:
    if result.home_score == result.away_score:
        return None  # this market assumes a decisive winner (basketball/baseball/table tennis all do) — a
        # tie here means an unmodeled scenario (e.g. an unfinished/abandoned fixture slipping through as
        # COMPLETED with equal scores), not a real "no winner" case worth fabricating a call for.
    home_won = result.home_score > result.away_score
    return ResolvedOutcome("home_win" if home_won else "away_win", matches_positive=home_won)


MARKET_OUTCOME_RESOLVERS: dict[str, Callable[[MatchResult], ResolvedOutcome | None]] = {
    "football.both_teams_to_score": _both_teams_to_score,
    "football.total_goals_over_under": _total_goals_over_under_2_5,
    "football.total_goals_over_under_0_5": _total_goals_over_under_0_5,
    "football.total_goals_over_under_1_5": _total_goals_over_under_1_5,
    "football.total_goals_over_under_3_5": _total_goals_over_under_3_5,
    "football.total_goals_over_under_4_5": _total_goals_over_under_4_5,
    "football.home_team_total_goals": _home_team_total_goals_over_under_1_5,
    "football.away_team_total_goals": _away_team_total_goals_over_under_1_5,
    "football.home_clean_sheet": _home_clean_sheet,
    "football.away_clean_sheet": _away_clean_sheet,
    "football.home_win_to_nil": _home_win_to_nil,
    "football.away_win_to_nil": _away_win_to_nil,
    "basketball.moneyline": _moneyline_home_win,
    "baseball.moneyline": _moneyline_home_win,
    "table_tennis.match_winner": _moneyline_home_win,
}


def _match_winner_home_draw_away(result: MatchResult) -> str:
    if result.home_score > result.away_score:
        return "HOME_WIN"
    if result.away_score > result.home_score:
        return "AWAY_WIN"
    return "DRAW"


# Three-outcome markets (Milestone 9.2 Phase 3): the resolved answer is one of three unambiguous
# real labels with no affirmative/negative polarity, so these return the label directly rather
# than a `ResolvedOutcome` — evaluated by direct equality against the prediction's stored value.
THREE_WAY_MARKET_RESOLVERS: dict[str, Callable[[MatchResult], str]] = {
    "football.match_winner": _match_winner_home_draw_away,
}


@dataclass
class OutcomeResolutionService:
    predictions: PredictionRepositoryPort
    markets: MarketRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort

    async def resolve_for_fixture(
        self, fixture_id: str, home_score: int, away_score: int, now: datetime
    ) -> list[PredictionOutcome]:
        """Called once a fixture is known COMPLETED with a final score. For every PUBLISHED
        prediction on that fixture whose market has a registered resolver, records the real
        outcome — idempotently, so a fixture re-synced after it's already evaluated (e.g. a
        provider re-reporting the same final score) does not create duplicate outcome rows."""
        result = MatchResult(home_score, away_score)
        recorded: list[PredictionOutcome] = []
        for prediction in await self.predictions.list_by_subject(fixture_id):
            if not prediction.is_published():
                continue
            if await self.outcomes.get_for_prediction(prediction.id) is not None:
                continue  # already evaluated

            market = await self.markets.get(prediction.market_id)
            if market is None:
                continue

            three_way_resolver = THREE_WAY_MARKET_RESOLVERS.get(market.market_key)
            if three_way_resolver is not None:
                actual_label = three_way_resolver(result)
                error = 0.0 if prediction.value == actual_label else 1.0
                outcome = PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()),
                    prediction_id=prediction.id,
                    actual_value=actual_label,
                    error=error,
                    evaluated_at=now,
                )
                recorded.append(await self.outcomes.record(outcome))
                continue

            resolver = MARKET_OUTCOME_RESOLVERS.get(market.market_key)
            if resolver is None:
                continue
            # Milestone 9.2 Phase 2: `prediction.value` is now the market's real label (e.g.
            # "YES"/"OVER"/"HOME_WIN") for markets in MARKET_OUTCOME_LABELS, not the generic
            # predictor's bare "positive"/"negative" — `real_label_is_positive` recognizes both,
            # so a prediction generated before or after that change evaluates the same way.
            predicted_positive = real_label_is_positive(market.market_key, prediction.value)
            if predicted_positive is None:
                continue  # neither a real label for this market nor the legacy generic value

            resolved = resolver(result)
            if resolved is None:
                continue

            error = 0.0 if predicted_positive == resolved.matches_positive else 1.0
            outcome = PredictionOutcome(
                id=PredictionOutcomeId(uuid4()),
                prediction_id=prediction.id,
                actual_value=resolved.actual_value,
                error=error,
                evaluated_at=now,
            )
            recorded.append(await self.outcomes.record(outcome))
        return recorded
