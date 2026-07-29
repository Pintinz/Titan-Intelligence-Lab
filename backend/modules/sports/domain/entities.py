"""Core sport-agnostic domain entities (docs/database_schema.md §2).

Sport-specific variation lives in each entity's ``stat_set``/``payload`` dict, validated
against the owning sport plugin's StatisticSchema/MatchEventTypeCatalog at the application
layer — these classes hold no framework imports and no persistence concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.sports.domain.contracts.competition import SeasonLifecycleRules
from modules.sports.domain.contracts.fixture import is_valid_fixture_transition
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    CountryId,
    DateRange,
    EntityId,
    FixtureId,
    FixtureStatus,
    LineupId,
    LineupRole,
    MatchId,
    PlayerId,
    ProviderRef,
    SeasonId,
    SeasonStatus,
    SportCode,
    SportId,
    TeamId,
    VenueId,
)


@dataclass
class Sport:
    id: SportId
    code: SportCode
    name: str
    status: str = "active"
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Country:
    """Reference/lookup entity — docs/roadmap.md Milestone 5 Entity Expansion Matrix.

    Existing string ``country`` fields on Venue/Team/Competition are left as-is this
    milestone (no breaking migration); linking them to this table via FK is a follow-up
    normalization task, not part of Milestone 5's scope (see decisions.md)."""

    id: CountryId
    code: str  # ISO 3166-1 alpha-2, e.g. "GB"
    name: str
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Venue:
    id: VenueId
    name: str
    city: str
    country: str
    capacity: int | None = None
    surface: str | None = None
    timezone: str = "UTC"
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Competition:
    id: CompetitionId
    sport_id: SportId
    name: str
    type: CompetitionType
    country: str | None
    tier: int | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Season:
    id: SeasonId
    competition_id: CompetitionId
    label: str
    date_range: DateRange
    status: SeasonStatus = SeasonStatus.UPCOMING
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)

    def transition_to(self, target: SeasonStatus) -> "Season":
        if target not in SeasonLifecycleRules[self.status]:
            raise ValueError(f"cannot transition season from {self.status} to {target}")
        return Season(
            id=self.id,
            competition_id=self.competition_id,
            label=self.label,
            date_range=self.date_range,
            status=target,
            version=self.version,
            provider_refs=self.provider_refs,
        )


@dataclass
class Team:
    id: TeamId
    sport_id: SportId
    name: str
    short_name: str
    country: str | None
    venue_id: VenueId | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Player:
    id: PlayerId
    sport_id: SportId
    name: str
    date_of_birth: datetime | None
    position: str | None
    team_id: TeamId | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class CoachingStaffMember:
    id: EntityId
    team_id: TeamId | None
    person_name: str
    role: str


@dataclass
class Official:
    id: EntityId
    sport_id: SportId
    name: str
    role: str


@dataclass
class Fixture:
    id: FixtureId
    season_id: SeasonId
    home_team_id: TeamId
    away_team_id: TeamId
    venue_id: VenueId | None
    scheduled_at: datetime
    status: FixtureStatus = FixtureStatus.SCHEDULED
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)

    def transition_to(self, target: FixtureStatus) -> "Fixture":
        if not is_valid_fixture_transition(self.status, target):
            raise ValueError(f"cannot transition fixture from {self.status} to {target}")
        return Fixture(
            id=self.id,
            season_id=self.season_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            venue_id=self.venue_id,
            scheduled_at=self.scheduled_at,
            status=target,
            version=self.version,
            provider_refs=self.provider_refs,
        )


@dataclass
class Match:
    id: MatchId
    fixture_id: FixtureId
    started_at: datetime | None
    ended_at: datetime | None
    final_state: dict = field(default_factory=dict)


@dataclass
class MatchEvent:
    id: EntityId
    match_id: MatchId
    period: int
    event_type: str
    payload: dict = field(default_factory=dict)
    team_id: TeamId | None = None
    player_id: PlayerId | None = None


@dataclass
class TeamStatistics:
    id: EntityId
    match_id: MatchId
    team_id: TeamId
    stat_set: dict = field(default_factory=dict)
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class PlayerStatistics:
    id: EntityId
    match_id: MatchId
    player_id: PlayerId
    stat_set: dict = field(default_factory=dict)


@dataclass
class Standing:
    id: EntityId
    season_id: SeasonId
    team_id: TeamId
    snapshot_at: datetime
    rank: int
    points: float
    record: dict = field(default_factory=dict)
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class LineupSlot:
    """One player's inclusion in a Lineup — not a standalone aggregate, always embedded in a
    Lineup's starters/substitutes tuples."""

    player_id: PlayerId
    role: LineupRole
    position: str | None = None
    shirt_number: int | None = None


@dataclass
class Lineup:
    """A team's full lineup for one match — docs/roadmap.md Milestone 5 Entity Expansion
    Matrix. One Lineup per (match, team) pair."""

    id: LineupId
    match_id: MatchId
    team_id: TeamId
    formation: str | None = None
    slots: tuple[LineupSlot, ...] = field(default_factory=tuple)
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)

    def starters(self) -> tuple[LineupSlot, ...]:
        return tuple(s for s in self.slots if s.role is LineupRole.STARTER)

    def substitutes(self) -> tuple[LineupSlot, ...]:
        return tuple(s for s in self.slots if s.role is LineupRole.SUBSTITUTE)


@dataclass
class Injury:
    id: EntityId
    player_id: PlayerId
    reported_at: datetime
    status: str
    expected_return: datetime | None = None
    source_ref: ProviderRef | None = None


@dataclass
class Suspension:
    id: EntityId
    player_id: PlayerId
    reason: str
    start_date: datetime
    end_date: datetime | None = None


@dataclass
class Transfer:
    id: EntityId
    player_id: PlayerId
    from_team_id: TeamId | None
    to_team_id: TeamId | None
    effective_date: datetime


@dataclass
class Ranking:
    id: EntityId
    sport_id: SportId
    scope: str  # "team" | "player"
    entity_id: EntityId
    system: str
    value: float
    as_of: datetime
