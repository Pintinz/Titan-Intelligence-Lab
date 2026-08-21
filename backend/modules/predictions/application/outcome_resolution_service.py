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

ML-architecture consolidation follow-up (2026-08-06): `GRID_MARKET_RESOLVERS` is a third resolution
shape, same direct-label-equality mechanics as `THREE_WAY_MARKET_RESOLVERS` but for a market whose
real answer is one of an arbitrarily large finite set of labels rather than exactly three —
`football.correct_score`'s own `_correct_score_grid()` (`market_outcome_registry.py`) bucketed
scoreline, resolved straight from the final score with no stored line/threshold needed. This is the
resolver `football.correct_score` never had (its catalog entry's `resolver_key` was `None` since
the market was first added) — the gap that left it permanently unable to accumulate real training
outcomes even before the Poisson-predictor removal, confirmed by dev.db showing 0 resolved outcomes
against 12 stale predictions versus every other formerly-Poisson-served market already resolving
real outcomes as its (already-wired) resolver runs. `_label_from_outcome` (dataset_builder_service.py)
is the piece that turns this resolver's output into a trainable multiclass label.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.application.outcome_label_mapper import (
    MARKET_OUTCOME_LABELS,
    real_label_is_positive,
    real_outcome_is_positive,
)
from modules.predictions.domain.entities import PredictionOutcome
from modules.predictions.domain.market_outcome_registry import MARKET_OUTCOME_CATALOG
from modules.predictions.domain.value_objects import PredictionOutcomeId
from modules.predictions.ports.repositories import (
    MarketRepositoryPort,
    PredictionOutcomeRepositoryPort,
    PredictionRepositoryPort,
)


@dataclass
class MarketReview:
    """One market's real reading for the AI Review surface — predicted vs actual, when known."""

    market_id: str
    market_key: str
    market_name: str
    predicted_value: str
    probability: float
    confidence: float
    probability_distribution: dict[str, float]
    top_positive_features: list[tuple[str, float]]
    top_negative_features: list[tuple[str, float]]
    ai_explanation: str | None
    generated_at: datetime | None
    actual_value: str | None
    is_correct: bool | None
    evaluated_at: datetime | None


@dataclass(frozen=True)
class MatchResult:
    home_score: int
    away_score: int
    # Milestone (post-M24) — half-time score, when the fixture's provenance genuinely carries one
    # (Fixture.period_scores with kind="half" for football, or kind="quarter" for basketball —
    # basketball's own halftime is legitimately quarters 1+2 combined, the real rule of the sport,
    # not a football convention borrowed for a different game). None for a fixture whose provider
    # never reports period-level scores, or (basketball) whose game hasn't reached Q2. Never
    # fabricated, never inferred from the final score.
    home_score_ht: int | None = None
    away_score_ht: int | None = None
    # POST-M24 Phase 5A — baseball's "first five innings" segment score (innings 1-5 combined),
    # from Fixture.period_scores with kind="inning". A distinct segment from "half-time" (baseball
    # has no halftime), backing `baseball.first_five_innings_winner`. None unless all five innings
    # genuinely have a recorded score for both sides — never derived from a partial count.
    home_score_first5: int | None = None
    away_score_first5: int | None = None
    # POST-M24 Phase 5B — basketball's individual per-quarter points, from Fixture.period_scores
    # (kind="quarter"). Backs the four quarter-winner markets; distinct from home_score_ht (Q1+Q2
    # combined) since a quarter winner needs each period in isolation, not a running total. None
    # unless the fixture's provenance genuinely carries a quarter-level breakdown — never inferred
    # from the half-time or full-time score.
    home_quarters: tuple[int, ...] | None = None
    away_quarters: tuple[int, ...] | None = None


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


def _total_points_over_under(line: float) -> Callable[[MatchResult], ResolvedOutcome]:
    """Factory for a fixed-line total-points resolver (basketball full-time score) — same shape as
    `_total_goals_over_under`, computed from `home_score + away_score`. Line only differs per call
    site, same reasoning as the goals factory above."""

    def _resolve(result: MatchResult) -> ResolvedOutcome:
        total = result.home_score + result.away_score
        over = total > line
        return ResolvedOutcome(f"total_points_{total}_{'over' if over else 'under'}_{line}", matches_positive=over)

    return _resolve


