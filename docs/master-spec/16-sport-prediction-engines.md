# 16 — Sport Prediction Engines

> Part of the standalone `docs/master-spec/` set — see the notice at the top of
> [`01-system-architecture.md`](01-system-architecture.md). This document is the concrete
> instantiation of the sport-plugin contract from [`01-system-architecture.md`](01-system-architecture.md) §4:
> for each sport, the baseline model, the ML model, and the full market catalog with each market's
> resolver logic and key required features.

Every market listed below is registered exactly as a
[`markets.market_definitions`](10-market-registry-schema.md) row with a real `resolver_key`, and
every "key required features" list is a subset of that market's
[`feature_market_mappings`](10-market-registry-schema.md) — these are not illustrative, they are
the minimum set a market must have `is_required=true` mappings for before it can leave `DRAFT`
(§ [10](10-market-registry-schema.md) §2).

## 1. Football

**Baseline — Dixon–Coles Adjusted Poisson.** Models each team's goal-scoring as a Poisson process
parameterized by attack strength, defense strength, and home advantage, fit per-competition from
recent results; the Dixon–Coles adjustment corrects the independent-Poisson assumption's known
underestimate of low-scoring draws (0-0, 1-1). Produces a full scoreline probability matrix, from
which every market below (win/draw/loss, totals, BTTS, correct score) is derived analytically —
one baseline fit serves every football market, not one baseline per market.

**ML — LightGBM Residual Model.** Trained per market to predict the residual between the
Dixon–Coles probability and the real outcome, using features the closed-form baseline can't
incorporate directly: recent-form differential, market odds movement, injury-adjusted lineup
strength, rest-days differential (§ [02-ml-architecture.md](02-ml-architecture.md) §4).

| Market | `market_key` | Kind / target | Resolver | Key required features |
|---|---|---|---|---|
| Match Winner | `football.match_winner` | HOME_DRAW_AWAY / classification | `home_score` vs `away_score` → HOME/DRAW/AWAY | form_diff_last5, home_advantage_rating, injury_impact, rest_days_diff |
| Double Chance | `football.double_chance` | 3-way binary / classification | HOME_OR_DRAW / AWAY_OR_DRAW / HOME_OR_AWAY from final score | same as Match Winner (derived market, shares its feature set) |
| Over/Under Goals | `football.total_goals_{line}` | BINARY (per line, e.g. 2.5) / classification | `home_score + away_score` vs line | attack_strength_home, attack_strength_away, expected_goals_dixon_coles |
| BTTS | `football.btts` | BINARY / classification | both scores > 0 → YES/NO | attack_strength_home, attack_strength_away, clean_sheet_rate_last10 |
| Over/Under Corners | `football.total_corners_{line}` | BINARY (per line) / classification | total match corners vs line | corners_for_avg, corners_against_avg, playing_style_rating |
| Team Corners | `football.team_corners_{team}_{line}` | BINARY (per line) / classification | one team's corners vs line | corners_for_avg (that team), possession_share_avg |
| Team Goals | `football.team_goals_{team}_{line}` | BINARY (per line) / classification | one team's goals vs line | attack_strength (that team), opponent_defense_strength |
| Correct Score | `football.correct_score` | multi-class (finite scoreline set) / classification | exact `home_score`-`away_score` | full Dixon–Coles scoreline matrix + form_diff_last5 |

## 2. Basketball

**Baseline — Possession Efficiency Model.** Estimates each team's points-per-possession on offense
and defense from recent games, combines with estimated possession count (pace) for the matchup to
produce an expected score for each side; win probability and spread/total markets derive from the
implied score distribution around those two expected values.

**ML — LightGBM.** Trained directly per market (not a residual model here — basketball's
possession-efficiency baseline is less analytically complete than football's Dixon–Coles matrix, so
the ML layer contributes more independently), on efficiency ratings, pace, rest days, travel
distance, and injury-adjusted rotation strength.

| Market | `market_key` | Kind / target | Resolver | Key required features |
|---|---|---|---|---|
| Moneyline | `basketball.moneyline` | BINARY / classification | winning team from final score | offensive_efficiency_diff, defensive_efficiency_diff, pace_estimate |
| Point Spread | `basketball.point_spread_{line}` | BINARY (per line) / classification | `home_score - away_score` vs line | same as Moneyline + home_court_rating |
| Total Points | `basketball.total_points_{line}` | BINARY (per line) / classification | `home_score + away_score` vs line | pace_estimate, combined_offensive_efficiency |
| First Half Total Points | `basketball.first_half_total_{line}` | BINARY (per line) / classification | first-half combined score vs line | first_half_pace_avg, early_foul_rate |
| Team Total Points | `basketball.team_total_{team}_{line}` | BINARY (per line) / classification | one team's final score vs line | offensive_efficiency (that team), opponent_defensive_efficiency |
| First Half Winner | `basketball.first_half_winner` | BINARY / classification | leading team at halftime | first_half_offensive_efficiency, rotation_strength |

