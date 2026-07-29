"""RAG Foundation extension (Milestone 8 "RAG FOUNDATION": "Extend the existing retrieval
framework. Prepare retrieval interfaces for: News, Community, Knowledge Graph, AI Reports. No
vector embeddings yet. No LLM prompting layer yet.").

Milestone 7 shipped `modules.knowledge_graph.ports.retrieval.GraphRetrievalPort` — retrieval
interfaces only, no embeddings, no LLM call, structured facts rather than prose. This module
defines the same shape of contract generalized to text-based sources (News, Community, AI
Reports/Summaries) that aren't graph nodes, plus a facade
(`modules.intelligence.application.intelligence_retrieval_service.IntelligenceRetrievalService`)
that fans out across all four modalities including the Knowledge Graph's own port via a thin
adapter — extending the existing framework, not replacing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class IntelligenceRetrievalQuery:
    subject_ref: str
    max_results: int = 20


@dataclass(frozen=True)
class IntelligenceRetrievalDocument:
    """One retrievable fact — structured, not prose. Turning these into prompt text is a
    future RAG generation step's job, explicitly not this one's (same posture as
    `modules.knowledge_graph.ports.retrieval.RetrievalDocument`)."""

    modality: str  # "news" | "community" | "knowledge_graph" | "ai_reports"
    subject_ref: str
    text: str
    source: str
    confidence: float
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class IntelligenceRetrievalResult:
    query: IntelligenceRetrievalQuery
    documents: tuple[IntelligenceRetrievalDocument, ...]
    truncated: bool = False


class IntelligenceRetrievalPort(Protocol):
    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult: ...
