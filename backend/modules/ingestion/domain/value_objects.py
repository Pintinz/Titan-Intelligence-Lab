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


class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"  # some records ingested, some rejected/failed


class SyncTrigger(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    RETRY = "retry"
    LIVE = "live"  # triggered by live-match adaptive polling, not the regular schedule


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
