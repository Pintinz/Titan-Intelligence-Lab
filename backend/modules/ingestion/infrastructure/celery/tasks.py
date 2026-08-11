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
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import UUID

from modules.ingestion.application.sync_orchestrator import SyncOrchestrator
from modules.ingestion.infrastructure.celery.celery_app import celery_app
from modules.sports.domain.value_objects import ProviderRef, SeasonId

_orchestrator_factory: Callable[[], Awaitable[SyncOrchestrator]] | None = None


def set_orchestrator_factory(factory: Callable[[], Awaitable[SyncOrchestrator]]) -> None:
    global _orchestrator_factory
    _orchestrator_factory = factory


async def _get_orchestrator() -> SyncOrchestrator:
    if _orchestrator_factory is None:
        raise RuntimeError("orchestrator factory not configured — call set_orchestrator_factory() at worker startup")
    return await _orchestrator_factory()


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


@celery_app.task(name="ingestion.sync_countries", bind=True, queue="default", **_RETRY_KWARGS)
def sync_countries_task(self, sport_code: str, now_iso: str | None = None) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_countries(sport_code, _resolve_now(now_iso))

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_teams", bind=True, queue="default", **_RETRY_KWARGS)
def sync_teams_task(self, sport_code: str, competition_ref: str, now_iso: str | None = None) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_teams(sport_code, competition_ref, _resolve_now(now_iso))

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_fixtures", bind=True, queue="default", **_RETRY_KWARGS)
def sync_fixtures_task(
    self, sport_code: str, competition_ref: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_fixtures(
            sport_code, competition_ref, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_live_fixtures", bind=True, queue="live", **_RETRY_KWARGS)
def sync_live_fixtures_task(
    self, sport_code: str, competition_ref: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_live_fixtures(
            sport_code, competition_ref, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_upcoming_fixtures", bind=True, queue="default", **_RETRY_KWARGS)
def sync_upcoming_fixtures_task(
    self, sport_code: str, competition_id: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_upcoming_fixtures(
            sport_code, competition_id, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_completed_fixtures", bind=True, queue="default", **_RETRY_KWARGS)
def sync_completed_fixtures_task(
    self, sport_code: str, competition_id: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_completed_fixtures(
            sport_code, competition_id, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_standings", bind=True, queue="default", **_RETRY_KWARGS)
def sync_standings_task(
    self, sport_code: str, competition_ref: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_standings(
            sport_code, competition_ref, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_standings_alt", bind=True, queue="default", **_RETRY_KWARGS)
def sync_standings_alt_task(
    self, sport_code: str, competition_id: str, season_label: str, season_id_str: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        return await orchestrator.sync_standings_alt(
            sport_code, competition_id, season_label, SeasonId(UUID(season_id_str)), _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_odds", bind=True, queue="default", **_RETRY_KWARGS)
def sync_odds_task(
    self, sport_code: str, fixture_ref_provider: str, fixture_ref_external_id: str, fixture_id: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        fixture_ref = ProviderRef(provider=fixture_ref_provider, external_id=fixture_ref_external_id)
        return await orchestrator.sync_odds_for_fixture(sport_code, fixture_ref, fixture_id, _resolve_now(now_iso))

    return _run_summary(asyncio.run(_do()))


@celery_app.task(name="ingestion.sync_team_statistics", bind=True, queue="default", **_RETRY_KWARGS)
def sync_team_statistics_task(
    self, sport_code: str, fixture_ref_provider: str, fixture_ref_external_id: str, fixture_id: str, now_iso: str | None = None
) -> dict | None:
    async def _do():
        orchestrator = await _get_orchestrator()
        fixture_ref = ProviderRef(provider=fixture_ref_provider, external_id=fixture_ref_external_id)
        return await orchestrator.sync_team_statistics_for_fixture(
            sport_code, fixture_ref, fixture_id, _resolve_now(now_iso)
        )

    return _run_summary(asyncio.run(_do()))