# 219.5 is the real median of this platform's own 1,708 completed basketball fixtures (min 118,
# max 397, median 220.0, mean 214.8, dev.db audit) — not an arbitrary guess, same grounding as
# football's 2.5-goals line.
_total_points_over_under_219_5 = _total_points_over_under(219.5)

# POST-M24 Phase 15 — four more lines bracketing the median, same "unit-increment spread around the
# real central tendency" shape as football's total_goals_over_under_0_5/1_5/3_5/4_5 around 2.5.
# Basketball scores in ~10-point increments, not football's ~1-goal increments, so the bracket is
# scaled accordingly: real dev.db percentiles for the same 1,708-fixture population are p25=199,
# median=220, p75=237 — 199.5/209.5/229.5/239.5 are real, evidence-grounded brackets around the
# already-real 219.5 line, not arbitrary round numbers.
_total_points_over_under_199_5 = _total_points_over_under(199.5)
_total_points_over_under_209_5 = _total_points_over_under(209.5)
_total_points_over_under_229_5 = _total_points_over_under(229.5)
_total_points_over_under_239_5 = _total_points_over_under(239.5)


def _total_runs_over_under(line: float) -> Callable[[MatchResult], ResolvedOutcome]:
    """Factory for a fixed-line total-runs resolver (baseball full-time score) — same shape as
    `_total_goals_over_under`/`_total_points_over_under`, computed from `home_score + away_score`.
    POST-M24 Phase 13 — `baseball.total_runs` had never had a resolver wired at all (0 real
    predictions/outcomes ever recorded, confirmed via direct dev.db audit), not a missing-data
    problem: the real final score this resolver needs already exists for all 3,912 completed
    baseball fixtures."""

    def _resolve(result: MatchResult) -> ResolvedOutcome:
        total = result.home_score + result.away_score
        over = total > line
        return ResolvedOutcome(f"total_runs_{total}_{'over' if over else 'under'}_{line}", matches_positive=over)

    return _resolve


# 8.5 is the real median/mean of this platform's own 3,912 completed baseball fixtures (min 0,
# max 29, median 8.0, mean 8.75, dev.db audit) — matches the real-world MLB total-runs betting
# convention, not an arbitrary guess.
_total_runs_over_under_8_5 = _total_runs_over_under(8.5)

# POST-M24 Phase 15 — four more lines bracketing the median, mirroring football's unit-increment
# spread around its own central line (0.5/1.5/2.5/3.5/4.5 around 2.5 goals). Baseball, like
# football, scores in whole-run increments, so a 1-run bracket is the right granularity: real
# dev.db percentiles for the same 3,913-fixture population are p25=5, median=8, p75=12 —
# 6.5/7.5/9.5/10.5 are real, evidence-grounded brackets around the already-real 8.5 line.
_total_runs_over_under_6_5 = _total_runs_over_under(6.5)
_total_runs_over_under_7_5 = _total_runs_over_under(7.5)
_total_runs_over_under_9_5 = _total_runs_over_under(9.5)
_total_runs_over_under_10_5 = _total_runs_over_under(10.5)


# POST-M24 Phase 16 — real REGRESSION resolvers (a continuous predicted total, not just an
# Over/Under call against a fixed line) for basketball.game_total_points_prediction and
# baseball.total_runs_prediction. Both sports use the identical `home_score + away_score`
# computation the fixed-line TOTAL resolvers above already use — the only thing that changes is
# what gets done with it: a classification resolver reduces it to a boolean against a line, this
# returns the real number itself, for DatasetBuilder's REGRESSION branch (`_label_from_outcome`,
# `float(actual_value)`) to train against directly.
def _total_score_regression(result: MatchResult) -> float:
    return float(result.home_score + result.away_score)


REGRESSION_MARKET_RESOLVERS: dict[str, Callable[[MatchResult], float | None]] = {
    "basketball.game_total_points_prediction": _total_score_regression,
    "baseball.total_runs_prediction": _total_score_regression,
}


