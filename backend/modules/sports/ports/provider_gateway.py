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
    logo_url: str | None = None
    # An exact-identity claim from the provider itself that this team is the same real-world club
    # as another provider's own team id — e.g. TheSportsDB embeds each team's api-football id
    # directly (`idAPIfootball`), verified live (2026-08-10). Deterministic, so
    # EntityReconciliationService.reconcile_team auto-merges into that existing team rather than
    # creating a duplicate, unlike CrossProviderTeamMappingService's name-fuzzy suggestions (which
    # stay admin-confirmed since a name match is a guess, not a claim). None for every adapter
    # that doesn't have this signal — safe default, no behavior change for existing callers.
    cross_provider_ref: ProviderRef | None = None


@dataclass(frozen=True)
class ProviderFixtureRecord:
    external_ref: ProviderRef
    home_team_ref: ProviderRef
    away_team_ref: ProviderRef
    scheduled_at: datetime
    competition_ref: str
    season_label: str
    venue_name: str | None = None
    # Raw provider status code (e.g. API-Sports' "NS"/"1H"/"FT"/"PST"/"CANC" family, shared across
    # its football/basketball/baseball products) — normalized into FixtureStatus by
    # modules.sports.domain.contracts.fixture.normalize_provider_fixture_status, not here, so the
    # gateway stays a thin "ask the provider, get normalized-shape data back" layer per this
    # file's own docstring. None means the provider didn't report a status (reconciliation keeps
    # whatever status the fixture already has).
    status: str | None = None
    # Final score, when the provider has reported one (typically once status is finished). None
    # for a fixture that hasn't been played yet, or whose provider doesn't report goals.
    home_score: int | None = None
    away_score: int | None = None
    # Period-by-period score breakdown, when the provider reports one (basketball quarters,
    # baseball innings) — {"kind": "quarter"|"inning", "home": [...], "away": [...]}. None for
    # football (not fetched) or before the provider has reported any periods.
    period_scores: dict | None = None


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
    photo_url: str | None = None


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
class ProviderOddsRecord:
    """One fixture's pre-match win-market odds, decimal format (> 1.0). ``draw`` is ``None``
    for a sport with no draw outcome (basketball, baseball, table tennis) — only football
    populates it today. At least one of the three is present whenever a real record is
    returned; ``fetch_odds`` returns ``None`` entirely rather than an all-``None`` record when
    a provider has no line for this fixture yet."""

    fixture_ref: ProviderRef
    home_win: float | None = None
    draw: float | None = None
    away_win: float | None = None


@dataclass(frozen=True)
class ProviderMarketLineRecord:
    """POST-M24 Phase 6 — one real, normalized sportsbook quote for one fixture, the canonical
    read-path shape `fetch_market_lines` returns (distinct from `ProviderOddsRecord`, which stays
    football's own moneyline-only DTO backing its already-working odds-feature pipeline —
    deliberately not touched or replaced this phase).

    Fields mirror `modules.sports.domain.entities.MarketLine` exactly (`market_type`/`selection`/
    `line`/`price`/`bookmaker`/`observed_at`) so reconciliation is a straight field copy, no
    provider-specific shape ever crossing into the domain layer. `line` is `None` for a
    moneyline quote."""

    fixture_ref: ProviderRef
    bookmaker: str
    market_type: str  # mirrors MarketLineType's string values — kept a plain string at the port
    # boundary so this DTO has no dependency on the domain enum
    selection: str
    line: float | None
    price: float
    observed_at: datetime | None = None


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


@dataclass(frozen=True)
class ProviderInjuryRecord:
    """One player's reported unavailability. ``status``/``reason`` are the provider's own raw
    text (e.g. API-Football's ``player.type``/``player.reason`` — "Missing Fixture"/"Hamstring")
    — no normalized enum, since the real states a provider reports don't map cleanly onto one.
    No expected-return date: no connected provider reports one, so it is never fabricated here."""

    player_ref: ProviderRef
    team_ref: ProviderRef
    status: str
    reason: str | None = None
    reported_at: datetime | None = None


@dataclass(frozen=True)
class ProviderTransferRecord:
    """A confirmed transfer only. ``transfer_type`` is the provider's raw fee/type text (e.g.
    "Loan", "Free", "€25.5M") — not parsed into a numeric fee, since providers report it in
    wildly inconsistent formats. ``from_team_ref``/``to_team_ref`` are ``None`` when the
    provider itself doesn't report that side (e.g. a free agent signing with no "from" club)."""

    player_ref: ProviderRef
    from_team_ref: ProviderRef | None
    to_team_ref: ProviderRef | None
    effective_date: datetime
    transfer_type: str | None = None


@dataclass(frozen=True)
class ProviderCoachRecord:
    team_ref: ProviderRef
    person_name: str
    role: str = "head_coach"


class SportsDataProviderPort(Protocol):
    provider_key: str

    async def fetch_teams(self, competition_ref: str, season_label: str | None = None) -> list[ProviderTeamRecord]: ...

    async def fetch_fixtures(
        self, competition_ref: str, season_label: str, now: datetime
    ) -> list[ProviderFixtureRecord]: ...

    async def fetch_countries(self) -> list[ProviderCountryRecord]: ...

    async def fetch_players(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderPlayerRecord]: ...

    async def fetch_standings(
        self, competition_ref: str, season_label: str
    ) -> list[ProviderStandingRecord]: ...

    async def fetch_team_statistics(self, fixture_ref: ProviderRef) -> list[ProviderTeamStatisticsRecord]: ...

    async def fetch_lineups(self, fixture_ref: ProviderRef) -> list[ProviderLineupRecord]: ...

    async def fetch_odds(self, fixture_ref: ProviderRef) -> ProviderOddsRecord | None:
        """Pre-match win-market odds for one fixture, or ``None`` if the provider has no line
        for it yet (fixture too far out, market not offered, etc.) — a real absence, not an
        error, matching ``fetch_lineups``' "no data source yet" contract for the sports that
        genuinely don't have one."""
        ...

    async def fetch_injuries(self, team_ref: ProviderRef, season_label: str | None = None) -> list[ProviderInjuryRecord]:
        """Every player currently reported unavailable for this team. Empty list is the honest,
        common case (most teams have no reported injuries at any given moment) — never an
        error."""
        ...

    async def fetch_transfers(self, team_ref: ProviderRef) -> list[ProviderTransferRecord]:
        """Confirmed transfers involving this team, in and out. See
        ``ProviderTransferRecord``'s own docstring for why there is no rumour/negotiating
        staging here."""
        ...

    async def fetch_coach(self, team_ref: ProviderRef) -> ProviderCoachRecord | None:
        """This team's current head coach/manager, or ``None`` if the provider has no record for
        it — never fabricated."""
        ...


class ITableTennisProvider(SportsDataProviderPort, Protocol):
    """The interface a future Table Tennis provider integration implements.

    No provider has been selected yet (docs/titaniq.md §6, docs/roadmap.md open items) — this
    exists so the domain, application, and presentation layers can be built, wired, and tested
    against ``MockTableTennisProvider`` now, and a real integration slots in later purely as a
    new class implementing this Protocol plus a provider registration + credential in the
    Provider Management System. No other layer changes when that happens.
    """
