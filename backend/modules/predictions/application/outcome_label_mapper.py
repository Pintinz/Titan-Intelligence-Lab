"""Generation-time real-label mapper (Milestone 9.2 — Market Registry & Prediction Domain
Normalization, Phase 2).

Phase 1 built the specification (`modules.predictions.domain.market_outcome_registry`) and a
pluggable resolver contract without changing what any predictor emits. This module is the first
piece that actually eliminates ``"positive"``/``"negative"`` from a *stored* `Prediction.value` —
scoped to exactly the binary markets that already have a real, tested evaluation resolver in
`outcome_resolution_service.MARKET_OUTCOME_RESOLVERS` (six from Phase 2, nine more added in the
2026-08-02 football market catalog expansion), so generation and evaluation agree on one label
convention for the same markets rather than drifting apart. Every other market is untouched:
`map_generic_value_to_real_label` returns its input unchanged when the market isn't in
`MARKET_OUTCOME_LABELS`, so `PredictionEngine` keeps emitting exactly what it did before Phase 2
for every market neither phase covers.

The "positive" side is defined identically to `outcome_resolution_service`'s own resolvers (BTTS:
YES; Over markets: OVER; Moneyline/Match Winner: home team) — not redecided here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutcomeLabelPair:
    positive_label: str
    negative_label: str


MARKET_OUTCOME_LABELS: dict[str, OutcomeLabelPair] = {
    "football.both_teams_to_score": OutcomeLabelPair("YES", "NO"),
    "football.total_goals_over_under": OutcomeLabelPair("OVER", "UNDER"),
    "football.total_goals_over_under_0_5": OutcomeLabelPair("OVER", "UNDER"),
    "football.total_goals_over_under_1_5": OutcomeLabelPair("OVER", "UNDER"),
    "football.total_goals_over_under_3_5": OutcomeLabelPair("OVER", "UNDER"),
    "football.total_goals_over_under_4_5": OutcomeLabelPair("OVER", "UNDER"),
    "football.home_team_total_goals": OutcomeLabelPair("OVER", "UNDER"),
    "football.away_team_total_goals": OutcomeLabelPair("OVER", "UNDER"),
    "football.home_clean_sheet": OutcomeLabelPair("YES", "NO"),
    "football.away_clean_sheet": OutcomeLabelPair("YES", "NO"),
    "football.home_win_to_nil": OutcomeLabelPair("YES", "NO"),
    "football.away_win_to_nil": OutcomeLabelPair("YES", "NO"),
    # Post-M24: both now have a real resolver_key in market_outcome_registry.py
    # (_first_half_goals_over_under_0_5 / _first_half_both_teams_to_score in
    # outcome_resolution_service.py), so this table's evaluation contract is honestly satisfied —
    # but neither will actually resolve any real outcome yet, since no provider adapter parses a
    # football fixture's half-time score today (see outcome_resolution_service.py's docs). A
    # generated prediction will claim "OVER"/"YES" here exactly as it does for every other market
    # in this table; it simply won't have a checkable outcome until that separate ingestion gap
    # closes — the same honest, not-yet-populated state as the gated pre-match intelligence
    # features, not a fabricated evaluation.
    "football.first_half_goals": OutcomeLabelPair("OVER", "UNDER"),
    "football.first_half_both_teams_to_score": OutcomeLabelPair("YES", "NO"),
    "basketball.moneyline": OutcomeLabelPair("HOME", "AWAY"),
    "basketball.game_total_points": OutcomeLabelPair("OVER", "UNDER"),
    "basketball.game_total_points_199_5": OutcomeLabelPair("OVER", "UNDER"),
    "basketball.game_total_points_209_5": OutcomeLabelPair("OVER", "UNDER"),
    "basketball.game_total_points_229_5": OutcomeLabelPair("OVER", "UNDER"),
    "basketball.game_total_points_239_5": OutcomeLabelPair("OVER", "UNDER"),
    "basketball.first_half_total_points": OutcomeLabelPair("OVER", "UNDER"),
    "baseball.moneyline": OutcomeLabelPair("HOME_WIN", "AWAY_WIN"),
    "baseball.total_runs": OutcomeLabelPair("OVER", "UNDER"),
    "baseball.total_runs_6_5": OutcomeLabelPair("OVER", "UNDER"),
    "baseball.total_runs_7_5": OutcomeLabelPair("OVER", "UNDER"),
    "baseball.total_runs_9_5": OutcomeLabelPair("OVER", "UNDER"),
    "baseball.total_runs_10_5": OutcomeLabelPair("OVER", "UNDER"),
    "table_tennis.match_winner": OutcomeLabelPair("HOME_WIN", "AWAY_WIN"),
}


def map_generic_value_to_real_label(market_key: str, generic_value: str) -> str:
    """`predictor_output.value` in, the market's real label out — or `generic_value` unchanged
    when this market isn't covered yet (no market_key match) or the value isn't the generic
    predictor's ``"positive"``/``"negative"`` shape (e.g. a `TOTAL`-kind raw number string)."""
    pair = MARKET_OUTCOME_LABELS.get(market_key)
    if pair is None:
        return generic_value
    if generic_value == "positive":
        return pair.positive_label
    if generic_value == "negative":
        return pair.negative_label
    return generic_value


