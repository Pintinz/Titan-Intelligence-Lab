"""One-off backfill (2026-08-06): retires football.match_winner's placeholder Champion
(`heuristic_logistic_v1`, registered at market seeding time, never actually trained —
`dataset_version` was always None) and backfills real `Prediction` + `PredictionOutcome` rows so
the existing bootstrap loop can train a real one.

Why this market needed a different fix than the 12 markets fixed earlier today: those had NO
Champion at all, so `ScheduledRetrainingOrchestrator`'s "never trained, always retry" bootstrap
branch already applied to them the moment training data existed. `football.match_winner` has
always had a Champion — a placeholder registered directly at PRODUCTION-market-seeding time, never
through the real train/evaluate/promote pipeline. Because a Champion already exists,
`_check_and_retrain`'s `is_bootstrap` check (`get_champion() is None`) is False, so it instead goes
through `RetrainingScheduler.should_retrain()`, which needs a PRIOR real Dataset to compare
staleness against — one that was never built, since no dataset ever existed for this market. Net
effect: this market was stuck in limbo, silently serving a formula prediction under a "Champion"
label with no path to ever becoming a real trained model. Retiring the placeholder is what makes it
honestly untrained again, matching the "one real trained model per market, never a fabricated
placeholder" posture the 2026-08-04 consolidation already established for the other 12 markets.

Label encoding: football.match_winner resolves via THREE_WAY_MARKET_RESOLVERS (direct label
equality against HOME_WIN/DRAW/AWAY_WIN) — `_label_from_outcome`'s multiclass path only ever reads
`PredictionOutcome.actual_value`, never `Prediction.value`, so every backfilled `Prediction.value`
here is the same honest inert placeholder used for the earlier 12-market backfill, not a fabricated
historical prediction. Feature snapshot includes all 3 required features (implied_probability_home/
away, form_shots_on_target_diff_last5) plus whichever of the 5 optional stat-differential features
are available for a given fixture — exactly mirroring what a live PredictionContextBuilder
resolution would have produced.

Idempotent: skips any fixture that already has a football.match_winner prediction.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_match_winner_training_data.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from scripts.production_safety_guard import require_confirmation_outside_development
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.model_registry_service import ModelAlreadyRegisteredError, ModelRegistryService
from modules.predictions.application.outcome_resolution_service import THREE_WAY_MARKET_RESOLVERS, MatchResult
from modules.predictions.domain.entities import ConfidenceBreakdown, ExplanationBundle, Prediction, PredictionOutcome
from modules.predictions.domain.value_objects import PredictionId, PredictionOutcomeId, PredictionStatus
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureMarketMappingRepository,
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyPredictionOutcomeRepository,
    SqlAlchemyPredictionRepository,
)
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.features.infrastructure.persistence.repositories import (
    SqlAlchemyFeatureDefinitionRepository,
    SqlAlchemyFeatureValueRepository,
)

MARKET_KEY = "football.match_winner"
_INERT_CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.0, feature_freshness=0.0, historical_accuracy=0.0, knowledge_graph_completeness=0.0,
    news_reliability=0.0, community_reliability=0.0, data_completeness=0.0, model_reliability=0.0,
    prediction_stability=0.0,
)


def _dashed(fixture_id_hex: str) -> str:
    return f"{fixture_id_hex[0:8]}-{fixture_id_hex[8:12]}-{fixture_id_hex[12:16]}-{fixture_id_hex[16:20]}-{fixture_id_hex[20:32]}"


async def _feature_value_as_of(session, feature_key: str, dashed: str, cutoff: datetime) -> float | None:
    """Point-in-time read, not "latest ever written" — a feature recomputed after `cutoff` (e.g.
    by a later live re-sync touching this same historical fixture) must stay invisible here.

    Goes through `SqlAlchemyFeatureValueRepository.get_as_of` — the same repository method the
    live serve path already uses — rather than a raw-SQL `as_of <= :cutoff` bound: a first attempt
    at the latter compared a tz-aware Python `datetime` bound parameter against
    `DateTime(timezone=True)`-typed rows as raw SQLite TEXT, and the two didn't serialize to the
    same string format, silently matching nothing (caught by this fix's own regression tests).
    The ORM comparison is spared that entirely."""
    value = await SqlAlchemyFeatureValueRepository(session=session).get_as_of(
        FeatureKey(feature_key), EntityType.FIXTURE, dashed, cutoff
    )
    return None if value is None else value.value


async def main() -> None:
    require_confirmation_outside_development(__file__)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets_repo = SqlAlchemyMarketRepository(session=session)
        model_registry = ModelRegistryService(models=SqlAlchemyModelRepository(session=session))
        predictions = SqlAlchemyPredictionRepository(session=session)
        outcomes = SqlAlchemyPredictionOutcomeRepository(session=session)
        resolver = THREE_WAY_MARKET_RESOLVERS[MARKET_KEY]

        now = datetime.now(timezone.utc)

        market = await markets_repo.get_by_key(MARKET_KEY)
        if market is None:
            raise RuntimeError(f"market '{MARKET_KEY}' not found")

        # Forensic audit finding #2 (2026-08-30): required/optional features used to be
        # hand-copied here from market_seeding.py's spec — a third, independently-maintained
        # declaration of "which features back this market", alongside market_seeding.py itself
        # and FeatureMarketMappingService's persisted mappings, with nothing keeping the three in
        # sync. Reading the live mapping directly means a market_seeding.py spec change (or a
        # `reconcile_feature` correction) reaches this backfill automatically, the same way it now
        # reaches live inference.
        mapping_service = FeatureMarketMappingService(
            mappings=SqlAlchemyFeatureMarketMappingRepository(session=session),
            markets=markets_repo,
            feature_definitions=SqlAlchemyFeatureDefinitionRepository(session=session),
        )
        mappings = await mapping_service.list_for_market(MARKET_KEY)
        required_features = tuple(m.feature_key for m in mappings if m.is_required)
        optional_features = tuple(m.feature_key for m in mappings if not m.is_required)

        champion = await model_registry.models.get_champion(market.id)
        if champion is not None and champion.status.value == "champion":
            await model_registry.retire(champion.id, now)
            print(f"Retired placeholder champion: {champion.model_key} (algorithm={champion.algorithm})")

        try:
            anchor = await model_registry.register(
                market_id=market.id, model_key=f"{MARKET_KEY}.historical-backfill", version=1,
                algorithm="backfill-anchor", now=now,
            )
        except ModelAlreadyRegisteredError:
            anchor = await model_registry.models.get_by_key_version(f"{MARKET_KEY}.historical-backfill", 1)

        fixture_ids = [
            row[0]
            for row in (
                await session.execute(
                    text("SELECT id FROM fixtures WHERE status = 'completed' AND home_score IS NOT NULL")
                )
            ).all()
        ]

        created = skipped_existing = skipped_missing_required = 0

        for fixture_id in fixture_ids:
            dashed = _dashed(fixture_id)
            if await predictions.list_by_subject(dashed, market.id):
                skipped_existing += 1
                continue

            row = (
                await session.execute(
                    text("SELECT home_score, away_score, scheduled_at FROM fixtures WHERE id = :fixture_id"),
                    {"fixture_id": fixture_id},
                )
            ).one()
            home_score, away_score, scheduled_at = row
            # The cutoff for every feature this fixture's snapshot may see — its own kickoff, never
            # the batch's wall-clock `now`. Computed once, before any feature read.
            cutoff = (datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at) or now

            feature_snapshot: dict[str, float] = {}
            missing_required = False
            for key in required_features:
                value = await _feature_value_as_of(session, key, dashed, cutoff)
                if value is None:
                    missing_required = True
                    break
                feature_snapshot[key] = value
            if missing_required:
                skipped_missing_required += 1
                continue
            for key in optional_features:
                value = await _feature_value_as_of(session, key, dashed, cutoff)
                if value is not None:
                    feature_snapshot[key] = value

            actual_value = resolver(MatchResult(home_score, away_score))
            evaluated_at = cutoff

            prediction = await predictions.record(
                Prediction(
                    id=PredictionId(uuid4()),
                    market_id=market.id,
                    model_id=anchor.id,
                    subject_ref=dashed,
                    value="insufficient_historical_data",
                    probability=0.0,
                    confidence=_INERT_CONFIDENCE,
                    explanation=ExplanationBundle(),
                    feature_snapshot=feature_snapshot,
                    model_version="backfill.v1",
                    status=PredictionStatus.DRAFT,
                    generated_at=now,
                    data_freshness=evaluated_at,
                )
            )
            await outcomes.record(
                PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()),
                    prediction_id=prediction.id,
                    actual_value=actual_value,
                    error=None,
                    evaluated_at=evaluated_at,
                )
            )
            created += 1

        await session.commit()
        print(
            f"{MARKET_KEY}: backfilled {created}, skipped {skipped_existing} existing, "
            f"{skipped_missing_required} missing required features"
        )


if __name__ == "__main__":
    asyncio.run(main())
