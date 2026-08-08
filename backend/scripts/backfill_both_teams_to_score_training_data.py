"""One-off backfill (2026-08-06): same fix as `backfill_match_winner_training_data.py`, applied to
football.both_teams_to_score — retires its placeholder Champion (`heuristic_logistic_v1`, never
actually trained) and backfills real `Prediction`/`PredictionOutcome` rows so the bootstrap loop can
train a real one. Full audit of every market's Champion state (2026-08-06) found this is the only
other production market stuck in the same limbo: a Champion already existed (blocking the "never
trained" bootstrap branch) but no Dataset was ever built (blocking the normal staleness-retrain
path either) — see that script's docstring for the full mechanism.

football.both_teams_to_score already had a real resolver (`_both_teams_to_score`, wired long before
this session's work) and a real binary label pair (`MARKET_OUTCOME_LABELS["football.both_teams_to_score"]`
= YES/NO) — this backfill uses the exact same (claim, error) encoding as
`backfill_line_aware_markets_training_data.py`'s binary markets, just with this market's own
required features (`football.market.overround`, `football.fixture.form_shots_on_target_diff_last5`,
plus whichever of the 5 optional stat-differential features are available per fixture) instead of
the expected-goals pair those eleven markets use.

Idempotent: skips any fixture that already has a football.both_teams_to_score prediction.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_both_teams_to_score_training_data.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
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

MARKET_KEY = "football.both_teams_to_score"
REQUIRED_FEATURES = ("football.market.overround", "football.fixture.form_shots_on_target_diff_last5")
OPTIONAL_FEATURES = (
    "football.fixture.form_possession_pct_diff_last5",
    "football.fixture.form_shots_total_diff_last5",
    "football.fixture.form_corners_diff_last5",
    "football.fixture.form_fouls_diff_last5",
    "football.fixture.form_cards_yellow_diff_last5",
)
_INERT_CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.0, feature_freshness=0.0, historical_accuracy=0.0, knowledge_graph_completeness=0.0,
    news_reliability=0.0, community_reliability=0.0, data_completeness=0.0, model_reliability=0.0,
    prediction_stability=0.0,
)


def _dashed(fixture_id_hex: str) -> str:
    return f"{fixture_id_hex[0:8]}-{fixture_id_hex[8:12]}-{fixture_id_hex[12:16]}-{fixture_id_hex[16:20]}-{fixture_id_hex[20:32]}"


async def _latest_feature_value(session, feature_key: str, dashed: str) -> float | None:
    row = (
        await session.execute(
            text(
                "SELECT value FROM feature_values_offline WHERE feature_key = :fk AND entity_id = :eid "
                "ORDER BY as_of DESC LIMIT 1"
            ),
            {"fk": feature_key, "eid": dashed},
        )
    ).fetchone()
    return None if row is None else json.loads(row[0])["v"]


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets_repo = SqlAlchemyMarketRepository(session=session)
        model_registry = ModelRegistryService(models=SqlAlchemyModelRepository(session=session))
        predictions = SqlAlchemyPredictionRepository(session=session)
        outcomes = SqlAlchemyPredictionOutcomeRepository(session=session)
        resolver = MARKET_OUTCOME_RESOLVERS[MARKET_KEY]
        positive_label = MARKET_OUTCOME_LABELS[MARKET_KEY].positive_label

        now = datetime.now(timezone.utc)

        market = await markets_repo.get_by_key(MARKET_KEY)
        if market is None:
            raise RuntimeError(f"market '{MARKET_KEY}' not found")

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

            feature_snapshot: dict[str, float] = {}
            missing_required = False
            for key in REQUIRED_FEATURES:
                value = await _latest_feature_value(session, key, dashed)
                if value is None:
                    missing_required = True
                    break
                feature_snapshot[key] = value
            if missing_required:
                skipped_missing_required += 1
                continue
            for key in OPTIONAL_FEATURES:
                value = await _latest_feature_value(session, key, dashed)
                if value is not None:
                    feature_snapshot[key] = value

            resolved = resolver(MatchResult(home_score, away_score))
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
                    actual_value=resolved.actual_value,
                    error=0.0 if resolved.matches_positive else 1.0,
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
