"""POST-M24 Phase 3: pure taxonomy/registry tests — no I/O, no fakes needed. Verifies the
football/basketball/baseball capability matrices against the same source-code facts the registry
itself cites, and that table tennis has no real-provider entry."""

from __future__ import annotations

from modules.sports.domain.provider_capabilities import (
    PROVIDER_CAPABILITIES,
    ProviderDomain,
    SourceRole,
    TemporalMode,
    providers_for_sport,
)
from modules.sports.domain.value_objects import SportCode


# -- Football matrix -----------------------------------------------------------------------------


def test_api_football_supports_every_real_domain():
    caps = PROVIDER_CAPABILITIES["api_football"]
    for domain in (
        ProviderDomain.TEAMS, ProviderDomain.FIXTURES, ProviderDomain.COUNTRIES, ProviderDomain.PLAYERS,
        ProviderDomain.STANDINGS, ProviderDomain.TEAM_STATISTICS, ProviderDomain.LINEUPS,
        ProviderDomain.ODDS, ProviderDomain.INJURIES, ProviderDomain.TRANSFERS, ProviderDomain.COACHING_STAFF,
    ):
        assert caps.supports_domain(domain), f"api_football should support {domain}"


def test_api_football_has_no_dedicated_results_endpoint():
    # No fetch_completed_fixtures anywhere in api_sports_adapter.py — historical data comes
    # through the general fetch_fixtures + HISTORICAL temporal mode instead.
    assert not PROVIDER_CAPABILITIES["api_football"].supports_domain(ProviderDomain.RESULTS)


def test_api_football_supports_every_temporal_mode():
    caps = PROVIDER_CAPABILITIES["api_football"]
    for mode in TemporalMode:
        assert caps.supports_temporal_mode(mode), f"api_football should support {mode}"


def test_api_football_is_primary_and_enrichment_role():
    caps = PROVIDER_CAPABILITIES["api_football"]
    assert caps.supports_source_role(SourceRole.PRIMARY)
    assert caps.supports_source_role(SourceRole.ENRICHMENT)
    assert not caps.supports_source_role(SourceRole.HISTORICAL)


def test_football_data_org_lacks_enrichment_domains():
    caps = PROVIDER_CAPABILITIES["football_data_org"]
    for domain in (ProviderDomain.ODDS, ProviderDomain.INJURIES, ProviderDomain.TRANSFERS, ProviderDomain.LINEUPS, ProviderDomain.COACHING_STAFF):
        assert not caps.supports_domain(domain)
    assert caps.supports_domain(ProviderDomain.RESULTS)  # its one distinguishing real method
    assert not caps.supports_temporal_mode(TemporalMode.LIVE)
    assert not caps.supports_temporal_mode(TemporalMode.PRE_MATCH)
    assert caps.fixture_schedule_scoped is True


def test_thesportsdb_matches_football_data_org_shape():
    caps = PROVIDER_CAPABILITIES["thesportsdb"]
    assert caps.supports_domain(ProviderDomain.RESULTS)
    assert not caps.supports_domain(ProviderDomain.ODDS)
    assert caps.fixture_schedule_scoped is True
    assert caps.supports_source_role(SourceRole.FALLBACK)


def test_football_providers_for_sport_returns_all_three():
    keys = {caps.provider_key for caps in providers_for_sport(SportCode.FOOTBALL)}
    assert keys == {"api_football", "football_data_org", "thesportsdb"}


# -- Basketball matrix ----------------------------------------------------------------------------


def test_api_basketball_supports_core_domains_only():
    caps = PROVIDER_CAPABILITIES["api_basketball"]
    for domain in (ProviderDomain.TEAMS, ProviderDomain.PLAYERS, ProviderDomain.FIXTURES, ProviderDomain.STANDINGS, ProviderDomain.TEAM_STATISTICS, ProviderDomain.COUNTRIES):
        assert caps.supports_domain(domain)
    for domain in (ProviderDomain.LINEUPS, ProviderDomain.ODDS, ProviderDomain.INJURIES, ProviderDomain.TRANSFERS, ProviderDomain.COACHING_STAFF, ProviderDomain.RESULTS):
        assert not caps.supports_domain(domain), f"api_basketball should NOT claim {domain} (stub/no method)"


def test_api_basketball_supports_live_but_not_pre_match():
    caps = PROVIDER_CAPABILITIES["api_basketball"]
    assert caps.supports_temporal_mode(TemporalMode.LIVE)
    assert caps.supports_temporal_mode(TemporalMode.HISTORICAL)
    assert not caps.supports_temporal_mode(TemporalMode.PRE_MATCH)


def test_api_basketball_is_primary_only():
    caps = PROVIDER_CAPABILITIES["api_basketball"]
    assert caps.source_roles == frozenset({SourceRole.PRIMARY})


# -- Baseball matrix ------------------------------------------------------------------------------


def test_api_baseball_matches_basketball_shape():
    caps = PROVIDER_CAPABILITIES["api_baseball"]
    assert caps.supports_domain(ProviderDomain.TEAM_STATISTICS)
    assert not caps.supports_domain(ProviderDomain.LINEUPS)
    assert caps.supports_temporal_mode(TemporalMode.LIVE)
    assert not caps.supports_temporal_mode(TemporalMode.PRE_MATCH)
    assert caps.source_roles == frozenset({SourceRole.PRIMARY})


# -- Table tennis: no real provider ----------------------------------------------------------------


def test_table_tennis_has_no_registered_provider():
    assert providers_for_sport(SportCode.TABLE_TENNIS) == ()
    assert all(caps.sport is not SportCode.TABLE_TENNIS for caps in PROVIDER_CAPABILITIES.values())


def test_no_current_provider_claims_the_taxonomy_only_domains():
    """MATCH_EVENTS/PLAYER_STATISTICS exist in the enum for taxonomy completeness but no current
    adapter implements a corresponding fetch method — no registered provider should claim them."""
    for caps in PROVIDER_CAPABILITIES.values():
        assert not caps.supports_domain(ProviderDomain.MATCH_EVENTS)
        assert not caps.supports_domain(ProviderDomain.PLAYER_STATISTICS)


def test_no_current_provider_has_historical_only_source_role():
    """HISTORICAL source role is reserved for a future offline-only source (e.g. a Kaggle
    importer, Phase 4+) — every current provider is a live/operational one, even though several
    also happen to serve historical data as one of several temporal modes."""
    for caps in PROVIDER_CAPABILITIES.values():
        assert not caps.supports_source_role(SourceRole.HISTORICAL)


def test_taxonomy_can_represent_a_future_historical_only_source_without_registering_one():
    """Proves the taxonomy is Phase-4-ready without implementing anything Kaggle-related: a
    hypothetical historical-only source can be constructed and correctly queried, entirely outside
    `PROVIDER_CAPABILITIES` (never registered as real)."""
    from modules.sports.domain.provider_capabilities import ProviderCapabilities

    hypothetical = ProviderCapabilities(
        provider_key="hypothetical_historical_football",
        sport=SportCode.FOOTBALL,
        domains=frozenset({ProviderDomain.FIXTURES, ProviderDomain.RESULTS}),
        temporal_modes=frozenset({TemporalMode.HISTORICAL}),
        source_roles=frozenset({SourceRole.HISTORICAL}),
    )

    assert hypothetical.supports_source_role(SourceRole.HISTORICAL)
    assert not hypothetical.supports_temporal_mode(TemporalMode.LIVE)
    assert not hypothetical.supports_temporal_mode(TemporalMode.PRE_MATCH)
    assert "hypothetical_historical_football" not in PROVIDER_CAPABILITIES  # never actually registered
