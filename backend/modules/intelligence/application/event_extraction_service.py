"""Event Extraction — structured event detection + entity linking (Milestone 8 "EVENT
EXTRACTION": "Detect events including Transfers, Injuries, Recoveries, Suspensions, Manager
Changes, Formation Changes, Tactical Changes, Training Updates, Weather Reports, Travel Delays,
Stadium Changes, Match Postponements, Player Availability, Lineup Expectations. Every event
must contain: Confidence, Source, Timestamp, Affected entities, Knowledge Graph links.").

Wraps `TextIntelligenceProviderPort.extract_events` and persists the result as a `NewsEvent`
carrying every required field. Actually creating graph *edges* for the event (e.g. a
`TRANSFERRED_TO` edge) is `KnowledgeGraphEnrichmentService`'s job (Milestone 8), which reads
these persisted events rather than this service reaching into the graph's write path directly.

Milestone 9 audit fix: this used to build `affected_entity_refs` as a flat
`raw.entities + resolved_refs` union — the provider's own *unresolved* entity mentions from
`extract_events` (a separate NLP call from `extract_entities`, sharing no resolution step) mixed
directly with the *actually KG-resolved* refs from `EntityExtractionService.extract_and_link`,
with no way for any downstream consumer to tell which was which. `MockGeminiAdapter.extract_events`
hardcodes literal `"mock_player"`/`"mock_team"` strings here — this is exactly how those strings
were reaching `affected_entity_refs`, unfiltered, indistinguishable from a real resolved
Knowledge Graph node id. Fixed: `affected_entity_refs` is now populated ONLY from the properly
resolved path (RESOLVED-only, its originally-intended contract — every existing consumer, e.g.
`NewsImpactEngine._looks_like_node_id`, already assumed every ref there is a real KG node id).
The provider's own raw entity mentions are no longer silently merged in at all; the real
per-mention resolution status is preserved on `NewsEvent.resolved_entities` instead of being
discarded, so an event with only unresolved entities is still stored (raw intelligence) but
`is_feature_eligible()` correctly excludes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.intelligence.application.entity_extraction_service import EntityExtractionService
from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
)
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
        resolved_entities = tuple(
            ResolvedNewsEntity(
                ref=str(mention.kg_node_id) if mention.kg_node_id is not None else mention.text,
                node_type=mention.node_type.value if mention.node_type is not None else None,
                status=(
                    EntityResolutionStatus.RESOLVED
                    if mention.kg_node_id is not None
                    else EntityResolutionStatus.UNRESOLVED
                ),
            )
            for mention in linked_mentions
        )
        # RESOLVED-only, deduped, order-preserving — the field's original intended contract.
        affected = tuple(
            dict.fromkeys(e.ref for e in resolved_entities if e.status is EntityResolutionStatus.RESOLVED)
        )

        recorded: list[NewsEvent] = []
        for raw in raw_events:
            event_type = self._resolve_event_type(raw.event_type)
            if event_type is None:
                continue
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
                resolved_entities=resolved_entities,
            )
            recorded.append(await self.events.record(event))
        return recorded

    def _resolve_event_type(self, raw_type: str) -> NewsEventType | None:
        normalized = _EVENT_TYPE_ALIASES.get(raw_type, raw_type)
        try:
            return NewsEventType(normalized)
        except ValueError:
            return None
