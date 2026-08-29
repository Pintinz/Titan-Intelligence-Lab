"""One-off backfill (2026-08-06, ML-architecture consolidation follow-up): constructs real
`Prediction` + `PredictionOutcome` rows for `football.correct_score` directly from dev.db's already-
completed fixtures, bypassing the live generation API entirely.

Why this exists — a genuine chicken-and-egg gap, not a shortcut: `DatasetBuilder` (Dataset
Platform) only ever reads training labels from *resolved* `PredictionOutcome` rows, which only
exist for `Prediction` rows that already exist. But `football.correct_score` has deliberately had
no Champion and no formula fallback since the ML-architecture consolidation (2026-08-04) — every
live `POST /predictions/generate` call for it raises `NoChampionModelError` ("insufficient
historical data") by design. So the ~800 real completed fixtures already sitting in dev.db, with
their real final scores and already-backfilled `expected_home_goals`/`expected_away_goals`
features (Milestone task #145), can never reach the training pipeline through the normal
generate-then-resolve flow — nothing has ever been allowed to generate a Correct Score prediction
for them in the first place. This script is the one-time unblock: it constructs the `Prediction`/
`PredictionOutcome` pair directly, the same shape the live pipeline would have produced had a real
predictor existed at the time, so `ScheduledRetrainingOrchestrator`'s existing bootstrap loop
(unmodified — Milestone task #200) can pick up football.correct_score on its next sweep and train
a real Champion.

Every backfilled `Prediction.value`/`probability`/`confidence`/`explanation` is an honest inert
placeholder, NOT a fabricated historical prediction — no real predictor ever ran for these fixtures
(that's the entire point being fixed), so claiming otherwise would misrepresent what happened. Only
`feature_snapshot` (real, from the Feature Store) and the resulting `PredictionOutcome.actual_value`
(the real final score, bucketed through the same grid `_correct_score` resolver production traffic
uses) are real. `_label_from_outcome`'s multiclass path (dataset_builder_service.py) only ever reads
`outcome.actual_value` for these markets, never `prediction.value` — so the placeholder is provably
inert to the one thing this backfill exists to produce: real (features, real-label-index) pairs.

Idempotent: skips any fixture that already has a `football.correct_score` prediction (checked via
`list_by_subject`), so re-running after new fixtures complete only backfills the new ones. Reuses
(or registers once) a single non-Champion, never-promoted CANDIDATE `ModelDefinition` purely as the
required `model_id` foreign key anchor — this deliberately never becomes a Challenger/Champion, so
`ScheduledRetrainingOrchestrator`'s `is_bootstrap` check (no Champion exists yet) stays true exactly
as it was before this script ran.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_correct_score_training_data.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from scripts.production_safety_guard import require_confirmation_outside_development
from modules.predictions.domain.entities import ConfidenceBreakdown, ExplanationBundle, Prediction, PredictionOutcome
from modules.predictions.domain.value_objects import ModelId, PredictionId, PredictionOutcomeId, PredictionStatus
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyPredictionOutcomeRepository,
    SqlAlchemyPredictionRepository,
)
from modules.predictions.application.model_registry_service import ModelAlreadyRegisteredError, ModelRegistryService
from modules.predictions.domain.market_outcome_registry import MARKET_OUTCOME_CATALOG

MARKET_KEY = "football.correct_score"
BACKFILL_MODEL_KEY = "football.correct_score.historical-backfill"
_INERT_CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.0, feature_freshness=0.0, historical_accuracy=0.0, knowledge_graph_completeness=0.0,
    news_reliability=0.0, community_reliability=0.0, data_completeness=0.0, model_reliability=0.0,
    prediction_stability=0.0,
)


def _dashed(fixture_id_hex: str) -> str:
    return f"{fixture_id_hex[0:8]}-{fixture_id_hex[8:12]}-{fixture_id_hex[12:16]}-{fixture_id_hex[16:20]}-{fixture_id_hex[20:32]}"


def _bucket_scoreline(home_score: int, away_score: int, allowed_values: tuple[str, ...]) -> str:
    scoreline = f"{home_score}-{away_score}"
    return scoreline if scoreline in allowed_values else "OTHER"


async def main() -> None:
    require_confirmation_outside_development(__file__)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        model_registry = ModelRegistryService(models=SqlAlchemyModelRepository(session=session))
        predictions = SqlAlchemyPredictionRepository(session=session)
        outcomes = SqlAlchemyPredictionOutcomeRepository(session=session)

        market = await markets.get_by_key(MARKET_KEY)
        if market is None:
            raise RuntimeError(f"market '{MARKET_KEY}' not found — run scripts/seed_football_markets.py first")

        allowed_values = tuple(MARKET_OUTCOME_CATALOG[MARKET_KEY].allowed_values)

        try:
            anchor = await model_registry.register(
                market_id=market.id, model_key=BACKFILL_MODEL_KEY, version=1, algorithm="backfill-anchor",
                now=datetime.now(timezone.utc),
            )
        except ModelAlreadyRegisteredError:
            anchor = await model_registry.models.get_by_key_version(BACKFILL_MODEL_KEY, 1)

        fixture_ids = [
            row[0]
            for row in (
                await session.execute(
                    text("SELECT id FROM fixtures WHERE status = 'completed' AND home_score IS NOT NULL")
                )
            ).all()
        ]

        created = 0
        skipped_existing = 0
        skipped_missing_features = 0
        now = datetime.now(timezone.utc)

        for fixture_id in fixture_ids:
            dashed = _dashed(fixture_id)
            existing = await predictions.list_by_subject(dashed, market.id)
            if existing:
                skipped_existing += 1
                continue

            row = (
                await session.execute(
                    text(
                        """
                        SELECT f.home_score, f.away_score, f.scheduled_at,
                          (SELECT v.value FROM feature_values_offline v
                           WHERE v.feature_key = 'football.fixture.expected_home_goals' AND v.entity_id = :dashed
                           AND v.as_of <= f.scheduled_at
                           ORDER BY v.as_of DESC LIMIT 1) AS eh,
                          (SELECT v.value FROM feature_values_offline v
                           WHERE v.feature_key = 'football.fixture.expected_away_goals' AND v.entity_id = :dashed
                           AND v.as_of <= f.scheduled_at
                           ORDER BY v.as_of DESC LIMIT 1) AS ea
                        FROM fixtures f WHERE f.id = :fixture_id
                        """
                    ),
                    {"fixture_id": fixture_id, "dashed": dashed},
                )
            ).one()
            home_score, away_score, scheduled_at, eh_json, ea_json = row
            if eh_json is None or ea_json is None:
                skipped_missing_features += 1
                continue

            feature_snapshot = {
                "football.fixture.expected_home_goals": json.loads(eh_json)["v"],
                "football.fixture.expected_away_goals": json.loads(ea_json)["v"],
            }
            actual_value = _bucket_scoreline(home_score, away_score, allowed_values)
            evaluated_at = (
                datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at
            ) or now

            prediction = await predictions.record(
                Prediction(
                    id=PredictionId(uuid4()),
                    market_id=market.id,
                    model_id=anchor.id,
                    subject_ref=dashed,
                    # Honest inert placeholder — no real predictor ever ran for this fixture+market
                    # (that gap is exactly what this backfill exists to close); never a fabricated
                    # historical prediction. See module docstring.
                    value="insufficient_historical_data",
                    probability=0.0,
                    confidence=_INERT_CONFIDENCE,
                    explanation=ExplanationBundle(),
                    feature_snapshot=feature_snapshot,
                    model_version="backfill-anchor.v1",
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
            f"Backfilled {created} football.correct_score (Prediction, PredictionOutcome) pairs, "
            f"skipped {skipped_existing} already-backfilled fixtures and {skipped_missing_features} "
            f"missing expected-goals features."
        )


if __name__ == "__main__":
    asyncio.run(main())
