"""Event Extraction — structured event detection + entity linking (Milestone 8 "EVENT
EXTRACTION": "Detect events including Transfers, Injuries, Recoveries, Suspensions, Manager
Changes, Formation Changes, Tactical Changes, Training Updates, Weather Reports, Travel Delays,
Stadium Changes, Match Postponements, Player Availability, Lineup Expectations. Every event
must contain: Confidence, Source, Timestamp, Affected entities, Knowledge Graph links.").

Wraps `TextIntelligenceProviderPort.extract_events` and persists the result as a `NewsEvent`
carrying every required field. "Affected entities" combines the provider's own entity list with
whatever `EntityExtractionService` resolves from the same text — resolved Knowledge Graph node
ids where a match exists, the raw mention text otherwise. Actually creating graph *edges* for
the event (e.g. a `TRANSFERRED_TO` edge) is `KnowledgeGraphEnrichmentService`'s job (Milestone
8), which reads these persisted events rather than this service reaching into the graph's write
path directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.domain.entities import NewsEvent
from modules.intelligence.domain.value_objects import NewsArticleId, NewsEventId, NewsEventType, NewsSourceId
from modules.intelligence.ports.repositories import NewsEventRepositoryPort
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort

# Provider output occasionally uses a near-synonym of a NewsEventType value; normalized here
# rather than widening the enum for a label difference with no distinct meaning.
_EVENT_TYPE_ALIASES = {"sign": "transfer", "signing": "transfer"}


@dataclass
class EventExtractionService:
    text_intelligence: TextIntelligenceProviderPort
    entity_extraction: EntityExtractionService
    events: NewsEventRepositoryPort

    async def extract_and_record(
        self,
        text: str,
        source_id: NewsSourceId,
        article_id: NewsArticleId,
        occurred_at: datetime,
        now: datetime,
    ) -> list[NewsEvent]:
        raw_events = await self.text_intelligence.extract_events(text)
        if not raw_events:
            return []

        linked_mentions = await self.entity_extraction.extract_and_link(text)
        resolved_refs = tuple(
            str(mention.kg_node_id) if mention.kg_node_id is not None else mention.text
            for mention in linked_mentions
        )

        recorded: list[NewsEvent] = []
        for raw in raw_events:
            event_type = self._resolve_event_type(raw.event_type)
            if event_type is None:
                continue
            affected = tuple(dict.fromkeys(raw.entities + resolved_refs))  # union, order-preserving, deduped
            event = NewsEvent(
                id=NewsEventId(uuid4()),
                event_type=event_type,
                summary=raw.summary,
                confidence=raw.confidence,
                source_id=source_id,
                article_id=article_id,
                occurred_at=occurred_at,
                detected_at=now,
                affected_entity_refs=affected,
            )
            recorded.append(await self.events.record(event))
        return recorded

    def _resolve_event_type(self, raw_type: str) -> NewsEventType | None:
        normalized = _EVENT_TYPE_ALIASES.get(raw_type, raw_type)
        try:
            return NewsEventType(normalized)
        except ValueError:
            return None
