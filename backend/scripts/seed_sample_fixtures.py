"""One-off local dev helper: seeds a minimal, real reference-data graph (venue, competition,
season, teams, fixtures) into dev.db so match-scoped pages (Match Intelligence, Prediction
Laboratory, Related Matches) have something real to render during manual verification. Nothing
in the ingestion pipeline has run against this local DB, so competitions/seasons/teams/fixtures
are all empty even after scripts/seed_sports.py (mirrors that script's pattern one level deeper
in the schema).

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/seed_sample_fixtures.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.sports.domain.entities import Competition, Fixture, Season, Team, Venue
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    DateRange,
    FixtureId,
    SeasonId,
    SeasonStatus,
    SportCode,
    TeamId,
    VenueId,
)
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyVenueRepository,
)


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        sports = SqlAlchemySportRepository(session=session)
        venues = SqlAlchemyVenueRepository(session=session)
        competitions = SqlAlchemyCompetitionRepository(session=session)
        seasons = SqlAlchemySeasonRepository(session=session)
        teams = SqlAlchemyTeamRepository(session=session)
        fixtures = SqlAlchemyFixtureRepository(session=session)

        football = await sports.get_by_code(SportCode.FOOTBALL)
        if football is None:
            raise SystemExit("Run scripts/seed_sports.py first — no 'football' sport row yet.")

        venue = Venue(id=VenueId(uuid4()), name="Emirates Stadium", city="London", country="England", capacity=60704)
        await venues.upsert(venue)

        competition = Competition(
            id=CompetitionId(uuid4()),
            sport_id=football.id,
            name="Premier League",
            type=CompetitionType.LEAGUE,
            country="England",
            tier=1,
        )
        await competitions.upsert(competition)

        now = datetime.now(timezone.utc)
        season = Season(
            id=SeasonId(uuid4()),
            competition_id=competition.id,
            label="2025/26",
            date_range=DateRange(start=now - timedelta(days=60), end=now + timedelta(days=250)),
            status=SeasonStatus.ACTIVE,
        )
        await seasons.upsert(season)

        team_specs = [
            ("Arsenal", "ARS"),
            ("Chelsea", "CHE"),
            ("Fulham", "FUL"),
        ]
        team_entities: dict[str, Team] = {}
        for name, short_name in team_specs:
            team = Team(id=TeamId(uuid4()), sport_id=football.id, name=name, short_name=short_name, country="England", venue_id=venue.id)
            await teams.upsert(team)
            team_entities[name] = team

        fixture_specs = [
            ("Arsenal", "Chelsea", now + timedelta(days=3)),
            ("Arsenal", "Fulham", now + timedelta(days=10)),
            ("Chelsea", "Fulham", now - timedelta(days=4)),
        ]
        headline_fixture_id = None
        for home, away, scheduled_at in fixture_specs:
            fixture = Fixture(
                id=FixtureId(uuid4()),
                season_id=season.id,
                home_team_id=team_entities[home].id,
                away_team_id=team_entities[away].id,
                venue_id=venue.id,
                scheduled_at=scheduled_at,
            )
            await fixtures.upsert(fixture)
            if headline_fixture_id is None:
                headline_fixture_id = fixture.id.value
            print(f"Seeded fixture {home} vs {away} ({fixture.id.value}) at {scheduled_at.isoformat()}")

        await session.commit()
        print(f"\nMatch Intelligence URL: /app/football/matches/{headline_fixture_id}")


if __name__ == "__main__":
    asyncio.run(main())
