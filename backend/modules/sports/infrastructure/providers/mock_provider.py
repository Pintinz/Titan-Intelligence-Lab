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
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderLineupSlotRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
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
_TYPICAL_DURATION_BY_SPORT = {
    "football": timedelta(hours=2),
    "basketball": timedelta(hours=2, minutes=30),
    "baseball": timedelta(hours=3, minutes=30),
    "table_tennis": timedelta(hours=1),
}
_COUNTRIES = (
    ("GB", "United Kingdom"), ("US", "United States"), ("BR", "Brazil"), ("DE", "Germany"),
    ("JP", "Japan"), ("FR", "France"), ("ES", "Spain"), ("IT", "Italy"),
)
_INJURY_REASONS = ("Hamstring", "Knee Injury", "Ankle Sprain", "Illness", "Muscle Strain", "Calf Injury")
_TRANSFER_TYPES = ("Loan", "Free", "Undisclosed Fee", "€8.5M", "€22M")
_COACH_FIRST_NAMES = ("Marco", "David", "Erik", "Thiago", "Klaus", "Pierre", "Hiroshi", "Carlos")
_COACH_LAST_NAMES = ("Ferreira", "Novak", "Lindqvist", "Almeida", "Bauer", "Dubois", "Tanaka", "Reyes")


def _team_stat_set(rng: random.Random, sport_code: str) -> dict:
    generators = {
        "football": lambda: {
            "possession_pct": round(rng.uniform(35, 65), 1), "shots_total": rng.randint(5, 20),
            "shots_on_target": rng.randint(1, 10), "corners": rng.randint(0, 12), "fouls": rng.randint(5, 18),
            "cards_yellow": rng.randint(0, 5), "cards_red": rng.randint(0, 1),
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

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]:
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
        self, competition_ref: str, season_label: str, now: datetime
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
            scheduled_at = base_date + timedelta(days=i * 7, hours=rng.randint(0, 5))
            fixtures.append(
                ProviderFixtureRecord(
                    external_ref=ProviderRef(
                        provider=self.provider_key, external_id=f"{competition_ref}-{season_label}-fx-{i}"
                    ),
                    home_team_ref=home.external_ref,
                    away_team_ref=away.external_ref,
                    scheduled_at=scheduled_at,
                    competition_ref=competition_ref,
                    season_label=season_label,
                    venue_name=home.venue_name,
                    status=self._mock_status(scheduled_at, now),
                )
            )
        return fixtures

    def _mock_status(self, scheduled_at: datetime, now: datetime) -> str:
        """No real live-score feed exists for the mock provider — this derives a status purely
        from real wall-clock time against the fixture's own real scheduled_at, the only genuine
        signal available, rather than fabricating a random one. Raw codes match the real
        API-Sports vocabulary so the same normalize_provider_fixture_status handles both."""
        duration = _TYPICAL_DURATION_BY_SPORT.get(self.sport_code, timedelta(hours=2))
        if scheduled_at > now:
            return "NS"
        if now - scheduled_at < duration:
            return "LIVE"
        return "FT"

    async def fetch_countries(self) -> list[ProviderCountryRecord]:
        return [ProviderCountryRecord(code=code, name=name) for code, name in _COUNTRIES]

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]:
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

    async def fetch_odds(self, fixture_ref: ProviderRef) -> ProviderOddsRecord | None:
        """Only football gets a modeled line today — the three markets that actually consume
        odds-derived features (both_teams_to_score, correct_score, match_winner) are all
        football-only. Deterministic like every other mock method: true win/draw/away strengths
        seeded from the fixture ref, scaled up by a fixed ~6% bookmaker margin so the resulting
        decimal odds land on a realistic overround rather than a fair (vig-free) line."""
        if self.sport_code != "football":
            return None
        rng = self._rng(f"odds:{fixture_ref.external_id}")
        home_strength = rng.uniform(0.28, 0.52)
        draw_strength = rng.uniform(0.18, 0.30)
        away_strength = max(0.12, 1.0 - home_strength - draw_strength)
        total_strength = home_strength + draw_strength + away_strength
        overround = 1.06

        def _odds(strength: float) -> float:
            implied_probability = (strength / total_strength) * overround
            return round(1.0 / implied_probability, 2)

        return ProviderOddsRecord(
            fixture_ref=fixture_ref,
            home_win=_odds(home_strength), draw=_odds(draw_strength), away_win=_odds(away_strength),
        )

    async def fetch_injuries(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderInjuryRecord]:
        """Deterministic, small (0-2 players) — most real squads have few or no reported
        injuries at any given moment, and an always-populated mock would misrepresent that."""
        rng = self._rng(f"injuries:{team_ref.external_id}")
        count = rng.choice([0, 0, 1, 1, 2])
        records = []
        for i in rng.sample(range(15), k=count):
            records.append(
                ProviderInjuryRecord(
                    player_ref=ProviderRef(provider=self.provider_key, external_id=f"{team_ref.external_id}-player-{i}"),
                    team_ref=team_ref,
                    status="Missing Fixture",
                    reason=rng.choice(_INJURY_REASONS),
                    reported_at=None,
                )
            )
        return records

    async def fetch_transfers(self, team_ref: ProviderRef) -> list[ProviderTransferRecord]:
        """A small, deterministic set of past transfers involving this team — mock has no
        cross-team consistency (no shared player namespace across two mock teams), so every
        transfer is modeled as this team's own roster slot moving in from an unspecified prior
        club, which is enough to exercise the real ingestion/display path without fabricating a
        misleading second team's involvement."""
        rng = self._rng(f"transfers:{team_ref.external_id}")
        count = rng.choice([0, 1, 1, 2])
        records = []
        for i in rng.sample(range(15), k=count):
            records.append(
                ProviderTransferRecord(
                    player_ref=ProviderRef(provider=self.provider_key, external_id=f"{team_ref.external_id}-player-{i}"),
                    from_team_ref=None,
                    to_team_ref=team_ref,
                    effective_date=datetime(2026, 7, rng.randint(1, 28), tzinfo=timezone.utc),
                    transfer_type=rng.choice(_TRANSFER_TYPES),
                )
            )
        return records

    async def fetch_coach(self, team_ref: ProviderRef) -> ProviderCoachRecord | None:
        rng = self._rng(f"coach:{team_ref.external_id}")
        name = f"{rng.choice(_COACH_FIRST_NAMES)} {rng.choice(_COACH_LAST_NAMES)}"
        return ProviderCoachRecord(team_ref=team_ref, person_name=name)