def _first_half_points_over_under_109_5(result: MatchResult) -> ResolvedOutcome | None:
    """Basketball's genuine half-time total (Q1+Q2 combined) — `MatchResult.home_score_ht`/
    `away_score_ht` are always populated for basketball (unlike football's still-unwired half-time
    ingestion, see `_first_half_goals_over_under_0_5` below), since all 1,708 completed basketball
    fixtures carry a real per-quarter breakdown (confirmed via direct dev.db audit). 109.5 is the
    real median of that same population (min 52, max 193, median 110.0, mean 107.6). `None` when
    the half-time score genuinely isn't present — never derived from the full-time score."""
    if result.home_score_ht is None or result.away_score_ht is None:
        return None
    total = result.home_score_ht + result.away_score_ht
    over = total > 109.5
    return ResolvedOutcome(f"first_half_points_{total}_{'over' if over else 'under'}_109.5", matches_positive=over)


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


def _first_half_both_teams_to_score(result: MatchResult) -> ResolvedOutcome | None:
    """Milestone (post-M24) — same shape as `_both_teams_to_score`, but against the half-time
    score, which is only ever present on a fixture whose provider adapter parsed one (`MatchResult
    .home_score_ht`/`away_score_ht`). `None` here means "not resolvable yet", handled by
    `resolve_for_fixture` exactly like every other resolver's `None` — the prediction is simply
    skipped this pass, never scored against a fabricated half-time result."""
    if result.home_score_ht is None or result.away_score_ht is None:
        return None
    scored_both = result.home_score_ht >= 1 and result.away_score_ht >= 1
    return ResolvedOutcome(
        "first_half_btts_yes" if scored_both else "first_half_btts_no", matches_positive=scored_both
    )


def _first_half_goals_over_under_0_5(result: MatchResult) -> ResolvedOutcome | None:
    """Same `_total_goals_over_under` shape and 0.5 line as the market's own declared name
    ("First Half Goals Over/Under 0.5", `market_seeding.py`), computed against the half-time score
    only — `None` (unresolved) when it isn't present, never derived from the full-time score."""
    if result.home_score_ht is None or result.away_score_ht is None:
        return None
    total = result.home_score_ht + result.away_score_ht
    over = total > 0.5
    return ResolvedOutcome(
        f"first_half_goals_{total}_{'over' if over else 'under'}_0.5", matches_positive=over
    )


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
    "football.first_half_both_teams_to_score": _first_half_both_teams_to_score,
    "football.first_half_goals": _first_half_goals_over_under_0_5,
    "basketball.moneyline": _moneyline_home_win,
    "basketball.game_total_points": _total_points_over_under_219_5,
    "basketball.game_total_points_199_5": _total_points_over_under_199_5,
    "basketball.game_total_points_209_5": _total_points_over_under_209_5,
    "basketball.game_total_points_229_5": _total_points_over_under_229_5,
    "basketball.game_total_points_239_5": _total_points_over_under_239_5,
    "basketball.first_half_total_points": _first_half_points_over_under_109_5,
    "baseball.moneyline": _moneyline_home_win,
    "baseball.total_runs": _total_runs_over_under_8_5,
    "baseball.total_runs_6_5": _total_runs_over_under_6_5,
    "baseball.total_runs_7_5": _total_runs_over_under_7_5,
    "baseball.total_runs_9_5": _total_runs_over_under_9_5,
    "baseball.total_runs_10_5": _total_runs_over_under_10_5,
    "table_tennis.match_winner": _moneyline_home_win,
}


def _correct_score(result: MatchResult) -> str:
    """Buckets the real final score into `football.correct_score`'s own declared grid
    (`MARKET_OUTCOME_CATALOG`'s `allowed_values`, sourced from `_correct_score_grid()`) — any score
    outside the grid (either side scoring beyond the grid's `max_goals`) resolves to the same
    "OTHER" catch-all the grid itself reserves for that case, never a fabricated cell."""
    scoreline = f"{result.home_score}-{result.away_score}"
    allowed_values = MARKET_OUTCOME_CATALOG["football.correct_score"].allowed_values
    return scoreline if scoreline in allowed_values else "OTHER"


GRID_MARKET_RESOLVERS: dict[str, Callable[[MatchResult], str | None]] = {
    "football.correct_score": _correct_score,
}


