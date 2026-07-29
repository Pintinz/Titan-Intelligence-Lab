"""Graph-native retrieval — the one implementation of `GraphRetrievalPort` this milestone
ships (docs/ontology.md §11). Turns a bounded neighborhood expansion into structured
`RetrievalDocument`s: no embeddings, no LLM call, no prompt text — exactly the "retrieval
interfaces only" scope the constitution specifies. A future embedding-backed retriever
(semantic/vector search over node content) implements the same port and slots in without
touching any consumer, the same mock-first/adapter-swap shape used elsewhere in this module
(docs/decisions.md ADR-008).
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.knowledge_graph.application.graph_query_service import GraphQueryService
from modules.knowledge_graph.ports.retrieval import RetrievalDocument, RetrievalQuery, RetrievalResult


@dataclass
class GraphNativeRetrieval:
    query: GraphQueryService

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        subgraph = await self.query.neighborhood(query.subject_id, depth=query.depth, max_nodes=query.max_facts)
        if not any(n.id == query.subject_id for n in subgraph.nodes):
            return RetrievalResult(query=query, documents=(), truncated=False)

        node_by_id = {n.id: n for n in subgraph.nodes}
        documents: list[RetrievalDocument] = []
        for edge in subgraph.edges:
            if len(documents) >= query.max_facts:
                break
            from_node = node_by_id.get(edge.from_node_id)
            to_node = node_by_id.get(edge.to_node_id)
            if from_node is None or to_node is None:
                continue
            documents.append(
                RetrievalDocument(
                    subject_ref=from_node.entity_ref,
                    subject_type=from_node.node_type,
                    relation=edge.edge_type.value,
                    related_ref=to_node.entity_ref,
                    related_type=to_node.node_type,
                    confidence=edge.confidence,
                    source=edge.source,
                )
            )
        truncated = subgraph.truncated or len(documents) >= query.max_facts
        return RetrievalResult(query=query, documents=tuple(documents), truncated=truncated)
