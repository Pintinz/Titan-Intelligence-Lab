"""RAG Foundation — retrieval-only interfaces (docs/ontology.md §11, Milestone 7: "Prepare the
graph for future LLM retrieval. Implement retrieval interfaces only. Do NOT implement RAG.
Expose retrieval services for Gemini, Future LLMs, Explainability, AI Assistant,
Recommendations.").

`GraphRetrievalPort` is the seam a future RAG pipeline calls to pull graph facts as context.
Deliberately out of scope here and in every implementation of this port: embeddings, vector
search, prompt construction, and any LLM call — those are RAG itself, reserved for a future
milestone. What's in scope is exactly "retrieval": turning graph structure into a bounded list
of structured facts a future generation step can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType


@dataclass(frozen=True)
class RetrievalQuery:
    subject_id: KGNodeId
    purpose: str = "general"  # consumer-defined free-form tag, e.g. "explainability", "ai_assistant"
    depth: int = 1
    max_facts: int = 50


@dataclass(frozen=True)
class RetrievalDocument:
    """One retrievable fact — structured, not prose. Turning these into prompt text is a future
    RAG generation step's job, explicitly not this one's."""
    subject_ref: str
    subject_type: NodeType
    relation: str
    related_ref: str
    related_type: NodeType
    confidence: float
    source: str


@dataclass(frozen=True)
class RetrievalResult:
    query: RetrievalQuery
    documents: tuple[RetrievalDocument, ...]
    truncated: bool = False


class GraphRetrievalPort(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...
