"""Text Intelligence Provider port — Google Gemini's contract in TitanIQ.

Deliberately excludes anything resembling "predict a probability." Per the provider
configuration directive: Gemini is used ONLY for news intelligence, injury extraction, tactical
analysis, match context analysis, AI explanations, community sentiment interpretation, NL
summaries, report generation, and recommendation reasoning — prediction probabilities always
come from TitanIQ's own trained models (docs/architecture.md §6, Prediction Intelligence
Platform). There is no method on this port that could be misused to source a probability from
an LLM instead of a model — that's an architectural guardrail, not just a convention.

Milestone 8 adds Named Entity Recognition, Relationship Extraction, Topic Classification,
Language Detection, and Key Phrase Extraction — additive only, every Milestone 3 method
(`extract_events`, `summarize`, `explain`, `interpret_sentiment`) is unchanged. Every new method
is equally incapable of producing a prediction probability, same guardrail as above.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractedEvent:
    """A structured event pulled from unstructured text (docs/titaniq.md news pipeline) —
    e.g. an injury report, transfer rumor, or lineup change. Confidence is Gemini's own
    extraction confidence, not a prediction confidence — it still goes through the platform's
    News Validation step before influencing anything (docs/titaniq.md News Intelligence)."""

    event_type: str
    summary: str
    entities: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class ExtractedEntity:
    """One Named Entity Recognition hit — a mention, not yet a resolved Knowledge Graph node.
    Resolving ``text`` to a canonical `KGNode` (alias/provider-ref matching, disambiguation) is
    `EntityExtractionService`'s job (Milestone 8), not this port's — Gemini identifies "this
    span of text names a player," it doesn't know which player in our graph that is."""

    text: str
    entity_type: str  # free-form label ("player", "team", "competition", "coach", "venue", ...)
    confidence: float


@dataclass(frozen=True)
class ExtractedRelationship:
    """A subject-relation-object triple extracted from text, e.g. ("Mbappe", "transferred_to",
    "Real Madrid") — the NLP-extraction analog of a Knowledge Graph edge, before it has been
    resolved against actual graph nodes."""

    subject: str
    relation: str
    obj: str
    confidence: float


@dataclass(frozen=True)
class KeyPhrase:
    phrase: str
    score: float


class TextIntelligenceProviderPort(Protocol):
    provider_key: str

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        """News/injury/transfer extraction — structured events out of unstructured text."""
        ...

    async def summarize(self, text: str, *, max_words: int = 120) -> str:
        """Natural-language summary of a longer text (report generation, news digest)."""
        ...

    async def explain(self, context: dict) -> str:
        """Turns structured context (feature importances, supporting stats) into a
        human-readable explanation — consumed by the Explainability Engine
        (docs/api_specification.md §3), never generates the prediction itself."""
        ...

    async def interpret_sentiment(self, text: str) -> str:
        """Community sentiment interpretation — supporting signal only
        (docs/titaniq.md Community Intelligence: "never replace verified statistical data")."""
        ...

    async def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Named Entity Recognition — every player/team/competition/coach/venue/etc. mention in
        the text, unresolved against the Knowledge Graph (Milestone 8)."""
        ...

    async def extract_relationships(self, text: str) -> list[ExtractedRelationship]:
        """Relationship Extraction — subject-relation-object triples between entity mentions
        (Milestone 8), the NLP-side counterpart to the Knowledge Graph's `EdgeType` catalog."""
        ...

    async def classify_topics(self, text: str) -> list[str]:
        """Topic Classification — free-form topic labels (e.g. "injury", "transfer window",
        "tactics") describing what the text is about (Milestone 8)."""
        ...

    async def detect_language(self, text: str) -> str:
        """Language Detection — an ISO 639-1 code (Milestone 8); non-English sources are still
        ingested, this is what lets downstream processing know which language it received."""
        ...

    async def extract_key_phrases(self, text: str, *, limit: int = 5) -> list[KeyPhrase]:
        """Key Phrase Extraction — the most salient phrases in the text, ranked by relevance
        score (Milestone 8); feeds search indexing and quick-scan summaries."""
        ...