def _match_winner_home_draw_away(result: MatchResult) -> str:
    if result.home_score > result.away_score:
        return "HOME_WIN"
    if result.away_score > result.home_score:
        return "AWAY_WIN"
    return "DRAW"


def _first_half_winner(result: MatchResult) -> str | None:
    """Milestone (post-M24) — same HOME_WIN/DRAW/AWAY_WIN shape as `_match_winner_home_draw_away`,
    against the half-time score. `None` (unresolved, not "DRAW") when the fixture's provenance
    doesn't carry a half-time score — `resolve_for_fixture`'s three-way branch skips a `None`
    result exactly like the binary-market branch already does, never recording an outcome for it."""
    if result.home_score_ht is None or result.away_score_ht is None:
        return None
    if result.home_score_ht > result.away_score_ht:
        return "HOME_WIN"
    if result.away_score_ht > result.home_score_ht:
        return "AWAY_WIN"
    return "DRAW"


def _second_half_winner(result: MatchResult) -> str | None:
    """Second-half goals are never ingested directly — derived as full-time minus half-time, per
    this market's own spec (`second_half_home_goals = full_time_home_goals -
    first_half_home_goals`). `None` (unresolved) both when the half-time score is missing and when
    the derived second-half goal counts would be negative (impossible/inconsistent data — e.g. a
    provider correction that changed the full-time score without a matching half-time correction);
    never fabricated, never clamped to zero."""
    if result.home_score_ht is None or result.away_score_ht is None:
        return None
    home_2h = result.home_score - result.home_score_ht
    away_2h = result.away_score - result.away_score_ht
    if home_2h < 0 or away_2h < 0:
        return None
    if home_2h > away_2h:
        return "HOME_WIN"
    if away_2h > home_2h:
        return "AWAY_WIN"
    return "DRAW"


def _quarter_winner(quarter_index: int) -> Callable[[MatchResult], str | None]:
    """POST-M24 Phase 5B — factory for a basketball single-quarter winner resolver. Every quarter
    is resolved identically from the same `home_quarters`/`away_quarters` arrays, only the index
    differs, so one shape serves all four (`_quarter_winner(0)` through `_quarter_winner(3)`)
    rather than four near-identical functions — same reasoning as `_total_goals_over_under`
    above. `None` (unresolved) when the fixture's period data doesn't cover this quarter (e.g. a
    game abandoned early) — never inferred from the half-time or full-time score."""

    def _resolve(result: MatchResult) -> str | None:
        if result.home_quarters is None or result.away_quarters is None:
            return None
        if quarter_index >= len(result.home_quarters) or quarter_index >= len(result.away_quarters):
            return None
        home_q = result.home_quarters[quarter_index]
        away_q = result.away_quarters[quarter_index]
        if home_q is None or away_q is None:
            return None
        if home_q > away_q:
            return "HOME_WIN"
        if away_q > home_q:
            return "AWAY_WIN"
        return "DRAW"  # a tied quarter is a real, common basketball outcome — not unresolved

    return _resolve


_q1_winner = _quarter_winner(0)
_q2_winner = _quarter_winner(1)
_q3_winner = _quarter_winner(2)
_q4_winner = _quarter_winner(3)


def _first_five_innings_winner(result: MatchResult) -> str | None:
    """POST-M24 Phase 5A — baseball's "First Five Innings Winner" (a real, standard baseball
    prop-betting segment, distinct from a football/basketball half): resolved from the combined
    score across innings 1-5 only. `None` (unresolved) when that segment score isn't available —
    never derived from the full-game final score, and never from a game that was postponed/
    abandoned before completing five innings on both sides."""
    if result.home_score_first5 is None or result.away_score_first5 is None:
        return None
    if result.home_score_first5 > result.away_score_first5:
        return "HOME_WIN"
    if result.away_score_first5 > result.home_score_first5:
        return "AWAY_WIN"
    return "DRAW"  # a tie after five innings is a real, common baseball outcome — not unresolved


