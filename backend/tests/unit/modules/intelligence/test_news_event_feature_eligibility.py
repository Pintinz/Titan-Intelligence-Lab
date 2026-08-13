from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _event(**overrides) -> NewsEvent:
    defaults = dict(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="x", confidence=0.7,
        source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()), occurred_at=T0, detected_at=T0,
        availability_classification="VERIFIED_PRE_MATCH",
    )
    defaults.update(overrides)
    return NewsEvent(**defaults)


def test_verified_event_with_no_entities_at_all_is_eligible():
    """An event with zero resolved_entities vacuously satisfies "every entity is resolved" — it
    just can't feed any entity-scoped feature. Availability is the only real gate here."""
    event = _event(resolved_entities=())

    assert event.is_feature_eligible() is True


def test_verified_event_with_only_resolved_entities_is_eligible():
    event = _event(
        resolved_entities=(ResolvedNewsEntity(ref="node-1", node_type="player", status=EntityResolutionStatus.RESOLVED),)
    )

    assert event.is_feature_eligible() is True


def test_verified_event_with_any_unresolved_entity_is_not_eligible():
    event = _event(
        resolved_entities=(
            ResolvedNewsEntity(ref="node-1", node_type="player", status=EntityResolutionStatus.RESOLVED),
            ResolvedNewsEntity(ref="mock_player", node_type=None, status=EntityResolutionStatus.UNRESOLVED),
        )
    )

    assert event.is_feature_eligible() is False


def test_unknown_availability_event_is_never_eligible_even_with_fully_resolved_entities():
    event = _event(
        availability_classification="UNKNOWN_AVAILABILITY_TIME",
        resolved_entities=(ResolvedNewsEntity(ref="node-1", node_type="player", status=EntityResolutionStatus.RESOLVED),),
    )

    assert event.is_feature_eligible() is False


def test_invalid_availability_event_is_never_eligible():
    event = _event(availability_classification="INVALID")

    assert event.is_feature_eligible() is False
