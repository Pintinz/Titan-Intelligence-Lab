"""Baseball market seeding (Milestone 9 task #140) — mirrors
modules.predictions.football.market_seeding's shape (see that module's ADR note on
representative-not-exhaustive scope, same posture here).

Baseball's spec market list (Moneyline, Run Line, First Five Innings, Team Totals, Runs, Hits,
Home Runs, Strikeouts, Pitcher Props, Batter Props, Inning Markets, Extra Innings, NRFI, YRFI)
seeds one market per distinct `MarketKind` it implies (Moneyline->BINARY, Run Line->SPREAD, Total
Runs->TOTAL, Team Total Runs->TEAM_TOTAL, First Five Innings Winner->SEGMENT_WINNER, Pitcher
Strikeouts->PLAYER_PROP), not the literal named market list. `PLAYER_PROP` is backed by the
fixture-level form-differential feature as its only required signal, the same documented
proxy-not-fabrication choice `basketball.market_seeding` makes for its own player prop.

POST-M24 Phase 5A: `required_features` below points at `baseball.fixture.form_runs_diff_last5`
(`EntityType.FIXTURE`), not the original `baseball.team.form_runs_last5` (`EntityType.TEAM`) —
see `basketball.market_seeding`'s own Phase 5A note for the full reasoning (a team-scoped feature
is structurally invisible to a fixture-scoped market prediction request).
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
from modules.predictions.application.windowed_feature_engineering_service import (
    FixtureFormDifferentialCalculator,
    RollingTeamStatAverageCalculator,
)
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
        required_features=("baseball.fixture.form_runs_diff_last5", "baseball.market.overround"),
    ),
    dict(
        market_key="baseball.run_line",
        name="Run Line",
        category="spread",
        market_kind=MarketKind.SPREAD,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    dict(
        market_key="baseball.total_runs",
        name="Total Runs Over/Under 8.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
        # POST-M24 Phase 13 — real resolver added: `_total_runs_over_under_8_5` in
        # outcome_resolution_service.py, line grounded in this platform's own 3,912-fixture median
        # (dev.db audit: min 0, max 29, median 8.0, mean 8.75) — was seeded with no resolver before.
    ),
    # POST-M24 Phase 15 — four more lines bracketing the median, same shape as football's
    # total_goals_over_under_0_5/1_5/3_5/4_5 around its own 2.5 line. Real dev.db percentiles for
    # the same 3,913-fixture population: p25=5, median=8, p75=12.
    dict(
        market_key="baseball.total_runs_6_5",
        name="Total Runs Over/Under 6.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    dict(
        market_key="baseball.total_runs_7_5",
        name="Total Runs Over/Under 7.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    dict(
        market_key="baseball.total_runs_9_5",
        name="Total Runs Over/Under 9.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    dict(
        market_key="baseball.total_runs_10_5",
        name="Total Runs Over/Under 10.5",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    # POST-M24 Phase 16 — a real REGRESSION market predicting the continuous total itself (e.g.
    # "9 runs"), not just Over/Under a fixed line, mirroring football.correct_score's real
    # predicted-value display. Real resolver: `_total_score_regression` in
    # outcome_resolution_service.py, against `home_score + away_score` — same real final score
    # every other total-runs market already uses, just reported as the number instead of a
    # boolean classification.
    dict(
        market_key="baseball.total_runs_prediction",
        name="Predicted Total Runs",
        category="totals",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.REGRESSION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    dict(
        market_key="baseball.team_total_runs",
        name="Team Total Runs Over/Under",
        category="team_totals",
        market_kind=MarketKind.TEAM_TOTAL,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
    dict(
        market_key="baseball.first_five_innings_winner",
        name="First Five Innings Winner",
        category="segment_winner",
        market_kind=MarketKind.SEGMENT_WINNER,
        target_type=TargetType.CLASSIFICATION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
        # POST-M24 Phase 5A — real resolver: THREE_WAY_MARKET_RESOLVERS' `_first_five_innings_winner`
        # against Fixture.period_scores (innings 1-5 combined).
        resolver_key="baseball.first_five_innings_winner",
    ),
    dict(
        market_key="baseball.pitcher_strikeouts_prop",
        name="Pitcher Strikeouts Over/Under",
        category="player_prop",
        market_kind=MarketKind.PLAYER_PROP,
        target_type=TargetType.REGRESSION,
        required_features=("baseball.fixture.form_runs_diff_last5",),
    ),
)


@dataclass
class BaseballMarketSeeder:
    registration: FeatureRegistrationService
    markets: MarketRegistryService
    mappings: FeatureMarketMappingService
    windowed_calculator: RollingTeamStatAverageCalculator
    # POST-M24 Phase 5A — see `basketball.market_seeding.BasketballMarketSeeder`'s own note.
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
                resolver_key=spec.get("resolver_key"),
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
