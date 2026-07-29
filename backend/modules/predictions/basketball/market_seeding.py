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
25+ named markets. The `PLAYER_PROP` market is backed by the team-level form feature as its only
required signal — a real but imperfect proxy (a player's scoring correlates with team offensive
form) since no player-level windowed feature exists yet (no `PlayerStatistics` repository port
was built this milestone — a documented gap, not a fabricated one).
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
from modules.predictions.application.windowed_feature_engineering_service import RollingTeamStatAverageCalculator
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
        required_features=("basketball.team.form_points_last5", "basketball.market.overround"),
    ),
    dict(
        market_key="basketball.point_spread",
        name="Point Spread",
        category="spread",
        market_kind=MarketKind.SPREAD,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.team.form_points_last5",),
    ),
    dict(
        market_key="basketball.game_total_points",
        name="Game Total Points Over/Under",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.team.form_points_last5",),
    ),
    dict(
        market_key="basketball.team_total_points",
        name="Individual Team Full-Time Points Over/Under",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.team.form_points_last5",),
    ),
    dict(
        market_key="basketball.first_half_winner",
        name="First Half Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.team.form_points_last5",),
    ),
    dict(
        market_key="basketball.race_to_20_points",
        name="Race To 20 Points",
        category="race_to",
        market_kind=MarketKind.RACE_TO,
        target_type=TargetType.CLASSIFICATION,
        required_features=("basketball.team.form_points_last5",),
    ),
    dict(
        market_key="basketball.player_points_prop",
        name="Player Points Over/Under",
        category="player_prop",
        market_kind=MarketKind.PLAYER_PROP,
        target_type=TargetType.REGRESSION,
        required_features=("basketball.team.form_points_last5",),
    ),
)


@dataclass
class BasketballMarketSeeder:
    registration: FeatureRegistrationService
    markets: MarketRegistryService
    mappings: FeatureMarketMappingService
    windowed_calculator: RollingTeamStatAverageCalculator

    async def seed(self, now: datetime) -> None:
        await self._ensure_single_record_features_registered(now)
        await self.windowed_calculator.ensure_registered(now)

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
