from __future__ import annotations

from modules.intelligence.application.news_validity_policy import validity_window_hours
from modules.intelligence.domain.value_objects import NewsEventType


def test_transfer_window_is_ninety_days():
    assert validity_window_hours(NewsEventType.TRANSFER) == 90 * 24


def test_injury_window_is_fourteen_days():
    assert validity_window_hours(NewsEventType.INJURY) == 14 * 24


def test_lineup_expectation_window_is_the_shortest_speculative_default():
    assert validity_window_hours(NewsEventType.LINEUP_EXPECTATION) == 3 * 24


def test_every_news_event_type_has_a_documented_window_not_the_fallback_default():
    """Every member of NewsEventType must have its own explicit entry in
    `_VALIDITY_WINDOW_HOURS` — falling through to `_DEFAULT_TTL_HOURS` for a real event type
    would silently violate the spec's "document the rationale, no arbitrary defaults" rule."""
    from modules.intelligence.application.news_validity_policy import _DEFAULT_TTL_HOURS, _VALIDITY_WINDOW_HOURS

    assert set(_VALIDITY_WINDOW_HOURS) == set(NewsEventType)
    for event_type in NewsEventType:
        assert _VALIDITY_WINDOW_HOURS[event_type] > 0
    # sanity: the fallback constant itself still exists and is positive, even though nothing
    # in the real enum should ever hit it.
    assert _DEFAULT_TTL_HOURS > 0
