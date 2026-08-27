from datetime import datetime, timezone

import pytest

from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.domain.value_objects import EdgeType, NodeType
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.fixture
def service(sqlite_session):
    return KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=sqlite_session),
        edges=SqlAlchemyKGEdgeRepository(session=sqlite_session),
    )


@pytest.mark.asyncio
async def test_upsert_node_is_idempotent_by_type_and_ref(service):
    first = await service.upsert_node(NodeType.TEAM, "team-1", {"name": "Arsenal"})
    second = await service.upsert_node(NodeType.TEAM, "team-1", {"name": "Arsenal FC"})

    assert first.id == second.id
    assert second.attributes["name"] == "Arsenal FC"


@pytest.mark.asyncio
async def test_upsert_edge_is_idempotent_and_updates_attributes(service):
    team = await service.upsert_node(NodeType.TEAM, "team-1")
    competition = await service.upsert_node(NodeType.COMPETITION, "comp-1")

    first = await service.upsert_edge(team, competition, EdgeType.COMPETES_IN, T0, attributes={"rank": 3})
    second = await service.upsert_edge(team, competition, EdgeType.COMPETES_IN, T0, attributes={"rank": 1})

    assert first.id == second.id
    assert second.attributes["rank"] == 1
    # SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — compare the
    # naive wall-clock value to confirm valid_from was preserved from creation, not overwritten.
    assert second.valid_from.replace(tzinfo=timezone.utc) == T0


@pytest.mark.asyncio
async def test_populate_competition_links_to_sport(service):
    competition_node = await service.populate_competition("comp-1", "football", T0, name="Premier League")

    edges = await service.edges.list_from(competition_node.id, EdgeType.BELONGS_TO)
    assert len(edges) == 1
    sport_node = await service.nodes.get(edges[0].to_node_id)
    assert sport_node.node_type is NodeType.SPORT
    assert sport_node.entity_ref == "football"


@pytest.mark.asyncio
async def test_populate_team_links_sport_and_country(service):
    team_node = await service.populate_team("team-1", "football", T0, name="Arsenal", country_id="GB")

    belongs_to = await service.edges.list_from(team_node.id, EdgeType.BELONGS_TO)
    located_in = await service.edges.list_from(team_node.id, EdgeType.LOCATED_IN)

    assert len(belongs_to) == 1
    assert len(located_in) == 1
    country_node = await service.nodes.get(located_in[0].to_node_id)
    assert country_node.node_type is NodeType.COUNTRY
    assert country_node.entity_ref == "GB"


@pytest.mark.asyncio
async def test_populate_team_without_country_skips_located_in_edge(service):
    team_node = await service.populate_team("team-1", "football", T0)

    located_in = await service.edges.list_from(team_node.id, EdgeType.LOCATED_IN)
    assert located_in == []


@pytest.mark.asyncio
async def test_populate_player_links_team_and_sport(service):
    player_node = await service.populate_player("player-1", "football", T0, team_id="team-1", name="Alex Carter")

    plays_for = await service.edges.list_from(player_node.id, EdgeType.PLAYS_FOR)
    belongs_to = await service.edges.list_from(player_node.id, EdgeType.BELONGS_TO)

    assert len(plays_for) == 1
    assert len(belongs_to) == 1


@pytest.mark.asyncio
async def test_populate_fixture_links_both_teams_and_venue(service):
    match_node = await service.populate_fixture("fx-1", "team-1", "team-2", T0, venue_id="venue-1")

    home_edges = await service.edges.list_to(match_node.id, EdgeType.INVOLVED_IN)
    scheduled = await service.edges.list_from(match_node.id, EdgeType.SCHEDULED_AT)

    assert len(home_edges) == 2
    sides = {e.attributes["side"] for e in home_edges}
    assert sides == {"home", "away"}
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_populate_fixture_without_venue_skips_scheduled_at(service):
    match_node = await service.populate_fixture("fx-1", "team-1", "team-2", T0)

    scheduled = await service.edges.list_from(match_node.id, EdgeType.SCHEDULED_AT)
    assert scheduled == []


@pytest.mark.asyncio
async def test_populate_team_statistics_links_match_and_team(service):
    stats_node = await service.populate_team_statistics("fx-1", "team-1", T0)

    derived_from = await service.edges.list_from(stats_node.id, EdgeType.DERIVED_FROM)
    assert len(derived_from) == 2


@pytest.mark.asyncio
async def test_populate_standing_stores_rank_and_points_on_edge(service):
    await service.populate_standing("team-1", "season-1", T0, rank=2, points=45.0)

    team_node = await service.nodes.get_by_entity_ref(NodeType.TEAM, "team-1")
    edges = await service.edges.list_from(team_node.id, EdgeType.COMPETES_IN)

    assert len(edges) == 1
    assert edges[0].attributes == {"rank": 2, "points": 45.0}


