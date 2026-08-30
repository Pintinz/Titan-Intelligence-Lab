"""Table Tennis market seeding (Milestone 9 task #141) — mirrors
modules.predictions.football.market_seeding's shape (see that module's ADR note on
representative-not-exhaustive scope, same posture here).

Table Tennis's spec market list (Match Winner, Match Handicap, Set Handicap, Total Sets, Total
Points, Race To Points, Correct Score, Set Winner, Live Winner) seeds one market per distinct
`MarketKind` it implies (Match Winner->BINARY, Match Handicap->SPREAD, Total Points->TOTAL,
Correct Score->CORRECT_SCORE, Race To Points->RACE_TO, Set Winner->SEGMENT_WINNER), not the
literal named market list.

Table Tennis is individual, not team-based (modules.sports.table_tennis.plugin's
`RosterRules(min_on_field=1, max_on_field=2, ...)` models each singles player as a roster of
one) — so it reuses the exact same `TeamStatistics`/`TeamId` machinery every other sport does,
with the plugin's own declared `points_won` stat field (`table_tennis.team.form_points_won_last5`,
task #137), not a separate player-statistics port.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureRegistrationService,
)
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.market_registry_service import MarketAlreadyRegisteredError, MarketRegistryService
from modules.predictions.application.windowed_feature_engineering_service import RollingTeamStatAverageCalculator
from modules.predictions.domain.value_objects import MarketKind, MarketStatus, TargetType

SYSTEM_REVIEWER = "prediction-platform"
SPORT_CODE = "table_tennis"

SINGLE_RECORD_FEATURES: dict[str, tuple[str, str, EntityType]] = {
    "table_tennis.market.implied_probability_player_a": (
        "Implied Probability (Player A)", "1 / decimal player-A-to-win odds.", EntityType.FIXTURE,
    ),
    "table_tennis.market.implied_probability_player_b": (
        "Implied Probability (Player B)", "1 / decimal player-B-to-win odds.", EntityType.FIXTURE,
    ),
    "table_tennis.market.overround": (
        "Market Overround", "Bookmaker margin across player-A/player-B match-winner odds.", EntityType.FIXTURE,
    ),
    "fixture.hours_until_kickoff": (
        "Hours Until Match Start", "Hours between now and match start.", EntityType.FIXTURE,
    ),
}

MARKETS: tuple[dict, ...] = (
    dict(
        market_key="table_tennis.match_winner",
        name="Match Winner",
        category="match_outcome",
        market_kind=MarketKind.BINARY,
        target_type=TargetType.CLASSIFICATION,
        required_features=("table_tennis.team.form_points_won_last5", "table_tennis.market.overround"),
    ),
    dict(
        market_key="table_tennis.match_handicap",
        name="Match Handicap",
        category="spread",
        market_kind=MarketKind.SPREAD,
        target_type=TargetType.CLASSIFICATION,
        required_features=("table_tennis.team.form_points_won_last5",),
    ),
    dict(
        market_key="table_tennis.total_points",
        name="Total Points Over/Under",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("table_tennis.team.form_points_won_last5",),
    ),
    dict(
        market_key="table_tennis.correct_score",
        name="Correct Score",
        category="score",
        market_kind=MarketKind.CORRECT_SCORE,
        target_type=TargetType.CLASSIFICATION,
        required_features=("table_tennis.team.form_points_won_last5",),
    ),
    dict(
        market_key="table_tennis.race_to_11_points",
        name="Race To 11 Points",
        category="race_to",
        market_kind=MarketKind.RACE_TO,
        target_type=TargetType.CLASSIFICATION,
        required_features=("table_tennis.team.form_points_won_last5",),
    ),
    dict(
        market_key="table_tennis.set_winner",
        name="Set Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("table_tennis.team.form_points_won_last5",),
    ),
)


@dataclass
class TableTennisMarketSeeder:
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
                    leakage_classification="PRE_MATCH_SAFE",
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
            await self.mappings.reconcile_feature(spec["market_key"], feature_key, is_required=True)

        market = await self.markets.markets.get_by_key(spec["market_key"])
        if market.status is MarketStatus.DRAFT:
            await self.markets.submit_for_review(spec["market_key"])
            await self.markets.approve(spec["market_key"], reviewer=SYSTEM_REVIEWER, now=now)
            await self.markets.promote_to_production(spec["market_key"], now=now)
