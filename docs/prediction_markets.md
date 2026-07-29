# TitanIQ — Prediction Market Registry

Status: **Live, Milestone 9** — `MarketDefinition` rows registered and promoted to PRODUCTION
across Football, Basketball, Baseball, and Table Tennis, each backed by real registered
features. TitanIQ never uses one universal model — every market is scored by one of two generic
statistical `PredictorPort` implementations selected by `MarketKind`, not a bespoke model per
market (see [prediction_engine.md](prediction_engine.md) §4, [decisions.md](decisions.md)
ADR-043/ADR-044).

## 1. Data-Driven Market Registry

A `MarketDefinition` ([database_schema.md](database_schema.md) §4, schema `predictions`,
table `prediction_markets`) is a registry **row**, not a class:

`id · market_key (unique) · sport_code · name · category · market_kind · target_type ·
description · min_historical_window_days · required_data_quality · explainability_required ·
confidence_threshold · status · owner · version · created_at/updated_at ·
reviewed_by/reviewed_at · rejection_reason · deprecated_at`.

`market_kind` is one of 8 `MarketKind` values — the reusable computational *strategy* a market
needs, not the market itself:

| `MarketKind` | Meaning | Example |
|---|---|---|
| `BINARY` | Two-outcome | Moneyline, Match Winner, Both Teams To Score |
| `SPREAD` | Point spread / handicap | Point Spread, Run Line, Match Handicap |
| `TOTAL` | Over/under game total | Total Goals, Total Runs, Total Points |
| `TEAM_TOTAL` | One side's own total | Team Total Points/Runs/Goals |
| `PLAYER_PROP` | Player/individual regression target | Player Points, Pitcher Strikeouts |
| `CORRECT_SCORE` | Exact score/distribution | Correct Score |
| `RACE_TO` | Race to N points | Race To 20 Points, Race To 11 Points |
| `SEGMENT_WINNER` | Winner of a bounded segment | First Half Winner, Set Winner |

`PredictorPort` implementations are written against `MarketKind`, so a handful of real predictor
classes serve every named market across all four sports — see
[prediction_engine.md](prediction_engine.md) §4.

## 2. Market Record Fields (as actually implemented)

Every `MarketDefinition` declares:

- **Required Features / Optional Features** — via `FeatureMarketMapping` rows
  (`predictions.feature_market_mappings`: `market_id`, `feature_key`, `is_required`,
  `importance`, `confidence_contribution`, `weight`). "No prediction model may consume features
  outside its registered Feature-to-Market mapping" is enforced by
  `FeatureMarketMappingService.resolve_feature_snapshot()`, which raises
  `MissingRequiredFeatureError` on a missing required feature.
- **Minimum Historical Window** — `min_historical_window_days`.
- **Required Data Quality** — `required_data_quality`.
- **Explainability Requirements** — `explainability_required` (every prediction gets a full
  `ExplanationBundle` regardless; this flag is a declared expectation the Admin Control Center
  can audit against).
- **Confidence Threshold** — `confidence_threshold`; gates auto-publication vs. DRAFT
  (ADR-047).

## 3. Lifecycle

`MarketRegistryService`: **Draft → In Review → Approved → Production → Deprecated → Archived →
Removed**. Only a PRODUCTION market may generate predictions
(`MarketDefinition.is_production()`, enforced by `PredictionContextBuilder`). Promotion to
PRODUCTION is refused (`MarketNotReadyForProductionError`) unless at least one required feature
is mapped — a market can never reach production with nothing backing it, closing the
"speculative filler" risk this document originally flagged before any market existed.

## 4. Design Constraints (unchanged from the original framework)

- Prioritize scientific validity, explainability, predictive value, user value, business value,
  and long-term maintainability — in that order when they conflict.