# Three-outcome markets (Milestone 9.2 Phase 3): the resolved answer is one of three unambiguous
# real labels with no affirmative/negative polarity, so these return the label directly rather
# than a `ResolvedOutcome` — evaluated by direct equality against the prediction's stored value.
# `None` means "not resolvable this pass" (Milestone post-M24's half-result resolvers use this;
# the original two never did) — `resolve_for_fixture` must skip a `None` here, not record it.
THREE_WAY_MARKET_RESOLVERS: dict[str, Callable[[MatchResult], str | None]] = {
    "football.match_winner": _match_winner_home_draw_away,
    "football.first_half_winner": _first_half_winner,
    "football.second_half_winner": _second_half_winner,
    # POST-M24 Phase 5A — `_first_half_winner` is already generic (reads MatchResult.home_score_ht/
    # away_score_ht, no football-specific logic inside it); basketball's own halftime is genuinely
    # the same real-world concept (score after quarters 1+2), so this reuses the exact function,
    # not a duplicate.
    "basketball.first_half_winner": _first_half_winner,
    # POST-M24 Phase 5B — `_second_half_winner` is already generic (full-time minus half-time via
    # MatchResult.home_score/home_score_ht), and basketball's home_score_ht is genuinely Q1+Q2, so
    # `home_score - home_score_ht` is genuinely Q3+Q4 (the real second half) — reused directly, not
    # duplicated, exactly like `_first_half_winner` above.
    "basketball.second_half_winner": _second_half_winner,
    "basketball.q1_winner": _q1_winner,
    "basketball.q2_winner": _q2_winner,
    "basketball.q3_winner": _q3_winner,
    "basketball.q4_winner": _q4_winner,
    "baseball.first_five_innings_winner": _first_five_innings_winner,
}


def _display_actual_value(market_key: str, prediction_value: str, outcome: PredictionOutcome | None) -> str | None:
    """`PredictionOutcome.actual_value` is a raw internal fact string for the nine `MARKET_OUTCOME_RESOLVERS`
    binary markets (e.g. "away_win_to_nil_yes") — accurate for training/calibration, which read it
    through `real_outcome_is_positive` rather than the string itself, but not something a user should
    read verbatim next to a "YES"/"NO" predicted value. For exactly those markets, re-derive the same
    real label (`MARKET_OUTCOME_LABELS`) the predicted value already uses, via the same polarity
    recovery the Dataset Builder and Calibration Fitting already share. Every other market (three-way,
    grid) already stores its real label directly and passes through unchanged."""
    if outcome is None:
        return None
    pair = MARKET_OUTCOME_LABELS.get(market_key)
    if pair is None:
        return outcome.actual_value
    positive = real_outcome_is_positive(market_key, prediction_value, outcome.error)
    if positive is None:
        return outcome.actual_value
    return pair.positive_label if positive else pair.negative_label


