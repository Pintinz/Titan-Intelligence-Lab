from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class AlertType(str, Enum):
    """Only types with a real, currently-firing trigger. Kickoff/Final Result: fixture status
    transitioning through modules.ingestion.application.entity_reconciliation_service's now-real
    reconcile_fixture. Prediction Changed: PredictionCacheService republishing over a superseded
    prediction. Goal, Injury, Lineup, and Breaking News have no real data source wired yet (no
    match-events ingestion, no injury/lineup feed, no impact-scored news signal) — deliberately
    absent here rather than represented and never firing; the frontend lists them separately as
    not-yet-available so the gap stays visible instead of silently missing."""

    KICKOFF = "kickoff"
    FINAL_RESULT = "final_result"
    PREDICTION_CHANGED = "prediction_changed"


@dataclass(frozen=True)
class AlertEventId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