class TestPopulateWritesAliases:
    """Entity-resolution audit fix (2026-08-27): every `populate_*` wrapper that accepts a real
    `name` used to write it into `attributes["name"]` but never into `aliases` — the field
    `EntityResolutionService.find_by_alias` exclusively searches when resolving a free-text news
    mention against the graph. Confirmed live: every real TEAM/PLAYER node in dev.db had
    `aliases == []` despite a correct `attributes["name"]`, so a completely accurate news mention
    like "Manchester City" could never resolve. These tests pin the fix at the write path."""

    async def test_populate_team_writes_name_into_aliases(self, service):
        team_node = await service.populate_team("team-1", "football", T0, name="Arsenal")
        assert team_node.aliases == ["Arsenal"]

    async def test_populate_player_writes_name_into_aliases(self, service):
        player_node = await service.populate_player("player-1", "football", T0, name="Alex Carter")
        assert player_node.aliases == ["Alex Carter"]

    async def test_populate_venue_writes_name_into_aliases(self, service):
        venue_node = await service.populate_venue("venue-1", T0, name="Emirates Stadium")
        assert venue_node.aliases == ["Emirates Stadium"]

    async def test_populate_competition_writes_name_into_aliases(self, service):
        competition_node = await service.populate_competition("comp-1", "football", T0, name="Premier League")
        assert competition_node.aliases == ["Premier League"]

    async def test_populate_organization_writes_name_into_aliases(self, service):
        org_node = await service.populate_organization("org-1", T0, name="Nike")
        assert org_node.aliases == ["Nike"]

    async def test_populate_country_writes_name_into_aliases(self, service):
        country_node = await service.populate_country("GB", T0, code="GB", name="United Kingdom")
        assert country_node.aliases == ["United Kingdom"]

    async def test_populate_sport_writes_name_into_aliases(self, service):
        sport_node = await service.populate_sport("football", T0, name="Football")
        assert sport_node.aliases == ["Football"]

    async def test_populate_team_without_name_leaves_aliases_empty(self, service):
        """No fabricated alias when no real name was ever supplied."""
        team_node = await service.populate_team("team-1", "football", T0)
        assert team_node.aliases == []

    async def test_repeated_calls_with_the_same_name_do_not_duplicate_the_alias(self, service):
        await service.populate_team("team-1", "football", T0, name="Arsenal")
        second = await service.populate_team("team-1", "football", T0, name="Arsenal")
        assert second.aliases == ["Arsenal"]

    async def test_a_renamed_entity_accumulates_both_names_as_aliases(self, service):
        """A team's canonical name changing (e.g. a provider correction) must not lose the old
        alias — a news article published under the old name should still resolve."""
        await service.populate_team("team-1", "football", T0, name="Arsenal")
        second = await service.populate_team("team-1", "football", T0, name="Arsenal FC")
        assert second.aliases == ["Arsenal", "Arsenal FC"]

    async def test_backfilled_alias_makes_a_real_news_mention_resolvable(self, service, sqlite_session):
        """End-to-end proof, not just an isolated field assertion: after `populate_team` writes
        the alias, `EntityResolutionService.find_by_alias` — the exact lookup
        `EntityExtractionService.extract_and_link` uses to resolve a free-text news mention like
        "Manchester City" — actually finds the node. This is the concrete defect that made every
        genuinely Gemini-extracted `NewsEvent` in dev.db resolve zero entities before this fix."""
        from modules.knowledge_graph.application.entity_resolution_service import EntityResolutionService

        team_node = await service.populate_team("team-1", "football", T0, name="Manchester City")

        resolver = EntityResolutionService(nodes=service.nodes, edges=service.edges, population=service)
        matches = await resolver.find_by_alias(NodeType.TEAM, "Manchester City")

        assert [m.id for m in matches] == [team_node.id]


@pytest.mark.asyncio
async def test_populate_venue_links_country(service):
    venue_node = await service.populate_venue("venue-1", T0, name="Anfield", country_id="GB")

    located_in = await service.edges.list_from(venue_node.id, EdgeType.LOCATED_IN)
    assert len(located_in) == 1
    country_node = await service.nodes.get(located_in[0].to_node_id)
    assert country_node.entity_ref == "GB"


@pytest.mark.asyncio
async def test_populate_venue_without_country_skips_located_in_edge(service):
    venue_node = await service.populate_venue("venue-1", T0)

    located_in = await service.edges.list_from(venue_node.id, EdgeType.LOCATED_IN)
    assert located_in == []


@pytest.mark.asyncio
async def test_populate_team_competition_links_team_and_competition(service):
    await service.populate_team_competition("team-1", "comp-1", T0)

    team_node = await service.nodes.get_by_entity_ref(NodeType.TEAM, "team-1")
    edges = await service.edges.list_from(team_node.id, EdgeType.COMPETES_IN)
    assert len(edges) == 1


# -- M6 business entities: organizations/users/subscriptions/providers ------------------------


@pytest.mark.asyncio
async def test_populate_organization(service):
    org_node = await service.populate_organization("org-1", T0, name="Acme Sports")

    assert org_node.node_type is NodeType.ORGANIZATION
    assert org_node.attributes["name"] == "Acme Sports"


@pytest.mark.asyncio
async def test_populate_user(service):
    user_node = await service.populate_user("user-1", T0, email="owner@example.com")

    assert user_node.node_type is NodeType.USER
    assert user_node.attributes["email"] == "owner@example.com"


@pytest.mark.asyncio
async def test_populate_subscription_links_to_organization(service):
    subscription_node = await service.populate_subscription(
        "sub-1", "organization", "org-1", T0, plan_key="premium"
    )

    assert subscription_node.attributes["plan_key"] == "premium"
    edges = await service.edges.list_from(subscription_node.id, EdgeType.BELONGS_TO)
    assert len(edges) == 1
    subject_node = await service.nodes.get(edges[0].to_node_id)
    assert subject_node.node_type is NodeType.ORGANIZATION


@pytest.mark.asyncio
async def test_populate_subscription_links_to_user_when_subject_is_not_organization(service):
    subscription_node = await service.populate_subscription("sub-1", "user", "user-1", T0)

    edges = await service.edges.list_from(subscription_node.id, EdgeType.BELONGS_TO)
    subject_node = await service.nodes.get(edges[0].to_node_id)
    assert subject_node.node_type is NodeType.USER


@pytest.mark.asyncio
async def test_populate_provider(service):
    provider_node = await service.populate_provider("provider-1", T0, key="api_football")

    assert provider_node.node_type is NodeType.PROVIDER
    assert provider_node.attributes["key"] == "api_football"
