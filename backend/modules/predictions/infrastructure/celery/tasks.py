"""Celery task for Scheduled Retraining (audit fix, 2026-08-02) — the periodic "Scheduled
Retraining" job the self-learning platform brief named but that was never wired up:
`RetrainingScheduler.should_retrain()` and `AutomaticModelSelectionService` both already existed
and were already composed, but only reachable via a manual Ops Center button, never a schedule.

Same pattern as `modules.ingestion.infrastructure.celery.tasks` /
`modules.admin.infrastructure.celery.tasks`: a worker process can't share the FastAPI app's
per-request DB session, so the task builds its own orchestrator via an injected factory rather
than importing apps/api's composition module directly.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.predictions.application.calibration_fitting_service import CalibrationFittingService
from modules.predictions.application.calibration_validation_service import CalibrationValidationService
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.application.model_health_audit_service import REPAIRABLE_STATUSES, ModelHealthAuditService
from modules.predictions.application.scheduled_prediction_generation_orchestrator import (
    ScheduledPredictionGenerationOrchestrator,
)
from modules.predictions.application.scheduled_retraining_orchestrator import ScheduledRetrainingOrchestrator
from modules.predictions.application.windowed_feature_engineering_service import FixtureVenueStrengthCalculator
from modules.predictions.football.market_seeding import FootballMarketSeeder
from modules.sports.domain.value_objects import SeasonId, SportId, TeamId

logger = logging.getLogger("titaniq.predictions.tasks")


def _logged(task_name: str):
    """See `modules.ingestion.infrastructure.celery.tasks._logged` — identical structured
    start/success/failure logging, duplicated per-module rather than centralized (same convention
    already used for `_RETRY_KWARGS` in every one of these `celery/tasks.py` files). Especially
    worth having here: retraining/calibration are high-stakes ML operations that previously left
    no log trail at all if they failed silently past their retry budget."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            task_id = getattr(self.request, "id", None)
            logger.info("celery_task.started", extra={"task": task_name, "task_id": task_id})
            try:
                result = fn(self, *args, **kwargs)
            except Exception:
                logger.error("celery_task.failed", extra={"task": task_name, "task_id": task_id}, exc_info=True)
                raise
            logger.info("celery_task.succeeded", extra={"task": task_name, "task_id": task_id})
            return result

        return wrapper

    return decorator


_RetrainingOrchestratorFactory = Callable[[], Awaitable[ScheduledRetrainingOrchestrator]]
_retraining_orchestrator_factory: _RetrainingOrchestratorFactory | None = None


def set_retraining_orchestrator_factory(factory: _RetrainingOrchestratorFactory) -> None:
    global _retraining_orchestrator_factory
    _retraining_orchestrator_factory = factory


