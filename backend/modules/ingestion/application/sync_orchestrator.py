"""Sync Orchestrator (docs/roadmap.md Milestone 5 — Provider Synchronization Engine,
Incremental Synchronization, Live Data Synchronization).

One generic ``_run_sync`` handles everything entity-agnostic: distributed locking (no two
workers sync the same scope concurrently), incremental skip (never reload unnecessarily —
"Delta Updates"/"Last Modified Tracking"), SyncRun lifecycle, retry/failure bookkeeping on the
checkpoint ("Resume"/"Retry"/"Failure Recovery"), quality-report generation, and timeline/audit
events. Per-entity ``sync_*`` methods only supply *what* to fetch and how to reconcile one
record — matching the same "shared machinery, explicit per-entity methods" shape as
``EntityReconciliationService``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from modules.ingestion.application.data_quality_engine import IngestionQualityEngine
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.ingestion.application.entity_reconciliation_service import (
    EntityReconciliationService,
    ReconciliationDependencyError,
)
from modules.ingestion.application.provenance import (
    LINEUP_PREMATCH_WINDOW_MINUTES,
    STRUCTURED_INTEL_SYNC_WINDOW_HOURS,
    is_within_prematch_window,
)
from modules.ingestion.domain.entities import SyncCheckpoint, SyncRun, TimelineEvent
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId, SyncStatus, SyncTrigger, TimelineEventId, TimelineEventType
from modules.ingestion.ports.cache import SyncCachePort
from modules.ingestion.ports.lock import DistributedLockPort
from modules.ingestion.ports.repositories import (
    CompetitionFixtureSourceRepositoryPort,
    SyncCheckpointRepositoryPort,
    SyncRunRepositoryPort,
    TimelineEventRepositoryPort,
)
from modules.predictions.football.odds_feature_writer import FootballOddsFeatureWriter
from modules.sports.domain.value_objects import FixtureId, FixtureStatus, ProviderRef, SportCode
from modules.sports.infrastructure.providers.provider_router import SportsProviderRouter
from modules.sports.ports.repositories import SportRepositoryPort

logger = logging.getLogger(__name__)

DEFAULT_MIN_SYNC_INTERVAL_SECONDS = 300  # "never reload complete datasets unnecessarily"
LIVE_MIN_SYNC_INTERVAL_SECONDS = 30  # live fixtures poll far more often — adaptive scheduling
DEFAULT_LOCK_TTL_SECONDS = 120
# Redis/Celery pipeline verification (2026-08-25) — real defect, empirically reproduced: a
# solo-pool worker's live-fixtures sync for a large competition (basketball/baseball, hundreds of
# in-progress games) genuinely took 277-300s wall-clock against real api-sports.io responses,
# while Beat re-fires this same scope's task every LIVE_MIN_SYNC_INTERVAL_SECONDS (30s).
# DEFAULT_LOCK_TTL_SECONDS (120s) is shorter than that real runtime, so `_run_sync`'s own
# overlap-guard lock silently expired mid-run — every duplicate message Beat had queued in the
# meantime then found the lock "free" once popped, and re-ran the *entire* fetch+reconcile
# against the provider all over again (confirmed live: 5,797 queued tasks, 94% redundant
# sync_live_fixtures re-fires, each a full redundant provider call, not a cheap skip). Since
# `sync_live_fixtures` also bypasses the checkpoint-based `_should_skip` (trigger=LIVE at line
# ~138 below), the lock is the *only* overlap guard this path has — its TTL must outlast the
# realistic worst-case run, not just the common case. 600s gives ~2x headroom over the largest
# observed run without weakening the lock for any other (fast, checkpoint-gated) sync path, which
# still uses DEFAULT_LOCK_TTL_SECONDS unchanged.
LIVE_FIXTURES_LOCK_TTL_SECONDS = 600
# Live-verified production incident, 2026-08-30: a solo-pool worker consumed exactly one
# sync_live_fixtures run, completed its fetch(), then went silent forever — no more log output,
# no next task ever picked up, for 25+ minutes (far past the 277-300s worst-case a FULL run was
# ever empirically observed to take — see LIVE_FIXTURES_LOCK_TTL_SECONDS's own comment above).
# Celery's task_time_limit is confirmed NOT enforced under --pool=solo (this codebase's own
# established finding — see beat_schedule.py/tasks.py comments), so a genuine hang anywhere
# inside one record's `process_one` (fixture reconciliation touches many downstream
# calculators — news/KG/feature writes — any one of which could have an unbounded await) freezes
# the entire single-threaded worker indefinitely, with no automatic recovery. Bounding each
# record's processing time here, in the one shared sync loop every entity type funnels through,
# protects the whole ingestion pipeline against this failure class at once rather than chasing
# down one specific downstream call.
RECORD_PROCESSING_TIMEOUT_SECONDS = 60
# Same incident as RECORD_PROCESSING_TIMEOUT_SECONDS above, refined once live evidence showed
# exactly where this specific recurring hang sits: the SAME task_id (a poison-pill message,
# `task_acks_late=True` meaning an unfinished task is never acked and keeps getting redelivered
# to every fresh worker instance) got "received" and "started" on at least two separate worker
# restarts hours apart, but never logged even the fetch's own HTTP request/response — meaning the
# hang is inside `fetch()` itself (before any HTTP call is even made — e.g. resolving the
# provider's decrypted API key, a DB call with no timeout of its own), not inside per-record
# processing. Bounding fetch() the same way closes that gap.
FETCH_TIMEOUT_SECONDS = 120


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as modules.ingestion.application.data_quality_engine._ensure_aware — SQLite/
    aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007); a naive value is assumed
    UTC and stamped to match ``reference``'s awareness before comparison."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


class SportNotReconciledError(RuntimeError):
    """A sync method was called for a sport that reconcile_sport() hasn't been run for yet."""