def map_generic_distribution_to_real_labels(market_key: str, distribution: dict[str, float]) -> dict[str, float]:
    """`predictor_output.distribution` in, keyed by the market's real outcome labels out — the
    distribution-shaped sibling of `map_generic_value_to_real_label`, applying the exact same
    ``"positive"``/``"negative"`` -> real-label table. A predictor whose distribution keys are
    already real (the ordinal/Poisson predictors) passes through unchanged, same as the
    ``generic_value`` fallback above."""
    pair = MARKET_OUTCOME_LABELS.get(market_key)
    if pair is None:
        return dict(distribution)
    mapped: dict[str, float] = {}
    for key, value in distribution.items():
        if key == "positive":
            mapped[pair.positive_label] = value
        elif key == "negative":
            mapped[pair.negative_label] = value
        else:
            mapped[key] = value
    return mapped


def real_label_is_positive(market_key: str, value: str) -> bool | None:
    """The evaluation-side inverse: given a market this table covers and a stored `Prediction.value`,
    returns whether it's that market's affirmative side. Recognizes both the new real label and
    (for safety across a rolling deploy) the pre-Phase-2 generic ``"positive"``/``"negative"``.
    Returns ``None`` — never a guess — when the market isn't covered or the value matches neither
    known label; callers must treat `None` as "cannot evaluate this prediction."""
    pair = MARKET_OUTCOME_LABELS.get(market_key)
    if pair is None:
        return None
    if value == pair.positive_label:
        return True
    if value == pair.negative_label:
        return False
    if value == "positive":
        return True
    if value == "negative":
        return False
    return None


def real_outcome_is_positive(market_key: str, prediction_value: str, error: float | None) -> bool | None:
    """What actually happened, not what was predicted — the real training/calibration label.
    Recovers it from what the prediction claimed (`real_label_is_positive`) flipped by whether
    that claim matched reality (`PredictionOutcome.error`, 0.0 = matched, 1.0 = missed — recorded
    by `OutcomeResolutionService`). Returns ``None`` — never a guess — when the market has no
    binary-polarity mapping (e.g. a 3-way market) or `error` wasn't recorded. Shared by the
    Dataset Builder (training labels) and Calibration Fitting (calibration samples), since both
    need exactly this same real-outcome-polarity recovery from the same two stored facts."""
    predicted_positive = real_label_is_positive(market_key, prediction_value)
    if predicted_positive is None or error is None:
        return None
    return predicted_positive if error == 0.0 else not predicted_positive
