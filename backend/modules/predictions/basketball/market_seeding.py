"""Basketball market seeding (Milestone 9 task #139) — mirrors
modules.predictions.football.market_seeding's shape: a representative (not exhaustive — see that
module's ADR note, same posture here) set of basketball prediction markets, one per relevant
`MarketKind`, each backed by real registered features.

Basketball's spec market list (Moneyline, Spread, Alternative Spread, Team Totals, Individual
Team Full-Time Points, First Half/Second Half Winner, Quarter Winners/Spreads/Totals, Player
Props: Rebounds/Assists/Blocks/Steals/Turnovers/PRA, Double Double, Triple Double, Overtime, Race
To Points) is far larger than football's — this seeds one market per distinct `MarketKind` the
list implies (Moneyline->BINARY, Spread->SPREAD, Team Totals->TEAM_TOTAL, First Half
Winner->SEGMENT_WINNER, Race To Points->RACE_TO, Player Points->PLAYER_PROP), not the literal
25+ named markets. The `PLAYER_PROP` market is backed by the fixture-level form-differential
feature as its only required signal — a real but imperfect proxy (a player's scoring correlates
with team offensive form) since no player-level windowed feature exists yet (no
`PlayerStatistics` repository port was built this milestone — a documented gap, not a fabricated
one).

POST-M24 Phase 5A: `required_features` below points at `basketball.fixture.form_points_diff_last5`
(`EntityType.FIXTURE`), not the original `basketball.team.form_points_last5`
(`EntityType.TEAM`) — a team-scoped feature is structurally invisible to a fixture-scoped market
prediction request (`PredictionContextBuilder` only resolves a mapped feature against the exact
entity_type/entity_id the request was made for), the same gap football's own required-features fix
closed for its markets (see `football.market_seeding`'s own history). `basketball_form_calculator`
(the team-scoped rolling average) is left in place and still registered — it remains a legitimate
per-team signal for any future team-scoped consumer (e.g. a team page), just not a valid
market-required feature on its own.
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
    FixtureFormDifferentialCalculator,
    RollingTeamStatAverageCalculator,
)
from modules.predictions.domain.value_objects import MarketKind, MarketStatus, TargetType

SYSTEM_REVIEWER = "prediction-platform"
SPORT_CODE = "basketball"

SINGLE_RECORD_FEATURES: dict[str, tuple[str, str, EntityType]] = {
    "basketball.market.implied_probability_home": (
        "Implied Probability (Home)", "1 / decimal home-win moneyline odds.", EntityType.FIXTURE,
    ),
    "basketball.market.implied_probability_away": (
        "Implied Probability (Away)", "1 / decimal away-win moneyline odds.", EntityType.FIXTURE,
    ),
    "basketball.market.overround": (
        "Market Overround", "Bookmaker margin across home/away moneyline odds.", EntityType.FIXTURE,
    ),
    "fixture.hours_until_kickoff": (
        "Hours Until Tip-Off", "Hours between now and tip-off.", EntityType.FIXTURE,
    ),
}

MARKETS: tuple[dict, ...] = (
    dict(
        market_key="basketball.moneyline",
        name="Moneyline",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5", "basketball.market.overround"),
    ),
    dict(
        market_key="basketball.point_spread",
        name="Point Spread",
        category="spread",
        market_kind=MarketKind.SPREAD,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.game_total_points",
        name="Game Total Points Over/Under 219.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        # Real resolver added post-M24: `_total_points_over_under_219_5` in
        # outcome_resolution_service.py, line grounded in this platform's own 1,708-fixture median
        # (dev.db audit: min 118, max 397, median 220.0) — was seeded with no resolver before.
    ),
    # POST-M24 Phase 15 — four more lines bracketing the median, same shape as football's
    # total_goals_over_under_0_5/1_5/3_5/4_5 around its own 2.5 line. Real dev.db percentiles for
    # the same 1,708-fixture population: p25=199, median=220, p75=237.
    dict(
        market_key="basketball.game_total_points_199_5",
        name="Game Total Points Over/Under 199.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.game_total_points_209_5",
        name="Game Total Points Over/Under 209.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.game_total_points_229_5",
        name="Game Total Points Over/Under 229.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.game_total_points_239_5",
        name="Game Total Points Over/Under 239.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    # POST-M24 Phase 16 — a real REGRESSION market predicting the continuous total itself (e.g.
    # "227 points"), not just Over/Under a fixed line, mirroring football.correct_score's real
    # predicted-value display. Real resolver: `_total_score_regression` in
    # outcome_resolution_service.py, against `home_score + away_score` — same real final score
    # every other total-points market already uses, just reported as the number instead of a
    # boolean classification.
    dict(
        market_key="basketball.game_total_points_prediction",
        name="Predicted Total Points",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.REGRESSION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    # New market — basketball's genuine half-time (Q1+Q2) point total, distinct from
    # first_half_winner (who leads, not the combined score). Real resolver:
    # `_first_half_points_over_under_109_5`, backed by `Fixture.period_scores` (kind="quarter"),
    # confirmed 100%-covered across all 1,708 completed basketball fixtures — unlike football's
    # still-unwired half-time score ingestion, this genuinely resolves today. Line (109.5) is the
    # real median of that same population (min 52, max 193, median 110.0).
    dict(
        market_key="basketball.first_half_total_points",
        name="First Half Total Points Over/Under 109.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.team_total_points",
        name="Individual Team Full-Time Points Over/Under",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.first_half_winner",
        name="First Half Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        # POST-M24 Phase 5A — real resolver: THREE_WAY_MARKET_RESOLVERS reuses football's own
        # `_first_half_winner` against Fixture.period_scores (quarters 1+2), a genuine basketball
        # halftime score, not a borrowed football convention.
        resolver_key="basketball.first_half_winner",
    ),
    # POST-M24 Phase 5B — new period-winner markets, added after confirming (via direct dev.db
    # audit) that all 1,708 completed basketball fixtures carry complete real per-quarter scores.
    # required_features reuse the exact same fixture-scoped form-differential feature every other
    # basketball market already maps — no new feature was needed for a pure outcome resolver over
    # already-ingested period data.
    dict(
        market_key="basketball.second_half_winner",
        name="Second Half Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        resolver_key="basketball.second_half_winner",
    ),
    dict(
        market_key="basketball.q1_winner",
        name="1st Quarter Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        resolver_key="basketball.q1_winner",
    ),
    dict(
        market_key="basketball.q2_winner",
        name="2nd Quarter Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        resolver_key="basketball.q2_winner",
    ),
    dict(
        market_key="basketball.q3_winner",
        name="3rd Quarter Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        resolver_key="basketball.q3_winner",
    ),
    dict(
        market_key="basketball.q4_winner",
        name="4th Quarter Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
        resolver_key="basketball.q4_winner",
    ),
    dict(
        market_key="basketball.race_to_20_points",
        name="Race To 20 Points",
        category="race_to",
        market_kind=MarketKind.RACE_TO,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
    dict(
        market_key="basketball.player_points_prop",
        name="Player Points Over/Under",
        category="player_prop",
        market_kind=MarketKind.PLAYER_PROP,
        target_type=TargetType.REGRESSION,
        required_features=("basketball.fixture.form_points_diff_last5",),
    ),
)


@dataclass
class BasketballMarketSeeder:
    registration: FeatureRegistrationService
    markets: MarketRegistryService
    mappings: FeatureMarketMappingService
    windowed_calculator: RollingTeamStatAverageCalculator
    # POST-M24 Phase 5A — the fixture-scoped feature `required_features` below actually maps
    # (`basketball.fixture.form_points_diff_last5`); `windowed_calculator`'s own TEAM-scoped
    # feature remains registered too (a real per-team signal for any future team-scoped
    # consumer), but is no longer what any market maps as required.
    differential_calculator: FixtureFormDifferentialCalculator

    async def seed(self, now: datetime) -> None:
        await self._ensure_single_record_features_registered(now)
        await self.windowed_calculator.ensure_registered(now)
        await self.differential_calculator.ensure_registered(now)

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
                resolver_key=spec.get("resolver_key"),
            )
        except MarketAlreadyRegisteredError:
            pass

        for feature_key in spec["required_features"]:
            try:
                await self.mappings.map_feature(spec["market_key"], feature_key, is_required=True)
            except MappingAlreadyExistsError:
                continue

        market = await self.markets.markets.get_by_key(spec["market_key"])
        if market.status is MarketStatus.DRAFT:
            await self.markets.submit_for_review(spec["market_key"])
            await self.markets.approve(spec["market_key"], reviewer=SYSTEM_REVIEWER, now=now)
            await self.markets.promote_to_production(spec["market_key"], now=now)
