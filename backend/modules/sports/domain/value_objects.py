"""Sport-agnostic value objects shared by every sport plugin.

No framework imports here (see docs/architecture.md §2, "Domain has zero imports from
FastAPI, SQLAlchemy, Supabase SDKs, or any provider SDK").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class SportCode(str, Enum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    BASEBALL = "baseball"
    TABLE_TENNIS = "table_tennis"


class CompetitionType(str, Enum):
    LEAGUE = "league"
    CUP = "cup"
    TOURNAMENT = "tournament"


class SeasonStatus(str, Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"


class FixtureStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    COMPLETED = "completed"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class MatchPeriodKind(str, Enum):
    """Sport-specific match subdivisions, normalized to a common vocabulary.

    Football uses HALF, basketball uses QUARTER, baseball uses INNING,
    table tennis uses SET — a sport plugin declares which kind(s) it uses
    (see contracts/fixture.py MatchLifecycleRules).
    """

    HALF = "half"
    QUARTER = "quarter"
    INNING = "inning"
    SET = "set"
    OVERTIME = "overtime"


@dataclass(frozen=True)
class ProviderRef:
    """Opaque pointer to an external provider's identifier for an entity.

    Stored as JSONB on the owning entity (docs/database_schema.md §1) — kept out of the
    primary schema so provider replacement never touches domain or persistence structure.
    """

    provider: str
    external_id: str


@dataclass(frozen=True)
class DateRange:
    start: datetime
    end: datetime | None = None

    def contains(self, moment: datetime) -> bool:
        if moment < self.start:
            return False
        if self.end is not None and moment > self.end:
            return False
        return True


@dataclass(frozen=True)
class EntityId:
    """Typed wrapper around a UUID primary key to prevent id-type mix-ups
    (e.g., passing a TeamId where a PlayerId is expected)."""

    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SportId(EntityId):
    pass


@dataclass(frozen=True)
class CompetitionId(EntityId):
    pass


@dataclass(frozen=True)
class SeasonId(EntityId):
    pass


@dataclass(frozen=True)
class TeamId(EntityId):
    pass


@dataclass(frozen=True)
class PlayerId(EntityId):
    pass


@dataclass(frozen=True)
class VenueId(EntityId):
    pass


@dataclass(frozen=True)
class FixtureId(EntityId):
    pass


@dataclass(frozen=True)
class MatchId(EntityId):
    pass


@dataclass(frozen=True)
class CountryId(EntityId):
    pass


@dataclass(frozen=True)
class LineupId(EntityId):
    pass


class LineupRole(str, Enum):
    """Whether a player was in the starting lineup or on the bench for a match — the
    Lineup canonical entity (docs/roadmap.md Milestone 5 Entity Expansion Matrix)."""

    STARTER = "starter"
    SUBSTITUTE = "substitute"
