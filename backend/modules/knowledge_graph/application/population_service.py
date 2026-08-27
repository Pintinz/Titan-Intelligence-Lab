"""Knowledge Graph Population Service — write path (docs/ontology.md).

Milestone 5 scope ("Only establish graph population infrastructure. Do NOT implement AI
reasoning yet.") remains true of `upsert_node`/`upsert_edge`'s core behavior: idempotent
upsert-in-place, no traversal/similarity/reasoning logic here — that lives in
``modules.knowledge_graph.application.graph_query_service`` and friends (Milestone 7).

Milestone 7 threads ``now`` through to `upsert_node` so ``created_at``/``updated_at`` populate
correctly (they didn't exist as fields before this milestone), and increments ``version`` on
every update to an existing node — the minimal versioning the Sports Ontology spec asks for,
without changing any external call site's signature (every ``populate_*`` wrapper already
receives ``now``; this just forwards it one level deeper than before).

Standing and Lineup data continue to live relationally in ``modules.sports`` — the graph
represents their *relationships* (a team's ranking in a season, a player's participation in a
match) as edge attributes rather than as separate graph nodes, keeping the graph focused on
entities with independent identity rather than mirroring every relational join-row.

News-intelligence entity-resolution audit fix (2026-08-27): every ``populate_*`` wrapper that
accepts a real-world ``name`` (team/player/venue/competition/organization/country/sport) wrote it
into ``attributes["name"]`` but never into ``aliases`` — a real, structural bug, not a cosmetic
gap: `EntityResolutionService.find_by_alias` (the ONLY lookup `EntityExtractionService` uses to
resolve a free-text news mention like "Manchester City" against the graph) searches `aliases`
exclusively, never `attributes`. Confirmed live: every real TEAM/PLAYER node in dev.db had
``aliases == []`` despite a real, correct ``attributes["name"]``, and every one of the 29
genuinely Gemini-extracted `NewsEvent`s in dev.db (as opposed to mock-adapter placeholder events)
had zero resolved entities as a direct, 100%-reproducing consequence — the entire news-to-feature
pipeline (`NewsMarketImpactEngine` and everything the Correct Score / News Intelligence master
prompts ask to build on top of it) was structurally unable to ever resolve a single real mention,
regardless of how exact the match would have been. Fixed at the write path (``aliases=[name]``
alongside the existing ``attributes``) so every future reconciliation call self-heals the alias
list going forward; ``scripts/backfill_kg_node_aliases.py`` backfills every already-populated node
whose ``aliases`` is still empty from its own ``attributes["name"]``, so already-synced teams and
players resolve immediately without waiting for their next reconciliation pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.knowledge_graph.domain.entities import KGEdge, KGNode
from modules.knowledge_graph.domain.value_objects import EdgeType, KGEdgeId, KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGEdgeRepositoryPort, KGNodeRepositoryPort


@dataclass
class KnowledgeGraphPopulationService:
    nodes: KGNodeRepositoryPort
    edges: KGEdgeRepositoryPort

    async def upsert_node(
        self,
        node_type: NodeType,
        entity_ref: str,
        attributes: dict | None = None,
        now: datetime | None = None,
        provider_refs: dict | None = None,
        aliases: list[str] | None = None,
        source: str = "ingestion",
        confidence: float = 1.0,
    ) -> KGNode:
        existing = await self.nodes.get_by_entity_ref(node_type, entity_ref)
        node = KGNode(
            id=existing.id if existing else KGNodeId(uuid4()),
            node_type=node_type,
            entity_ref=entity_ref,
            attributes=attributes or (existing.attributes if existing else {}),
            provider_refs={**(existing.provider_refs if existing else {}), **(provider_refs or {})},
            aliases=sorted(set((existing.aliases if existing else []) + (aliases or []))),
            source=source,
            version=(existing.version + 1) if existing else 1,
            status=existing.status if existing else "active",
            confidence=confidence,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            merged_into=existing.merged_into if existing else None,
        )
        return await self.nodes.upsert(node)

    async def upsert_edge(
        self,
        from_node: KGNode,
        to_node: KGNode,
        edge_type: EdgeType,
        now: datetime,
        weight: float = 1.0,
        attributes: dict | None = None,
        confidence: float = 1.0,
        source: str = "ingestion",
        directed: bool = True,
    ) -> KGEdge:
        """Idempotent on (from_node, to_node, edge_type): updates the current edge's
        weight/attributes in place rather than creating a duplicate, preserving the original
        ``valid_from``. Closing an edge and opening a new one on a genuine relationship change
        (e.g. a transfer ending one team's PLAYS_FOR edge) is ``GraphQueryService``/
        ``TemporalGraphService``'s ``supersede_edge`` (Milestone 7), a distinct explicit
        operation from this method's in-place idempotent update."""
        existing = await self.edges.get_current(from_node.id, to_node.id, edge_type)
        edge = KGEdge(
            id=existing.id if existing else KGEdgeId(uuid4()),
            from_node_id=from_node.id, to_node_id=to_node.id, edge_type=edge_type,
            valid_from=existing.valid_from if existing else now,
            weight=weight, attributes=attributes or {}, valid_to=None,
            confidence=confidence, source=source,
            version=(existing.version + 1) if existing else 1,
            directed=directed,
        )
        return await self.edges.upsert(edge)

    # -- convenience wrappers matching the Milestone 5 representative entity set ----------------

    async def populate_sport(self, sport_id: str, now: datetime, name: str | None = None) -> KGNode:
        return await self.upsert_node(
            NodeType.SPORT, sport_id, {"name": name} if name else None, now=now, aliases=[name] if name else None,
        )

    async def populate_country(self, country_id: str, now: datetime, code: str, name: str) -> KGNode:
        return await self.upsert_node(
            NodeType.COUNTRY, country_id, {"code": code, "name": name}, now=now, aliases=[name],
        )

    async def populate_competition(
        self, competition_id: str, sport_id: str, now: datetime, name: str | None = None
    ) -> KGNode:
        competition_node = await self.upsert_node(
            NodeType.COMPETITION, competition_id, {"name": name} if name else None, now=now,
            aliases=[name] if name else None,
        )
        sport_node = await self.upsert_node(NodeType.SPORT, sport_id, now=now)
        await self.upsert_edge(competition_node, sport_node, EdgeType.BELONGS_TO, now)
        return competition_node

    async def populate_season(self, season_id: str, competition_id: str, now: datetime, label: str | None = None) -> KGNode:
        season_node = await self.upsert_node(NodeType.SEASON, season_id, {"label": label} if label else None, now=now)
        competition_node = await self.upsert_node(NodeType.COMPETITION, competition_id, now=now)
        await self.upsert_edge(season_node, competition_node, EdgeType.BELONGS_TO, now)
        return season_node

    async def populate_venue(
        self, venue_id: str, now: datetime, name: str | None = None, country_id: str | None = None
    ) -> KGNode:
        venue_node = await self.upsert_node(
            NodeType.VENUE, venue_id, {"name": name} if name else None, now=now, aliases=[name] if name else None,
        )
        if country_id:
            country_node = await self.upsert_node(NodeType.COUNTRY, country_id, now=now)
            await self.upsert_edge(venue_node, country_node, EdgeType.LOCATED_IN, now)
        return venue_node

    async def populate_team(
        self, team_id: str, sport_id: str, now: datetime, name: str | None = None, country_id: str | None = None
    ) -> KGNode:
        team_node = await self.upsert_node(
            NodeType.TEAM, team_id, {"name": name} if name else None, now=now, aliases=[name] if name else None,
        )
        sport_node = await self.upsert_node(NodeType.SPORT, sport_id, now=now)
        await self.upsert_edge(team_node, sport_node, EdgeType.BELONGS_TO, now)
        if country_id:
            country_node = await self.upsert_node(NodeType.COUNTRY, country_id, now=now)
            await self.upsert_edge(team_node, country_node, EdgeType.LOCATED_IN, now)
        return team_node

    async def populate_team_competition(self, team_id: str, competition_id: str, now: datetime) -> None:
        team_node = await self.upsert_node(NodeType.TEAM, team_id, now=now)
        competition_node = await self.upsert_node(NodeType.COMPETITION, competition_id, now=now)
        await self.upsert_edge(team_node, competition_node, EdgeType.COMPETES_IN, now)

    async def populate_player(
        self, player_id: str, sport_id: str, now: datetime, team_id: str | None = None, name: str | None = None
    ) -> KGNode:
        player_node = await self.upsert_node(
            NodeType.PLAYER, player_id, {"name": name} if name else None, now=now, aliases=[name] if name else None,
        )
        sport_node = await self.upsert_node(NodeType.SPORT, sport_id, now=now)
        await self.upsert_edge(player_node, sport_node, EdgeType.BELONGS_TO, now)
        if team_id:
            team_node = await self.upsert_node(NodeType.TEAM, team_id, now=now)
            await self.upsert_edge(player_node, team_node, EdgeType.PLAYS_FOR, now)
        return player_node

    async def populate_fixture(
        self, fixture_id: str, home_team_id: str, away_team_id: str, now: datetime, venue_id: str | None = None
    ) -> KGNode:
        match_node = await self.upsert_node(NodeType.MATCH, fixture_id, now=now)
        home_node = await self.upsert_node(NodeType.TEAM, home_team_id, now=now)
        away_node = await self.upsert_node(NodeType.TEAM, away_team_id, now=now)
        await self.upsert_edge(home_node, match_node, EdgeType.INVOLVED_IN, now, attributes={"side": "home"})
        await self.upsert_edge(away_node, match_node, EdgeType.INVOLVED_IN, now, attributes={"side": "away"})
        if venue_id:
            venue_node = await self.upsert_node(NodeType.VENUE, venue_id, now=now)
            await self.upsert_edge(match_node, venue_node, EdgeType.SCHEDULED_AT, now)
        return match_node

    async def populate_team_statistics(self, fixture_id: str, team_id: str, now: datetime) -> KGNode:
        stats_node = await self.upsert_node(NodeType.STATISTICS, f"{fixture_id}:{team_id}", now=now)
        match_node = await self.upsert_node(NodeType.MATCH, fixture_id, now=now)
        team_node = await self.upsert_node(NodeType.TEAM, team_id, now=now)
        await self.upsert_edge(stats_node, match_node, EdgeType.DERIVED_FROM, now)
        await self.upsert_edge(stats_node, team_node, EdgeType.DERIVED_FROM, now)
        return stats_node

    async def populate_standing(self, team_id: str, season_id: str, now: datetime, rank: int, points: float) -> None:
        team_node = await self.upsert_node(NodeType.TEAM, team_id, now=now)
        season_node = await self.upsert_node(NodeType.SEASON, season_id, now=now)
        await self.upsert_edge(
            team_node, season_node, EdgeType.COMPETES_IN, now, attributes={"rank": rank, "points": points}
        )

    # -- M6 business entities: organizations/users/subscriptions/providers ----------------------

    async def populate_organization(self, organization_id: str, now: datetime, name: str | None = None) -> KGNode:
        return await self.upsert_node(
            NodeType.ORGANIZATION, organization_id, {"name": name} if name else None, now=now,
            aliases=[name] if name else None,
        )

    async def populate_user(self, user_id: str, now: datetime, email: str | None = None) -> KGNode:
        return await self.upsert_node(NodeType.USER, user_id, {"email": email} if email else None, now=now)

    async def populate_subscription(
        self, subscription_id: str, subject_type: str, subject_id: str, now: datetime, plan_key: str | None = None
    ) -> KGNode:
        subscription_node = await self.upsert_node(
            NodeType.SUBSCRIPTION, subscription_id, {"plan_key": plan_key} if plan_key else None, now=now
        )
        subject_node_type = NodeType.ORGANIZATION if subject_type == "organization" else NodeType.USER
        subject_node = await self.upsert_node(subject_node_type, subject_id, now=now)
        await self.upsert_edge(subscription_node, subject_node, EdgeType.BELONGS_TO, now)
        return subscription_node

    async def populate_provider(self, provider_id: str, now: datetime, key: str | None = None) -> KGNode:
        return await self.upsert_node(NodeType.PROVIDER, provider_id, {"key": key} if key else None, now=now)
