"""Repository ports — abstract persistence interfaces the application layer depends on.

Concrete implementations live in modules/sports/infrastructure/persistence/repositories.py
(docs/architecture.md §3). Application/domain code must only ever import from here, never
from the infrastructure package directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.sports.domain.entities import (
    Competition,
    Country,
    Fixture,
    Lineup,
    Player,
    Season,
    Sport,
    Standing,
    Team,
    TeamStatistics,
    Venue,
)
from modules.sports.domain.value_objects import (
    CompetitionId,
    CountryId,
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


class StandingRepositoryPort(Protocol):
    async def list_by_season(self, season_id: SeasonId) -> list[Standing]: ...
    async def upsert(self, standing: Standing) -> Standing: ...


class CountryRepositoryPort(Protocol):
    async def get(self, country_id: CountryId) -> Country | None: ...
    async def get_by_code(self, code: str) -> Country | None: ...
    async def list_all(self) -> list[Country]: ...
    async def upsert(self, country: Country) -> Country: ...


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
