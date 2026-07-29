"""In-memory `LatencySampleRepositoryPort` — the dev/offline-test adapter (docs/decisions.md
ADR-008 mock-first/adapter-swap posture). A future Redis-backed adapter (reusing Milestone 5's
generic distributed cache) implements the same port for production without
`ModelMonitoringService` changing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.predictions.domain.value_objects import MarketId


@dataclass
class InMemoryLatencySampleRepository:
    _store: dict = field(default_factory=dict)  # MarketId -> list[(duration_ms, recorded_at)]

    async def record(self, market_id: MarketId, duration_ms: float, now: datetime) -> None:
        self._store.setdefault(market_id, []).append((duration_ms, now))

    async def list_recent(self, market_id: MarketId, limit: int = 500) -> list[tuple[float, datetime]]:
        samples = self._store.get(market_id, [])
        return samples[-limit:]
