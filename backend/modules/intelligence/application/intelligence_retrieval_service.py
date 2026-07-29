"""RAG Foundation extension — News, Community, Knowledge Graph, and AI Reports retrieval
(Milestone 8 "RAG FOUNDATION"). Every implementation here returns structured
`IntelligenceRetrievalDocument`s; none of them call an LLM, compute an embedding, or construct a
prompt — retrieval only, exactly like Milestone 7's `GraphNativeRetrieval` this module extends
rather than replaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

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
from modules.knowledge_graph.domain.value_objects import KGNodeId
from modules.knowledge_graph.ports.retrieval import GraphRetrievalPort, RetrievalQuery


@dataclass
class NewsRetrieval:
    """News modality: every `NewsEvent` naming ``subject_ref`` among its affected entities."""

    events: NewsEventRepositoryPort

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        matches = await self.events.list_for_entity(query.subject_ref, limit=query.max_results)
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
    """Community modality: recent posts whose text mentions ``subject_ref`` — a plain substring
    search, since `CommunityPost` doesn't carry resolved entity links the way `NewsEvent` does
    (Milestone 8's Community Intelligence scope is filtering/credibility, not NER)."""

    posts: CommunityPostRepositoryPort
    platform: CommunityPlatform | None = None
    scan_limit: int = 500

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        candidates = await self.posts.list_recent(platform=self.platform, limit=self.scan_limit)
        needle = query.subject_ref.lower()
        matches = [p for p in candidates if needle in p.text.lower()][: query.max_results]
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
    not reimplemented."""

    graph_retrieval: GraphRetrievalPort

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        try:
            node_id = KGNodeId(UUID(query.subject_ref))
        except ValueError:
            return IntelligenceRetrievalResult(query=query, documents=(), truncated=False)

        graph_result = await self.graph_retrieval.retrieve(
            RetrievalQuery(subject_id=node_id, max_facts=query.max_results)
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
class IntelligenceRetrievalService:
    """Fans out across every modality and returns the combined result — the facade a future
    RAG generation step (out of scope this milestone) would call once instead of four."""

    news: NewsRetrieval
    community: CommunityRetrieval
    knowledge_graph: KnowledgeGraphRetrievalAdapter
    ai_reports: AIReportRetrieval

    async def retrieve_all(self, subject_ref: str, max_results_per_modality: int = 10) -> tuple[IntelligenceRetrievalDocument, ...]:
        query = IntelligenceRetrievalQuery(subject_ref=subject_ref, max_results=max_results_per_modality)
        documents: list[IntelligenceRetrievalDocument] = []
        for port in (self.news, self.community, self.knowledge_graph, self.ai_reports):
            result = await port.retrieve(query)
            documents.extend(result.documents)
        return tuple(documents)