## 3. Baseball

**Baseline — Run Expectancy Model.** A base/out-state run-expectancy matrix (24 base-out states)
combined with starting-pitcher and lineup quality estimates to project each team's expected runs;
markets derive from the resulting expected-run differential and total.

**ML — CatBoost** (benchmarked against LightGBM per training run, § [12](12-training-pipeline.md)
§1 — CatBoost is the expected/primary winner given baseball's naturally categorical
pitcher-vs-batter matchup features, but the roster always includes LightGBM so the choice is
evidence-based per market, not assumed). Trained on starting-pitcher recent form, bullpen fatigue
(recent appearances), batting-order-adjusted lineup strength, and park factors.

| Market | `market_key` | Kind / target | Resolver | Key required features |
|---|---|---|---|---|
| Moneyline | `baseball.moneyline` | BINARY / classification | winning team from final score | starting_pitcher_era_last5, lineup_wOBA_avg, bullpen_fatigue |
| Run Line | `baseball.run_line_{line}` | BINARY (typically ±1.5) / classification | `home_runs - away_runs` vs line | same as Moneyline + park_factor |
| Total Runs | `baseball.total_runs_{line}` | BINARY (per line) / classification | `home_runs + away_runs` vs line | combined_starting_pitcher_era, park_factor, weather_wind_factor |
| Team Runs | `baseball.team_runs_{team}_{line}` | BINARY (per line) / classification | one team's runs vs line | lineup_wOBA_avg (that team), opponent_starting_pitcher_era |
| First 5 Innings Winner | `baseball.first5_winner` | BINARY / classification | leading team through 5 innings | starting_pitcher_era_last5, bullpen not yet relevant (starters only) |
| First 5 Innings Total Runs | `baseball.first5_total_runs_{line}` | BINARY (per line) / classification | combined runs through 5 innings vs line | starting_pitcher_era_last5 (both), park_factor |

## 4. Tennis

**Baseline — Elo/Glicko Rating System.** Surface-specific Elo (hard/clay/grass carried as separate
rating tracks per player, since surface specialization is large and well-documented in tennis)
combined with a Glicko-style rating-deviation term that widens uncertainty for players returning
from injury or with sparse recent matches on the relevant surface.

**ML — LightGBM.** Trained on surface-specific Elo differential, recent-form (last 10 matches on
this surface), head-to-head record, and fatigue (sets/matches played in the preceding days —
relevant for tournaments with short turnarounds).

| Market | `market_key` | Kind / target | Resolver | Key required features |
|---|---|---|---|---|
| Match Winner | `tennis.match_winner` | BINARY / classification | winning player from match result | surface_elo_diff, form_last10_surface, h2h_record |
| Set Winner | `tennis.set_winner_{set_number}` | BINARY / classification | winner of the specified set | surface_elo_diff, fatigue_sets_last72h |
| Total Games | `tennis.total_games_{line}` | BINARY (per line) / classification | total games played in the match vs line | surface_elo_diff (closer ratings → more games), break_point_conversion_rate (both) |
| Game Handicap | `tennis.game_handicap_{line}` | BINARY (per line) / classification | game-count differential vs line | surface_elo_diff, service_hold_rate_diff |
| Correct Set Score | `tennis.correct_set_score` | multi-class (finite set-score set, best-of-3 or best-of-5 aware) / classification | exact set score | surface_elo_diff, fatigue_sets_last72h, best_of (match format flag) |
| First Set Winner | `tennis.first_set_winner` | BINARY / classification | winner of set 1 | surface_elo_diff, form_last10_surface |

## 5. Adding a Fifth Sport

Following the plugin contract in [`01-system-architecture.md`](01-system-architecture.md) §4: a new
sport supplies (1) a set of feature calculators registered in the Feature Registry, (2) a market
catalog registered in the Market Registry with real resolvers, and (3) a baseline statistical model
appropriate to the sport's scoring structure (Poisson-family for low-scoring team sports, Elo/Glicko
for head-to-head individual sports, efficiency/rate models for high-possession team sports). None of
the core pipeline code in Milestones 3–4 changes.
