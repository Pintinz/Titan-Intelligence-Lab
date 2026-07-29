"""Baseball market seeding (Milestone 9 task #140) — mirrors
modules.predictions.football.market_seeding's shape (see that module's ADR note on
representative-not-exhaustive scope, same posture here).

Baseball's spec market list (Moneyline, Run Line, First Five Innings, Team Totals, Runs, Hits,
Home Runs, Strikeouts, Pitcher Props, Batter Props, Inning Markets, Extra Innings, NRFI, YRFI)
seeds one market per distinct `MarketKind` it implies (Moneyline->BINARY, Run Line->SPREAD, Total
Runs->TOTAL, Team Total Runs->TEAM_TOTAL, First Five Innings Winner->SEGMENT_WINNER, Pitcher
Strikeouts->PLAYER_PROP), not the literal named market list. `PLAYER_PROP` is backed by the
team-level form feature as its only required signal, the same documented proxy-not-fabrication
choice `basketball.market_seeding` makes for its own player prop.
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
SPORT_CODE = "baseball"

SINGLE_RECORD_FEATURES: dict[str, tuple[str, str, EntityType]] = {
    "baseball.market.implied_probability_home": (
        "Implied Probability (Home)", "1 / decimal home-win moneyline odds.", EntityType.FIXTURE,
    ),
    "baseball.market.implied_probability_away": (
        "Implied Probability (Away)", "1 / decimal away-win moneyline odds.", EntityType.FIXTURE,
    ),
    "baseball.market.overround": (
        "Market Overround", "Bookmaker margin across home/away moneyline odds.", EntityType.FIXTURE,
    ),
    "fixture.hours_until_kickoff": (
        "Hours Until First Pitch", "Hours between now and first pitch.", EntityType.FIXTURE,
    ),
}

MARKETS: tuple[dict, ...] = (
    dict(
        market_key="baseball.moneyline",
        name="Moneyline",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.team.form_runs_last5", "baseball.market.overround"),
    ),
    dict(
        market_key="baseball.run_line",
        name="Run Line",
        category="spread",
        market_kind=MarketKind.SPREAD,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.team.form_runs_last5",),
    ),
    dict(
        market_key="baseball.total_runs",
        name="Total Runs Over/Under",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.team.form_runs_last5",),
    ),
    dict(
        market_key="baseball.team_total_runs",
        name="Team Total Runs Over/Under",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.team.form_runs_last5",),
    ),
    dict(
        market_key="baseball.first_five_innings_winner",
        name="First Five Innings Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.team.form_runs_last5",),
    ),
    dict(
        market_key="baseball.pitcher_strikeouts_prop",
        name="Pitcher Strikeouts Over/Under",
        category="player_prop",
        market_kind=MarketKind.PLAYER_PROP,
        target_type=TargetType.REGRESSION,
        required_features=("baseball.team.form_runs_last5",),
    ),
)


@dataclass
class BaseballMarketSeeder:
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
