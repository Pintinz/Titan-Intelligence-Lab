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
see weighted_scoring.py's docstring). Now requires `FixtureExpectedGoalsCalculator`'s two
real historical scoring-rate features instead, served by the new `PoissonScorePredictor`.
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
from modules.predictions.application.windowed_feature_engineering_service import (
    FixtureExpectedGoalsCalculator,
    FixtureFormDifferentialCalculator,
    RollingTeamStatAverageCalculator,
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
# `football.correct_score` deliberately excludes these: `PoissonScorePredictor` only ever reads
# its own two expected-goals feature keys, so mapping extra features to that market would just be
# dead weight, never something the predictor could act on.
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
# unweighted (weight=1.0) implied-probability/shots-on-target features already driving these
# markets — sized roughly in inverse proportion to each stat's typical differential magnitude, so
# no single one dominates the weighted-sum predictors' raw_score. Meant to nudge the existing
# calibrated signal, not swamp it; recalibrate once real outcome history exists to fit against
# (e.g. via a future CalibrationFittingService-style feature-importance pass).
NEW_STAT_FEATURE_WEIGHTS: dict[str, float] = {
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
# them `PoissonGoalsThresholdPredictor` (composition.py) instead — real per-market answers
# derived from the same independent-Poisson expected-goals model `football.correct_score`
# already uses, via closed-form Poisson math (sum-of-Poissons, PMF/CDF), not a fabricated one.
_EXPECTED_GOALS_FEATURES: tuple[str, ...] = (
    "football.fixture.expected_home_goals",
    "football.fixture.expected_away_goals",
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
            *_NEW_STAT_DIFFERENTIAL_FEATURES,
        ),
    ),
    dict(
        market_key="football.total_goals_over_under",
        name="Total Goals Over/Under 2.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.home_team_total_goals",
        name="Home Team Total Goals Over/Under 1.5",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.correct_score",
        name="Correct Score",
        category="score",
        market_kind=MarketKind.CORRECT_SCORE,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.fixture.expected_home_goals", "football.fixture.expected_away_goals"),
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
        required_features=("football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES),
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
            *_NEW_STAT_DIFFERENTIAL_FEATURES,
        ),
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
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.total_goals_over_under_1_5",
        name="Total Goals Over/Under 1.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.total_goals_over_under_3_5",
        name="Total Goals Over/Under 3.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.total_goals_over_under_4_5",
        name="Total Goals Over/Under 4.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.away_team_total_goals",
        name="Away Team Total Goals Over/Under 1.5",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.home_clean_sheet",
        name="Home Clean Sheet",
        category="clean_sheet",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.away_clean_sheet",
        name="Away Clean Sheet",
        category="clean_sheet",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.home_win_to_nil",
        name="Home Win To Nil",
        category="win_to_nil",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        market_key="football.away_win_to_nil",
        name="Away Win To Nil",
        category="win_to_nil",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=_EXPECTED_GOALS_FEATURES,
    ),
    dict(
        # Same audit fix as football.first_half_winner above — a second half can end drawn too.
        market_key="football.second_half_winner",
        name="Second Half Winner",
        category="segment_winner",
        market_kind=MarketKind.HOME_DRAW_AWAY,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES),
    ),
    dict(
        market_key="football.first_half_goals",
        name="First Half Goals Over/Under 0.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES),
    ),
    dict(
        market_key="football.first_half_both_teams_to_score",
        name="First Half Both Teams To Score",
        category="goals",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.fixture.form_shots_on_target_diff_last5", *_NEW_STAT_DIFFERENTIAL_FEATURES),
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

    async def seed(self, now: datetime) -> None:
        await self._ensure_single_record_features_registered(now)
        await self.windowed_calculator.ensure_registered(now)
        for calculator in self.differential_calculators:
            await calculator.ensure_registered(now)
        await self.expected_goals_calculator.ensure_registered(now)

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
                    is_required=feature_key not in _NEW_STAT_DIFFERENTIAL_FEATURES,
                    weight=NEW_STAT_FEATURE_WEIGHTS.get(feature_key, 1.0),
                )
            except MappingAlreadyExistsError:
                continue

        market = await self.markets.markets.get_by_key(spec["market_key"])
        if market.status is MarketStatus.DRAFT:
            await self.markets.submit_for_review(spec["market_key"])
            await self.markets.approve(spec["market_key"], reviewer=SYSTEM_REVIEWER, now=now)
            await self.markets.promote_to_production(spec["market_key"], now=now)
