"""Sports data provider gateway port (docs/architecture.md §5, Provider Adapter Pattern).

Adapters return these normalized DTOs, not raw provider payloads — no provider-specific field
name ever appears outside modules/sports/infrastructure/providers/. Resolving a
``ProviderTeamRecord``/``ProviderFixtureRecord`` into a persisted domain entity (matching it
against an existing ``Team``/``Fixture`` by ``ProviderRef``, or creating a new one) is the
ingestion pipeline's job (Milestone 5) — the gateway's only responsibility is "ask the provider,
get normalized data back," so it can be exercised and tested well before ingestion exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from modules.sports.domain.value_objects import ProviderRef


@dataclass(frozen=True)
class ProviderTeamRecord:
    external_ref: ProviderRef
    name: str
    short_name: str
    country: str | None
    venue_name: str | None = None


@dataclass(frozen=True)
class ProviderFixtureRecord:
    external_ref: ProviderRef
    home_team_ref: ProviderRef
    away_team_ref: ProviderRef
    scheduled_at: datetime
    competition_ref: str
    season_label: str
    venue_name: str | None = None


@dataclass(frozen=True)
class ProviderCountryRecord:
    code: str  # ISO 3166-1 alpha-2, e.g. "GB"
    name: str


@dataclass(frozen=True)
class ProviderPlayerRecord:
    external_ref: ProviderRef
    team_ref: ProviderRef
    name: str
    date_of_birth: datetime | None
    position: str | None


@dataclass(frozen=True)
class ProviderStandingRecord:
    team_ref: ProviderRef
    rank: int
    points: float
    record: dict  # sport-agnostic bag, e.g. {"won": 10, "drawn": 2, "lost": 1}


@dataclass(frozen=True)
class ProviderTeamStatisticsRecord:
    fixture_ref: ProviderRef
    team_ref: ProviderRef
    stat_set: dict


@dataclass(frozen=True)
class ProviderLineupSlotRecord:
    player_ref: ProviderRef
    role: str  # "starter" | "substitute" — kept a plain string here and mapped to the
    # LineupRole enum during reconciliation, so this DTO doesn't couple to that specific enum
    position: str | None = None
    shirt_number: int | None = None


@dataclass(frozen=True)
class ProviderLineupRecord:
    fixture_ref: ProviderRef
    team_ref: ProviderRef
    formation: str | None
    slots: tuple[ProviderLineupSlotRecord, ...]


class SportsDataProviderPort(Protocol):
    provider_key: str

    async def fetch_teams(self, competition_ref: str) -> list[ProviderTeamRecord]: ...

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderFixtureRecord]: ...

    async def fetch_countries(self) -> list[ProviderCountryRecord]: ...

    async def fetch_players(self, team_ref: ProviderRef) -> list[ProviderPlayerRecord]: ...

    async def fetch_standings(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderStandingRecord]: ...

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]: ...

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]: ...


class ITableTennisProvider(SportsDataProviderPort, Protocol):
    """The interface a future Table Tennis provider integration implements.

    No provider has been selected yet (docs/titaniq.md §6, docs/roadmap.md open items) — this
    exists so the domain, application, and presentation layers can be built, wired, and tested
    against ``MockTableTennisProvider`` now, and a real integration slots in later purely as a
    new class implementing this Protocol plus a provider registration + credential in the
    Provider Management System. No other layer changes when that happens.
    """
