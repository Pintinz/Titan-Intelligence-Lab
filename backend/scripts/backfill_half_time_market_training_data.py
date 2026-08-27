"""Phase 1 (PROJECT TITANIQ — PHASE 1 COMMAND PROMPT): backfills real Prediction + PredictionOutcome
rows for the 4 half-time football markets (first_half_winner, second_half_winner,
first_half_goals, first_half_both_teams_to_score), now that real half-time scores exist on
`Fixture.period_scores` for the 2022-2024 seasons (see backfill_football_half_time_scores.py).

Same idiom as `backfill_match_winner_training_data.py`: these markets have never had a Champion,
so `DatasetBuilder.build()` needs real historical `PredictionOutcome` rows to train from — it reads
`self.outcomes.list_by_market(...)` then `self.predictions.get(outcome.prediction_id)`, it does not
resolve labels directly from `Fixture` rows. Every `Prediction.value` here is the same honest inert
anchor value the match_winner backfill used — never a fabricated historical prediction — and every
`PredictionOutcome.actual_value`/`error` is computed from the real, now-backfilled half-time score
via the market's own real resolver (`THREE_WAY_MARKET_RESOLVERS`/`MARKET_OUTCOME_RESOLVERS`, the
exact same resolvers `OutcomeResolutionService.resolve_for_fixture` uses for live evaluation).

first_half_winner/second_half_winner (3-way HOME_WIN/DRAW/AWAY_WIN): `Prediction.value` is the
inert placeholder "insufficient_historical_data" (matches football.match_winner's backfill,
since `_label_from_outcome`'s multiclass branch only ever reads `PredictionOutcome.actual_value`).

first_half_goals/first_half_both_teams_to_score (binary OVER/UNDER, YES/NO): `Prediction.value` is
set to the market's own positive label (`MARKET_OUTCOME_LABELS`) as an arbitrary anchor —
`PredictionOutcome.error` (0.0/1.0, computed by comparing that anchor's polarity against the real
resolved outcome) is what `real_outcome_is_positive` uses to recover the genuine historical label
during dataset building, regardless of which anchor was chosen; this is the same mechanism
`OutcomeResolutionService.resolve_for_fixture`'s live evaluation path already uses.

Only resolves a fixture whose half-time score is genuinely present (`resolver(...) is not None`)
— never derives or guesses one. Idempotent: skips any fixture that already has a prediction for
the given market.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_half_time_market_training_data.py
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
from modules.predictions.application.outcome_resolution_service import (
    MARKET_OUTCOME_RESOLVERS,
    THREE_WAY_MARKET_RESOLVERS,
    MatchResult,
)
from modules.predictions.domain.entities import ConfidenceBreakdown, ExplanationBundle, Prediction, PredictionOutcome
from modules.predictions.domain.value_objects import PredictionId, PredictionOutcomeId, PredictionStatus
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyPredictionOutcomeRepository,
    SqlAlchemyPredictionRepository,
)
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.features.infrastructure.persistence.repositories import SqlAlchemyFeatureValueRepository

THREE_WAY_MARKETS = ("football.first_half_winner", "football.second_half_winner")
BINARY_MARKETS = ("football.first_half_goals", "football.first_half_both_teams_to_score")

REQUIRED_FEATURES = ("football.fixture.form_shots_on_target_diff_last5",)
OPTIONAL_FEATURES = (
    "football.fixture.form_possession_pct_diff_last5",
    "football.fixture.form_shots_total_diff_last5",
    "football.fixture.form_corners_diff_last5",
    "football.fixture.form_fouls_diff_last5",
    "football.fixture.form_cards_yellow_diff_last5",
    "football.fixture.home_lineup_continuity",
    "football.fixture.away_lineup_continuity",
    "football.fixture.home_transfer_activity",
    "football.fixture.away_transfer_activity",
)
_INERT_CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.0, feature_freshness=0.0, historical_accuracy=0.0, knowledge_graph_completeness=0.0,
    news_reliability=0.0, community_reliability=0.0, data_completeness=0.0, model_reliability=0.0,
    prediction_stability=0.0,
)


def _dashed(fixture_id_hex: str) -> str:
    return f"{fixture_id_hex[0:8]}-{fixture_id_hex[8:12]}-{fixture_id_hex[12:16]}-{fixture_id_hex[16:20]}-{fixture_id_hex[20:32]}"


async def _feature_value_as_of(session, feature_key: str, dashed: str, cutoff: datetime) -> float | None:
    """Point-in-time read — see `backfill_match_winner_training_data.py`'s identical helper for the
    full rationale (including why this goes through the ORM repository, not a raw-SQL bound
    parameter). A feature recomputed after `cutoff` must stay invisible here."""
    value = await SqlAlchemyFeatureValueRepository(session=session).get_as_of(
        FeatureKey(feature_key), EntityType.FIXTURE, dashed, cutoff
    )
    return None if value is None else value.value


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets_repo = SqlAlchemyMarketRepository(session=session)
        model_registry = ModelRegistryService(models=SqlAlchemyModelRepository(session=session))
        predictions = SqlAlchemyPredictionRepository(session=session)
        outcomes = SqlAlchemyPredictionOutcomeRepository(session=session)
        now = datetime.now(timezone.utc)

        fixture_rows = (
            await session.execute(
                text(
                    "SELECT f.id, f.home_score, f.away_score, f.period_scores, f.scheduled_at "
                    "FROM fixtures f "
                    "JOIN seasons se ON se.id = f.season_id "
                    "JOIN competitions c ON c.id = se.competition_id "
                    "JOIN sports s ON s.id = c.sport_id "
                    "WHERE s.code = 'football' AND f.status = 'completed' "
                    "AND f.home_score IS NOT NULL AND f.away_score IS NOT NULL AND f.period_scores IS NOT NULL"
                )
            )
        ).all()
        print(f"{len(fixture_rows)} completed football fixtures with period_scores column set", flush=True)

        for market_key in THREE_WAY_MARKETS + BINARY_MARKETS:
            market = await markets_repo.get_by_key(market_key)
            if market is None:
                print(f"{market_key}: market not found — skipping", flush=True)
                continue

            anchor_key = f"{market_key}.historical-backfill"
            try:
                anchor = await model_registry.register(
                    market_id=market.id, model_key=anchor_key, version=1, algorithm="backfill-anchor", now=now,
                )
            except ModelAlreadyRegisteredError:
                anchor = await model_registry.models.get_by_key_version(anchor_key, 1)

            three_way_resolver = THREE_WAY_MARKET_RESOLVERS.get(market_key)
            binary_resolver = MARKET_OUTCOME_RESOLVERS.get(market_key)
            label_pair = MARKET_OUTCOME_LABELS.get(market_key)

            created = skipped_existing = skipped_unresolvable = skipped_missing_required = 0
            for fixture_id, home_score, away_score, period_scores_raw, scheduled_at in fixture_rows:
                dashed = _dashed(fixture_id)
                if await predictions.list_by_subject(dashed, market.id):
                    skipped_existing += 1
                    continue

                period_scores = json.loads(period_scores_raw)
                home_ht = away_ht = None
                if period_scores is not None and period_scores.get("kind") == "half":
                    home_ht = period_scores["home"][0]
                    away_ht = period_scores["away"][0]
                result = MatchResult(home_score, away_score, home_ht, away_ht)

                if three_way_resolver is not None:
                    actual_value = three_way_resolver(result)
                    if actual_value is None:
                        skipped_unresolvable += 1
                        continue
                    prediction_value = "insufficient_historical_data"
                    error = None
                else:
                    resolved = binary_resolver(result)
                    if resolved is None:
                        skipped_unresolvable += 1
                        continue
                    prediction_value = label_pair.positive_label
                    actual_value = resolved.actual_value
                    error = 0.0 if resolved.matches_positive else 1.0

                # The cutoff for every feature this fixture's snapshot may see — its own kickoff,
                # never the batch's wall-clock `now`. Computed once, before any feature read.
                cutoff = (
                    datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at
                ) or now

                feature_snapshot: dict[str, float] = {}
                missing_required = False
                for key in REQUIRED_FEATURES:
                    value = await _feature_value_as_of(session, key, dashed, cutoff)
                    if value is None:
                        missing_required = True
                        break
                    feature_snapshot[key] = value
                if missing_required:
                    skipped_missing_required += 1
                    continue
                for key in OPTIONAL_FEATURES:
                    value = await _feature_value_as_of(session, key, dashed, cutoff)
                    if value is not None:
                        feature_snapshot[key] = value

                evaluated_at = cutoff

                prediction = await predictions.record(
                    Prediction(
                        id=PredictionId(uuid4()),
                        market_id=market.id,
                        model_id=anchor.id,
                        subject_ref=dashed,
                        value=prediction_value,
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
                        error=error,
                        evaluated_at=evaluated_at,
                    )
                )
                created += 1

            await session.commit()
            print(
                f"{market_key}: created={created} skipped_existing={skipped_existing} "
                f"skipped_unresolvable_ht={skipped_unresolvable} skipped_missing_required={skipped_missing_required}",
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
