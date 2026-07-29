"""Mock sports data provider — generates deterministic, realistic-shaped data so every
consumer (ingestion, features, predictions, UI) can be built and tested without a live API key
(provider configuration directive: "No milestone should be blocked because API credentials are
unavailable"). Implements the same `SportsDataProviderPort` a real adapter implements, so
swapping one for the other is invisible to callers.

Deterministic: seeded by ``competition_ref`` so repeated calls (and tests) get stable data,
matching real-provider caching behavior instead of generating fresh nonsense every call.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)

_CITY_NAMES = (
    "Riverside", "Northgate", "Eastfield", "Westbrook", "Summit", "Ashford", "Kingsport",
    "Millhaven", "Bridgeton", "Fairview", "Lakeside", "Cedarville", "Harborview", "Stonebridge",
)
_CLUB_SUFFIXES_BY_SPORT = {
    "football": ("United", "City", "Rovers", "Athletic", "Wanderers"),
    "basketball": ("Hawks", "Comets", "Titans", "Wolves", "Blazers"),
    "baseball": ("Pioneers", "Anchors", "Foxes", "Miners", "Herons"),
    "table_tennis": ("Spinners", "Smashers", "Paddlers", "Aces"),
}
_FIRST_NAMES = ("Alex", "Jordan", "Sam", "Casey", "Morgan", "Taylor", "Riley", "Drew", "Quinn", "Avery")
_LAST_NAMES = ("Carter", "Reyes", "Novak", "Singh", "Okafor", "Lindgren", "Petrov", "Silva", "Nakamura", "Haddad")
_POSITIONS_BY_SPORT = {
    "football": ("goalkeeper", "defender", "midfielder", "forward"),
    "basketball": ("point_guard", "shooting_guard", "small_forward", "power_forward", "center"),
    "baseball": ("pitcher", "catcher", "first_base", "shortstop", "left_field"),
    "table_tennis": ("singles", "doubles"),
}
_COUNTRIES = (
    ("GB", "United Kingdom"), ("US", "United States"), ("BR", "Brazil"), ("DE", "Germany"),
    ("JP", "Japan"), ("FR", "France"), ("ES", "Spain"), ("IT", "Italy"),
)


def _team_stat_set(rng: random.Random, sport_code: str) -> dict:
    generators = {
        "football": lambda: {
            "possession_pct": round(rng.uniform(35, 65), 1), "shots_total": rng.randint(5, 20),
            "shots_on_target": rng.randint(1, 10), "corners": rng.randint(0, 12), "fouls": rng.randint(5, 18),
        },
        "basketball": lambda: {
            "points": rng.randint(80, 120), "field_goals_made": rng.randint(30, 50),
            "field_goals_attempted": rng.randint(60, 90), "rebounds": rng.randint(30, 55), "turnovers": rng.randint(5, 20),
        },
        "baseball": lambda: {
            "runs": rng.randint(0, 12), "hits": rng.randint(3, 15), "errors": rng.randint(0, 3),
            "left_on_base": rng.randint(2, 10),
        },
        "table_tennis": lambda: {
            "points_won": rng.randint(40, 66), "sets_won": rng.randint(0, 4), "unforced_errors": rng.randint(2, 20),
        },
    }
    return generators.get(sport_code, generators["football"])()


@dataclass
class MockSportsDataProvider:
    provider_key: str
    sport_code: str  # matches modules.sports.domain.value_objects.SportCode.value

    def _rng(self, seed_key: str) -> random.Random:
        return random.Random(f"{self.provider_key}:{self.sport_code}:{seed_key}")

    async def fetch_teams(self, competition_ref: str) -> list[ProviderTeamRecord]:
        rng = self._rng(f"teams:{competition_ref}")
        suffixes = _CLUB_SUFFIXES_BY_SPORT.get(self.sport_code, ("Club",))
        team_count = 10
        cities = rng.sample(_CITY_NAMES, k=min(team_count, len(_CITY_NAMES)))
        teams = []
        for i, city in enumerate(cities):
            suffix = suffixes[i % len(suffixes)]
            name = f"{city} {suffix}"
            teams.append(
                ProviderTeamRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=f"{competition_ref}-team-{i}"),
                    name=name,
                    short_name=(city[:3] + suffix[:3]).upper(),
                    country="Mockland",
                    venue_name=f"{city} Stadium",
                )
            )
        return teams

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderFixtureRecord]:
        rng = self._rng(f"fixtures:{competition_ref}:{season_label}")
        teams = await self.fetch_teams(competition_ref)
        if len(teams) < 2:
            return []
        fixtures: list[ProviderFixtureRecord] = []
        base_date = datetime(2026, 8, 1, tzinfo=timezone.utc)
        # Simple single round-robin so the mock is representative without O(n^2) blow-up.
        for i in range(len(teams)):
            home = teams[i]
            away = teams[(i + 1) % len(teams)]
            if home is away:
                continue
            fixtures.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(
                        provider=self.provider_key, external_id=f"{competition_ref}-{season_label}-fx-{i}"
                    ),
                    home_team_ref=home.external_ref,
                    away_team_ref=away.external_ref,
                    scheduled_at=base_date + timedelta(days=i * 7, hours=rng.randint(0, 5)),
                    competition_ref=competition_ref,
                    season_label=season_label,
                    venue_name=home.venue_name,
                )
            )
        return fixtures

    async def fetch_countries(self) -> list[ProviderCountryRecord]:
        return [ProviderCountryRecord(code=code, name=name) for code, name in _COUNTRIES]

    async def fetch_players(self, team_ref: ProviderRef) -> list[ProviderPlayerRecord]:
        rng = self._rng(f"players:{team_ref.external_id}")
        positions = _POSITIONS_BY_SPORT.get(self.sport_code, ("player",))
        roster_size = 15
        players = []
        for i in range(roster_size):
            first = rng.choice(_FIRST_NAMES)
            last = rng.choice(_LAST_NAMES)
            players.append(
                ProviderPlayerRecord(
                    external_ref=ProviderRef(provider=self.provider_key, external_id=f"{team_ref.external_id}-player-{i}"),
                    team_ref=team_ref,
                    name=f"{first} {last}",
                    date_of_birth=datetime(2026 - rng.randint(18, 34), rng.randint(1, 12), rng.randint(1, 28), tzinfo=timezone.utc),
                    position=positions[i % len(positions)],
                )
            )
        return players

    async def fetch_standings(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderStandingRecord]:
        rng = self._rng(f"standings:{competition_ref}:{season_label}")
        teams = await self.fetch_teams(competition_ref)
        ranked = sorted(teams, key=lambda t: rng.random())
        standings = []
        points = 100
        for rank, team in enumerate(ranked, start=1):
            won = rng.randint(0, 10)
            drawn = rng.randint(0, 5)
            lost = rng.randint(0, 10)
            standings.append(
                ProviderStandingRecord(
                    team_ref=team.external_ref, rank=rank, points=float(points - rank),
                    record={"won": won, "drawn": drawn, "lost": lost},
                )
            )
        return standings

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]:
        rng = self._rng(f"team_stats:{fixture_ref.external_id}")
        return [
            ProviderTeamStatisticsRecord(
                fixture_ref=fixture_ref,
                team_ref=ProviderRef(provider=self.provider_key, external_id=f"{fixture_ref.external_id}-home"),
                stat_set=_team_stat_set(rng, self.sport_code),
            ),
            ProviderTeamStatisticsRecord(
                fixture_ref=fixture_ref,
                team_ref=ProviderRef(provider=self.provider_key, external_id=f"{fixture_ref.external_id}-away"),
                stat_set=_team_stat_set(rng, self.sport_code),
            ),
        ]

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]:
        rng = self._rng(f"lineups:{fixture_ref.external_id}")
        positions = _POSITIONS_BY_SPORT.get(self.sport_code, ("player",))
        lineups = []
        for side in ("home", "away"):
            team_ref = ProviderRef(provider=self.provider_key, external_id=f"{fixture_ref.external_id}-{side}")
            slots = []
            for i in range(11):
                slots.append(
                    ProviderLineupSlotRecord(
                        player_ref=ProviderRef(provider=self.provider_key, external_id=f"{team_ref.external_id}-player-{i}"),
                        role="starter" if i < 11 else "substitute",
                        position=positions[i % len(positions)],
                        shirt_number=i + 1,
                    )
                )
            for i in range(11, 14):
                slots.append(
                    ProviderLineupSlotRecord(
                        player_ref=ProviderRef(provider=self.provider_key, external_id=f"{team_ref.external_id}-player-{i}"),
                        role="substitute",
                        position=positions[i % len(positions)],
                        shirt_number=i + 1,
                    )
                )
            lineups.append(
                ProviderLineupRecord(
                    fixture_ref=fixture_ref, team_ref=team_ref,
                    formation="4-3-3" if self.sport_code == "football" else None,
                    slots=tuple(slots),
                )
            )
        return lineups