@asynccontextmanager
async def _get_retraining_orchestrator() -> AsyncIterator[ScheduledRetrainingOrchestrator]:
    """Milestone 24 §3/1(b): closes the worker session tagged onto the orchestrator by the
    production factory (`bootstrap.py`'s `_worker_session` attribute) before this task's
    `asyncio.run()` call tears down its event loop — see
    `modules.ingestion.infrastructure.celery.tasks._get_orchestrator` for the full rationale,
    identical here."""
    if _retraining_orchestrator_factory is None:
        raise RuntimeError(
            "retraining orchestrator factory not configured — call set_retraining_orchestrator_factory() at worker startup"
        )
    orchestrator = await _retraining_orchestrator_factory()
    try:
        yield orchestrator
    finally:
        session = getattr(orchestrator, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(orchestrator, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


@dataclass
class MarketFeatureRepairContext:
    """Bundles exactly the composed pieces `repair_correct_score_feature_requirements_task` needs
    — the market seeder (re-applies market_seeding.py's current spec), the feature-market mapping
    service (`set_required`, for demoting a mapping the seeder itself can only ever create, never
    update), and the venue-strength calculator (for backfilling real values on upcoming fixtures)
    — plus the raw session so `_get_market_feature_repair_context` can close it, same
    `_worker_session` teardown shape every other factory-built object in this module uses."""

    seeder: FootballMarketSeeder
    mappings: FeatureMarketMappingService
    venue_strength_calculator: FixtureVenueStrengthCalculator
    session: Any


_MarketFeatureRepairContextFactory = Callable[[], Awaitable[MarketFeatureRepairContext]]
_market_feature_repair_context_factory: _MarketFeatureRepairContextFactory | None = None


def set_market_feature_repair_context_factory(factory: _MarketFeatureRepairContextFactory) -> None:
    global _market_feature_repair_context_factory
    _market_feature_repair_context_factory = factory


@asynccontextmanager
async def _get_market_feature_repair_context() -> AsyncIterator[MarketFeatureRepairContext]:
    """Milestone 24 §3/1(b): same session-closing rationale as `_get_retraining_orchestrator`
    above."""
    if _market_feature_repair_context_factory is None:
        raise RuntimeError(
            "market feature repair context factory not configured — call "
            "set_market_feature_repair_context_factory() at worker startup"
        )
    context = await _market_feature_repair_context_factory()
    try:
        yield context
    finally:
        await context.session.close()
        await asyncio.sleep(0)


_CalibrationServiceFactory = Callable[[], Awaitable[CalibrationFittingService]]
_calibration_service_factory: _CalibrationServiceFactory | None = None


def set_calibration_service_factory(factory: _CalibrationServiceFactory) -> None:
    global _calibration_service_factory
    _calibration_service_factory = factory


@asynccontextmanager
async def _get_calibration_service() -> AsyncIterator[CalibrationFittingService]:
    """Milestone 24 §3/1(b): same session-closing rationale as `_get_retraining_orchestrator` above."""
    if _calibration_service_factory is None:
        raise RuntimeError(
            "calibration service factory not configured — call set_calibration_service_factory() at worker startup"
        )
    service = await _calibration_service_factory()
    try:
        yield service
    finally:
        session = getattr(service, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(service, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_PredictionGenerationOrchestratorFactory = Callable[[], Awaitable[ScheduledPredictionGenerationOrchestrator]]
_prediction_generation_orchestrator_factory: _PredictionGenerationOrchestratorFactory | None = None


def set_prediction_generation_orchestrator_factory(factory: _PredictionGenerationOrchestratorFactory) -> None:
    global _prediction_generation_orchestrator_factory
    _prediction_generation_orchestrator_factory = factory


@asynccontextmanager
async def _get_prediction_generation_orchestrator() -> AsyncIterator[ScheduledPredictionGenerationOrchestrator]:
    """Milestone 24 §3/1(b): same session-closing rationale as `_get_retraining_orchestrator` above."""
    if _prediction_generation_orchestrator_factory is None:
        raise RuntimeError(
            "prediction generation orchestrator factory not configured — call "
            "set_prediction_generation_orchestrator_factory() at worker startup"
        )
    orchestrator = await _prediction_generation_orchestrator_factory()
    try:
        yield orchestrator
    finally:
        session = getattr(orchestrator, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(orchestrator, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_CalibrationValidationServiceFactory = Callable[[], Awaitable[CalibrationValidationService]]
_calibration_validation_service_factory: _CalibrationValidationServiceFactory | None = None


def set_calibration_validation_service_factory(factory: _CalibrationValidationServiceFactory) -> None:
    global _calibration_validation_service_factory
    _calibration_validation_service_factory = factory


@asynccontextmanager
async def _get_calibration_validation_service() -> AsyncIterator[CalibrationValidationService]:
    """Phase 3 audit fix: same session-closing rationale as `_get_calibration_service` above —
    `CalibrationValidationService` (sklearn `CalibratedClassifierCV`-based Platt/isotonic
    comparison) previously had zero scheduled callers, reachable only via a manual script."""
    if _calibration_validation_service_factory is None:
        raise RuntimeError(
            "calibration validation service factory not configured — call "
            "set_calibration_validation_service_factory() at worker startup"
        )
    service = await _calibration_validation_service_factory()
    try:
        yield service
    finally:
        session = getattr(service, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(service, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        await asyncio.sleep(0)


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}

# Phase 5 (Celery Worker+Beat verification, 2026-08-25) — production runs `titaniq-worker` with
# `--pool=solo` (fixed a real prefork-pool OOM: forking duplicates the already-loaded
# sklearn/shap/xgboost import weight per child). Celery's own `task_time_limit`/`soft_time_limit`
# (`celery_app.py`'s `task_time_limit=600`) are silently NOT ENFORCED under the solo pool —
# confirmed against the installed celery 5.6.3's `celery.concurrency.solo.TaskPool._get_info()`,
# whose `'timeouts': ()` is exactly the field Celery's own worker code checks before ever applying
# either limit. A hung task under solo blocks every other scheduled task indefinitely (single-
# threaded, non-preemptive) with no automatic recovery — worse for these three tasks than for the
# cheap, fast ingestion ones, since they're the heaviest work this worker does (dataset build,
# multi-algorithm training, sklearn `CalibratedClassifierCV` comparison).
#
# `asyncio.wait_for()` below is an application-level bound that works regardless of pool type —
# but it can only ever preempt at an `await` suspension point. It reliably bounds an I/O-bound
# hang (a stuck DB query, a provider API call that never returns) but CANNOT interrupt a single
# long-running *synchronous* call within one un-awaited stretch (e.g. one sklearn `.fit()` call,
# which is synchronous CPU-bound code with no async API) — an honest, documented limitation, not a
# complete guarantee, same "real but partial mitigation, not fabricated as total" posture this
# codebase already uses elsewhere (e.g. `calibration_fitting_service.py`'s own v1 scope note).
# Values are generous relative to each task's own 6-hour (retraining/validation) or 1-hour
# (calibration fitting) Beat cadence — see `beat_schedule.py` — so a legitimately slow-but-healthy
# run is never mistaken for a hang, while a genuinely stuck run still recovers well before the
# next scheduled tick.
_RETRAINING_TASK_TIMEOUT_SECONDS = 1800  # heavy: dataset build + multi-algorithm training
_CALIBRATION_FITTING_TASK_TIMEOUT_SECONDS = 300  # cheap: reads outcome history, fits one logistic regression
_CALIBRATION_VALIDATION_TASK_TIMEOUT_SECONDS = 1800  # heavy: comparably costly to a retrain
# Redis/Celery pipeline verification (2026-08-26) — real defect already fixed once in this exact
# codebase (see ingestion/beat_schedule.py's LIVE_FIXTURES_LOCK_TTL_SECONDS docstring for the full
# incident): a Beat interval shorter than a task's own worst-case runtime causes queued duplicates
# to pile up and redundantly re-run. Applying that lesson up front here rather than rediscovering
# it live — 900s comfortably bounds a sweep over a week's worth of upcoming fixtures × PRODUCTION
# markets (each generation is a feature lookup + inference, not a network-bound provider call, so
# this is generously long relative to the real expected cost), and `beat_schedule.py`'s own
# SCHEDULED_PREDICTION_GENERATION_INTERVAL_SECONDS (1 hour) leaves 4x headroom over it.
_PREDICTION_GENERATION_TASK_TIMEOUT_SECONDS = 900
# On-demand only (see repair_broken_champions_task). 2026-08-30 reliability fix: this task is now
# audit-only (read-only artifact-loadability checks over every PRODUCTION market, each bounded by
# the artifact store's own 30s HTTP timeout) plus dispatching one small task per broken market —
# the actual repair work (dataset build + training) moved to repair_one_champion_task's own
# smaller budget below, so this no longer needs the hour-long ceiling a full inline sweep did.
_AUDIT_ONLY_TIMEOUT_SECONDS = 1800


@celery_app.task(name="predictions.check_scheduled_prediction_generation", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_prediction_generation")
def check_scheduled_prediction_generation_task(self, now_iso: str | None = None) -> dict:
    """Real gap found live (2026-08-26) — `ingestion.sync_upcoming_fixtures` already syncs real
    upcoming fixtures on its own schedule, but nothing ever generated predictions for them
    automatically; every prediction that ever existed was manually/admin-triggered. Generates (or
    refreshes) a prediction, for every PRODUCTION market, for every fixture of that market's sport
    due within the orchestrator's lookahead window — the automatic half of prediction generation,
    manual/admin triggering being the other half (same shape as retraining above)."""

    async def _do() -> dict:
        async with _get_prediction_generation_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(
                orchestrator.run(now), timeout=_PREDICTION_GENERATION_TASK_TIMEOUT_SECONDS
            )
            return {
                "pairs_checked": len(outcomes),
                "published": sum(1 for o in outcomes if o.status == "published"),
                "draft": sum(1 for o in outcomes if o.status == "draft"),
                "skipped": sum(1 for o in outcomes if o.status == "skipped"),
                "results": [
                    {
                        "fixture_id": o.fixture_id, "market_key": o.market_key, "status": o.status,
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="predictions.check_scheduled_retraining", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_retraining")
def check_scheduled_retraining_task(self, now_iso: str | None = None) -> dict:
    """Runs the same drift/staleness check the Ops Center's manual "check retraining" button
    already performs, for every PRODUCTION market, and trains + registers a Challenger wherever
    it says yes — the automatic half of retraining, manual triggering being the other half."""

    async def _do() -> dict:
        async with _get_retraining_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(orchestrator.run(now), timeout=_RETRAINING_TASK_TIMEOUT_SECONDS)
            return {
                "markets_checked": len(outcomes),
                "retrained": sum(1 for o in outcomes if o.challenger is not None),
                "skipped": sum(1 for o in outcomes if o.should_retrain and o.challenger is None),
                "results": [
                    {
                        "market_key": o.market_key,
                        "should_retrain": o.should_retrain,
                        "reason": o.reason,
                        "challenger_model_key": o.challenger.model_key if o.challenger else None,
                        "challenger_version": o.challenger.version if o.challenger else None,
                        "skipped_reason": o.skipped_reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="predictions.repair_broken_champions", bind=True, **_RETRY_KWARGS)
@_logged("predictions.repair_broken_champions")
def repair_broken_champions_task(self, now_iso: str | None = None) -> dict:
    """On-demand only — not on Beat's schedule. Real production incident, 2026-08-29:
    `GET /api/v1/admin/system/model-health` found 40 of 53 PRODUCTION markets' registered
    Champions pointed at artifacts that were never actually durable.

    Reliability fix, 2026-08-30: this used to repair every broken market inline, in one task, with
    a 1-hour budget — on this deployment's single-threaded `--pool=solo` worker, a single stalled
    market (or an unrelated hung ingestion task sharing the same process) blocked the ENTIRE sweep
    with zero visibility, confirmed live (a 6-minute worker stall on one hung provider HTTP call
    froze everything behind it). Now this task only *audits* (fast, read-only) and dispatches one
    `repair_one_champion_task` per broken market — each with its own bounded timeout, independent
    retry budget, and independently visible in `model-health` the moment it lands, so one market's
    trouble can never block another's, and progress is observable market-by-market rather than
    all-or-nothing."""

    async def _do() -> dict:
        async with _get_retraining_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            audit_service = ModelHealthAuditService(
                markets=orchestrator.markets, models=orchestrator.models,
                artifact_store=orchestrator.model_selection.artifact_store,
            )
            entries = await audit_service.audit_all_production_markets()
            broken = [e for e in entries if e.status in REPAIRABLE_STATUSES]

            dispatched = []
            for entry in broken:
                result = repair_one_champion_task.delay(entry.market.market_key, now_iso=now.isoformat())
                dispatched.append({"market_key": entry.market.market_key, "was_status": entry.status, "task_id": result.id})

            return {
                "total_production_markets": len(entries),
                "already_healthy": sum(1 for e in entries if e.status == "HEALTHY"),
                "dispatched_repairs": len(dispatched),
                "results": dispatched,
            }

    return asyncio.run(asyncio.wait_for(_do(), timeout=_AUDIT_ONLY_TIMEOUT_SECONDS))


_REPAIR_ONE_MARKET_TIMEOUT_SECONDS = 300  # one market's dataset build + candidate training


@celery_app.task(name="predictions.repair_one_champion", bind=True, **_RETRY_KWARGS)
@_logged("predictions.repair_one_champion")
def repair_one_champion_task(self, market_key: str, now_iso: str | None = None) -> dict:
    """The per-market unit of work `repair_broken_champions_task` dispatches — see that task's
    docstring for why this is split out rather than inline. Fetches the market fresh (never
    trusts the dispatcher's stale snapshot) and repairs it via
    `ScheduledRetrainingOrchestrator.repair_broken_champion`, same repair logic as before, just
    scoped to one market per task invocation."""

    async def _do() -> dict:
        async with _get_retraining_orchestrator() as orchestrator:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            market = await orchestrator.markets.get_by_key(market_key)
            if market is None:
                return {"market_key": market_key, "repaired": False, "error": "market no longer exists"}
            try:
                outcome = await orchestrator.repair_broken_champion(market, now)
            except Exception as exc:  # noqa: BLE001 — reported, not swallowed; this task's own failure must not crash the caller
                return {"market_key": market_key, "repaired": False, "error": str(exc)}
            return {
                "market_key": market_key,
                "repaired": outcome.skipped_reason is None,
                "skipped_reason": outcome.skipped_reason,
                "new_champion_model_key": (
                    outcome.challenger.model_key if outcome.skipped_reason is None and outcome.challenger else None
                ),
            }

    return asyncio.run(asyncio.wait_for(_do(), timeout=_REPAIR_ONE_MARKET_TIMEOUT_SECONDS))


_FEATURE_REPAIR_TASK_TIMEOUT_SECONDS = 900

# Correct Score forensic audit (2026-08-26, market_seeding.py) replaced these two with
# `_VENUE_STRENGTH_FEATURES` as football.correct_score's real required expected-goals signal,
# demoting the old pair to optional — but `_seed_market` only ever *adds* a mapping
# (`except MappingAlreadyExistsError: continue`), so a spec change like this never reaches an
# already-seeded market's persisted `is_required` flag on its own. `FeatureMarketMappingService.
# set_required` exists for exactly this drift; nothing had ever called it for this one.
_CORRECT_SCORE_STALE_REQUIRED_FEATURES = (
    "football.fixture.expected_home_goals",
    "football.fixture.expected_away_goals",
)


@celery_app.task(name="predictions.repair_correct_score_feature_requirements", bind=True, **_RETRY_KWARGS)
@_logged("predictions.repair_correct_score_feature_requirements")
def repair_correct_score_feature_requirements_task(self, now_iso: str | None = None) -> dict:
    """On-demand only. Real production incident, 2026-08-30: football.correct_score's live
    required-feature mapping in the database still pointed at the pre-2026-08-26 venue-blind
    expected-goals pair, blocking every real "Generate Intelligence" request for this market with
    a MissingRequiredFeatureError even for fixtures whose teams had abundant real completed-match
    history (confirmed live against production before this fix — the venue-strength audit fix had
    shipped in code but the DB mapping it depends on had never been re-seeded, and the four new
    venue-strength mappings had never been created there either). Re-seeds football's market
    catalog (idempotent — creates only what's missing), demotes the two stale expected-goals
    mappings to optional, then backfills real venue-strength feature values for every football
    fixture that hasn't kicked off yet, so an upcoming fixture doesn't have to wait for its next
    reconciliation cycle to generate a real prediction."""

    async def _do() -> dict:
        async with _get_market_feature_repair_context() as ctx:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)

            await ctx.seeder.seed(now)

            demoted = []
            for feature_key in _CORRECT_SCORE_STALE_REQUIRED_FEATURES:
                try:
                    await ctx.mappings.set_required("football.correct_score", feature_key, False)
                    demoted.append(feature_key)
                except KeyError:
                    continue

            rows = (
                await ctx.session.execute(
                    text(
                        "SELECT f.id, f.home_team_id, f.away_team_id, f.season_id, c.sport_id "
                        "FROM sports.fixtures f "
                        "JOIN sports.seasons se ON f.season_id = se.id "
                        "JOIN sports.competitions c ON se.competition_id = c.id "
                        "JOIN sports.sports s ON c.sport_id = s.id "
                        "WHERE s.code = 'football' AND f.status != 'completed'"
                    )
                )
            ).all()

            backfilled = 0
            for raw_fixture_id, raw_home_team_id, raw_away_team_id, raw_season_id, raw_sport_id in rows:
                home_value, *_rest = await ctx.venue_strength_calculator.compute_and_write(
                    str(UUID(str(raw_fixture_id))),
                    TeamId(UUID(str(raw_home_team_id))),
                    TeamId(UUID(str(raw_away_team_id))),
                    SportId(UUID(str(raw_sport_id))),
                    SeasonId(UUID(str(raw_season_id))),
                    now,
                )
                if home_value is not None:
                    backfilled += 1

            await ctx.session.commit()
            return {
                "seeded": True,
                "demoted_to_optional": demoted,
                "upcoming_football_fixtures_checked": len(rows),
                "venue_strength_backfilled": backfilled,
            }

    return asyncio.run(asyncio.wait_for(_do(), timeout=_FEATURE_REPAIR_TASK_TIMEOUT_SECONDS))


@celery_app.task(name="predictions.backfill_venue_strength_for_completed_fixtures", bind=True, **_RETRY_KWARGS)
@_logged("predictions.backfill_venue_strength_for_completed_fixtures")
def backfill_venue_strength_for_completed_fixtures_task(self, now_iso: str | None = None) -> dict:
    """On-demand only. `repair_correct_score_feature_requirements_task` above backfills
    venue-strength features for fixtures that haven't kicked off yet (the live-prediction path)
    — it deliberately excludes completed fixtures, so it does nothing for football.correct_score's
    actual TRAINING data. Real production incident (2026-08-30): the ~800 real completed EPL
    fixtures a retrain draws its samples from were all reconciled before
    `FixtureVenueStrengthCalculator` existed, so every one of them has zero recorded values for
    these four features — 0% coverage means a retrain can never learn from the signal even once
    the feature-requirement mapping and leakage classification are both correct. This is the
    historical-training-data counterpart, same shape as `scripts/
    backfill_venue_strength_for_completed_fixtures.py` (a local dev-only script — this is the
    production-safe version, running through the real deployed worker's own DB credentials rather
    than requiring TITANIQ_DB_URL set locally).

    Point-in-time safety is the entire reason a completed fixture's own `scheduled_at` — never
    `now` — is the cutoff passed to `compute_and_write`: using `now` would let a team's later
    (even post-fixture) results leak into what must be a pre-match feature for that same fixture,
    exactly the class of leakage this codebase tests against everywhere else."""

    async def _do() -> dict:
        async with _get_market_feature_repair_context() as ctx:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            await ctx.venue_strength_calculator.ensure_registered(now)

            rows = (
                await ctx.session.execute(
                    text(
                        "SELECT f.id, f.home_team_id, f.away_team_id, f.season_id, f.scheduled_at, c.sport_id "
                        "FROM sports.fixtures f "
                        "JOIN sports.seasons se ON f.season_id = se.id "
                        "JOIN sports.competitions c ON se.competition_id = c.id "
                        "JOIN sports.sports s ON c.sport_id = s.id "
                        "WHERE s.code = 'football' AND f.status = 'completed' AND f.home_score IS NOT NULL"
                    )
                )
            ).all()

            backfilled = 0
            for raw_fixture_id, raw_home_team_id, raw_away_team_id, raw_season_id, raw_scheduled_at, raw_sport_id in rows:
                cutoff = raw_scheduled_at if raw_scheduled_at.tzinfo else raw_scheduled_at.replace(tzinfo=timezone.utc)
                home_value, *_rest = await ctx.venue_strength_calculator.compute_and_write(
                    str(UUID(str(raw_fixture_id))),
                    TeamId(UUID(str(raw_home_team_id))),
                    TeamId(UUID(str(raw_away_team_id))),
                    SportId(UUID(str(raw_sport_id))),
                    SeasonId(UUID(str(raw_season_id))),
                    cutoff,
                )
                if home_value is not None:
                    backfilled += 1

            await ctx.session.commit()
            return {
                "completed_football_fixtures_checked": len(rows),
                "venue_strength_backfilled": backfilled,
            }

    return asyncio.run(asyncio.wait_for(_do(), timeout=_FEATURE_REPAIR_TASK_TIMEOUT_SECONDS))


@celery_app.task(name="predictions.check_scheduled_calibration", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_calibration")
def check_scheduled_calibration_task(self, now_iso: str | None = None) -> dict:
    """Audit fix (2026-08-02) — `CalibratorPort.fit()` had zero real call sites anywhere, so every
    "calibrated" probability was actually just the unfitted identity transform. (Re)fits each
    PRODUCTION market's Champion against its real outcome history, for every market with enough
    accumulated samples."""

    async def _do() -> dict:
        async with _get_calibration_service() as service:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(
                service.fit_all_production_markets(now), timeout=_CALIBRATION_FITTING_TASK_TIMEOUT_SECONDS
            )
            return {
                "markets_checked": len(outcomes),
                "fitted": sum(1 for o in outcomes if o.fitted),
                "skipped": sum(1 for o in outcomes if not o.fitted),
                "results": [
                    {
                        "market_key": o.market_key,
                        "model_id": str(o.model_id) if o.model_id else None,
                        "sample_count": o.sample_count,
                        "fitted": o.fitted,
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="predictions.check_scheduled_calibration_validation", bind=True, **_RETRY_KWARGS)
@_logged("predictions.check_scheduled_calibration_validation")
def check_scheduled_calibration_validation_task(self, now_iso: str | None = None) -> dict:
    """Phase 3 audit fix — `CalibrationValidationService` (real sklearn `CalibratedClassifierCV`
    Platt/isotonic comparison against every PRODUCTION market's Champion, persisting a
    `CalibrationReport` per candidate and registering a new CHALLENGER on a genuine win) existed
    since Phase 3 but was reachable only via a manual script, never a schedule. Never auto-promotes
    — a win only registers a CHALLENGER for the existing human `promote_to_champion` review, same
    posture as every other automated retraining path in this codebase."""

    async def _do() -> dict:
        async with _get_calibration_validation_service() as service:
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
            outcomes = await asyncio.wait_for(
                service.validate_all_production_markets(now), timeout=_CALIBRATION_VALIDATION_TASK_TIMEOUT_SECONDS
            )
            return {
                "markets_checked": len(outcomes),
                "validated": sum(1 for o in outcomes if o.validated),
                "skipped": sum(1 for o in outcomes if not o.validated),
                "results": [
                    {
                        "market_key": o.market_key,
                        "validated": o.validated,
                        "winner": o.result.winner.value if o.result else None,
                        "decision_reason": o.result.decision_reason if o.result else None,
                        "promoted_model_id": (
                            str(o.result.promoted_model_id) if o.result and o.result.promoted_model_id else None
                        ),
                        "reason": o.reason,
                    }
                    for o in outcomes
                ],
            }

    return asyncio.run(_do())
