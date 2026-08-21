"""Provider capability taxonomy (POST-M24 Phase 3 "Provider Capabilities & Source
Orchestration"). Answers "what can this provider supply" — sport, data domain, temporal mode,
source role — as a declarative, read-only contract, separate from HOW a provider is called
(that remains `SportsDataProviderPort`/the concrete adapters, untouched by this module).

Every entry in `PROVIDER_CAPABILITIES` below is derived directly from what the corresponding
adapter class in `modules.sports.infrastructure.providers.*` actually implements — verified by
reading each adapter's real method overrides (`api_sports_adapter.py`,
`football_data_org_adapter.py`, `thesportsdb_adapter.py`) and the Celery Beat schedule
(`modules.ingestion.infrastructure.celery.beat_schedule.BEAT_SCHEDULE`) for which sports/leagues
actually exercise LIVE and PRE_MATCH sync in production today — never guessed. A domain/temporal
mode is included for a provider only when a real, non-stub code path proves it; a stubbed method
(e.g. `ApiBasketballAdapter.fetch_lineups` returning `[]`, or `_ApiSportsHttpAdapterBase`'s base
`fetch_odds`/`fetch_injuries`/`fetch_transfers`/`fetch_coach` returning empty/`None`) is correctly
absent, not marked "unsupported" via a special value — absence from the `domains`/`temporal_modes`
frozensets *is* "not supported."

Table tennis has no real provider today (`PROVIDER_KEY_BY_SPORT` in `apps/api/composition.py` has
no entry for it) — deliberately absent from `PROVIDER_CAPABILITIES` rather than represented with a
fabricated entry. `CapabilityResolver.has_real_provider(SportCode.TABLE_TENNIS)` returns `False`.

Capability != provenance != current availability. `supports_temporal_mode(provider, LIVE) == True`
means the provider is *capable* of supplying live data, not that live data is available right now
(that's `CircuitBreaker`/`QuotaIntelligenceEngine`'s job, unchanged from Phase 2) — and it never
implies anything about `SyncTrigger`/`VERIFIED_PRE_MATCH` provenance, which remains governed
exclusively by `modules.ingestion.application.provenance.classify_availability` (untouched).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.sports.domain.value_objects import SportCode


class ProviderDomain(str, Enum):
    """Mirrors `SportsDataProviderPort`'s real method surface, plus the two request-scoping
    concepts (`COMPETITIONS`/`SEASONS`) every one of those methods is already parameterized by.
    `MATCH_EVENTS`/`PLAYER_STATISTICS` are included for taxonomy completeness (the master
    prompt's minimum vocabulary) even though no current adapter implements a corresponding fetch
    method — no provider's `domains` set ever includes them today, which is the honest answer,
    not an omission."""

    COMPETITIONS = "competitions"
    SEASONS = "seasons"
    COUNTRIES = "countries"
    TEAMS = "teams"
    PLAYERS = "players"
    FIXTURES = "fixtures"  # general fetch_fixtures — covers upcoming AND historical, see TemporalMode
    RESULTS = "results"  # a *dedicated* fetch_completed_fixtures endpoint (only the two
    # fixture-schedule-role adapters have one) — distinct from FIXTURES+HISTORICAL, which is
    # "past fixtures via the same general method," a capability the primary per-sport adapters do
    # have (confirmed: dev.db's 1,708 real basketball / 3,923 real baseball fixtures were
    # populated via the ordinary fetch_fixtures, proving it already returns historical data).
    STANDINGS = "standings"
    MATCH_EVENTS = "match_events"  # taxonomy-only — no adapter implements this today
    TEAM_STATISTICS = "team_statistics"
    PLAYER_STATISTICS = "player_statistics"  # taxonomy-only — no adapter implements this today
    LINEUPS = "lineups"
    ODDS = "odds"
    INJURIES = "injuries"
    TRANSFERS = "transfers"
    COACHING_STAFF = "coaching_staff"


class TemporalMode(str, Enum):
    HISTORICAL = "historical"
    UPCOMING = "upcoming"
    LIVE = "live"
    PRE_MATCH = "pre_match"
    POST_MATCH = "post_match"


class SourceRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    FALLBACK = "fallback"
    ENRICHMENT = "enrichment"
    HISTORICAL = "historical"


@dataclass(frozen=True)
class ProviderCapabilities:
    """Immutable, code-declared (not database-backed — see Phase 3 report §20 for why) capability
    contract for one provider. `fixture_schedule_scoped=True` marks a provider that only ever
    serves via `SportsProviderRouter.fixture_schedule_adapters` — an explicit, per-competition
    admin opt-in (`CompetitionFixtureSourcePreference`), never a sport's default adapter — which
    is exactly how `CapabilityResolver.supports_competition` decides whether such a provider is
    eligible for a *specific* competition (see that module)."""

    provider_key: str
    sport: SportCode
    domains: frozenset[ProviderDomain]
    temporal_modes: frozenset[TemporalMode]
    source_roles: frozenset[SourceRole]
    fixture_schedule_scoped: bool = False

    def supports_domain(self, domain: ProviderDomain) -> bool:
        return domain in self.domains

    def supports_temporal_mode(self, mode: TemporalMode) -> bool:
        return mode in self.temporal_modes

    def supports_source_role(self, role: SourceRole) -> bool:
        return role in self.source_roles


_FOOTBALL_CORE_DOMAINS = frozenset({
    ProviderDomain.COMPETITIONS, ProviderDomain.SEASONS, ProviderDomain.TEAMS, ProviderDomain.FIXTURES,
    ProviderDomain.STANDINGS,
})

PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    # ApiFootballAdapter overrides all 12 SportsDataProviderPort methods with real HTTP calls
    # (verified: modules/sports/infrastructure/providers/api_sports_adapter.py lines 184-448) —
    # the only provider with real odds/injuries/transfers/lineups/coach data, which is exactly why
    # it's the sole real ENRICHMENT-role source (LineupContinuityCalculator/TransferActivityCalculator
    # consume precisely this data). No dedicated completed-fixtures endpoint (no RESULTS domain) —
    # historical fixtures come through the general FIXTURES method + HISTORICAL temporal mode
    # instead. LIVE confirmed by Beat's "sync-live-fixtures-football-epl" entry; PRE_MATCH confirmed
    # by Beat's "sync-upcoming-structured-intelligence-football-epl" (the only real
    # LIVE_SCHEDULED-provenance path, football/EPL-scoped).
    "api_football": ProviderCapabilities(
        provider_key="api_football", sport=SportCode.FOOTBALL,
        domains=_FOOTBALL_CORE_DOMAINS | frozenset({
            ProviderDomain.COUNTRIES, ProviderDomain.PLAYERS, ProviderDomain.TEAM_STATISTICS,
            ProviderDomain.LINEUPS, ProviderDomain.ODDS, ProviderDomain.INJURIES,
            ProviderDomain.TRANSFERS, ProviderDomain.COACHING_STAFF,
        }),
        temporal_modes=frozenset({
            TemporalMode.HISTORICAL, TemporalMode.UPCOMING, TemporalMode.LIVE,
            TemporalMode.PRE_MATCH, TemporalMode.POST_MATCH,
        }),
        source_roles=frozenset({SourceRole.PRIMARY, SourceRole.ENRICHMENT}),
    ),
    # FootballDataOrgAdapter: real teams/fixtures/completed_fixtures/standings only (verified:
    # football_data_org_adapter.py) — every other method's own docstring says "stays
    # api-football's job by design." Only ever reached via `fixture_schedule_adapters`
    # (`CompetitionFixtureSourcePreference` opt-in), never a sport's default — hence
    # `fixture_schedule_scoped=True`. No LIVE (no live-specific method or Beat entry), no
    # PRE_MATCH (no lineups/injuries/transfers).
    "football_data_org": ProviderCapabilities(
        provider_key="football_data_org", sport=SportCode.FOOTBALL,
        domains=_FOOTBALL_CORE_DOMAINS | frozenset({ProviderDomain.RESULTS}),
        temporal_modes=frozenset({TemporalMode.HISTORICAL, TemporalMode.UPCOMING, TemporalMode.POST_MATCH}),
        source_roles=frozenset({SourceRole.SECONDARY, SourceRole.FALLBACK}),
        fixture_schedule_scoped=True,
    ),
    # TheSportsDbAdapter: identical real-method shape to football_data_org (verified:
    # thesportsdb_adapter.py) — same fixture-schedule-scoped, secondary/fallback role.
    "thesportsdb": ProviderCapabilities(
        provider_key="thesportsdb", sport=SportCode.FOOTBALL,
        domains=_FOOTBALL_CORE_DOMAINS | frozenset({ProviderDomain.RESULTS}),
        temporal_modes=frozenset({TemporalMode.HISTORICAL, TemporalMode.UPCOMING, TemporalMode.POST_MATCH}),
        source_roles=frozenset({SourceRole.SECONDARY, SourceRole.FALLBACK}),
        fixture_schedule_scoped=True,
    ),
    # ApiBasketballAdapter: real teams/fixtures/players/standings/team_statistics (verified:
    # api_sports_adapter.py lines 449-606); fetch_lineups explicitly stubbed (`return []`, own
    # docstring: "does not expose a dedicated pre-match lineup endpoint"); odds/injuries/
    # transfers/coach inherited from the base class's stubs (never overridden) — so none of
    # LINEUPS/ODDS/INJURIES/TRANSFERS/COACHING_STAFF/PRE_MATCH are claimed. COUNTRIES is real
    # (inherited from the base class's *shared, real* `/countries` implementation, not overridden
    # because it doesn't need to be). LIVE confirmed by Beat's "sync-live-fixtures-basketball-nba"/
    # "-euroleague" entries. No RESULTS (no dedicated completed-fixtures method) — historical
    # basketball data (1,708 real fixtures in dev.db) comes through general FIXTURES + HISTORICAL.
    "api_basketball": ProviderCapabilities(
        provider_key="api_basketball", sport=SportCode.BASKETBALL,
        domains=frozenset({
            ProviderDomain.COMPETITIONS, ProviderDomain.SEASONS, ProviderDomain.COUNTRIES,
            ProviderDomain.TEAMS, ProviderDomain.PLAYERS, ProviderDomain.FIXTURES,
            ProviderDomain.STANDINGS, ProviderDomain.TEAM_STATISTICS,
        }),
        temporal_modes=frozenset({TemporalMode.HISTORICAL, TemporalMode.UPCOMING, TemporalMode.LIVE, TemporalMode.POST_MATCH}),
        source_roles=frozenset({SourceRole.PRIMARY}),
    ),
    # ApiBaseballAdapter: identical real-method shape to ApiBasketballAdapter (verified:
    # api_sports_adapter.py lines 607-750). LIVE confirmed by Beat's
    # "sync-live-fixtures-baseball-mlb"/"-npb" entries.
    "api_baseball": ProviderCapabilities(
        provider_key="api_baseball", sport=SportCode.BASEBALL,
        domains=frozenset({
            ProviderDomain.COMPETITIONS, ProviderDomain.SEASONS, ProviderDomain.COUNTRIES,
            ProviderDomain.TEAMS, ProviderDomain.PLAYERS, ProviderDomain.FIXTURES,
            ProviderDomain.STANDINGS, ProviderDomain.TEAM_STATISTICS,
        }),
        temporal_modes=frozenset({TemporalMode.HISTORICAL, TemporalMode.UPCOMING, TemporalMode.LIVE, TemporalMode.POST_MATCH}),
        source_roles=frozenset({SourceRole.PRIMARY}),
    ),
    # Table tennis: deliberately absent. No real provider is registered anywhere in
    # `apps/api/composition.py` (`PROVIDER_KEY_BY_SPORT` has no "table_tennis" key) — see
    # `CapabilityResolver.has_real_provider`.
}


def providers_for_sport(sport: SportCode) -> tuple[ProviderCapabilities, ...]:
    """Every registered provider's capabilities for a sport, in no particular order — callers
    wanting a prioritized order use `SourceSelectionService`, which additionally applies health/
    quota/configuration filtering this pure lookup deliberately does not."""
    return tuple(caps for caps in PROVIDER_CAPABILITIES.values() if caps.sport is sport)
