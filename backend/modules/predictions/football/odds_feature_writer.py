"""Wires real bookmaker odds into the Feature Store (audit fix 2026-08-02).

Two pieces of real, tested infrastructure existed with zero real invocation path before this:
``FeaturePipeline`` (Milestone 5 — a composable single-record calculator runner, `run()` never
called outside its own tests) and ``ImpliedProbabilityCalculator``/``OddsOverroundCalculator``
(Milestone 9 — registered nowhere). This is that missing caller — the first place either one is
actually exercised against real data, rather than duplicating their logic in a bespoke class.

Feeds ``football.market.implied_probability_home``/``_away``/``football.market.overround`` (the
three ``SINGLE_RECORD_FEATURES`` already registered ACTIVE by ``FootballMarketSeeder.seed()``) —
the required features that block football.both_teams_to_score/correct_score/match_winner from
ever generating a prediction until real odds data reaches a fixture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.value_objects import EntityType
from modules.ingestion.application.data_validation_engine import ValidationResult
from modules.ingestion.application.feature_pipeline import FeaturePipeline
from modules.ingestion.infrastructure.feature_calculators import ImpliedProbabilityCalculator, OddsOverroundCalculator
from modules.sports.ports.provider_gateway import ProviderOddsRecord

IMPLIED_PROBABILITY_HOME_KEY = "football.market.implied_probability_home"
IMPLIED_PROBABILITY_AWAY_KEY = "football.market.implied_probability_away"
OVERROUND_KEY = "football.market.overround"


def _build_pipeline() -> FeaturePipeline:
    pipeline = FeaturePipeline()
    pipeline.register_calculator(ImpliedProbabilityCalculator(feature_key=IMPLIED_PROBABILITY_HOME_KEY, odds_key="home"))
    pipeline.register_calculator(ImpliedProbabilityCalculator(feature_key=IMPLIED_PROBABILITY_AWAY_KEY, odds_key="away"))
    pipeline.register_calculator(
        OddsOverroundCalculator(feature_key=OVERROUND_KEY, odds_keys=("home", "draw", "away"))
    )
    return pipeline


@dataclass
class FootballOddsFeatureWriter:
    store: FeatureStoreService
    pipeline: FeaturePipeline = field(default_factory=_build_pipeline)

    async def compute_and_write(self, fixture_id: str, odds: ProviderOddsRecord, now: datetime) -> tuple[str, ...]:
        """Runs the odds record through the pipeline (already-validated by
        ``DataValidationEngine.validate_odds`` upstream, so normalize/validate/clean are all
        identity here) and persists whichever of the three features the calculators could
        compute — ``OddsOverroundCalculator`` needs all three odds present, so a two-way-only
        record (no ``draw``) still yields the two implied-probability features."""
        raw = {"odds": {"home": odds.home_win, "draw": odds.draw, "away": odds.away_win}}
        result = await self.pipeline.run(
            raw, now, normalize=lambda r: r, validate=lambda r: ValidationResult.ok(), clean=lambda r: r
        )
        written = []
        for feature_key, value in result.computed_features:
            await self.store.write(feature_key, EntityType.FIXTURE, fixture_id, value, now)
            written.append(feature_key)
        return tuple(written)


def football_odds_feature_writer(store: FeatureStoreService) -> FootballOddsFeatureWriter:
    return FootballOddsFeatureWriter(store=store)
