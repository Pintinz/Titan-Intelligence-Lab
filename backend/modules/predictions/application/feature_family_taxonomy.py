"""Predictive Signal Recovery charter, Phase 2 — maps a real `feature_key` string to the charter's
named feature family (team form, shots, possession, odds, lineup continuity, transfer activity,
news intelligence, ...). Every pattern below is source-verified against the calculator that
actually writes it — never guessed:

- `windowed_feature_engineering_service.py`: `football_fixture_form_differential_calculator`
  (the original, still-in-use "team form" proxy — writes `football.fixture.form_shots_on_target
  _diff_last{window}`, kept as its own family despite the literal stat name, since it's what every
  market's `required_features` already calls its form signal), the five additional stat
  differentials from `_ADDITIONAL_FOOTBALL_STAT_KEYS` (`football.fixture.form_{possession_pct,
  shots_total,corners,fouls,cards_yellow}_diff_last{window}`), `FixtureExpectedGoalsCalculator`
  (`football.fixture.expected_{home,away}_goals`), `LineupContinuityCalculator`
  (`football.fixture.{home,away}_lineup_continuity`), `TransferActivityCalculator`
  (`football.fixture.{home,away}_transfer_activity`), and the basketball/baseball/table_tennis
  form-differential analogs (`{sport}.fixture.form_{points,runs,points_won}_diff_last{window}`,
  `{sport}.team.form_*_last{window}`).
- `football/odds_feature_writer.py`: `football.market.implied_probability_{home,away}`,
  `football.market.overround` — the ONLY real odds writer in the codebase (confirmed via a
  whole-repo grep for `OddsFeatureWriter`); basketball/baseball/table_tennis declare the
  analogous `{sport}.market.overround`/`implied_probability_*` keys in their own
  `market_seeding.py` `SINGLE_RECORD_FEATURES`, but nothing ever writes them.
- `news_market_impact_engine.py`: `NewsMarketImpactEngine.feature_key()` —
  `f"news.{sport_code}.{side}_{dimension}"` for `dimension` in `goal_impact`/`clean_sheet_impact`
  /`btts_impact`.

`NO_CALCULATOR_CONFIRMED_FAMILIES` is a separate, explicit list — families this session directly
confirmed have zero feature-producing calculator anywhere in the codebase (the `Injury` entity and
`DataValidationEngine.validate_injury()` exist at the raw-provider layer, but nothing turns an
injury into a `FeatureDefinition`/feature value). This is a source-code fact, not a DB fact, so
it's listed here explicitly rather than left to `classify_feature_key()` returning `None` — a
`None` result elsewhere in the report means "no real feature_key matched," which for most of the
charter's family list only proves "not found in the markets we audited," not "confirmed absent
from the whole codebase." Only injuries carries the stronger, individually-verified claim.
"""

from __future__ import annotations

FEATURE_KEY_PREFIXES: tuple[tuple[str, str], ...] = (
    # Football
    ("football.fixture.form_shots_on_target_diff_last", "team_form"),
    ("football.team.form_shots_on_target_last", "team_form"),
    ("football.fixture.form_possession_pct_diff_last", "possession"),
    ("football.fixture.form_shots_total_diff_last", "shots"),
    ("football.fixture.form_corners_diff_last", "corners"),
    ("football.fixture.form_fouls_diff_last", "fouls"),
    ("football.fixture.form_cards_yellow_diff_last", "cards"),
    ("football.fixture.expected_home_goals", "expected_goals"),
    ("football.fixture.expected_away_goals", "expected_goals"),
    ("football.fixture.home_lineup_continuity", "lineup_continuity"),
    ("football.fixture.away_lineup_continuity", "lineup_continuity"),
    ("football.fixture.home_transfer_activity", "transfer_activity"),
    ("football.fixture.away_transfer_activity", "transfer_activity"),
    ("football.market.implied_probability_", "odds"),
    ("football.market.overround", "odds"),
    ("news.football.", "news_intelligence"),
    # Basketball
    ("basketball.team.form_points_last", "team_form"),
    ("basketball.fixture.form_points_diff_last", "team_form"),
    ("basketball.market.implied_probability_", "odds"),
    ("basketball.market.overround", "odds"),
    # Baseball
    ("baseball.team.form_runs_last", "team_form"),
    ("baseball.fixture.form_runs_diff_last", "team_form"),
    ("baseball.market.implied_probability_", "odds"),
    ("baseball.market.overround", "odds"),
    # Table tennis
    ("table_tennis.team.form_points_won_last", "team_form"),
    ("table_tennis.market.implied_probability_", "odds"),
    ("table_tennis.market.overround", "odds"),
)

# Confirmed, source-verified: zero feature-producing calculator anywhere in the codebase for
# either of these — never derived from a missing key match.
NO_CALCULATOR_CONFIRMED_FAMILIES: tuple[str, ...] = ("injuries", "suspensions")

# The only real writer class for odds features, confirmed via whole-repo grep. Any sport not in
# this set that nonetheless declares odds/overround feature_keys has them DECLARED_BUT_NEVER_WRITTEN.
SPORTS_WITH_REAL_ODDS_WRITER: tuple[str, ...] = ("football",)


def classify_feature_key(feature_key: str) -> str | None:
    """Returns the charter family name for a real, registered `feature_key`, or `None` if it
    matches no known, source-verified pattern — never silently misclassifies."""
    for prefix, family in FEATURE_KEY_PREFIXES:
        if feature_key.startswith(prefix):
            return family
    return None
