"""RAG Foundation extension — News, Community, Knowledge Graph, and AI Reports retrieval
(Milestone 8 "RAG FOUNDATION"). Every implementation here returns structured
`IntelligenceRetrievalDocument`s; none of them call an LLM, compute an embedding, or construct a
prompt — retrieval only, exactly like Milestone 7's `GraphNativeRetrieval` this module extends
rather than replaces.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.intelligence.domain.value_objects import CommunityPlatform, SummaryType
from modules.intelligence.ports.repositories import (
    CommunityPostRepositoryPort,
    NewsEventRepositoryPort,
    SummaryRepositoryPort,
)
from modules.intelligence.ports.retrieval import (
    IntelligenceRetrievalDocument,
    IntelligenceRetrievalQuery,
    IntelligenceRetrievalResult,
)
from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.knowledge_graph.ports.retrieval import GraphRetrievalPort, RetrievalQuery


@dataclass
class NewsRetrieval:
    """News modality: every `NewsEvent` naming ``subject_ref`` (or one of ``additional_refs``)
    among its affected entities."""

    events: NewsEventRepositoryPort

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        seen: dict = {}
        for ref in (query.subject_ref, *query.additional_refs):
            for event in await self.events.list_for_entity(ref, limit=query.max_results):
                seen.setdefault(event.id, event)
        matches = list(seen.values())[: query.max_results]
        documents = tuple(
            IntelligenceRetrievalDocument(
                modality="news",
                subject_ref=query.subject_ref,
                text=event.summary,
                source=str(event.source_id),
                confidence=event.confidence,
                occurred_at=event.occurred_at,
            )
            for event in matches
        )
        return IntelligenceRetrievalResult(query=query, documents=documents, truncated=len(matches) >= query.max_results)


@dataclass
class CommunityRetrieval:
    """Community modality: recent posts whose text mentions ``subject_ref`` or one of
    ``additional_refs`` — a plain substring search, since `CommunityPost` doesn't carry resolved
    entity links the way `NewsEvent` does (Milestone 8's Community Intelligence scope is
    filtering/credibility, not NER)."""

    posts: CommunityPostRepositoryPort
    platform: CommunityPlatform | None = None
    scan_limit: int = 500

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        candidates = await self.posts.list_recent(platform=self.platform, limit=self.scan_limit)
        needles = tuple(ref.lower() for ref in (query.subject_ref, *query.additional_refs))
        matches = [p for p in candidates if any(needle in p.text.lower() for needle in needles)][: query.max_results]
        documents = tuple(
            IntelligenceRetrievalDocument(
                modality="community",
                subject_ref=query.subject_ref,
                text=post.text,
                source=f"{post.platform.value}:{post.author_ref}",
                confidence=post.credibility_score,
                occurred_at=post.posted_at,
            )
            for post in matches
        )
        return IntelligenceRetrievalResult(query=query, documents=documents, truncated=len(matches) >= query.max_results)


@dataclass
class AIReportRetrieval:
    """AI Reports modality: the most recent `Summary` of each type generated about
    ``subject_ref`` — the concrete data structure behind the ontology's reserved `AI_REPORT`
    node type (docs/ontology.md), until a dedicated report-generation pipeline exists."""

    summaries: SummaryRepositoryPort

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        documents = []
        for summary_type in SummaryType:
            summary = await self.summaries.get_latest(query.subject_ref, summary_type)
            if summary is not None:
                documents.append(
                    IntelligenceRetrievalDocument(
                        modality="ai_reports",
                        subject_ref=query.subject_ref,
                        text=summary.text,
                        source=summary.summary_type.value,
                        confidence=1.0,
                        occurred_at=summary.generated_at,
                    )
                )
            if len(documents) >= query.max_results:
                break
        return IntelligenceRetrievalResult(query=query, documents=tuple(documents), truncated=False)


@dataclass
class KnowledgeGraphRetrievalAdapter:
    """Adapts Milestone 7's `GraphRetrievalPort` to this module's `IntelligenceRetrievalPort` —
    the Knowledge Graph modality is Milestone 7's existing retrieval framework, reused as-is,
    not reimplemented.

    Audit finding (2026-08-02): this previously parsed ``query.subject_ref`` directly as the
    KG node's own primary key (``KGNodeId(UUID(subject_ref))``), silently returning zero facts
    for every real caller — `PredictionEngine`/`ExplainabilityEngine` always pass the *fixture*
    id as `subject_ref` (docs/database_schema.md `predictions.subject_ref`), which is the node's
    external `entity_ref`, not its internal id (`KnowledgeGraphPopulationService.populate_match`
    upserts the MATCH node keyed by `entity_ref=fixture_id`, minting its own separate node id).
    Every football prediction's `subject_ref` names a match, so this resolves through
    `KGNodeRepositoryPort.get_by_entity_ref(NodeType.MATCH, ...)` first, exactly like
    `graph_router.py`'s `/graph/entities/{node_type}/{entity_ref}` endpoint already does.
    """

    graph_retrieval: GraphRetrievalPort
    nodes: KGNodeRepositoryPort

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        node = await self.nodes.get_by_entity_ref(NodeType.MATCH, query.subject_ref)
        if node is None:
            return IntelligenceRetrievalResult(query=query, documents=(), truncated=False)

        graph_result = await self.graph_retrieval.retrieve(
            RetrievalQuery(subject_id=node.id, max_facts=query.max_results)
        )
        documents = tuple(
            IntelligenceRetrievalDocument(
                modality="knowledge_graph",
                subject_ref=query.subject_ref,
                text=f"{doc.subject_ref} {doc.relation} {doc.related_ref}",
                source=doc.source,
                confidence=doc.confidence,
            )
            for doc in graph_result.documents
        )
        return IntelligenceRetrievalResult(query=query, documents=documents, truncated=graph_result.truncated)


@dataclass
class MatchTeamNamesResolver:
    """Resolves a match's ``subject_ref`` (fixture id) to its home/away team display names.

    Audit finding (2026-08-02): News/Community intelligence is written in prose that names
    teams ("Newcastle confirm Howe resignation") — it never mentions a fixture's internal id, so
    `NewsRetrieval`/`CommunityRetrieval` matching literally against `subject_ref` can never find
    anything for a match-level prediction, no matter how much real coverage exists (confirmed:
    zero matches even after backfilling 32 real `NewsEvent`s). Reuses the same Knowledge Graph
    MATCH->TEAM edges `KnowledgeGraphRetrievalAdapter` already resolves through, one hop further
    to each TEAM node's real ``attributes["name"]`` (populated by
    `KnowledgeGraphPopulationService.populate_match`) — no new data source, no new dependency
    beyond the Knowledge Graph this module already depends on.
    """

    nodes: KGNodeRepositoryPort
    query: GraphQueryService

    async def team_names_for_match(self, subject_ref: str) -> tuple[str, ...]:
        match_node = await self.nodes.get_by_entity_ref(NodeType.MATCH, subject_ref)
        if match_node is None:
            return ()
        subgraph = await self.query.neighborhood(match_node.id, depth=1, max_nodes=50)
        names = (
            node.attributes.get("name")
            for node in subgraph.nodes
            if node.node_type is NodeType.TEAM and isinstance(node.attributes.get("name"), str)
        )
        return tuple(dict.fromkeys(name for name in names if name))


@dataclass
class IntelligenceRetrievalService:
    """Fans out across every modality and returns the combined result — the facade a future
    RAG generation step (out of scope this milestone) would call once instead of four."""

    news: NewsRetrieval
    community: CommunityRetrieval
    knowledge_graph: KnowledgeGraphRetrievalAdapter
    ai_reports: AIReportRetrieval
    team_names: MatchTeamNamesResolver

    async def retrieve_all(self, subject_ref: str, max_results_per_modality: int = 10) -> tuple[IntelligenceRetrievalDocument, ...]:
        additional_refs = await self.team_names.team_names_for_match(subject_ref)
        query = IntelligenceRetrievalQuery(
            subject_ref=subject_ref, max_results=max_results_per_modality, additional_refs=additional_refs
        )
        documents: list[IntelligenceRetrievalDocument] = []
        for port in (self.news, self.community, self.knowledge_graph, self.ai_reports):
            result = await port.retrieve(query)
            documents.extend(result.documents)
        return tuple(documents)
