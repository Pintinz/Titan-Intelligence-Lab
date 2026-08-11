"""Concrete SQLAlchemy repository implementations of modules.sports.ports.repositories.

Application-layer code depends on the ports, never on these classes directly — they're wired
up only in each app's composition module (docs/architecture.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from modules.sports.infrastructure.persistence import mappers
from modules.sports.infrastructure.persistence.models import (
    CoachingStaffModel,
    CompetitionModel,
    CountryModel,
    FixtureModel,
    InjuryModel,
    LineupModel,
    MatchModel,
    PlayerModel,
    SeasonModel,
    SportModel,
    StandingModel,
    TeamModel,
    TeamStatisticsModel,
    TransferModel,
    VenueModel,
)


@dataclass
class SqlAlchemySportRepository:
    session: AsyncSession

    async def get(self, sport_id: SportId) -> Sport | None:
        model = await self.session.get(SportModel, sport_id.value)
        return mappers.sport_to_domain(model) if model else None

    async def get_by_code(self, code: SportCode) -> Sport | None:
        result = await self.session.execute(select(SportModel).where(SportModel.code == code.value))
        model = result.scalar_one_or_none()
        return mappers.sport_to_domain(model) if model else None

    async def upsert(self, sport: Sport) -> Sport:
        existing = await self.session.get(SportModel, sport.id.value)
        model = mappers.sport_to_model(sport, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.sport_to_domain(model)


@dataclass
class SqlAlchemyTeamRepository:
    session: AsyncSession

    async def get(self, team_id: TeamId) -> Team | None:
        model = await self.session.get(TeamModel, team_id.value)
        return mappers.team_to_domain(model) if model else None

    async def list_by_sport(self, sport_id: SportId) -> list[Team]:
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.sport_id == sport_id.value)
        )
        return [mappers.team_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, team: Team) -> Team:
        existing = await self.session.get(TeamModel, team.id.value)
        model = mappers.team_to_model(team, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.team_to_domain(model)


@dataclass
class SqlAlchemyPlayerRepository:
    session: AsyncSession

    async def get(self, player_id: PlayerId) -> Player | None:
        model = await self.session.get(PlayerModel, player_id.value)
        return mappers.player_to_domain(model) if model else None

    async def list_by_team(self, team_id: TeamId) -> list[Player]:
        result = await self.session.execute(
            select(PlayerModel).where(PlayerModel.team_id == team_id.value)
        )
        return [mappers.player_to_domain(row) for row in result.scalars().all()]

    async def list_by_sport(self, sport_id: SportId, limit: int = 100) -> list[Player]:
        result = await self.session.execute(
            select(PlayerModel).where(PlayerModel.sport_id == sport_id.value).limit(limit)
        )
        return [mappers.player_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, player: Player) -> Player:
        existing = await self.session.get(PlayerModel, player.id.value)
        model = mappers.player_to_model(player, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.player_to_domain(model)


@dataclass
class SqlAlchemyVenueRepository:
    session: AsyncSession

    async def get(self, venue_id: VenueId) -> Venue | None:
        model = await self.session.get(VenueModel, venue_id.value)
        return mappers.venue_to_domain(model) if model else None

    async def upsert(self, venue: Venue) -> Venue:
        existing = await self.session.get(VenueModel, venue.id.value)
        model = mappers.venue_to_model(venue, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.venue_to_domain(model)


@dataclass
class SqlAlchemyCompetitionRepository:
    session: AsyncSession

    async def get(self, competition_id: CompetitionId) -> Competition | None:
        model = await self.session.get(CompetitionModel, competition_id.value)
        return mappers.competition_to_domain(model) if model else None

    async def list_by_sport(self, sport_id: SportId) -> list[Competition]:
        result = await self.session.execute(
            select(CompetitionModel).where(CompetitionModel.sport_id == sport_id.value)
        )
        return [mappers.competition_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, competition: Competition) -> Competition:
        existing = await self.session.get(CompetitionModel, competition.id.value)
        model = mappers.competition_to_model(competition, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.competition_to_domain(model)


@dataclass
class SqlAlchemySeasonRepository:
    session: AsyncSession

    async def get(self, season_id: SeasonId) -> Season | None:
        model = await self.session.get(SeasonModel, season_id.value)
        return mappers.season_to_domain(model) if model else None

    async def list_by_competition(self, competition_id: CompetitionId) -> list[Season]:
        result = await self.session.execute(
            select(SeasonModel).where(SeasonModel.competition_id == competition_id.value)
        )
        return [mappers.season_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, season: Season) -> Season:
        existing = await self.session.get(SeasonModel, season.id.value)
        model = mappers.season_to_model(season, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.season_to_domain(model)


@dataclass
class SqlAlchemyFixtureRepository:
    session: AsyncSession

    async def get(self, fixture_id: FixtureId) -> Fixture | None:
        model = await self.session.get(FixtureModel, fixture_id.value)
        return mappers.fixture_to_domain(model) if model else None

    async def list_by_season(self, season_id: SeasonId) -> list[Fixture]:
        result = await self.session.execute(
            select(FixtureModel).where(FixtureModel.season_id == season_id.value)
        )
        return [mappers.fixture_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, fixture: Fixture) -> Fixture:
        existing = await self.session.get(FixtureModel, fixture.id.value)
        model = mappers.fixture_to_model(fixture, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.fixture_to_domain(model)

    async def list_recent_by_team(self, team_id: TeamId, before: datetime, limit: int = 10) -> list[Fixture]:
        stmt = (
            select(FixtureModel)
            .where(
                or_(FixtureModel.home_team_id == team_id.value, FixtureModel.away_team_id == team_id.value),
                FixtureModel.scheduled_at < before,
            )
            .order_by(FixtureModel.scheduled_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.fixture_to_domain(row) for row in result.scalars().all()]

    async def list_upcoming_by_team(self, team_id: TeamId, after: datetime, limit: int = 10) -> list[Fixture]:
        stmt = (
            select(FixtureModel)
            .where(
                or_(FixtureModel.home_team_id == team_id.value, FixtureModel.away_team_id == team_id.value),
                FixtureModel.scheduled_at >= after,
            )
            .order_by(FixtureModel.scheduled_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.fixture_to_domain(row) for row in result.scalars().all()]

    async def find_by_teams_and_date_window(
        self, home_team_id: TeamId, away_team_id: TeamId, date_from: datetime, date_to: datetime
    ) -> list[Fixture]:
        stmt = select(FixtureModel).where(
            FixtureModel.home_team_id == home_team_id.value,
            FixtureModel.away_team_id == away_team_id.value,
            FixtureModel.scheduled_at >= date_from,
            FixtureModel.scheduled_at <= date_to,
        )
        result = await self.session.execute(stmt)
        return [mappers.fixture_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyStandingRepository:
    session: AsyncSession

    async def list_by_season(self, season_id: SeasonId) -> list[Standing]:
        result = await self.session.execute(
            select(StandingModel).where(StandingModel.season_id == season_id.value)
        )
        return [mappers.standing_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, standing: Standing) -> Standing:
        existing = await self.session.get(StandingModel, standing.id.value)
        model = mappers.standing_to_model(standing, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.standing_to_domain(model)


@dataclass
class SqlAlchemyCountryRepository:
    session: AsyncSession

    async def get(self, country_id: CountryId) -> Country | None:
        model = await self.session.get(CountryModel, country_id.value)
        return mappers.country_to_domain(model) if model else None

    async def get_by_code(self, code: str) -> Country | None:
        result = await self.session.execute(select(CountryModel).where(CountryModel.code == code))
        model = result.scalar_one_or_none()
        return mappers.country_to_domain(model) if model else None

    async def list_all(self) -> list[Country]:
        result = await self.session.execute(select(CountryModel))
        return [mappers.country_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, country: Country) -> Country:
        existing = await self.session.get(CountryModel, country.id.value)
        model = mappers.country_to_model(country, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.country_to_domain(model)


@dataclass
class SqlAlchemyMatchRepository:
    session: AsyncSession

    async def get_by_fixture(self, fixture_id: FixtureId) -> Match | None:
        stmt = select(MatchModel).where(MatchModel.fixture_id == fixture_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.match_to_domain(model) if model else None

    async def upsert(self, match: Match) -> Match:
        existing = await self.session.get(MatchModel, match.id.value)
        model = mappers.match_to_model(match, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.match_to_domain(model)


@dataclass
class SqlAlchemyTeamStatisticsRepository:
    session: AsyncSession

    async def get_for_match_team(self, match_id: MatchId, team_id: TeamId) -> TeamStatistics | None:
        stmt = select(TeamStatisticsModel).where(
            TeamStatisticsModel.match_id == match_id.value, TeamStatisticsModel.team_id == team_id.value
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.team_statistics_to_domain(model) if model else None

    async def list_by_match(self, match_id: MatchId) -> list[TeamStatistics]:
        stmt = select(TeamStatisticsModel).where(TeamStatisticsModel.match_id == match_id.value)
        result = await self.session.execute(stmt)
        return [mappers.team_statistics_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, statistics: TeamStatistics) -> TeamStatistics:
        existing = await self.session.get(TeamStatisticsModel, statistics.id.value)
        model = mappers.team_statistics_to_model(statistics, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.team_statistics_to_domain(model)

    async def list_recent_by_team(self, team_id: TeamId, before: datetime, limit: int = 10) -> list[TeamStatistics]:
        stmt = (
            select(TeamStatisticsModel)
            .join(MatchModel, MatchModel.id == TeamStatisticsModel.match_id)
            .where(TeamStatisticsModel.team_id == team_id.value, MatchModel.started_at < before)
            .order_by(MatchModel.started_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.team_statistics_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyLineupRepository:
    session: AsyncSession

    async def get(self, lineup_id: LineupId) -> Lineup | None:
        model = await self.session.get(LineupModel, lineup_id.value)
        return mappers.lineup_to_domain(model) if model else None

    async def get_for_match_team(self, match_id: MatchId, team_id: TeamId) -> Lineup | None:
        stmt = select(LineupModel).where(
            LineupModel.match_id == match_id.value, LineupModel.team_id == team_id.value
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.lineup_to_domain(model) if model else None

    async def list_by_match(self, match_id: MatchId) -> list[Lineup]:
        stmt = select(LineupModel).where(LineupModel.match_id == match_id.value)
        result = await self.session.execute(stmt)
        return [mappers.lineup_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, lineup: Lineup) -> Lineup:
        existing = await self.session.get(LineupModel, lineup.id.value)
        model = mappers.lineup_to_model(lineup, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.lineup_to_domain(model)


@dataclass
class SqlAlchemyInjuryRepository:
    session: AsyncSession

    async def get(self, injury_id: EntityId) -> Injury | None:
        model = await self.session.get(InjuryModel, injury_id.value)
        return mappers.injury_to_domain(model) if model else None

    async def list_by_player(self, player_id: PlayerId) -> list[Injury]:
        stmt = select(InjuryModel).where(InjuryModel.player_id == player_id.value).order_by(InjuryModel.reported_at.desc())
        result = await self.session.execute(stmt)
        return [mappers.injury_to_domain(row) for row in result.scalars().all()]

    async def list_current_by_team(self, team_id: TeamId) -> list[Injury]:
        """Every injury reported for a player currently on this team — not scoped to a status,
        since the provider's own `status` text already distinguishes ongoing vs resolved cases
        and TitanIQ never overwrites/removes a real reported injury (docs/roadmap.md Milestone 5
        provider-attribution rule: reconciliation only creates/updates, never deletes)."""
        stmt = (
            select(InjuryModel)
            .join(PlayerModel, PlayerModel.id == InjuryModel.player_id)
            .where(PlayerModel.team_id == team_id.value)
            .order_by(InjuryModel.reported_at.desc())
        )
        result = await self.session.execute(stmt)
        return [mappers.injury_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, injury: Injury) -> Injury:
        existing = await self.session.get(InjuryModel, injury.id.value)
        model = mappers.injury_to_model(injury, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.injury_to_domain(model)


@dataclass
class SqlAlchemyTransferRepository:
    session: AsyncSession

    async def get(self, transfer_id: EntityId) -> Transfer | None:
        model = await self.session.get(TransferModel, transfer_id.value)
        return mappers.transfer_to_domain(model) if model else None

    async def list_by_player(self, player_id: PlayerId) -> list[Transfer]:
        stmt = (
            select(TransferModel)
            .where(TransferModel.player_id == player_id.value)
            .order_by(TransferModel.effective_date.desc())
        )
        result = await self.session.execute(stmt)
        return [mappers.transfer_to_domain(row) for row in result.scalars().all()]

    async def list_by_team(self, team_id: TeamId) -> list[Transfer]:
        """Both incoming and outgoing transfers for this team, most recent first."""
        stmt = (
            select(TransferModel)
            .where(or_(TransferModel.from_team_id == team_id.value, TransferModel.to_team_id == team_id.value))
            .order_by(TransferModel.effective_date.desc())
        )
        result = await self.session.execute(stmt)
        return [mappers.transfer_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, transfer: Transfer) -> Transfer:
        existing = await self.session.get(TransferModel, transfer.id.value)
        model = mappers.transfer_to_model(transfer, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.transfer_to_domain(model)


@dataclass
class SqlAlchemyCoachingStaffRepository:
    session: AsyncSession

    async def get(self, staff_id: EntityId) -> CoachingStaffMember | None:
        model = await self.session.get(CoachingStaffModel, staff_id.value)
        return mappers.coaching_staff_to_domain(model) if model else None

    async def get_current_by_team(self, team_id: TeamId, role: str = "head_coach") -> CoachingStaffMember | None:
        stmt = (
            select(CoachingStaffModel)
            .where(
                CoachingStaffModel.team_id == team_id.value,
                CoachingStaffModel.role == role,
                CoachingStaffModel.valid_to.is_(None),
            )
            .order_by(CoachingStaffModel.valid_from.desc())
        )
        model = (await self.session.execute(stmt)).scalars().first()
        return mappers.coaching_staff_to_domain(model) if model else None

    async def list_by_team(self, team_id: TeamId) -> list[CoachingStaffMember]:
        """Full history, most recent first — a closed-out (``valid_to`` set) predecessor row is
        never overwritten, only superseded by a new row (see ``EntityReconciliationService.
        reconcile_coaching_staff``)."""
        stmt = (
            select(CoachingStaffModel)
            .where(CoachingStaffModel.team_id == team_id.value)
            .order_by(CoachingStaffModel.valid_from.desc().nulls_last())
        )
        result = await self.session.execute(stmt)
        return [mappers.coaching_staff_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, staff: CoachingStaffMember) -> CoachingStaffMember:
        existing = await self.session.get(CoachingStaffModel, staff.id.value)
        model = mappers.coaching_staff_to_model(staff, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.coaching_staff_to_domain(model)