@dataclass
class OutcomeResolutionService:
    predictions: PredictionRepositoryPort
    markets: MarketRepositoryPort
    outcomes: PredictionOutcomeRepositoryPort

    async def resolve_for_fixture(
        self,
        fixture_id: str,
        home_score: int,
        away_score: int,
        now: datetime,
        *,
        home_score_ht: int | None = None,
        away_score_ht: int | None = None,
        home_score_first5: int | None = None,
        away_score_first5: int | None = None,
        home_quarters: tuple[int, ...] | None = None,
        away_quarters: tuple[int, ...] | None = None,
    ) -> list[PredictionOutcome]:
        """Called once a fixture is known COMPLETED with a final score. For every PUBLISHED
        prediction on that fixture whose market has a registered resolver, records the real
        outcome — idempotently, so a fixture re-synced after it's already evaluated (e.g. a
        provider re-reporting the same final score) does not create duplicate outcome rows.

        `home_score_ht`/`away_score_ht` (Milestone post-M24): optional half-time (football) or
        first-half (basketball) score, sourced from the caller's `Fixture.period_scores` when it
        genuinely carries one. `home_score_first5`/`away_score_first5` (Phase 5A): optional
        baseball first-five-innings score, same sourcing. Every existing caller that doesn't pass
        them keeps behaving exactly as before — every segment-result market's resolver already
        treats a missing segment score as "not resolvable yet", never as a reason to fail the
        whole fixture's other markets.

        `home_quarters`/`away_quarters` (Phase 5B): optional basketball per-quarter points tuple,
        same sourcing/optionality posture as the fields above."""
        result = MatchResult(
            home_score, away_score, home_score_ht, away_score_ht, home_score_first5, away_score_first5,
            home_quarters, away_quarters,
        )
        recorded: list[PredictionOutcome] = []
        for prediction in await self.predictions.list_by_subject(fixture_id):
            if not prediction.is_published():
                continue
            if await self.outcomes.get_for_prediction(prediction.id) is not None:
                continue  # already evaluated

            market = await self.markets.get(prediction.market_id)
            if market is None:
                continue

            exact_label_resolver = THREE_WAY_MARKET_RESOLVERS.get(market.market_key) or GRID_MARKET_RESOLVERS.get(
                market.market_key
            )
            if exact_label_resolver is not None:
                actual_label = exact_label_resolver(result)
                if actual_label is None:
                    continue  # not resolvable this pass (e.g. half-time score not yet available) — never
                    # recorded as a fabricated/None outcome; will resolve on a later pass once real data exists
                error = 0.0 if prediction.value == actual_label else 1.0
                outcome = PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()),
                    prediction_id=prediction.id,
                    actual_value=actual_label,
                    error=error,
                    evaluated_at=now,
                    # Statistical-baseline charter, Phase 3 — real goal counts for a genuine Poisson
                    # baseline to fit λ_home/λ_away from, distinct from `actual_label`'s derived
                    # class index. Harmless for any other GRID market (none exist today).
                    raw_home_goals=result.home_score,
                    raw_away_goals=result.away_score,
                )
                recorded.append(await self.outcomes.record(outcome))
                continue

            regression_resolver = REGRESSION_MARKET_RESOLVERS.get(market.market_key)
            if regression_resolver is not None:
                actual = regression_resolver(result)
                if actual is None:
                    continue  # not resolvable this pass — never a fabricated/None outcome
                try:
                    predicted = float(prediction.value)
                except (TypeError, ValueError):
                    continue  # prediction.value wasn't a real regression output — skip, never guess
                outcome = PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()),
                    prediction_id=prediction.id,
                    actual_value=str(actual),
                    error=abs(predicted - actual),
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
                # Statistical-baseline charter, Phase 3 — real goal counts, unconditionally set for
                # every market this branch resolves (not just the football goals/score markets a
                # Poisson baseline actually trains on) since `result` is always the real MatchResult
                # here regardless of which market is resolving; harmless for every other market.
                raw_home_goals=result.home_score,
                raw_away_goals=result.away_score,
            )
            recorded.append(await self.outcomes.record(outcome))
        return recorded

    async def review_for_fixture(self, fixture_id: str) -> list[MarketReview]:
        """Real per-market rows for the AI Review surface (Match Discovery's "Recently Completed
        Intelligence" and the Match Review page): every PUBLISHED prediction on this fixture,
        joined with its resolved `PredictionOutcome` when one exists (only fixtures
        `resolve_for_fixture` has already evaluated carry one — a market with no registered
        resolver, or a fixture not yet completed, legitimately has none and is reported as
        unresolved rather than guessed at). Read-only — never writes an outcome itself."""
        rows: list[MarketReview] = []
        for prediction in await self.predictions.list_by_subject(fixture_id):
            if not prediction.is_published():
                continue
            market = await self.markets.get(prediction.market_id)
            if market is None:
                continue
            outcome = await self.outcomes.get_for_prediction(prediction.id)
            rows.append(
                MarketReview(
                    market_id=str(market.id),
                    market_key=market.market_key,
                    market_name=market.name,
                    predicted_value=prediction.value,
                    probability=prediction.probability,
                    confidence=prediction.confidence.composite,
                    probability_distribution=dict(prediction.probability_distribution),
                    top_positive_features=list(prediction.explanation.top_positive_features),
                    top_negative_features=list(prediction.explanation.top_negative_features),
                    ai_explanation=prediction.explanation.ai_explanation or None,
                    generated_at=prediction.generated_at,
                    actual_value=_display_actual_value(market.market_key, prediction.value, outcome),
                    is_correct=(outcome.error == 0.0) if outcome and outcome.error is not None else None,
                    evaluated_at=outcome.evaluated_at if outcome else None,
                )
            )
        return rows
