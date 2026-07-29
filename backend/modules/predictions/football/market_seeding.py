"""Football market seeding (Milestone 9 task #138) — the first per-sport instantiation of the
data-driven Market Registry (docs/decisions.md — data-driven market registry). Registers a
representative (not exhaustive — same ADR-narrowing posture as every other honestly-scoped v1
component this milestone) set of football prediction markets, one per relevant `MarketKind`,
each backed by real, already-registered features: the single-record market-derived signals from
task #136 (`ImpliedProbabilityCalculator`/`OddsOverroundCalculator`, registered here since that
task built the calculators but not their Feature Registry entries) plus task #137's windowed
team-form feature. No market here ever reaches PRODUCTION with zero features backing it —
`MarketRegistryService.promote_to_production` already refuses that.
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

MARKETS: tuple[dict, ...] = (
    dict(
        market_key="football.both_teams_to_score",
        name="Both Teams To Score",
        category="goals",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.team.form_shots_on_target_last5", "football.market.overround"),
    ),
    dict(
        market_key="football.total_goals_over_under",
        name="Total Goals Over/Under 2.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.team.form_shots_on_target_last5",),
    ),
    dict(
        market_key="football.home_team_total_goals",
        name="Home Team Total Goals Over/Under 1.5",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.team.form_shots_on_target_last5",),
    ),
    dict(
        market_key="football.correct_score",
        name="Correct Score",
        category="score",
        market_kind=MarketKind.CORRECT_SCORE,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.team.form_shots_on_target_last5", "football.market.implied_probability_home"),
    ),
    dict(
        market_key="football.first_half_winner",
        name="First Half Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("football.team.form_shots_on_target_last5",),
    ),
)


@dataclass
class FootballMarketSeeder:
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
