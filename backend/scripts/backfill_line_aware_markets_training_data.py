"""One-off backfill (2026-08-06, ML-architecture consolidation follow-up — companion to
`backfill_correct_score_training_data.py`): constructs real `Prediction` + `PredictionOutcome` rows
for the eleven remaining `NOT_YET_TRAINED_MARKET_KEYS` (the former Poisson-threshold markets —
Total Goals Over/Under at every line, Team Total Goals, Clean Sheet, Win To Nil) directly from
dev.db's already-completed fixtures, bypassing the blocked live-generation API entirely.

Same root cause as football.correct_score, minus the multiclass gap: these eleven markets already
have real, working resolvers (`MARKET_OUTCOME_RESOLVERS`) and a real binary label table
(`MARKET_OUTCOME_LABELS`) — unlike correct_score, they were never missing a resolver_key. What they
share with correct_score is the chicken-and-egg blocker: no formula predictor exists for any of
them since the Poisson-predictor removal, so no `Prediction` has ever been generated for them
(`NoChampionModelError` blocks it at the source), so no `PredictionOutcome` has ever accumulated,
so `DatasetBuilder` has nothing to build from, so `ScheduledRetrainingOrchestrator`'s bootstrap loop
can never fire — regardless of how many completed fixtures with real expected-goals features
already sit in dev.db.

Label encoding: every backfilled `Prediction.value` is the market's real positive label
(`MARKET_OUTCOME_LABELS[market_key].positive_label`, e.g. "OVER"/"YES") — an honest constant claim,
never a fabricated prediction — and `PredictionOutcome.error` (0.0/1.0) carries whether that claim
happened to be true for this fixture, the same (claim, error) -> real-polarity encoding
`OutcomeResolutionService.resolve_for_fixture` already uses for live traffic
(`real_outcome_is_positive`, outcome_label_mapper.py). `_label_from_outcome`
(dataset_builder_service.py) only ever reads this pair, never `prediction.value` as a real
prediction — see that module's docstring for why this is provably inert to what training actually
uses.

Idempotent: skips any (fixture, market) pair that already has a prediction. Reuses the same
non-Champion, never-promoted CANDIDATE `ModelDefinition` anchor per market
(`backfill_correct_score_training_data.py`'s naming convention), one per market so
`ScheduledRetrainingOrchestrator`'s `is_bootstrap` check (no Champion exists yet) stays true.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_line_aware_markets_training_data.py
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
from modules.predictions.application.model_registry_service import ModelAlreadyRegisteredError, ModelRegistryService
from modules.predictions.application.outcome_label_mapper import MARKET_OUTCOME_LABELS
from modules.predictions.application.outcome_resolution_service import MARKET_OUTCOME_RESOLVERS, MatchResult
from modules.predictions.domain.entities import ConfidenceBreakdown, ExplanationBundle, Prediction, PredictionOutcome
from modules.predictions.domain.value_objects import PredictionId, PredictionOutcomeId, PredictionStatus
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyPredictionOutcomeRepository,
    SqlAlchemyPredictionRepository,
)

MARKET_KEYS = (
    "football.total_goals_over_under",
    "football.total_goals_over_under_0_5",
    "football.total_goals_over_under_1_5",
    "football.total_goals_over_under_3_5",
    "football.total_goals_over_under_4_5",
    "football.home_team_total_goals",
    "football.away_team_total_goals",
    "football.home_clean_sheet",
    "football.away_clean_sheet",
    "football.home_win_to_nil",
    "football.away_win_to_nil",
)
_INERT_CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.0, feature_freshness=0.0, historical_accuracy=0.0, knowledge_graph_completeness=0.0,
    news_reliability=0.0, community_reliability=0.0, data_completeness=0.0, model_reliability=0.0,
    prediction_stability=0.0,
)


def _dashed(fixture_id_hex: str) -> str:
    return f"{fixture_id_hex[0:8]}-{fixture_id_hex[8:12]}-{fixture_id_hex[12:16]}-{fixture_id_hex[16:20]}-{fixture_id_hex[20:32]}"


async def main() -> None:
    require_confirmation_outside_development(__file__)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets_repo = SqlAlchemyMarketRepository(session=session)
        model_registry = ModelRegistryService(models=SqlAlchemyModelRepository(session=session))
        predictions = SqlAlchemyPredictionRepository(session=session)
        outcomes = SqlAlchemyPredictionOutcomeRepository(session=session)

        fixture_ids = [
            row[0]
            for row in (
                await session.execute(
                    text("SELECT id FROM fixtures WHERE status = 'completed' AND home_score IS NOT NULL")
                )
            ).all()
        ]

        now = datetime.now(timezone.utc)
        totals = {}

        for market_key in MARKET_KEYS:
            market = await markets_repo.get_by_key(market_key)
            if market is None:
                print(f"{market_key}: market not found, skipping")
                continue

            resolver = MARKET_OUTCOME_RESOLVERS[market_key]
            positive_label = MARKET_OUTCOME_LABELS[market_key].positive_label

            try:
                anchor = await model_registry.register(
                    market_id=market.id, model_key=f"{market_key}.historical-backfill", version=1,
                    algorithm="backfill-anchor", now=now,
                )
            except ModelAlreadyRegisteredError:
                anchor = await model_registry.models.get_by_key_version(f"{market_key}.historical-backfill", 1)

            created = skipped_existing = skipped_missing_features = skipped_unmodeled = 0

            for fixture_id in fixture_ids:
                dashed = _dashed(fixture_id)
                if await predictions.list_by_subject(dashed, market.id):
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

                resolved = resolver(MatchResult(home_score, away_score))
                if resolved is None:
                    skipped_unmodeled += 1  # e.g. moneyline resolvers skipping a draw — not relevant to these 11
                    continue

                feature_snapshot = {
                    "football.fixture.expected_home_goals": json.loads(eh_json)["v"],
                    "football.fixture.expected_away_goals": json.loads(ea_json)["v"],
                }
                evaluated_at = (
                    datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at
                ) or now

                prediction = await predictions.record(
                    Prediction(
                        id=PredictionId(uuid4()),
                        market_id=market.id,
                        model_id=anchor.id,
                        subject_ref=dashed,
                        value=positive_label,
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
                        actual_value=resolved.actual_value,
                        error=0.0 if resolved.matches_positive else 1.0,
                        evaluated_at=evaluated_at,
                    )
                )
                created += 1

            totals[market_key] = created
            print(
                f"{market_key}: backfilled {created}, skipped {skipped_existing} existing, "
                f"{skipped_missing_features} missing features, {skipped_unmodeled} unmodeled"
            )

        await session.commit()
        print(f"Total backfilled: {sum(totals.values())}")


if __name__ == "__main__":
    asyncio.run(main())
