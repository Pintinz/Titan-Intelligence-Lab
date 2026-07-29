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
