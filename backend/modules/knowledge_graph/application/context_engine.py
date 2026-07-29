"""Context Engine — Context Intelligence (docs/ontology.md §7, Milestone 7: "Generate
contextual information for Fixture, Match, Player, Team, Competition, Prediction, News,
Feature, Model, Explainability, Historical Comparison. This engine will become the context
provider for Prediction Engine, News Engine, Recommendation Engine, AI Assistant.")

One generic builder (`build_context`) does the real work — BFS neighborhood expansion via
`GraphQueryService`, then grouped by `NodeType` — since context is structurally the same
question for every entity kind ("what is this connected to, and how is that organized"), the
same shape `GraphStructuralSimilarity` already established for similarity (one metric serves
every `NodeType` named in the ontology). Every named ``context_for_*`` method below is a thin
wrapper choosing a depth/breadth appropriate to that entity's typical fan-out, not a distinct
implementation. No LLM/narrative generation here — that is RAG Foundation's job (Milestone 7
scope: "Implement retrieval interfaces only. Do NOT implement RAG.").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.domain.entities import KGNode
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.ports.graph_query import Subgraph
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort


@dataclass(frozen=True)
class ContextBundle:
    subject: KGNode
    neighborhood: Subgraph
    related_by_type: dict = field(default_factory=dict)  # NodeType -> tuple[KGNode, ...]
    generated_at: datetime | None = None


@dataclass
class ContextEngine:
    query: GraphQueryService
    nodes: KGNodeRepositoryPort

    async def build_context(
        self, node_id: KGNodeId, now: datetime, depth: int = 1, max_nodes: int = 100
    ) -> ContextBundle | None:
        subject = await self.nodes.get(node_id)
        if subject is None:
            return None
        neighborhood = await self.query.neighborhood(node_id, depth=depth, max_nodes=max_nodes)
        return ContextBundle(
            subject=subject,
            neighborhood=neighborhood,
            related_by_type=self._group_by_type(neighborhood, exclude=node_id),
            generated_at=now,
        )

    def _group_by_type(self, subgraph: Subgraph, exclude: KGNodeId) -> dict:
        groups: dict[NodeType, list[KGNode]] = {}
        for node in subgraph.nodes:
            if node.id == exclude:
                continue
            groups.setdefault(node.node_type, []).append(node)
        return {node_type: tuple(nodes) for node_type, nodes in groups.items()}

    # -- named context providers, one per constitution-listed entity kind -----------------------

    async def context_for_fixture(self, fixture_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(fixture_id, now, depth=1, max_nodes=150)

    async def context_for_match(self, match_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(match_id, now, depth=1, max_nodes=150)

    async def context_for_player(self, player_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(player_id, now, depth=2, max_nodes=150)

    async def context_for_team(self, team_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(team_id, now, depth=2, max_nodes=200)

    async def context_for_competition(self, competition_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(competition_id, now, depth=1, max_nodes=300)

    async def context_for_prediction(self, prediction_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(prediction_id, now, depth=1, max_nodes=100)

    async def context_for_news(self, news_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(news_id, now, depth=1, max_nodes=100)

    async def context_for_feature(self, feature_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(feature_id, now, depth=1, max_nodes=100)

    async def context_for_model(self, model_id: KGNodeId, now: datetime) -> ContextBundle | None:
        return await self.build_context(model_id, now, depth=1, max_nodes=100)

    async def context_for_explainability(self, subject_id: KGNodeId, now: datetime) -> ContextBundle | None:
        """Deeper expansion than the other single-entity providers — explaining a prediction or
        outcome typically needs the chain of features/models/statistics that produced it, not
        just its immediate neighbors."""
        return await self.build_context(subject_id, now, depth=2, max_nodes=200)

    async def context_for_historical_comparison(
        self, node_a_id: KGNodeId, node_b_id: KGNodeId, now: datetime
    ) -> tuple[ContextBundle | None, ContextBundle | None]:
        return (
            await self.build_context(node_a_id, now, depth=1, max_nodes=150),
            await self.build_context(node_b_id, now, depth=1, max_nodes=150),
        )
