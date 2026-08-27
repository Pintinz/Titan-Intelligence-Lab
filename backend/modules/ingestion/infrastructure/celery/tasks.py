"""Celery tasks wrapping SyncOrchestrator calls (docs/roadmap.md Milestone 5 "Background
Processing: Scheduled Jobs, Background Synchronization").

A worker process can't share the FastAPI app's per-request DB session, so each task builds its
own orchestrator via an injected factory (``set_orchestrator_factory``) rather than importing
apps/api's composition module directly — keeps this module decoupled from a specific app's
wiring, and lets tests substitute an in-memory/SQLite factory (see
tests/unit/modules/ingestion/test_celery_tasks.py).

Task args/results are plain JSON-serializable types (dicts, ISO datetime strings) — never the
domain's ``SyncRun``/enum objects directly — because ``task_serializer="json"`` (celery_app.py)
cannot serialize them, and because a worker process and the process reading task results may
not share this codebase's exact class definitions.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from modules.ingestion.application.scheduled_team_statistics_sync_orchestrator import ScheduledTeamStatisticsSyncOrchestrator
from modules.ingestion.application.sync_orchestrator import SyncOrchestrator
from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.sports.domain.value_objects import ProviderRef, SeasonId

logger = logging.getLogger("titaniq.ingestion.tasks")


def _logged(task_name: str):
    """Structured start/success/failure logging keyed by Celery's own task id — every task in
    this module previously had zero logging at all (Production Readiness Audit §2), so a failure
    was only ever visible via the dead-letter Redis list, never in the application log stream.
    Applied as the innermost decorator (below `@celery_app.task`) so it wraps the plain function
    Celery itself calls, regardless of `bind`/retry config on the outer decorator."""

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


_orchestrator_factory: Callable[[], Awaitable[SyncOrchestrator]] | None = None


def set_orchestrator_factory(factory: Callable[[], Awaitable[SyncOrchestrator]]) -> None:
    global _orchestrator_factory
    _orchestrator_factory = factory


@asynccontextmanager
async def _get_orchestrator() -> AsyncIterator[SyncOrchestrator]:
    """Milestone 24 §3/1(b): a context manager, not a plain awaitable — closes the worker session
    the production factory tagged onto the orchestrator (`bootstrap.py`'s `_worker_session`
    attribute) before this task's `asyncio.run()` call tears down its event loop. Without this, an
    unclosed session's connection outlives the loop it was opened on, surfacing later as a
    `RuntimeError: Event loop is closed` GC warning (found in M23, scoped project-wide in M24).
    A no-op in tests, whose fake factories return a plain object with no such attribute."""
    if _orchestrator_factory is None:
        raise RuntimeError("orchestrator factory not configured — call set_orchestrator_factory() at worker startup")
    orchestrator = await _orchestrator_factory()
    try:
        yield orchestrator
    finally:
        session = getattr(orchestrator, "_worker_session", None)
        if session is not None:
            await session.close()
        redis_client = getattr(orchestrator, "_worker_redis_client", None)
        if redis_client is not None:
            await redis_client.aclose()
        # Windows' ProactorEventLoop schedules a transport's actual socket teardown via
        # call_soon rather than completing it synchronously inside close()/aclose() — without
        # giving the loop one more iteration to run that callback, asyncio.run() can close the
        # loop first, leaving the transport to finalize later against an already-closed loop
        # (surfaces as `RuntimeError: Event loop is closed` on an unrelated later task).
        await asyncio.sleep(0)


_team_statistics_sync_orchestrator_factory: Callable[[], Awaitable[ScheduledTeamStatisticsSyncOrchestrator]] | None = None


def set_team_statistics_sync_orchestrator_factory(
    factory: Callable[[], Awaitable[ScheduledTeamStatisticsSyncOrchestrator]],
) -> None:
    global _team_statistics_sync_orchestrator_factory
    _team_statistics_sync_orchestrator_factory = factory


@asynccontextmanager
async def _get_team_statistics_sync_orchestrator() -> AsyncIterator[ScheduledTeamStatisticsSyncOrchestrator]:
    """Milestone 24 §3/1(b): same session-closing rationale as `_get_orchestrator` above."""
    if _team_statistics_sync_orchestrator_factory is None:
        raise RuntimeError(
            "team statistics sync orchestrator factory not configured — call "
            "set_team_statistics_sync_orchestrator_factory() at worker startup"
        )
    orchestrator = await _team_statistics_sync_orchestrator_factory()
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


def _run_summary(run) -> dict | None:
    if run is None:
        return None
    return {
        "run_id": str(run.id), "status": run.status.value, "records_fetched": run.records_fetched,
        "records_created": run.records_created, "records_updated": run.records_updated,
        "records_rejected": run.records_rejected,
    }


_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_backoff_max": 300, "max_retries": 3}


def _resolve_now(now_iso: str | None) -> datetime:
    """Beat's static schedule is evaluated once at worker startup, so a literal `now_iso` baked
    into ``BEAT_SCHEDULE``'s ``args`` would go stale after the first firing — every task instead
    defaults it to the real time of *this* firing when the caller omits it (Beat-triggered calls),
    while still accepting an explicit value for tests/manual invocation."""
    return datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)


# Redis/Celery pipeline verification (2026-08-26) — same "Beat interval must outlast the task's own
# worst-case runtime" lesson already applied once this session (see
# ingestion/beat_schedule.py's LIVE_FIXTURES_LOCK_TTL_SECONDS docstring for the original incident).
# This sweep calls a real per-fixture provider fetch for every completed fixture still missing team
# statistics, across every sport — generous headroom over the realistic worst case, with
# `SCHEDULED_TEAM_STATISTICS_SYNC_INTERVAL_SECONDS` (beat_schedule.py) giving 2x margin over it.
_TEAM_STATISTICS_SYNC_TASK_TIMEOUT_SECONDS = 1800


@celery_app.task(name="ingestion.sync_countries", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_countries")
def sync_countries_task(self, sport_code: str, now_iso: str | None = None) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_countries(sport_code, _resolve_now(now_iso))

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_teams", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_teams")
def sync_teams_task(self, sport_code: str, competition_ref: str, now_iso: str | None = None) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_teams(sport_code, competition_ref, _resolve_now(now_iso))

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_fixtures", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_fixtures")
def sync_fixtures_task(
    self, sport_code: str, competition_ref: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_fixtures(
                sport_code, competition_ref, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_live_fixtures", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_live_fixtures")
def sync_live_fixtures_task(
    self, sport_code: str, competition_ref: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_live_fixtures(
                sport_code, competition_ref, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_upcoming_fixtures", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_upcoming_fixtures")
def sync_upcoming_fixtures_task(
    self, sport_code: str, competition_id: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_upcoming_fixtures(
                sport_code, competition_id, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_completed_fixtures", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_completed_fixtures")
def sync_completed_fixtures_task(
    self, sport_code: str, competition_id: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_completed_fixtures(
                sport_code, competition_id, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_standings", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_standings")
def sync_standings_task(
    self, sport_code: str, competition_ref: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_standings(
                sport_code, competition_ref, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_standings_alt", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_standings_alt")
def sync_standings_alt_task(
    self, sport_code: str, competition_id: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_standings_alt(
                sport_code, competition_id, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_odds", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_odds")
def sync_odds_task(
    self, sport_code: str, fixture_ref_provider: str, fixture_ref_external_id: str, fixture_id: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            fixture_ref = ProviderRef(provider=fixture_ref_provider, external_id=fixture_ref_external_id)
            return await orchestrator.sync_odds_for_fixture(sport_code, fixture_ref, fixture_id, _resolve_now(now_iso))

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_team_statistics", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_team_statistics")
def sync_team_statistics_task(
    self, sport_code: str, fixture_ref_provider: str, fixture_ref_external_id: str, fixture_id: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        async with _get_orchestrator() as orchestrator:
            fixture_ref = ProviderRef(provider=fixture_ref_provider, external_id=fixture_ref_external_id)
            return await orchestrator.sync_team_statistics_for_fixture(
                sport_code, fixture_ref, fixture_id, _resolve_now(now_iso)
            )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_players_for_competition", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_players_for_competition")
def sync_players_for_competition_task(
    self, sport_code: str, season_id_str: str, now_iso: str | None = None
) -> list[dict | None]:
    """Premier League data-enrichment audit (2026-08-22) — the missing Celery entry point for
    `SyncOrchestrator.sync_players_for_competition` (see that method's own docstring for why it
    didn't have one)."""
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_players_for_competition(
                sport_code, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    runs = asyncio.run(_do())
    return [_run_summary(r) for r in runs]


@celery_app.task(name="ingestion.check_scheduled_team_statistics_sync", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.check_scheduled_team_statistics_sync")
def check_scheduled_team_statistics_sync_task(self, now_iso: str | None = None) -> dict:
    """Real gap found live (2026-08-26) — `SyncOrchestrator.sync_team_statistics_for_fixture`
    (fetch/validate/reconcile all real since the 2026-08-02 audit fix) was reachable only via a
    manual admin endpoint, so a completed fixture's "Match Statistics" panel stayed honestly empty
    forever unless an admin manually triggered a sync. Sweeps every completed fixture still missing
    team statistics (across every sport) and syncs it — the automatic half, manual/admin triggering
    being the other half (same shape as prediction generation)."""

    async def _do() -> dict:
        async with _get_team_statistics_sync_orchestrator() as orchestrator:
            now = _resolve_now(now_iso)
            outcomes = await asyncio.wait_for(orchestrator.run(now), timeout=_TEAM_STATISTICS_SYNC_TASK_TIMEOUT_SECONDS)
            return {
                "fixtures_checked": len(outcomes),
                "synced": sum(1 for o in outcomes if o.status == "synced"),
                "already_present": sum(1 for o in outcomes if o.status == "already_present"),
                "no_data_from_provider": sum(1 for o in outcomes if o.status == "no_data_from_provider"),
                "skipped": sum(1 for o in outcomes if o.status == "skipped"),
                "results": [
                    {"fixture_id": o.fixture_id, "status": o.status, "reason": o.reason}
                    for o in outcomes
                    if o.status != "already_present"
                ],
            }

    return asyncio.run(_do())


@celery_app.task(name="ingestion.sync_upcoming_structured_intelligence", bind=True, **_RETRY_KWARGS)
@_logged("ingestion.sync_upcoming_structured_intelligence")
def sync_upcoming_structured_intelligence_task(
    self, sport_code: str, season_id_str: str, now_iso: str | None = None
) -> list[dict | None]:
    """Milestone 5 — the Beat-driven entry point for injuries/transfers/lineups. Deliberately
    omits a `trigger` argument (unlike every other task above): `SyncOrchestrator
    .sync_upcoming_structured_intelligence`'s own default is `SyncTrigger.LIVE_SCHEDULED`, and
    this task is the *only* real caller — a Beat firing is exactly what that trigger value means.
    No other call site (admin API, backfill scripts) invokes this task, so there is no client
    input path that could ever claim `LIVE_SCHEDULED` for itself (Milestone 5 §13 — a client
    request must not be trusted as provenance)."""
    async def _do():
        async with _get_orchestrator() as orchestrator:
            return await orchestrator.sync_upcoming_structured_intelligence(
                sport_code, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
            )

    runs = asyncio.run(_do())
    return [_run_summary(r) for r in runs]