- Explicitly **not** a betting-odds clone: markets are chosen for analytical/predictive value.
  (Odds-derived features like implied probability/overround are legitimate *inputs* a market can
  use — they are not the market's own line.)
- A market is only promoted to PRODUCTION once it has a registered, non-leaking, ACTIVE feature
  behind it — enforced structurally, not just by convention (§3).

## 5. Registered Markets by Sport

Representative, not the literal exhaustive market list every sport's spec names — one market per
relevant `MarketKind`, each with a real feature backing it (ADR-048). The same seeding mechanism
(`modules.predictions.<sport>.market_seeding`) registers additional named markets as their real
features are built.

| Sport | `market_key` | `MarketKind` | Required feature(s) |
|---|---|---|---|
| Football | `football.both_teams_to_score` | BINARY | `football.team.form_shots_on_target_last5`, `football.market.overround` |
| Football | `football.total_goals_over_under` | TOTAL | `football.team.form_shots_on_target_last5` |
| Football | `football.home_team_total_goals` | TEAM_TOTAL | `football.team.form_shots_on_target_last5` |
| Football | `football.correct_score` | CORRECT_SCORE | `football.team.form_shots_on_target_last5`, `football.market.implied_probability_home` |
| Football | `football.first_half_winner` | SEGMENT_WINNER | `football.team.form_shots_on_target_last5` |
| Basketball | `basketball.moneyline` | BINARY | `basketball.team.form_points_last5`, `basketball.market.overround` |
| Basketball | `basketball.point_spread` | SPREAD | `basketball.team.form_points_last5` |
| Basketball | `basketball.game_total_points` | TOTAL | `basketball.team.form_points_last5` |
| Basketball | `basketball.team_total_points` | TEAM_TOTAL | `basketball.team.form_points_last5` |
| Basketball | `basketball.first_half_winner` | SEGMENT_WINNER | `basketball.team.form_points_last5` |
| Basketball | `basketball.race_to_20_points` | RACE_TO | `basketball.team.form_points_last5` |
| Basketball | `basketball.player_points_prop` | PLAYER_PROP | `basketball.team.form_points_last5` |
| Baseball | `baseball.moneyline` | BINARY | `baseball.team.form_runs_last5`, `baseball.market.overround` |
| Baseball | `baseball.run_line` | SPREAD | `baseball.team.form_runs_last5` |
| Baseball | `baseball.total_runs` | TOTAL | `baseball.team.form_runs_last5` |
| Baseball | `baseball.team_total_runs` | TEAM_TOTAL | `baseball.team.form_runs_last5` |
| Baseball | `baseball.first_five_innings_winner` | SEGMENT_WINNER | `baseball.team.form_runs_last5` |
| Baseball | `baseball.pitcher_strikeouts_prop` | PLAYER_PROP | `baseball.team.form_runs_last5` |
| Table Tennis | `table_tennis.match_winner` | BINARY | `table_tennis.team.form_points_won_last5`, `table_tennis.market.overround` |
| Table Tennis | `table_tennis.match_handicap` | SPREAD | `table_tennis.team.form_points_won_last5` |
| Table Tennis | `table_tennis.total_points` | TOTAL | `table_tennis.team.form_points_won_last5` |
| Table Tennis | `table_tennis.correct_score` | CORRECT_SCORE | `table_tennis.team.form_points_won_last5` |
| Table Tennis | `table_tennis.race_to_11_points` | RACE_TO | `table_tennis.team.form_points_won_last5` |
| Table Tennis | `table_tennis.set_winner` | SEGMENT_WINNER | `table_tennis.team.form_points_won_last5` |

`PLAYER_PROP` markets (basketball/baseball) are backed by the team-level form feature as a real
but imperfect proxy — no player-level windowed feature exists yet (no `PlayerStatistics`
repository port was built this milestone; a documented gap, not a fabricated signal).

## 6. Champion–Challenger Requirement

`ModelRegistryService` enforces exactly one CHAMPION model per market at a time
(`ModelStatus`: CANDIDATE → CHALLENGER → CHAMPION → RETIRED); promoting a CHALLENGER to CHAMPION
automatically retires the previous one. `predictions.experiments` (`Experiment` entity) is where
a documented Champion vs. Candidate offline benchmark is recorded before a promotion — this
milestone ships the repository/entity for it; the benchmarking workflow itself (running an
offline evaluation and writing the `Experiment` row) is a future addition against the same
`ExperimentRepositoryPort`, not yet automated.

## 7. Predictor & Calibration

Every registered market's champion model is one of two real, deterministic `PredictorPort`
implementations selected by `MarketKind` (never a per-market bespoke model) — see
[prediction_engine.md](prediction_engine.md) §4 for `WeightedLogisticPredictor`/
`WeightedLinearPredictor`, and §5 for `PlattScalingCalibrator`'s probability calibration.
