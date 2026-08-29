"""Task #158/#159 (Phase 10 follow-on) — backfills real Prediction/PredictionOutcome rows for
basketball and baseball, the exact same honest bootstrap mechanism already used for football's
`backfill_match_winner_training_data.py`/`backfill_both_teams_to_score_training_data.py`: register a
`backfill-anchor` Model (never served, no artifact), then for every real COMPLETED fixture with a
real recorded score, construct a real `Prediction` (inert placeholder value/probability/confidence —
never a fabricated guess) paired with a real `PredictionOutcome` whose `actual_value`/`error` is
recovered from the fixture's own real final score via the market's already-wired, already-tested
resolver (`MARKET_OUTCOME_RESOLVERS`/`THREE_WAY_MARKET_RESOLVERS`, `outcome_resolution_service.py`).
`DatasetBuilder.build()` reads exclusively from these two tables — this is the only legitimate way
to ever accumulate the training data `ScheduledRetrainingOrchestrator`'s bootstrap branch needs.

Scope, and why it's not all 18 markets: only 7 basketball markets (moneyline, first_half_winner,
second_half_winner, q1-q4_winner) and 2 baseball markets (moneyline, first_five_innings_winner) have
a real resolver registered in `outcome_resolution_service.py` at all. The other 9 (point_spread,
game_total_points, team_total_points, race_to_20_points, player_points_prop for basketball; run_line,
total_runs, team_total_runs, pitcher_strikeouts_prop for baseball) need a real stored betting
line/prop threshold or player-level box-score stats this platform doesn't ingest for these sports —
exactly the same "no resolver exists, never fabricate one" boundary `outcome_label_mapper.py`'s own
module docstring documents for football's own un-resolvable markets. Backfilling those 9 would mean
inventing a line/threshold with no real source, which is exactly what's prohibited. They stay
BLOCKED_BY_ARCHITECTURE.

Feature snapshot: read from the real `feature_values_offline` rows the existing
`backfill_secondary_sport_form_differential.py` already wrote — `{sport}.fixture.form_points_diff_last5`/
`form_runs_diff_last5` (required on every market below) plus `{sport}.market.overround` (required only
for `moneyline` — real coverage for this one is 0% today, since no odds provider is wired for these
two sports; that's an honest, separate `required_feature_coverage_acceptable` gap this backfill does
not paper over, not a reason to skip the market's other real signal).

Segment data (basketball quarters, baseball first-five-innings) is read directly from each fixture's
real `period_scores` JSON — never derived/inferred, matching every resolver's own documented
"None means unresolved, never guessed" contract.

Idempotent: skips any (fixture, market) pair that already has a prediction.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_secondary_sport_training_data.py
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
from modules.predictions.application.outcome_resolution_service import (
    MARKET_OUTCOME_RESOLVERS,
    REGRESSION_MARKET_RESOLVERS,
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

_INERT_CONFIDENCE = ConfidenceBreakdown(
    feature_quality=0.0, feature_freshness=0.0, historical_accuracy=0.0, knowledge_graph_completeness=0.0,
    news_reliability=0.0, community_reliability=0.0, data_completeness=0.0, model_reliability=0.0,
    prediction_stability=0.0,
)

# One entry per market this backfill can honestly resolve. `required_features` mirrors each
# market's real `required_features` from basketball/market_seeding.py or baseball/market_seeding.py
# exactly (never invented). `kind` picks the resolver dispatch: "binary" reads MARKET_OUTCOME_RESOLVERS
# + MARKET_OUTCOME_LABELS (same encoding backfill_both_teams_to_score_training_data.py uses);
# "three_way" reads THREE_WAY_MARKET_RESOLVERS directly (same as backfill_match_winner_training_data.py).
MARKET_SPECS: tuple[dict, ...] = (
    # Phase 17 (post-M24) — `basketball.market.overround`/`baseball.market.overround` were demoted
    # to optional on both moneyline markets (dev.db mapping fix, docs/post_m24_phase17_football_
    # prediction_recovery_report.md): no odds provider is wired for basketball/baseball, so the
    # feature has permanent 0% real coverage — requiring it here meant every fixture failed this
    # backfill's own honest "skip if missing required feature" check, so moneyline never
    # accumulated a single real Prediction/PredictionOutcome despite a real, populated
    # fixture-diff signal existing for every other market. Dropped from this backfill's own
    # required_features to match.
    dict(market_key="basketball.moneyline", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.first_half_winner", kind="three_way",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.second_half_winner", kind="three_way",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.q1_winner", kind="three_way",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.q2_winner", kind="three_way",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.q3_winner", kind="three_way",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.q4_winner", kind="three_way",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="baseball.moneyline", kind="binary",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    dict(market_key="baseball.first_five_innings_winner", kind="three_way",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    # POST-M24 Phase 13 — three more real resolvers added this phase, same "binary" dispatch shape.
    # required_features mirrors each market's post-stale-mapping-fix real required_features exactly.
    dict(market_key="basketball.game_total_points", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.first_half_total_points", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="baseball.total_runs", kind="binary",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    # POST-M24 Phase 15 — four more lines per sport, bracketing each market's already-real median
    # line, same dispatch shape (real resolver already wired in outcome_resolution_service.py).
    dict(market_key="basketball.game_total_points_199_5", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.game_total_points_209_5", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.game_total_points_229_5", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="basketball.game_total_points_239_5", kind="binary",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="baseball.total_runs_6_5", kind="binary",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    dict(market_key="baseball.total_runs_7_5", kind="binary",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    dict(market_key="baseball.total_runs_9_5", kind="binary",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    dict(market_key="baseball.total_runs_10_5", kind="binary",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
    # POST-M24 Phase 16 — two real REGRESSION markets, backfilled the same way as every other
    # market here: real feature_snapshot as X, the fixture's own real final-score total as y
    # (never a fabricated guess). "regression" is a new `kind` dispatch value handled below.
    dict(market_key="basketball.game_total_points_prediction", kind="regression",
         required_features=("basketball.fixture.form_points_diff_last5",)),
    dict(market_key="baseball.total_runs_prediction", kind="regression",
         required_features=("baseball.fixture.form_runs_diff_last5",)),
)

SPORT_BY_MARKET_PREFIX = {"basketball": "basketball", "baseball": "baseball"}


def _dashed(fixture_id_hex: str) -> str:
    return f"{fixture_id_hex[0:8]}-{fixture_id_hex[8:12]}-{fixture_id_hex[12:16]}-{fixture_id_hex[16:20]}-{fixture_id_hex[20:32]}"


def _match_result_for(sport: str, home_score: int, away_score: int, period_scores_raw: str | None) -> MatchResult:
    if period_scores_raw is None:
        return MatchResult(home_score, away_score)
    period = json.loads(period_scores_raw)

    if sport == "basketball" and period.get("kind") == "quarter":
        home_q, away_q = period.get("home") or [], period.get("away") or []
        home_ht = sum(home_q[:2]) if len(home_q) >= 2 and all(v is not None for v in home_q[:2]) else None
        away_ht = sum(away_q[:2]) if len(away_q) >= 2 and all(v is not None for v in away_q[:2]) else None
        return MatchResult(
            home_score, away_score, home_score_ht=home_ht, away_score_ht=away_ht,
            home_quarters=tuple(home_q) if home_q else None, away_quarters=tuple(away_q) if away_q else None,
        )

    if sport == "baseball" and period.get("kind") == "inning":
        home_i, away_i = period.get("home") or [], period.get("away") or []
        home_5 = sum(home_i[:5]) if len(home_i) >= 5 and all(v is not None for v in home_i[:5]) else None
        away_5 = sum(away_i[:5]) if len(away_i) >= 5 and all(v is not None for v in away_i[:5]) else None
        return MatchResult(home_score, away_score, home_score_first5=home_5, away_score_first5=away_5)

    return MatchResult(home_score, away_score)


async def _feature_value_as_of(session, feature_key: str, dashed: str, cutoff: datetime) -> float | None:
    """Point-in-time read — see `backfill_match_winner_training_data.py`'s identical helper for the
    full rationale (including why this goes through the ORM repository, not a raw-SQL bound
    parameter). A feature recomputed after `cutoff` must stay invisible here."""
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
        now = datetime.now(timezone.utc)

        for spec in MARKET_SPECS:
            market_key = spec["market_key"]
            sport = SPORT_BY_MARKET_PREFIX[market_key.split(".")[0]]
            market = await markets_repo.get_by_key(market_key)
            if market is None:
                print(f"{market_key}: SKIPPED — market not found (run market seeding first)")
                continue

            try:
                anchor = await model_registry.register(
                    market_id=market.id, model_key=f"{market_key}.historical-backfill", version=1,
                    algorithm="backfill-anchor", now=now,
                )
            except ModelAlreadyRegisteredError:
                anchor = await model_registry.models.get_by_key_version(f"{market_key}.historical-backfill", 1)

            fixture_rows = (
                await session.execute(
                    text(
                        "SELECT f.id, f.home_score, f.away_score, f.scheduled_at, f.period_scores "
                        "FROM fixtures f JOIN seasons se ON f.season_id = se.id "
                        "JOIN competitions c ON se.competition_id = c.id JOIN sports s ON c.sport_id = s.id "
                        "WHERE s.code = :sport AND f.status = 'completed' AND f.home_score IS NOT NULL"
                    ),
                    {"sport": sport},
                )
            ).all()

            created = skipped_existing = skipped_missing_features = skipped_unresolved = 0

            for fixture_id, home_score, away_score, scheduled_at, period_scores_raw in fixture_rows:
                dashed = _dashed(fixture_id)
                if await predictions.list_by_subject(dashed, market.id):
                    skipped_existing += 1
                    continue

                # The cutoff for every feature this fixture's snapshot may see — its own kickoff,
                # never the batch's wall-clock `now`. Computed once, before any feature read.
                cutoff = (
                    datetime.fromisoformat(scheduled_at) if isinstance(scheduled_at, str) else scheduled_at
                ) or now

                feature_snapshot: dict[str, float] = {}
                missing_required = False
                for key in spec["required_features"]:
                    value = await _feature_value_as_of(session, key, dashed, cutoff)
                    if value is None:
                        missing_required = True
                        break
                    feature_snapshot[key] = value
                if missing_required:
                    skipped_missing_features += 1
                    continue

                result = _match_result_for(sport, home_score, away_score, period_scores_raw)
                evaluated_at = cutoff

                if spec["kind"] == "binary":
                    resolver = MARKET_OUTCOME_RESOLVERS[market_key]
                    resolved = resolver(result)
                    if resolved is None:
                        skipped_unresolved += 1
                        continue
                    prediction_value = MARKET_OUTCOME_LABELS[market_key].positive_label
                    actual_value = resolved.actual_value
                    error = 0.0 if resolved.matches_positive else 1.0
                elif spec["kind"] == "regression":
                    resolver = REGRESSION_MARKET_RESOLVERS[market_key]
                    actual_total = resolver(result)
                    if actual_total is None:
                        skipped_unresolved += 1
                        continue
                    # The anchor's own placeholder value IS the real observed total (never a
                    # fabricated guess) — DatasetBuilder's REGRESSION branch only ever reads
                    # PredictionOutcome.actual_value (this same number) as the training label, so
                    # this placeholder is inert by construction; error is trivially 0.0 since the
                    # anchor equals the actual by definition.
                    prediction_value = f"{actual_total:.4f}"
                    actual_value = str(actual_total)
                    error = 0.0
                else:
                    resolver = THREE_WAY_MARKET_RESOLVERS[market_key]
                    actual_label = resolver(result)
                    if actual_label is None:
                        skipped_unresolved += 1
                        continue
                    prediction_value = "insufficient_historical_data"
                    actual_value = actual_label
                    error = None

                prediction = await predictions.record(
                    Prediction(
                        id=PredictionId(uuid4()), market_id=market.id, model_id=anchor.id, subject_ref=dashed,
                        value=prediction_value, probability=0.0, confidence=_INERT_CONFIDENCE,
                        explanation=ExplanationBundle(), feature_snapshot=feature_snapshot,
                        model_version="backfill.v1", status=PredictionStatus.DRAFT, generated_at=now,
                        data_freshness=evaluated_at,
                    )
                )
                await outcomes.record(
                    PredictionOutcome(
                        id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id, actual_value=actual_value,
                        error=error, evaluated_at=evaluated_at,
                    )
                )
                created += 1

            await session.commit()
            print(
                f"{market_key}: backfilled {created}, skipped {skipped_existing} existing, "
                f"{skipped_missing_features} missing required features, {skipped_unresolved} unresolved"
            )


if __name__ == "__main__":
    asyncio.run(main())
