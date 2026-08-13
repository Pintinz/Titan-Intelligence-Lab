"""Milestone 9 — News Validity Windows (spec §9): "Expired events must not continue contributing
indefinitely. Do not hardcode arbitrary expiry durations without documenting the rationale."

Every window below is a documented, event-type-specific default — the same "honest v1, no fitted
model, retune once real outcome history exists" posture already established for
`LINEUP_PREMATCH_WINDOW_MINUTES` (modules.ingestion.application.provenance) and
`TRANSFER_ACTIVITY_WINDOW_DAYS` (modules.predictions.application.windowed_feature_engineering_service).
Env-overridable per the same pattern those two use.
"""

from __future__ import annotations

import os

from modules.intelligence.domain.value_objects import NewsEventType


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Hours until a news event's confidence tier decays to EXPIRED
# (NewsEventConfidenceClassifier.classify) if nothing corroborates, contradicts, or supersedes it
# first. Rationale per event type, not one blanket number:
_VALIDITY_WINDOW_HOURS: dict[NewsEventType, int] = {
    # A confirmed transfer is a settled historical fact once registered — relevant for the rest
    # of the season it happens in, not just days. 90 days covers a full transfer window's worth
    # of squad-composition relevance without claiming indefinite validity.
    NewsEventType.TRANSFER: _env_int("TITANIQ_NEWS_TTL_TRANSFER_HOURS", 90 * 24),
    # An injury report is only actionable until the player is confirmed fit again — but with no
    # real recovery-date data (the same "no genuine timestamp" gap `has_genuine_timestamp=False`
    # already documents for structured injuries), 14 days is a conservative default long enough
    # to cover most short-term injuries without silently carrying a stale "OUT" status for months.
    NewsEventType.INJURY: _env_int("TITANIQ_NEWS_TTL_INJURY_HOURS", 14 * 24),
    NewsEventType.RECOVERY: _env_int("TITANIQ_NEWS_TTL_RECOVERY_HOURS", 7 * 24),
    NewsEventType.SUSPENSION: _env_int("TITANIQ_NEWS_TTL_SUSPENSION_HOURS", 21 * 24),
    # A manager appointment is valid until superseded by another manager-change event — no natural
    # decay, but an unbounded TTL contradicts the spec's explicit "must not contribute
    # indefinitely" rule, so a generous 180-day ceiling stands in for "until superseded."
    NewsEventType.MANAGER_CHANGE: _env_int("TITANIQ_NEWS_TTL_MANAGER_CHANGE_HOURS", 180 * 24),
    NewsEventType.FORMATION_CHANGE: _env_int("TITANIQ_NEWS_TTL_FORMATION_CHANGE_HOURS", 14 * 24),
    NewsEventType.TACTICAL_CHANGE: _env_int("TITANIQ_NEWS_TTL_TACTICAL_CHANGE_HOURS", 14 * 24),
    NewsEventType.TRAINING_UPDATE: _env_int("TITANIQ_NEWS_TTL_TRAINING_UPDATE_HOURS", 3 * 24),
    # Weather/travel/venue/postponement are all short-fuse, fixture-proximate signals — stale
    # within days regardless of event type.
    NewsEventType.WEATHER_REPORT: _env_int("TITANIQ_NEWS_TTL_WEATHER_REPORT_HOURS", 3 * 24),
    NewsEventType.TRAVEL_DELAY: _env_int("TITANIQ_NEWS_TTL_TRAVEL_DELAY_HOURS", 2 * 24),
    NewsEventType.STADIUM_CHANGE: _env_int("TITANIQ_NEWS_TTL_STADIUM_CHANGE_HOURS", 30 * 24),
    NewsEventType.MATCH_POSTPONEMENT: _env_int("TITANIQ_NEWS_TTL_MATCH_POSTPONEMENT_HOURS", 14 * 24),
    NewsEventType.PLAYER_AVAILABILITY: _env_int("TITANIQ_NEWS_TTL_PLAYER_AVAILABILITY_HOURS", 7 * 24),
    # Lineup expectations are speculative and fixture-proximate by nature — the shortest window,
    # the "shorter configurable TTL" the spec's own rumour/speculation example calls for.
    NewsEventType.LINEUP_EXPECTATION: _env_int("TITANIQ_NEWS_TTL_LINEUP_EXPECTATION_HOURS", 3 * 24),
}

_DEFAULT_TTL_HOURS = _env_int("TITANIQ_NEWS_TTL_DEFAULT_HOURS", 7 * 24)


def validity_window_hours(event_type: NewsEventType) -> int:
    return _VALIDITY_WINDOW_HOURS.get(event_type, _DEFAULT_TTL_HOURS)
