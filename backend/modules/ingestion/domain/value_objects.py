"""Value objects for the Sports Data Ingestion Engine (docs/roadmap.md Milestone 5).

No framework imports — same domain-purity rule as every other module
(docs/architecture.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class EntityKind(str, Enum):
    """The canonical entities Milestone 5 actively ingests (docs/database_schema.md Entity
    Expansion Matrix). Adding a new kind here plus a reconciler is the entire extension
    surface for a not-yet-wired entity — no other module changes."""

    SPORT = "sport"
    COUNTRY = "country"
    COMPETITION = "competition"
    SEASON = "season"
    VENUE = "venue"
    TEAM = "team"
    PLAYER = "player"
    FIXTURE = "fixture"
    TEAM_STATISTICS = "team_statistics"
    LINEUP = "lineup"
    STANDING = "standing"
    ODDS = "odds"
    INJURY = "injury"
    TRANSFER = "transfer"
    COACHING_STAFF = "coaching_staff"


class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"  # some records ingested, some rejected/failed


class SyncTrigger(str, Enum):
    """Milestone 5 (Verified Pre-Match Data Availability) extended this enum — previously
    ``SCHEDULED`` was the default `trigger=` value on every `SyncOrchestrator` method regardless
    of what actually invoked it (an admin's one-off button click, a backfill script, or a real
    Celery Beat firing all looked identical in `SyncRun.trigger`), which made it impossible to
    tell, after the fact, whether a sync's timing genuinely reflects real-world data availability.
    That ambiguity is exactly what blocked `information_available_at`/`availability_classification`
    from ever being trustworthy (see `docs/milestone5_verification_report.md`).

    Only ``LIVE_SCHEDULED`` — a real, periodic Celery Beat firing, distinct from ``SCHEDULED``'s
    prior overloaded meaning — is ever eligible to produce `VERIFIED_PRE_MATCH` provenance. Every
    other value (including the new ``ADMIN_MANUAL``/``BACKFILL``/``RECONCILIATION``/``SYSTEM``)
    must not, by construction — enforced in `modules.ingestion.application.provenance` and never
    trusted merely because a caller claims one of these values."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    RETRY = "retry"
    LIVE = "live"  # triggered by live-match adaptive polling, not the regular schedule
    LIVE_SCHEDULED = "live_scheduled"  # a real, periodic Celery Beat firing — see class docstring
    ADMIN_MANUAL = "admin_manual"  # an operator's one-off button click via the admin API
    BACKFILL = "backfill"  # a one-off dev/ops script backfilling historical data long after the fact
    RECONCILIATION = "reconciliation"  # an ad-hoc data-repair/reconciliation pass, not a data-freshness sync
    SYSTEM = "system"  # an internal system process other than the above (e.g. a downstream trigger)


class TimelineEventType(str, Enum):
    """docs/roadmap.md Milestone 5 "Event Timeline Engine" examples, plus the ingestion
    lifecycle events (SYNC_*, ENTITY_RECONCILED) that double as the audit log
    (docs/decisions.md — Event Timeline Engine doubling as ingestion audit log)."""

    # Ingestion lifecycle / audit
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"
    ENTITY_RECONCILED = "entity_reconciled"

    # Fixture/match lifecycle
    FIXTURE_CREATED = "fixture_created"
    FIXTURE_UPDATED = "fixture_updated"
    KICKOFF = "kickoff"
    MATCH_FINISHED = "match_finished"
    STATISTICS_FINALIZED = "statistics_finalized"
    PERIOD_FINISHED = "period_finished"

    # Match events (sport-agnostic vocabulary; sport-specific detail lives in the payload)
    GOAL = "goal"
    RUN = "run"
    POINT = "point"
    CARD = "card"
    TIMEOUT = "timeout"
    SUBSTITUTION = "substitution"
    INJURY = "injury"
    SET_WON = "set_won"


@dataclass(frozen=True)
class SyncRunId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class TimelineEventId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class DataQualityReportId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
