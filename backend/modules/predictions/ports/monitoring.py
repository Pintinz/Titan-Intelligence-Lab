"""Model Monitoring persistence port (Milestone 9.1) — where per-prediction latency samples are
recorded. Kept separate from `PredictionRepositoryPort` since latency is an operational metric,
not part of a `Prediction`'s own domain data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from modules.predictions.domain.value_objects import MarketId


class LatencySampleRepositoryPort(Protocol):
    async def record(self, market_id: MarketId, duration_ms: float, now: datetime) -> None: ...
    async def list_recent(self, market_id: MarketId, limit: int = 500) -> list[tuple[float, datetime]]: ...
