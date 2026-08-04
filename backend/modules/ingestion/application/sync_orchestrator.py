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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from modules.ingestion.application.data_quality_engine import IngestionQualityEngine
from modules.ingestion.application.data_validation_engine import DataValidationEngine
from modules.ingestion.application.entity_reconciliation_service import (
    EntityReconciliationService,
    ReconciliationDependencyError,
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
from modules.sports.domain.value_objects import FixtureId, ProviderRef, SportCode
from modules.sports.infrastructure.providers.provider_router import SportsProviderRouter
from modules.sports.ports.repositories import SportRepositoryPort

DEFAULT_MIN_SYNC_INTERVAL_SECONDS = 300  # "never reload complete datasets unnecessarily"
LIVE_MIN_SYNC_INTERVAL_SECONDS = 30  # live fixtures poll far more often — adaptive scheduling
DEFAULT_LOCK_TTL_SECONDS = 120


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
    ) -> SyncRun | None:
        checkpoint = await self.checkpoints.get(sport_code, entity_kind, scope_key)
        if not force and trigger != SyncTrigger.LIVE and await self._should_skip(checkpoint, now, min_interval_seconds):
            return None  # nothing to do — incremental skip, no SyncRun/quality-report noise

        lock_key = f"sync:{sport_code}:{entity_kind.value}:{scope_key}"
        if not await self.lock.acquire(lock_key, lock_ttl_seconds):
            return None  # another worker/process already syncing this exact scope

        try:
            run = SyncRun(
                id=SyncRunId(uuid4()), sport_code=sport_code, entity_kind=entity_kind, scope_key=scope_key,
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
                records = await fetch()
            except Exception as exc:  # noqa: BLE001 — deliberately broad: any provider/transport failure is a sync failure
                return await self._fail(run, checkpoint, sport_code, entity_kind, scope_key, now, str(exc))

            run.records_fetched = len(records)
            issue_counts = {"missing": 0, "invalid": 0, "relationship": 0, "duplicate": 0}
            for record in records:
                outcome = await process_one(record)
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
            fetch=fetch, process_one=process_one, force=force,
        )

    async def sync_live_fixtures(self, sport_code: str, competition_ref: str, season_label: str, season_id, now: datetime) -> SyncRun | None:
        """Same as sync_fixtures but tagged LIVE and polled far more often — the "intelligent
        scheduling to minimize API usage" the roadmap asks for is this different interval, not
        a different code path (docs/roadmap.md Milestone 5 "Live Data Synchronization")."""
        return await self.sync_fixtures(
            sport_code, competition_ref, season_label, season_id, now,
            trigger=SyncTrigger.LIVE, low_priority=False, min_interval_seconds=LIVE_MIN_SYNC_INTERVAL_SECONDS,
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
