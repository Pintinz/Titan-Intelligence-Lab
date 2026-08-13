"""Repository ports — abstract persistence interfaces the application layer depends on.

Concrete implementations live in modules/sports/infrastructure/persistence/repositories.py
(docs/architecture.md §3). Application/domain code must only ever import from here, never
from the infrastructure package directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.sports.domain.entities import (
    CoachingStaffMember,
    Competition,
    Country,
    Fixture,
    Injury,
    Lineup,
    Match,
    Player,
    Season,
    Sport,
    Standing,
    Team,
    TeamStatistics,
    Transfer,
    Venue,
)
from modules.sports.domain.value_objects import (
    CompetitionId,
    CountryId,
    EntityId,
    FixtureId,
    LineupId,
    MatchId,
    PlayerId,
    SeasonId,
    SportCode,
    SportId,
    TeamId,
    VenueId,
)


class SportRepositoryPort(Protocol):
    async def get(self, sport_id: SportId) -> Sport | None: ...
    async def get_by_code(self, code: SportCode) -> Sport | None: ...
    async def upsert(self, sport: Sport) -> Sport: ...


class TeamRepositoryPort(Protocol):
    async def get(self, team_id: TeamId) -> Team | None: ...
    async def list_by_sport(self, sport_id: SportId) -> list[Team]: ...
    async def upsert(self, team: Team) -> Team: ...


class PlayerRepositoryPort(Protocol):
    async def get(self, player_id: PlayerId) -> Player | None: ...
    async def list_by_team(self, team_id: TeamId) -> list[Player]: ...
    async def upsert(self, player: Player) -> Player: ...
    async def list_by_sport(self, sport_id: SportId, limit: int = 100) -> list[Player]:
        """Every player registered under a sport, regardless of team — the Player Center
        (Milestone 10) browsing view a per-team roster lookup can't answer. Mirrors
        ``TeamRepositoryPort.list_by_sport``. Additive: no existing method changed."""
        ...


class VenueRepositoryPort(Protocol):
    async def get(self, venue_id: VenueId) -> Venue | None: ...
    async def upsert(self, venue: Venue) -> Venue: ...


class CompetitionRepositoryPort(Protocol):
    async def get(self, competition_id: CompetitionId) -> Competition | None: ...
    async def list_by_sport(self, sport_id: SportId) -> list[Competition]: ...
    async def upsert(self, competition: Competition) -> Competition: ...


class SeasonRepositoryPort(Protocol):
    async def get(self, season_id: SeasonId) -> Season | None: ...
    async def list_by_competition(self, competition_id: CompetitionId) -> list[Season]: ...
    async def upsert(self, season: Season) -> Season: ...


class FixtureRepositoryPort(Protocol):
    async def get(self, fixture_id: FixtureId) -> Fixture | None: ...
    async def list_by_season(self, season_id: SeasonId) -> list[Fixture]: ...
    async def upsert(self, fixture: Fixture) -> Fixture: ...
    async def list_recent_by_team(
        self, team_id: TeamId, before: datetime, limit: int = 10
    ) -> list[Fixture]:
        """Every fixture (home or away) involving ``team_id`` scheduled before ``before``,
        most recent first — the windowed-history query engineered features need (Milestone 9)
        that a single ``get`` by id can't answer. Additive: no existing method changed."""
        ...

    async def find_by_teams_and_date_window(
        self, home_team_id: TeamId, away_team_id: TeamId, date_from: datetime, date_to: datetime
    ) -> list[Fixture]:
        """Fixtures with this exact home/away pairing scheduled within ``[date_from, date_to]`` —
        the cross-provider identity fallback ``EntityReconciliationService.reconcile_fixture``'s
        ``match_by_teams_and_date`` opt-in uses to recognize "this is the same real-world match a
        different provider already reported," since a second provider's own external fixture id
        never matches the first provider's. Additive: no existing method changed."""
        ...


class StandingRepositoryPort(Protocol):
    async def list_by_season(self, season_id: SeasonId) -> list[Standing]: ...
    async def upsert(self, standing: Standing) -> Standing: ...


class CountryRepositoryPort(Protocol):
    async def get(self, country_id: CountryId) -> Country | None: ...
    async def get_by_code(self, code: str) -> Country | None: ...
    async def list_all(self) -> list[Country]: ...
    async def upsert(self, country: Country) -> Country: ...


class MatchRepositoryPort(Protocol):
    """``Match`` (started_at/ended_at/final_state — the live-state wrapper around a `Fixture`,
    docs/database_schema.md `sports.matches`) has no provider-side identity of its own: a
    fixture's match always exists 1:1 (`MatchModel.fixture_id` is a unique FK), so ``get_or_create``
    is the only entry point real callers need — there's nothing to reconcile against a provider
    the way Team/Player/Fixture rows are."""

    async def get_by_fixture(self, fixture_id: FixtureId) -> Match | None: ...
    async def upsert(self, match: Match) -> Match: ...


class TeamStatisticsRepositoryPort(Protocol):
    async def get_for_match_team(self, match_id: MatchId, team_id: TeamId) -> TeamStatistics | None: ...
    async def list_by_match(self, match_id: MatchId) -> list[TeamStatistics]: ...
    async def upsert(self, statistics: TeamStatistics) -> TeamStatistics: ...
    async def list_recent_by_team(
        self, team_id: TeamId, before: datetime, limit: int = 10
    ) -> list[TeamStatistics]:
        """``team_id``'s statistics rows across past matches (joined through Match's
        ``started_at``), most recent first — the windowed-history query engineered features
        need (Milestone 9). Additive: no existing method changed."""
        ...


class LineupRepositoryPort(Protocol):
    async def get(self, lineup_id: LineupId) -> Lineup | None: ...
    async def get_for_match_team(self, match_id: MatchId, team_id: TeamId) -> Lineup | None: ...
    async def list_by_match(self, match_id: MatchId) -> list[Lineup]: ...
    async def upsert(self, lineup: Lineup) -> Lineup: ...
    async def list_recent_by_team(self, team_id: TeamId, before: datetime, limit: int = 10) -> list[Lineup]:
        """Milestone 6 — this team's lineups for fixtures scheduled before ``before``, most recent
        first, joined through `Match.fixture_id` (a `Lineup` carries no date of its own). Mirrors
        `FixtureRepositoryPort.list_recent_by_team`'s existing windowed-history shape. Additive:
        no existing method changed."""
        ...


class InjuryRepositoryPort(Protocol):
    async def get(self, injury_id: EntityId) -> Injury | None: ...
    async def list_by_player(self, player_id: PlayerId) -> list[Injury]: ...
    async def list_current_by_team(self, team_id: TeamId) -> list[Injury]: ...
    async def upsert(self, injury: Injury) -> Injury: ...


class TransferRepositoryPort(Protocol):
    async def get(self, transfer_id: EntityId) -> Transfer | None: ...
    async def list_by_player(self, player_id: PlayerId) -> list[Transfer]: ...
    async def list_by_team(self, team_id: TeamId) -> list[Transfer]: ...
    async def upsert(self, transfer: Transfer) -> Transfer: ...


class CoachingStaffRepositoryPort(Protocol):
    async def get(self, staff_id: EntityId) -> CoachingStaffMember | None: ...
    async def get_current_by_team(self, team_id: TeamId, role: str = "head_coach") -> CoachingStaffMember | None: ...
    async def list_by_team(self, team_id: TeamId) -> list[CoachingStaffMember]: ...
    async def upsert(self, staff: CoachingStaffMember) -> CoachingStaffMember: ...
