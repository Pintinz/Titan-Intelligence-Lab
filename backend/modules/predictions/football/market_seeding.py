"""Football market seeding (Milestone 9 task #138) — the first per-sport instantiation of the
data-driven Market Registry (docs/decisions.md — data-driven market registry). Registers a
representative (not exhaustive — same ADR-narrowing posture as every other honestly-scoped v1
component this milestone) set of football prediction markets, one per relevant `MarketKind`,
each backed by real, already-registered features: the single-record market-derived signals from
task #136 (`ImpliedProbabilityCalculator`/`OddsOverroundCalculator`, registered here since that
task built the calculators but not their Feature Registry entries) plus task #137's windowed
team-form feature. No market here ever reaches PRODUCTION with zero features backing it —
`MarketRegistryService.promote_to_production` already refuses that.

Audit fix (2026-08-02): every market's `required_features` used to reference
`football.team.form_shots_on_target_last5` — a real, computed, but TEAM-keyed feature.
`PredictionContextBuilder` resolves every required feature against the exact entity_type/entity_id
a prediction request was made for, and every real prediction request for a match-level market is
made with `entity_type=FIXTURE`, never `TEAM` — so this feature could never actually be resolved
for any real fixture, and every market past the zero-feature legacy `football.match_result` row
failed `MissingRequiredFeatureError` on every genuine generation attempt. `FixtureFormDifferentialCalculator`
(`windowed_feature_engineering_service.py`) was already built specifically to solve exactly this —
a FIXTURE-keyed `home_form - away_form` differential — but, like several other pieces this session
found, was never actually wired to any market. `required_features` now uses that differential
feature instead, and it's genuinely more informative for the market anyway (a signed edge, not an
absolute stat with no opponent context).

Audit fix (2026-08-02), same run: `football.correct_score` required a `WeightedLinearPredictor`-
shaped feature it can't meaningfully serve (a scoreline has no "over/under a threshold" reading —
see weighted_scoring.py's docstring). Now requires `FixtureExpectedGoalsCalculator`'s two real
historical scoring-rate features instead.

ML-architecture consolidation (2026-08-04): `football.correct_score` and the eleven Over/Under-
style markets below (see `_EXPECTED_GOALS_FEATURES`) no longer have any formula predictor at all —
their old Poisson-based fallbacks were removed as legacy statistical engines, per the "one real
trained model per market, never a fabricated placeholder" production rule. Their `required_features`
stay exactly as-is (expected-goals/stat-differential features are genuine ML inputs a trained
model will consume too) but these markets now serve an honest "insufficient historical data"
response instead of a prediction until `AutomaticModelSelectionService` has trained and a human
has promoted a real Champion for them — see `scripts/seed_football_markets.py`'s
`NOT_YET_TRAINED_MARKET_KEYS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureRegistrationService,
)
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey
from modules.predictions.application.feature_market_mapping_service import (
    FeatureMarketMappingService,
    MappingAlreadyExistsError,
)
from modules.predictions.application.market_registry_service import MarketAlreadyRegisteredError, MarketRegistryService
from modules.predictions.application.manager_change_context_calculator import ManagerChangeContextCalculator
from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine
from modules.predictions.application.windowed_feature_engineering_service import (
    FixtureExpectedGoalsCalculator,
    FixtureFormDifferentialCalculator,
    FixtureVenueStrengthCalculator,
    LineupContinuityCalculator,
    RollingTeamStatAverageCalculator,
    TransferActivityCalculator,
)
from modules.predictions.domain.market_outcome_registry import get_outcome_spec
from modules.predictions.domain.value_objects import MarketKind, MarketStatus, TargetType

SYSTEM_REVIEWER = "prediction-platform"
SPORT_CODE = "football"

# feature_key -> (name, description, entity_type)
SINGLE_RECORD_FEATURES: dict[str, tuple[str, str, EntityType]] = {
    "football.market.implied_probability_home": (
        "Implied Probability (Home)", "1 / decimal home-win odds.", EntityType.FIXTURE,
    ),
    "football.market.implied_probability_away": (
        "Implied Probability (Away)", "1 / decimal away-win odds.", EntityType.FIXTURE,
    ),
    "football.market.overround": (
        "Market Overround", "Bookmaker margin across home/draw/away odds.", EntityType.FIXTURE,
    ),
    "fixture.hours_until_kickoff": (
        "Hours Until Kickoff", "Hours between now and kickoff.", EntityType.FIXTURE,
    ),
}

# The five `TeamStatistics`-derived differential features every classification-shaped football
# market below additionally requires (2026-08-03) — four fields (`possession_pct`/`shots_total`/
# `corners`/`fouls`) API-Football already synced per fixture but that, until now, no market ever
# consumed, plus cards (`cards_yellow`), which the sync itself only just started mapping at all.
# Built the same way `form_shots_on_target_diff_last5` already was — see
# `windowed_feature_engineering_service.football_fixture_stat_differential_calculators`.
# `football.correct_score` deliberately excludes these: it's one of the not-yet-trained markets
# (see module docstring) and only maps its own two expected-goals feature keys — extra features
# here would just be dead weight until a real trained model is built to consume them.
_NEW_STAT_DIFFERENTIAL_FEATURES: tuple[str, ...] = (
    "football.fixture.form_possession_pct_diff_last5",
    "football.fixture.form_shots_total_diff_last5",
    "football.fixture.form_corners_diff_last5",
    "football.fixture.form_fouls_diff_last5",
    "football.fixture.form_cards_yellow_diff_last5",
)

# Conservative default weights for the five features above — no real historical outcome data
# exists yet to fit proper weights against (same "honest v1, no fitted model" posture as
# `WeightedOrdinalPredictor`'s cutpoints), so these are deliberately small relative to the
# unweighted (weight=1.0) implied-probability features already driving these markets — sized
# roughly in inverse proportion to each stat's typical differential magnitude, so no single one
# dominates the weighted-sum predictors' raw_score. Meant to nudge the existing calibrated
# signal, not swamp it; recalibrate once real outcome history exists to fit against (e.g. via a
# future CalibrationFittingService-style feature-importance pass).
#
# Audit fix (2026-08-06): `form_shots_on_target_diff_last5` predates this dict and was never
# added to it, so every market requiring it fell through `.get(feature_key, 1.0)` to the same
# unweighted default correctly used for `implied_probability_home`/`away` — but unlike those two
# (already 0..1-scaled probabilities), this is a raw shot-count differential of the exact same
# family as `form_shots_total_diff_last5` below (a real fixture routinely shows a 5-8 shot swing
# between two teams' recent form). Fed into a sigmoid at weight 1.0, that single feature alone
# was enough to saturate `raw_score` past ±7 and push every affected market's probability to
# ~99.9%+ regardless of any other signal — confirmed live (Match Winner and Both Teams To Score
# both landed at 99.97% for the same fixture, traced back to this exact contribution). Weighted
# the same as its sibling stat-diff features now, not the implied-probability features.
NEW_STAT_FEATURE_WEIGHTS: dict[str, float] = {
    "football.fixture.form_shots_on_target_diff_last5": 0.05,  # roughly -8..8, same family as shots_total below
    "football.fixture.form_possession_pct_diff_last5": 0.02,  # typical range roughly -30..30
    "football.fixture.form_shots_total_diff_last5": 0.05,  # roughly -15..15
    "football.fixture.form_corners_diff_last5": 0.05,  # roughly -8..8
    "football.fixture.form_fouls_diff_last5": 0.03,  # roughly -10..10
    "football.fixture.form_cards_yellow_diff_last5": 0.1,  # roughly -3..3, but a high-signal event
}

# Audit fix (2026-08-03): eleven markets below used to share this exact same
# `_NEW_STAT_DIFFERENTIAL_FEATURES` set (plus shots_on_target) with no market-specific signal at
# all — none of those features encode *which line* (0.5 vs 4.5 goals) or *which side* (home vs
# away) a market is actually asking about, so every one of them produced a byte-identical
# probability regardless of what the market conceptually represented. Fixed by giving each of
# them its own expected-goals features instead — a real per-market signal a trained model can
# learn to read the line/side out of. These eleven are among the not-yet-trained markets (module
# docstring) since their old Poisson-based formula fallback was removed as a legacy engine.
_EXPECTED_GOALS_FEATURES: tuple[str, ...] = (
    "football.fixture.expected_home_goals",
    "football.fixture.expected_away_goals",
)

# Correct Score forensic audit (2026-08-26): the venue-blind expected-goals pair above fed the
# Poisson model an identical home/away scoring-rate signal regardless of which team was actually
# at home, which the audit tied directly to a live-observed defect — six real fixtures in a row all
# predicted "1-1" because the model had no home-advantage signal to separate them on. These four
# features are FIXTURE-keyed, venue-restricted, and league-baseline-relative (a team's own recent
# home-scoring rate divided by the league's average home-scoring rate, not a raw count) — see
# `FixtureVenueStrengthCalculator` (windowed_feature_engineering_service.py). Scoped to
# `football.correct_score` only; `_EXPECTED_GOALS_FEATURES` and every other market that shares it
# (BTTS, Over/Under variants, Team Total Goals, Clean Sheets, Win to Nil) are untouched.
_VENUE_STRENGTH_FEATURES: tuple[str, ...] = (
    "football.fixture.home_attack_strength",
    "football.fixture.home_defence_strength",
    "football.fixture.away_attack_strength",
    "football.fixture.away_defence_strength",
)

# Milestone 6 (Verified Pre-Match Data Availability -> first real structured-intelligence feature):
# `LineupContinuityCalculator` only ever writes a value once a fixture's own lineup reaches
# `VERIFIED_PRE_MATCH` (windowed_feature_engineering_service.py) — added here only to the 14
# markets confirmed genuinely ML-trained (docs/milestone4_verification_report.md §9's Champion
# provenance trace), not the 5 heuristic-placeholder markets: those read `FeatureMarketMapping`
# live at inference time (`ModelDefinition.is_genuinely_trained()` is False for them, so
# `PredictionEngine` falls back to the formula predictor), so adding a feature there would be a
# live behavior change to already-serving predictions, not inert prep — out of scope for this
# milestone (see docs/milestone6_verification_report.md). For the 14 trained markets below,
# `required_features` only affects a *future* retrain's input vector — today's Champions are
# unaffected until one is separately retrained and promoted (still blocked, per the standing "no
# training/promotion" rule every milestone since Milestone 4 has honored).
_LINEUP_CONTINUITY_FEATURES: tuple[str, ...] = (
    "football.fixture.home_lineup_continuity",
    "football.fixture.away_lineup_continuity",
)

# Milestone 7 (the transfer-side counterpart to Milestone 6's lineup continuity feature, per
# docs/milestone5_verification_report.md's "Recommended Milestone 6 scope" §1 — "a real
# VERIFIED_PRE_MATCH signal exists for lineups AND transfers"): `TransferActivityCalculator` only
# ever writes a value once a team has at least one VERIFIED_PRE_MATCH transfer record on file
# (windowed_feature_engineering_service.py) — same 14-trained-market scope as
# `_LINEUP_CONTINUITY_FEATURES` above and for the same reason (inert `required_features` prep for
# a trained model's next retrain; the 5 heuristic markets read `FeatureMarketMapping` live and are
# deliberately untouched — see docs/milestone7_verification_report.md).
_TRANSFER_ACTIVITY_FEATURES: tuple[str, ...] = (
    "football.fixture.home_transfer_activity",
    "football.fixture.away_transfer_activity",
)

# Milestone 8 — unlike Milestones 6/7's wiring into the 14 trained markets (inert until a future
# retrain), the four heuristic-placeholder markets below are served LIVE by a formula predictor
# (`WeightedLogisticPredictor`/`WeightedLinearPredictor`/`WeightedOrdinalPredictor`,
# `weighted_scoring.py`) that reads `FeatureMarketMapping` fresh on every prediction request. Both
# feature sets are therefore mapped `is_required=False` here (see `optional_features` on each of
# the four market specs below, and `_seed_market`'s per-market check) — every fixture in dev.db
# has zero non-null values for either feature today, so `is_required=True` would immediately raise
# `MissingRequiredFeatureError` on every prediction these four markets serve.
#
# Weights are sized the same conservative way `NEW_STAT_FEATURE_WEIGHTS` already is, to avoid
# repeating the 2026-08-06 sigmoid-saturation incident documented above: `home/away_lineup_continuity`
# is a genuinely 0..1-scaled ratio (low risk even near weight 1.0), but `home/away_transfer_activity`
# is an unbounded non-negative count of the exact same shape as the stat-differential features that
# caused that incident — a busy transfer window could plausibly push it into double digits. 0.1 for
# continuity and 0.05 for transfer activity keep each feature's typical maximum contribution to
# `raw_score` under roughly 1 unit, well inside the sigmoid's non-saturating range, matching
# `form_shots_total_diff_last5`'s comparable sizing for a similarly-scaled raw count.
#
# Known limitation, documented rather than solved with new complexity here: `lineup_continuity` is
# an unsigned, always-non-negative value (Milestone 6's own docstring: "two independent features,
# not one differential"), unlike every other feature already safely wired into these formula
# predictors (all signed home-minus-away differentials centered near zero). Feeding it directly
# means a constant small positive nudge proportional to (home + away continuity), not a
# "which side is more continuous" signal — a real feature-engineering simplification, not a
# leakage or safety issue. A future milestone could replace this with a genuine signed differential
# feature if real outcome data ever shows this matters; not attempted here to keep this milestone
# to "wire the existing, already-verified features safely," not "invent a new feature."
STRUCTURED_INTEL_OPTIONAL_WEIGHTS: dict[str, float] = {
    "football.fixture.home_lineup_continuity": 0.1,
    "football.fixture.away_lineup_continuity": 0.1,
    "football.fixture.home_transfer_activity": 0.05,
    "football.fixture.away_transfer_activity": 0.05,
}

# Milestone 9 — News Market Impact Engine features (news_market_impact_engine.py). Unlike
# Milestones 6/7's lineup-continuity/transfer-activity (generic team-strength signals wired into
# all 14 trained markets), these are deliberately market-specific per the spec's own core
# requirement ("do NOT calculate one generic impact score and apply it to every market") — each
# dimension is wired only into the markets it's actually about. All three target only markets
# already among the 14 genuinely-trained set (never the 4 heuristic markets), so — unlike
# Milestone 8's wiring — these are required=True (the seeder's default), following exactly the
# same "inert until a future retrain" reasoning Milestones 6/7 already established: a trained
# Champion is unaffected until separately retrained and promoted.
_NEWS_GOAL_IMPACT_FEATURES: tuple[str, ...] = (
    "news.football.home_goal_impact",
    "news.football.away_goal_impact",
)
_NEWS_CLEAN_SHEET_IMPACT_FEATURES: tuple[str, ...] = (
    "news.football.home_clean_sheet_impact",
    "news.football.away_clean_sheet_impact",
)
_NEWS_BTTS_IMPACT_FEATURES: tuple[str, ...] = (
    "news.football.home_btts_impact",
    "news.football.away_btts_impact",
)

# News Intelligence audit (2026-08-27) — ManagerChangeContextCalculator's elapsed-time signal
# (manager_change_context_calculator.py). Unlike the three market-specific news-impact dimensions
# just above, this is a generic team-context signal with no particular market it's "about" — the
# same posture Milestones 6/7's lineup-continuity/transfer-activity already established, so it's
# wired into every one of the same markets those two are, always optional (never required): this
# event type only started resolving real entities with the 2026-08-27 KG-alias fix, so real
# non-null values are still sparse in practice — the same "optional until proven populated"
# caution `_NEWS_GOAL_IMPACT_FEATURES` already applies.
_MANAGER_CHANGE_FEATURES: tuple[str, ...] = (
    "news.football.home_days_since_manager_change",
    "news.football.away_days_since_manager_change",
)

MARKETS: tuple[dict, ...] = (
    dict(
        market_key="football.both_teams_to_score",
        name="Both Teams To Score",
        category="goals",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            "football.fixture.form_shots_on_target_diff_last5", "football.market.overround",
            *_NEW_STAT_DIFFERENTIAL_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_BTTS_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit (docs/post_m24_phase17_football_prediction_recovery_report.md):
        # lineup_continuity/transfer_activity/news-impact are structurally unpopulated for every
        # fixture in this platform's real history (their only writers fire near real kickoff or on
        # live news ingestion, which this dev environment's data has never exercised) — declaring
        # them required blocked every one of the 14 genuinely-trained markets below at both
        # training_inference_feature_parity preflight and live inference, even though a real
        # Champion existed. Demoted to optional here, same pattern Milestone 8 already established
        # for the 4 heuristic markets — never deleted, still wired the moment real coverage exists.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_BTTS_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.total_goals_over_under",
        name="Total Goals Over/Under 2.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.home_team_total_goals",
        name="Home Team Total Goals Over/Under 1.5",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.correct_score",
        name="Correct Score",
        category="score",
        market_kind=MarketKind.CORRECT_SCORE,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_VENUE_STRENGTH_FEATURES,
            *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above. The DB also
        # carries two orphaned required mappings for this market predating this spec
        # (football.fixture.form_shots_on_target_diff_last5, football.market.implied_probability_home
        # — neither appears in required_features above, so _seed_market's create-only seeding never
        # touches them) — both are the same confirmed-unpopulated features documented in
        # docs/feature_coverage_report.md (football's own team_form/odds families), so demoted here
        # too rather than left as a silent, undeclared block on this market's real Champion.
        #
        # Correct Score forensic audit (2026-08-26): the old venue-blind
        # `expected_home_goals`/`expected_away_goals` pair (still shared by other markets as
        # `_EXPECTED_GOALS_FEATURES`) is replaced above by `_VENUE_STRENGTH_FEATURES` — see that
        # constant's comment. Kept as optional here (not dropped outright) since a future model
        # variant may still find the raw expected-goals pair a useful secondary signal alongside
        # the venue-aware features.
        optional_features=(
            *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_EXPECTED_GOALS_FEATURES,
            "football.fixture.form_shots_on_target_diff_last5", "football.market.implied_probability_home",
        ),
    ),
    dict(
        # Audit fix (2026-08-02): a football half can end drawn, exactly like a full match — this
        # was wrongly registered as MarketKind.SEGMENT_WINNER (a genuinely two-sided kind, correct
        # for e.g. basketball.quarter_winner, which has no draw) while its own catalog entry
        # (market_outcome_registry.py) already declared a real 3-way HOME_DRAW_AWAY outcome
        # contract — the mismatch meant WeightedLogisticPredictor (2-way only) served a market that
        # could never express its own most likely outcome for an evenly-matched half. Now
        # HOME_DRAW_AWAY, matching football.match_winner's already-correct treatment below.
        market_key="football.first_half_winner",
        name="First Half Winner",
        category="segment_winner",
        market_kind=MarketKind.HOME_DRAW_AWAY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            "football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES,
            *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
        ),
        # Milestone 8 — both feature sets map optional (is_required=False) here: this market is
        # served live by a formula predictor, not a trained model, so an absent required feature
        # would raise MissingRequiredFeatureError on every prediction today (0 fixtures have a
        # non-null value for either feature yet). See STRUCTURED_INTEL_OPTIONAL_WEIGHTS's comment.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES),
    ),
    # Milestone 9.2 Phase 3 — the genuine 3-way market `WeightedOrdinalPredictor` serves. Distinct
    # from every market above (all MarketKind.BINARY/TOTAL/TEAM_TOTAL/CORRECT_SCORE/SEGMENT_WINNER):
    # a draw is a real possible outcome, so this is the first HOME_DRAW_AWAY-kind market registered.
    dict(
        market_key="football.match_winner",
        name="Match Winner",
        category="winner",
        market_kind=MarketKind.HOME_DRAW_AWAY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            "football.fixture.form_shots_on_target_diff_last5",
            "football.market.implied_probability_home",
            "football.market.implied_probability_away",
            *_NEW_STAT_DIFFERENTIAL_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES),
    ),
    # 2026-08-02 football market catalog expansion — twelve more real markets, all backed by the
    # same already-registered features every market above uses (no new feature work required),
    # doubling football's PRODUCTION catalog from 6 to 18. Real resolvers exist for nine of these
    # (see outcome_resolution_service.MARKET_OUTCOME_RESOLVERS) — the other three (first-half
    # goals/BTTS, second-half winner) are seeded PRODUCTION but unresolved, same honest gap
    # football.first_half_winner already had (no sub-match score data ingested yet).
    dict(
        market_key="football.total_goals_over_under_0_5",
        name="Total Goals Over/Under 0.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.total_goals_over_under_1_5",
        name="Total Goals Over/Under 1.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.total_goals_over_under_3_5",
        name="Total Goals Over/Under 3.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.total_goals_over_under_4_5",
        name="Total Goals Over/Under 4.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.away_team_total_goals",
        name="Away Team Total Goals Over/Under 1.5",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_GOAL_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_GOAL_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.home_clean_sheet",
        name="Home Clean Sheet",
        category="clean_sheet",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_CLEAN_SHEET_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_CLEAN_SHEET_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.away_clean_sheet",
        name="Away Clean Sheet",
        category="clean_sheet",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_CLEAN_SHEET_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_CLEAN_SHEET_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.home_win_to_nil",
        name="Home Win To Nil",
        category="win_to_nil",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_CLEAN_SHEET_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_CLEAN_SHEET_IMPACT_FEATURES),
    ),
    dict(
        market_key="football.away_win_to_nil",
        name="Away Win To Nil",
        category="win_to_nil",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            *_EXPECTED_GOALS_FEATURES, *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
            *_NEWS_CLEAN_SHEET_IMPACT_FEATURES,
        ),
        # Post-M24 Phase 17 audit — see football.both_teams_to_score's comment above.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES, *_NEWS_CLEAN_SHEET_IMPACT_FEATURES),
    ),
    dict(
        # Same audit fix as football.first_half_winner above — a second half can end drawn too.
        market_key="football.second_half_winner",
        name="Second Half Winner",
        category="segment_winner",
        market_kind=MarketKind.HOME_DRAW_AWAY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            "football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES,
            *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
        ),
        # Milestone 8 — both feature sets map optional (is_required=False) here: this market is
        # served live by a formula predictor, not a trained model, so an absent required feature
        # would raise MissingRequiredFeatureError on every prediction today (0 fixtures have a
        # non-null value for either feature yet). See STRUCTURED_INTEL_OPTIONAL_WEIGHTS's comment.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES),
    ),
    dict(
        market_key="football.first_half_goals",
        name="First Half Goals Over/Under 0.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            "football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES,
            *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
        ),
        # Milestone 8 — both feature sets map optional (is_required=False) here: this market is
        # served live by a formula predictor, not a trained model, so an absent required feature
        # would raise MissingRequiredFeatureError on every prediction today (0 fixtures have a
        # non-null value for either feature yet). See STRUCTURED_INTEL_OPTIONAL_WEIGHTS's comment.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES),
    ),
    dict(
        market_key="football.first_half_both_teams_to_score",
        name="First Half Both Teams To Score",
        category="goals",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=(
            "football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES,
            *_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES,
        ),
        # Milestone 8 — both feature sets map optional (is_required=False) here: this market is
        # served live by a formula predictor, not a trained model, so an absent required feature
        # would raise MissingRequiredFeatureError on every prediction today (0 fixtures have a
        # non-null value for either feature yet). See STRUCTURED_INTEL_OPTIONAL_WEIGHTS's comment.
        optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES, *_MANAGER_CHANGE_FEATURES),
    ),
)


@dataclass
class FootballMarketSeeder:
    registration: FeatureRegistrationService
    markets: MarketRegistryService
    mappings: FeatureMarketMappingService
    windowed_calculator: RollingTeamStatAverageCalculator
    differential_calculators: tuple[FixtureFormDifferentialCalculator, ...]
    expected_goals_calculator: FixtureExpectedGoalsCalculator
    lineup_continuity_calculators: tuple[LineupContinuityCalculator, LineupContinuityCalculator]
    transfer_activity_calculators: tuple[TransferActivityCalculator, TransferActivityCalculator]
    venue_strength_calculator: FixtureVenueStrengthCalculator
    news_market_impact_engine: NewsMarketImpactEngine
    manager_change_calculator: ManagerChangeContextCalculator

    async def seed(self, now: datetime) -> None:
        await self._ensure_single_record_features_registered(now)
        await self.windowed_calculator.ensure_registered(now)
        for calculator in self.differential_calculators:
            await calculator.ensure_registered(now)
        await self.expected_goals_calculator.ensure_registered(now)
        await self.venue_strength_calculator.ensure_registered(now)
        for calculator in self.lineup_continuity_calculators:
            await calculator.ensure_registered(now)
        for calculator in self.transfer_activity_calculators:
            await calculator.ensure_registered(now)
        await self.news_market_impact_engine.ensure_registered(now)
        await self.manager_change_calculator.ensure_registered(now)

        for spec in MARKETS:
            await self._seed_market(spec, now)

    async def _ensure_single_record_features_registered(self, now: datetime) -> None:
        for feature_key, (name, description, entity_type) in SINGLE_RECORD_FEATURES.items():
            existing = await self.registration.definitions.get(FeatureKey(feature_key))
            if existing is not None:
                continue
            try:
                await self.registration.register(
                    feature_key,
                    name,
                    description,
                    SPORT_CODE,
                    FeatureCategory.LIVE,
                    formula="derived from the provider's live odds feed",
                    data_type=FeatureDataType.FLOAT,
                    owner=SYSTEM_REVIEWER,
                    entity_type=entity_type,
                )
            except FeatureAlreadyRegisteredError:
                continue
            await self.registration.submit_for_review(feature_key)
            await self.registration.approve(feature_key, SYSTEM_REVIEWER, now)

    async def _seed_market(self, spec: dict, now: datetime) -> None:
        # Milestone 9.2 Phase 1's catalog is the single source of truth for a market's real
        # outcome-label contract — pull it here rather than duplicating it in MARKETS above, so
        # the two can never silently drift apart. Markets not yet in the catalog register with
        # outcome_type=None/allowed_values=()/resolver_key=None, same as before Phase 1 existed.
        outcome_spec = get_outcome_spec(spec["market_key"])
        try:
            await self.markets.register(
                market_key=spec["market_key"],
                sport_code=SPORT_CODE,
                name=spec["name"],
                category=spec["category"],
                market_kind=spec["market_kind"],
                target_type=spec["target_type"],
                owner=SYSTEM_REVIEWER,
                now=now,
                outcome_type=outcome_spec.outcome_type if outcome_spec else None,
                allowed_values=outcome_spec.allowed_values if outcome_spec else (),
                resolver_key=outcome_spec.resolver_key if outcome_spec else None,
            )
        except MarketAlreadyRegisteredError:
            pass

        # Milestone 8 — a market-specific opt-out, distinct from `_NEW_STAT_DIFFERENTIAL_FEATURES`'s
        # global one: `home/away_lineup_continuity`/`transfer_activity` must stay required=True on
        # the 14 trained markets (Milestones 6/7 — a training dataset should demand the pre-match
        # feature exist) but optional on these four live-formula-served markets specifically (see
        # `STRUCTURED_INTEL_OPTIONAL_WEIGHTS`'s comment above). Absent on every other market's spec,
        # so `spec.get(...)` defaults to an empty tuple and behavior there is unchanged.
        market_optional_features = spec.get("optional_features", ())

        for feature_key in spec["required_features"]:
            try:
                await self.mappings.map_feature(
                    spec["market_key"], feature_key,
                    # The five new stat-differential features (2026-08-03) are optional, not
                    # required: a rolling average needs 5 prior matches of TeamStatistics history
                    # for *both* teams, and cards specifically has none at all for any fixture
                    # whose team_statistics were synced before _STAT_TYPE_MAP started mapping it
                    # (an absent stat_set key, not a zero value) — genuinely missing for a real,
                    # unpredictable subset of fixtures. Blocking generation on that would defeat
                    # the entire "fine-tune when available" point of adding them;
                    # resolve_feature_snapshot already silently omits a missing optional feature
                    # rather than raising, exactly the behavior these need.
                    is_required=(
                        feature_key not in _NEW_STAT_DIFFERENTIAL_FEATURES
                        and feature_key not in market_optional_features
                    ),
                    weight=NEW_STAT_FEATURE_WEIGHTS.get(
                        feature_key, STRUCTURED_INTEL_OPTIONAL_WEIGHTS.get(feature_key, 1.0)
                    ),
                )
            except MappingAlreadyExistsError:
                continue

        market = await self.markets.markets.get_by_key(spec["market_key"])
        if market.status is MarketStatus.DRAFT:
            await self.markets.submit_for_review(spec["market_key"])
            await self.markets.approve(spec["market_key"], reviewer=SYSTEM_REVIEWER, now=now)
            await self.markets.promote_to_production(spec["market_key"], now=now)