class NoFixtureSourcePreferenceError(RuntimeError):
    """`sync_upcoming_fixtures` was called for a competition with no
    `CompetitionFixtureSourcePreference` configured (or the orchestrator wasn't wired with the
    repository at all). Deliberately not a silent fallback to `sync_fixtures` — this method only
    exists for competitions an admin explicitly opted into an alternate provider for; every other
    competition should just keep using `sync_fixtures`/`sync_live_fixtures` as before."""


@dataclass(frozen=True)
class RecordOutcome:
    created: bool = False
    updated: bool = False
    rejected: bool = False
    issue_category: str | None = None  # "missing" | "invalid" | "relationship" | "duplicate"


@dataclass
class SyncOrchestrator:
    router: SportsProviderRouter
    validator: DataValidationEngine
    quality: IngestionQualityEngine
    reconciler: EntityReconciliationService
    sports: SportRepositoryPort
    checkpoints: SyncCheckpointRepositoryPort
    sync_runs: SyncRunRepositoryPort
    timeline: TimelineEventRepositoryPort
    lock: DistributedLockPort
    cache: SyncCachePort | None = None
    odds_feature_writers: dict[str, FootballOddsFeatureWriter] = field(default_factory=dict)
    fixture_source_preferences: CompetitionFixtureSourceRepositoryPort | None = None
    # Provider keys registered in `fixture_source_preferences` whose completed-fixture data is
    # supplementary, not authoritative — e.g. TheSportsDB. `sync_completed_fixtures` never lets
    # these overwrite a score another provider already recorded (see that method's docstring and
    # `EntityReconciliationService.reconcile_fixture`'s `preserve_existing_score`). Empty by
    # default so football-data.org (and any future fixture-schedule provider) keeps its existing
    # "fetched score always wins" behavior unless explicitly opted out of that trust level here.
    supplementary_provider_keys: frozenset[str] = field(default_factory=frozenset)

    async def _get_reconciled_sport(self, sport_code: str):
        sport = await self.sports.get_by_code(SportCode(sport_code))
        if sport is None:
            raise SportNotReconciledError(f"sport '{sport_code}' has not been reconciled yet — call reconcile_sport first")
        return sport

    async def _should_skip(self, checkpoint: SyncCheckpoint | None, now: datetime, min_interval_seconds: int) -> bool:
        if checkpoint is None or checkpoint.last_synced_at is None:
            return False
        last_synced = _ensure_aware(checkpoint.last_synced_at, now)
        return (now - last_synced).total_seconds() < min_interval_seconds

    async def _run_sync(
        self,
        sport_code: str,
        entity_kind: EntityKind,
        scope_key: str,
        trigger: SyncTrigger,
        now: datetime,
        *,
        fetch: Callable[[], Awaitable[list]],
        process_one: Callable[[object], Awaitable[RecordOutcome]],
        min_interval_seconds: int = DEFAULT_MIN_SYNC_INTERVAL_SECONDS,
        force: bool = False,
        lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
        provider_key: str | None = None,
        run_id: SyncRunId | None = None,
    ) -> SyncRun | None:
        """Milestone 5: ``run_id``, when passed, lets a caller (e.g. ``sync_lineups``) know the
        exact ``SyncRunId`` this run will use *before* `_run_sync` itself assigns one — needed so
        its ``process_one`` closure can stamp each reconciled record with the real
        ``sync_run_id`` (Milestone 5 §11 traceability), which no caller could otherwise see since
        ``process_one`` runs inside this method, not the caller's own scope. Every other call site
        that doesn't need this (everything except lineups/injuries/transfers today) leaves it
        ``None`` and gets the same auto-generated id as before."""
        checkpoint = await self.checkpoints.get(sport_code, entity_kind, scope_key)
        if not force and trigger != SyncTrigger.LIVE and await self._should_skip(checkpoint, now, min_interval_seconds):
            return None  # nothing to do — incremental skip, no SyncRun/quality-report noise

        lock_key = f"sync:{sport_code}:{entity_kind.value}:{scope_key}"
        if not await self.lock.acquire(lock_key, lock_ttl_seconds):
            return None  # another worker/process already syncing this exact scope

        try:
            run = SyncRun(
                id=run_id or SyncRunId(uuid4()), sport_code=sport_code, entity_kind=entity_kind, scope_key=scope_key,
                trigger=trigger, status=SyncStatus.RUNNING, started_at=now,
            )
            await self.sync_runs.record(run)
            await self.timeline.record(
                TimelineEvent(
                    id=TimelineEventId(uuid4()), event_type=TimelineEventType.SYNC_STARTED, occurred_at=now,
                    sport_code=sport_code, entity_kind=entity_kind, entity_id=scope_key,
                )
            )

            try:
                records = await asyncio.wait_for(fetch(), timeout=FETCH_TIMEOUT_SECONDS)
            except Exception as exc:  # noqa: BLE001 — deliberately broad: any provider/transport failure (including a TimeoutError) is a sync failure
                # Previously silent: `_fail` stores `str(exc)` only in the SyncRun row, never in the
                # process log stream — a real production incident (2026-08-27) where every single
                # sync attempt failed for days took a live DB/admin-panel investigation to diagnose
                # because there was no other way to see why. Logged here, not inside `_fail`, so the
                # real traceback (fetch()'s actual exception) is captured, not a stringified re-throw.
                logger.error(
                    "sync_orchestrator.fetch_failed",
                    extra={"sport_code": sport_code, "entity_kind": entity_kind.value, "scope_key": scope_key},
                    exc_info=True,
                )
                # asyncio.wait_for's TimeoutError carries no message of its own (str(exc) == "") —
                # an admin reading the SyncRun row later would see a genuinely empty error_message,
                # exactly the kind of unhelpful gap the 2026-08-27 incident above already fixed
                # once for every OTHER exception type.
                message = str(exc) or f"fetch() timed out after {FETCH_TIMEOUT_SECONDS}s"
                return await self._fail(run, checkpoint, sport_code, entity_kind, scope_key, now, message)

            run.records_fetched = len(records)
            issue_counts = {"missing": 0, "invalid": 0, "relationship": 0, "duplicate": 0}
            for record in records:
                try:
                    outcome = await asyncio.wait_for(process_one(record), timeout=RECORD_PROCESSING_TIMEOUT_SECONDS)
                except TimeoutError:
                    # Never silently swallowed — a hang here is exactly the class of incident
                    # this timeout exists to catch, so it must be as visible as the fetch_failed
                    # case above once it happens for real.
                    logger.error(
                        "sync_orchestrator.process_one_timed_out",
                        extra={
                            "sport_code": sport_code, "entity_kind": entity_kind.value, "scope_key": scope_key,
                            "timeout_seconds": RECORD_PROCESSING_TIMEOUT_SECONDS,
                        },
                    )
                    outcome = RecordOutcome(rejected=True)
                if outcome.created:
                    run.records_created += 1
                elif outcome.updated:
                    run.records_updated += 1
                if outcome.rejected:
                    run.records_rejected += 1
                    run.validation_failures += 1
                    if outcome.issue_category:
                        issue_counts[outcome.issue_category] = issue_counts.get(outcome.issue_category, 0) + 1

            run.mark_succeeded(now)
            await self.sync_runs.update(run)

            checkpoint = checkpoint or SyncCheckpoint(sport_code=sport_code, entity_kind=entity_kind, scope_key=scope_key)
            checkpoint.last_synced_at = now
            checkpoint.last_success_at = now
            checkpoint.consecutive_failures = 0
            await self.checkpoints.upsert(checkpoint)

            await self.quality.generate_report(
                sport_code, entity_kind, now, sample_size=len(records),
                missing_count=issue_counts["missing"], invalid_count=issue_counts["invalid"],
                relationship_issue_count=issue_counts["relationship"], duplicate_count=issue_counts["duplicate"],
                provider_key=provider_key,
            )
            await self.timeline.record(
                TimelineEvent(
                    id=TimelineEventId(uuid4()), event_type=TimelineEventType.SYNC_COMPLETED, occurred_at=now,
                    sport_code=sport_code, entity_kind=entity_kind, entity_id=scope_key,
                    payload={"status": run.status.value, "records_fetched": run.records_fetched},
                )
            )
            return run
        finally:
            await self.lock.release(lock_key)

    async def _fail(self, run, checkpoint, sport_code, entity_kind, scope_key, now, error_message) -> SyncRun:
        run.mark_failed(now, error_message)
        await self.sync_runs.update(run)
        checkpoint = checkpoint or SyncCheckpoint(sport_code=sport_code, entity_kind=entity_kind, scope_key=scope_key)
        checkpoint.last_synced_at = now
        checkpoint.consecutive_failures += 1
        await self.checkpoints.upsert(checkpoint)
        await self.timeline.record(
            TimelineEvent(
                id=TimelineEventId(uuid4()), event_type=TimelineEventType.SYNC_FAILED, occurred_at=now,
                sport_code=sport_code, entity_kind=entity_kind, entity_id=scope_key, payload={"error": error_message},
            )
        )
        return run

    # -- per-entity sync methods ----------------------------------------------------------------

    async def sync_countries(self, sport_code: str, now: datetime, *, trigger=SyncTrigger.SCHEDULED, force: bool = False) -> SyncRun | None:
        async def fetch():
            return await self.router.fetch_countries(sport_code, now)

        async def process_one(record):
            result = self.validator.validate_country(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            _, created = await self.reconciler.reconcile_country(record, now)
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.COUNTRY, "global", trigger, now, fetch=fetch, process_one=process_one,
            min_interval_seconds=86400, force=force,  # countries change essentially never
        )

    async def sync_teams(
        self, sport_code: str, competition_ref: str, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = False, force: bool = False,
        season_label: str | None = None,
    ) -> SyncRun | None:
        sport = await self._get_reconciled_sport(sport_code)

        async def fetch():
            return await self.router.fetch_teams(
                sport_code, competition_ref, now, low_priority=low_priority, season_label=season_label
            )

        async def process_one(record):
            result = self.validator.validate_team(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            _, created = await self.reconciler.reconcile_team(record, sport.id, now)
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(sport_code, EntityKind.TEAM, competition_ref, trigger, now, fetch=fetch, process_one=process_one, force=force)

    async def sync_fixtures(
        self, sport_code: str, competition_ref: str, season_label: str, season_id, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = False, force: bool = False,
        min_interval_seconds: int = DEFAULT_MIN_SYNC_INTERVAL_SECONDS,
        lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
    ) -> SyncRun | None:
        async def fetch():
            return await self.router.fetch_fixtures(sport_code, competition_ref, season_label, now, low_priority=low_priority)

        async def process_one(record):
            result = self.validator.validate_fixture(record, now)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="relationship")
            try:
                _, created = await self.reconciler.reconcile_fixture(record, season_id, now, sport_code=sport_code)
            except ReconciliationDependencyError:
                # Home/away team hasn't been synced for this competition yet — reject just this
                # record rather than crashing the whole run (matches sync_standings' handling of
                # the same "referenced entity not reconciled" case).
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.FIXTURE, f"{competition_ref}:{season_label}", trigger, now,
            fetch=fetch, process_one=process_one, min_interval_seconds=min_interval_seconds, force=force,
            lock_ttl_seconds=lock_ttl_seconds,
        )

    async def sync_upcoming_fixtures(
        self, sport_code: str, competition_id: str, season_label: str, season_id, now: datetime, *,
        trigger=SyncTrigger.MANUAL, low_priority: bool = False, force: bool = False,
    ) -> SyncRun | None:
        """The alternate-provider counterpart to sync_fixtures: opt-in per competition via a
        `CompetitionFixtureSourcePreference` (set through the admin fixture-source endpoints),
        routes to `router.fetch_upcoming_fixtures` instead of the sport's default adapter, and
        reconciles with `match_by_teams_and_date=True` so a fixture api-football already created
        gets updated rather than duplicated. `competition_id` is TitanIQ's own internal
        competition id (not a provider-specific ref) — the preference row is what supplies the
        provider-specific ref the adapter actually needs, keeping this call site
        provider-independent."""
        if self.fixture_source_preferences is None:
            raise NoFixtureSourcePreferenceError(
                "SyncOrchestrator wasn't wired with a fixture_source_preferences repository"
            )
        preference = await self.fixture_source_preferences.get_by_competition(competition_id)
        if preference is None:
            raise NoFixtureSourcePreferenceError(
                f"competition '{competition_id}' has no fixture-source preference configured — "
                "use sync_fixtures for the default provider, or set one via the admin API first"
            )

        async def fetch():
            return await self.router.fetch_upcoming_fixtures(
                sport_code, preference.preferred_provider_key, preference.provider_competition_ref,
                season_label, now, low_priority=low_priority,
            )

        async def process_one(record):
            result = self.validator.validate_fixture(record, now)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="relationship")
            try:
                _, created = await self.reconciler.reconcile_fixture(
                    record, season_id, now, sport_code=sport_code, match_by_teams_and_date=True,
                )
            except ReconciliationDependencyError:
                # Home/away team hasn't been cross-provider-mapped yet — reject just this record
                # rather than crashing the whole run (matches sync_fixtures' handling above).
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.FIXTURE, f"upcoming:{competition_id}:{season_label}", trigger, now,
            fetch=fetch, process_one=process_one, force=force, provider_key=preference.preferred_provider_key,
        )

    async def sync_completed_fixtures(
        self, sport_code: str, competition_id: str, season_label: str, season_id, now: datetime, *,
        trigger=SyncTrigger.MANUAL, low_priority: bool = False, force: bool = False,
    ) -> SyncRun | None:
        """`sync_upcoming_fixtures`'s companion for final scores: same
        `CompetitionFixtureSourcePreference` gate and provider, routed to
        `router.fetch_completed_fixtures` instead. A fixture `sync_upcoming_fixtures` created
        while SCHEDULED/TIMED gets no further updates from that method once it kicks off — this
        is what actually moves it to COMPLETED with a final score (via
        `reconcile_fixture`'s existing score-merge: a fetched score always wins, never
        overwritten back to null), which in turn is what lets `reconcile_fixture` trigger
        prediction-outcome resolution and form-differential recomputation for these fixtures,
        matching what already happens for api-football-sourced ones. Uses the same
        `match_by_teams_and_date=True` reconciliation as `sync_upcoming_fixtures` so this updates
        the fixture that sync already created rather than creating a duplicate. Also passes
        `allow_skip_live=True`: this provider never reports IN_PLAY, so its fixtures jump straight
        from SCHEDULED to FINISHED — without this, `Fixture`'s normal lifecycle rule (never
        SCHEDULED->COMPLETED directly) would silently reject the status change forever, even
        though the score itself would still save (see `_resolve_fixture_status`'s docstring)."""
        if self.fixture_source_preferences is None:
            raise NoFixtureSourcePreferenceError(
                "SyncOrchestrator wasn't wired with a fixture_source_preferences repository"
            )
        preference = await self.fixture_source_preferences.get_by_competition(competition_id)
        if preference is None:
            raise NoFixtureSourcePreferenceError(
                f"competition '{competition_id}' has no fixture-source preference configured — "
                "set one via the admin API first"
            )

        async def fetch():
            return await self.router.fetch_completed_fixtures(
                sport_code, preference.preferred_provider_key, preference.provider_competition_ref,
                season_label, now, low_priority=low_priority,
            )

        # Supplementary sources (opted in via CompetitionFixtureSourcePreference but not treated
        # as authoritative — e.g. TheSportsDB) never overwrite a score another provider already
        # recorded; see EntityReconciliationService.reconcile_fixture's `preserve_existing_score`.
        # football-data.org is deliberately excluded — its existing "fetched score always wins"
        # behavior is unchanged, matching this method's own established precedent.
        preserve_existing_score = preference.preferred_provider_key in self.supplementary_provider_keys

        async def process_one(record):
            result = self.validator.validate_fixture(record, now)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="relationship")
            try:
                _, created = await self.reconciler.reconcile_fixture(
                    record, season_id, now, sport_code=sport_code, match_by_teams_and_date=True, allow_skip_live=True,
                    preserve_existing_score=preserve_existing_score,
                )
            except ReconciliationDependencyError:
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.FIXTURE, f"completed:{competition_id}:{season_label}", trigger, now,
            fetch=fetch, process_one=process_one, force=force, provider_key=preference.preferred_provider_key,
        )

    async def sync_live_fixtures(self, sport_code: str, competition_ref: str, season_label: str, season_id, now: datetime) -> SyncRun | None:
        """Same as sync_fixtures but tagged LIVE and polled far more often — the "intelligent
        scheduling to minimize API usage" the roadmap asks for is this different interval, not
        a different code path (docs/roadmap.md Milestone 5 "Live Data Synchronization").

        Passes LIVE_FIXTURES_LOCK_TTL_SECONDS rather than the default lock TTL: this path also
        bypasses the checkpoint-based min-interval skip (trigger=LIVE, see `_run_sync`), so the
        overlap lock is the only thing standing between a legitimately slow run and Beat's next
        30s re-fire re-running the same fetch from scratch (see that constant's own docstring)."""
        return await self.sync_fixtures(
            sport_code, competition_ref, season_label, season_id, now,
            trigger=SyncTrigger.LIVE, low_priority=False, min_interval_seconds=LIVE_MIN_SYNC_INTERVAL_SECONDS,
            lock_ttl_seconds=LIVE_FIXTURES_LOCK_TTL_SECONDS,
        )

    async def sync_standings(
        self, sport_code: str, competition_ref: str, season_label: str, season_id, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = False, force: bool = False,
    ) -> SyncRun | None:
        async def fetch():
            return await self.router.fetch_standings(sport_code, competition_ref, season_label, now, low_priority=low_priority)

        async def process_one(record):
            result = self.validator.validate_standing(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            try:
                await self.reconciler.reconcile_standing(record, season_id, now)
            except Exception:  # noqa: BLE001 — team not yet reconciled is a rejection, not a sync failure
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=True)

        return await self._run_sync(
            sport_code, EntityKind.STANDING, f"{competition_ref}:{season_label}", trigger, now,
            fetch=fetch, process_one=process_one, force=force,
        )

    async def sync_standings_alt(
        self, sport_code: str, competition_id: str, season_label: str, season_id, now: datetime, *,
        trigger=SyncTrigger.MANUAL, low_priority: bool = False, force: bool = False,
    ) -> SyncRun | None:
        """`sync_upcoming_fixtures`/`sync_completed_fixtures`'s companion for standings: same
        `CompetitionFixtureSourcePreference` gate and provider, routed to
        `router.fetch_standings_alt` instead of the sport's default adapter. Reuses
        `reconciler.reconcile_standing` unchanged — it already resolves `team_ref` by provider key,
        so this only works once every team in the table has a `football_data_org` provider_ref_index
        entry (true for any competition that's already synced fixtures from this provider, since
        that's what populates the mapping)."""
        if self.fixture_source_preferences is None:
            raise NoFixtureSourcePreferenceError(
                "SyncOrchestrator wasn't wired with a fixture_source_preferences repository"
            )
        preference = await self.fixture_source_preferences.get_by_competition(competition_id)
        if preference is None:
            raise NoFixtureSourcePreferenceError(
                f"competition '{competition_id}' has no fixture-source preference configured — "
                "use sync_standings for the default provider, or set one via the admin API first"
            )

        async def fetch():
            return await self.router.fetch_standings_alt(
                sport_code, preference.preferred_provider_key, preference.provider_competition_ref,
                season_label, now, low_priority=low_priority,
            )

        async def process_one(record):
            result = self.validator.validate_standing(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            try:
                await self.reconciler.reconcile_standing(record, season_id, now)
            except Exception:  # noqa: BLE001 — team not yet reconciled is a rejection, not a sync failure
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=True)

        return await self._run_sync(
            sport_code, EntityKind.STANDING, f"alt:{competition_id}:{season_label}", trigger, now,
            fetch=fetch, process_one=process_one, force=force, provider_key=preference.preferred_provider_key,
        )

    async def sync_odds_for_fixture(
        self, sport_code: str, fixture_ref: ProviderRef, fixture_id: str, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = True, force: bool = False,
    ) -> SyncRun | None:
        """Per-fixture, not per-competition, like sync_teams/sync_standings — one fixture's odds
        line, keyed by its own external_id so the incremental-skip window tracks each fixture
        independently. Silently no-ops the feature write (still records a real SyncRun) for a
        sport with no registered writer, same posture as EntityReconciliationService's
        form_differential_calculators — only football has one today."""
        async def fetch():
            record = await self.router.fetch_odds(sport_code, fixture_ref, now, low_priority=low_priority)
            return [record] if record is not None else []

        async def process_one(record):
            result = self.validator.validate_odds(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            writer = self.odds_feature_writers.get(sport_code)
            if writer is not None:
                await writer.compute_and_write(fixture_id, record, now)
            return RecordOutcome(created=True)

        return await self._run_sync(
            sport_code, EntityKind.ODDS, fixture_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force,
        )

    async def sync_team_statistics_for_fixture(
        self, sport_code: str, fixture_ref: ProviderRef, fixture_id: str, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = True, force: bool = False,
    ) -> SyncRun | None:
        """Per-fixture, like sync_odds_for_fixture — one fixture's two team-statistics rows (home
        + away), keyed by its own external_id. `fetch_team_statistics`/`validate_team_statistics`/
        `reconcile_team_statistics` were already real and fully built (audit fix 2026-08-02) but
        had no orchestration calling them. `reconcile_team_statistics` needs a `MatchId`, which
        `EntityReconciliationService.get_or_create_match` resolves from this same fixture_id — a
        Match has no provider identity of its own, so there's nothing to sync for it separately."""
        async def fetch():
            return await self.router.fetch_team_statistics(sport_code, fixture_ref, now, low_priority=low_priority)

        async def process_one(record):
            result = self.validator.validate_team_statistics(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            match = await self.reconciler.get_or_create_match(FixtureId(UUID(fixture_id)), now)
            try:
                _, created = await self.reconciler.reconcile_team_statistics(record, match.id, now)
            except ReconciliationDependencyError:
                # Team hasn't been synced for this competition yet — reject just this record
                # rather than crashing the whole run (matches sync_fixtures' handling above).
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.TEAM_STATISTICS, fixture_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force,
        )

    async def sync_players(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = True, force: bool = False,
        season_label: str | None = None,
    ) -> SyncRun | None:
        """Per-team, same shape as sync_team_statistics_for_fixture — fetch_players/
        validate_player/reconcile_player were already real and fully built but had no
        orchestration calling them, so the players table stayed empty even after teams/fixtures
        synced. `reconcile_player` resolves the roster's team itself from each record's own
        `team_ref`, so unlike team_statistics there's no separate "team not reconciled" rejection
        path to handle here — an unresolved team_ref just leaves the player's team_id null.
        `season_label` mirrors `sync_teams`'s own optional override: api-football's `/players`
        defaults to the current calendar year, which the free tier's credential rejects (only
        2022-2024 accessible) — pass an explicit in-range season to seed real historical rosters."""
        sport = await self._get_reconciled_sport(sport_code)

        async def fetch():
            return await self.router.fetch_players(sport_code, team_ref, now, low_priority=low_priority, season_label=season_label)

        async def process_one(record):
            result = self.validator.validate_player(record, now)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            _, created = await self.reconciler.reconcile_player(record, sport.id, now)
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.PLAYER, team_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force,
        )

    async def sync_players_for_competition(
        self, sport_code: str, season_id, now: datetime, *,
        trigger=SyncTrigger.ADMIN_MANUAL, low_priority: bool = True, force: bool = False,
        season_label: str | None = None,
    ) -> list[SyncRun]:
        """Premier League data-enrichment audit (2026-08-22): `sync_players` is real and fully
        built but per-team only (needs a `team_ref`) — there was no competition-wide entry point
        to sync every team's roster in one call, so it had no independent Celery task/Beat
        schedule of its own. Discovers teams the same way `sync_upcoming_structured_intelligence`
        already does (every team reconciled against this season's fixtures), reusing that
        team-discovery pattern rather than inventing a second one. Unlike that method, this looks
        at every fixture in the season, not just an upcoming window — a full roster sync doesn't
        have a kickoff-proximity reason to wait."""
        fixtures = await self.reconciler.fixtures.list_by_season(season_id)
        team_ids = {team_id for f in fixtures for team_id in (f.home_team_id, f.away_team_id)}

        runs: list[SyncRun] = []
        for team_id in team_ids:
            team = await self.reconciler.teams.get(team_id)
            if team is None or not team.provider_refs:
                continue
            run = await self.sync_players(
                sport_code, team.provider_refs[0], now,
                trigger=trigger, low_priority=low_priority, force=force, season_label=season_label,
            )
            if run is not None:
                runs.append(run)
        return runs

    async def sync_lineups(
        self, sport_code: str, fixture_ref: ProviderRef, fixture_id: str, now: datetime, *,
        trigger=SyncTrigger.ADMIN_MANUAL, low_priority: bool = True, force: bool = False,
    ) -> SyncRun | None:
        """Per-fixture, same shape as sync_team_statistics_for_fixture — `fetch_lineups`/
        `validate_lineup`/`reconcile_lineup` were already real and fully built (docs/roadmap.md
        Milestone 5) but had no orchestration calling them, so the lineups table stayed empty.
        `reconcile_lineup` needs a `MatchId`, resolved the same way sync_team_statistics_for_fixture
        does. Records with unresolved player slots are still saved (reconcile_lineup skips just
        those slots), never rejected wholesale for one missing player.

        Milestone 5 (Verified Pre-Match Data Availability): the `trigger` default flipped from
        `SCHEDULED` to `ADMIN_MANUAL` — `SCHEDULED` was never accurate here (no Beat schedule
        called this method until this milestone added one, via `sync_upcoming_lineups` below,
        which explicitly passes `LIVE_SCHEDULED`), so every prior caller (admin endpoint,
        backfill script) was silently mislabeled. Also resolves the fixture's own
        `scheduled_at`/`status` to feed `reconcile_lineup`'s kickoff-proximity gate — `sync_lineups`
        previously never looked at the fixture at all beyond its provider ref."""
        run_id = SyncRunId(uuid4())

        async def fetch():
            return await self.router.fetch_lineups(sport_code, fixture_ref, now, low_priority=low_priority)

        async def process_one(record):
            result = self.validator.validate_lineup(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            fixture = await self.reconciler.fixtures.get(FixtureId(UUID(fixture_id)))
            match = await self.reconciler.get_or_create_match(FixtureId(UUID(fixture_id)), now)
            try:
                _, created, _unresolved = await self.reconciler.reconcile_lineup(
                    record, match.id, now, trigger=trigger, sync_run_id=str(run_id.value),
                    kickoff=_ensure_aware(fixture.scheduled_at, now) if fixture else None,
                    fixture_status=fixture.status if fixture else None,
                    fixture_id=fixture_id, home_team_id=fixture.home_team_id if fixture else None,
                    sport_code=sport_code,
                )
            except ReconciliationDependencyError:
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.LINEUP, fixture_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force, run_id=run_id,
        )

    async def sync_injuries(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *,
        trigger=SyncTrigger.ADMIN_MANUAL, low_priority: bool = True, force: bool = False,
        season_label: str | None = None,
    ) -> SyncRun | None:
        """Per-team, same shape as sync_players. A team with no reported injuries returns zero
        records — a real `SyncRun` with `records_fetched=0` still gets written (that's the
        honest, common result), not treated as a failure.

        Milestone 5: `trigger` default flipped `SCHEDULED` -> `ADMIN_MANUAL` — see `sync_lineups`'s
        docstring for why."""
        run_id = SyncRunId(uuid4())

        async def fetch():
            return await self.router.fetch_injuries(sport_code, team_ref, now, low_priority=low_priority, season_label=season_label)

        async def process_one(record):
            result = self.validator.validate_injury(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            try:
                _, created = await self.reconciler.reconcile_injury(record, now, trigger=trigger, sync_run_id=str(run_id.value))
            except ReconciliationDependencyError:
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.INJURY, team_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force, run_id=run_id,
        )

    async def sync_transfers(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *,
        trigger=SyncTrigger.ADMIN_MANUAL, low_priority: bool = True, force: bool = False,
    ) -> SyncRun | None:
        """Per-team, same shape as sync_players.

        Milestone 5: `trigger` default flipped `SCHEDULED` -> `ADMIN_MANUAL` — see `sync_lineups`'s
        docstring for why."""
        run_id = SyncRunId(uuid4())

        async def fetch():
            return await self.router.fetch_transfers(sport_code, team_ref, now, low_priority=low_priority)

        async def process_one(record):
            result = self.validator.validate_transfer(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            try:
                await self.reconciler.reconcile_transfer(record, now, trigger=trigger, sync_run_id=str(run_id.value))
            except ReconciliationDependencyError:
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=True)

        return await self._run_sync(
            sport_code, EntityKind.TRANSFER, team_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force, run_id=run_id,
        )

    async def sync_upcoming_structured_intelligence(
        self, sport_code: str, season_id, now: datetime, *,
        trigger=SyncTrigger.LIVE_SCHEDULED,
        structured_intel_window_hours: int = STRUCTURED_INTEL_SYNC_WINDOW_HOURS,
        lineup_prematch_window_minutes: int = LINEUP_PREMATCH_WINDOW_MINUTES,
        force: bool = False,
    ) -> list[SyncRun]:
        """Milestone 5 §1 — "the scheduler must identify the relevant upcoming fixtures... and
        synchronize applicable intelligence before kickoff. Do not blindly synchronize every
        fixture unnecessarily." This is the entry point Celery Beat calls (via `LIVE_SCHEDULED`,
        the only trigger `classify_availability` ever honors) — it prioritizes fixtures already
        `SCHEDULED` and starting within `structured_intel_window_hours`, for the one season it's
        given (matching every other Beat-driven sync method's existing per-competition/season
        scoping, e.g. `sync_standings`), not the entire fixture catalog.

        Injuries/transfers/coaching staff are synced once per distinct team across the whole run
        (a team playing multiple upcoming fixtures in the window is not re-synced per fixture) —
        lineups are synced per fixture, gated by `sync_lineups`/`reconcile_lineup`'s own kickoff-
        proximity check, so calling this well before kickoff is safe: `reconcile_lineup` itself
        declines to mark anything `VERIFIED_PRE_MATCH` outside the window, it just won't have
        real lineup data yet either (the provider itself typically has none to return that
        early). `sync_coaching_staff` has no such gate — a team's current head coach is safe to
        confirm at any point before kickoff, matching injuries/transfers."""
        fixtures = await self.reconciler.fixtures.list_by_season(season_id)
        window_end = now + timedelta(hours=structured_intel_window_hours)
        upcoming = [
            f for f in fixtures
            if f.status is FixtureStatus.SCHEDULED and now <= _ensure_aware(f.scheduled_at, now) <= window_end
        ]

        runs: list[SyncRun] = []
        synced_team_ids: set[str] = set()
        for fixture in upcoming:
            for team_id in (fixture.home_team_id, fixture.away_team_id):
                key = str(team_id.value)
                if key in synced_team_ids:
                    continue
                synced_team_ids.add(key)
                team = await self.reconciler.teams.get(team_id)
                if team is None or not team.provider_refs:
                    continue
                team_ref = team.provider_refs[0]
                injury_run = await self.sync_injuries(sport_code, team_ref, now, trigger=trigger, force=force)
                transfer_run = await self.sync_transfers(sport_code, team_ref, now, trigger=trigger, force=force)
                coach_run = await self.sync_coaching_staff(sport_code, team_ref, now, trigger=trigger, force=force)
                runs.extend(r for r in (injury_run, transfer_run, coach_run) if r is not None)

            if not fixture.provider_refs:
                continue
            if not is_within_prematch_window(_ensure_aware(fixture.scheduled_at, now), now, lineup_prematch_window_minutes):
                continue  # not yet worth fetching — the provider itself won't have lineups this early
            lineup_run = await self.sync_lineups(
                sport_code, fixture.provider_refs[0], str(fixture.id.value), now, trigger=trigger, force=force,
            )
            if lineup_run is not None:
                runs.append(lineup_run)

        return runs

    async def sync_coaching_staff(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *,
        trigger=SyncTrigger.SCHEDULED, low_priority: bool = True, force: bool = False,
    ) -> SyncRun | None:
        """Per-team. `fetch_coach` returns at most one record (the current head coach) or
        ``None`` if the provider has no record for this team — an empty fetch, same honest-zero
        posture as sync_injuries."""
        async def fetch():
            record = await self.router.fetch_coach(sport_code, team_ref, now, low_priority=low_priority)
            return [record] if record is not None else []

        async def process_one(record):
            result = self.validator.validate_coach(record)
            if not result.is_valid:
                return RecordOutcome(rejected=True, issue_category="invalid")
            try:
                _, created = await self.reconciler.reconcile_coaching_staff(record, now)
            except ReconciliationDependencyError:
                return RecordOutcome(rejected=True, issue_category="relationship")
            return RecordOutcome(created=created, updated=not created)

        return await self._run_sync(
            sport_code, EntityKind.COACHING_STAFF, team_ref.external_id, trigger, now,
            fetch=fetch, process_one=process_one, force=force,
        )
