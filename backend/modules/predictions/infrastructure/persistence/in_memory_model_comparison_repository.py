"""In-memory `ModelComparisonRepositoryPort` — same dev/offline-test/composition-wiring default
posture as `InMemoryDatasetRepository` (docs/decisions.md ADR-008): a real implementation, not a
stub, with a SQL-backed one as future work once persistence-across-restarts has a real production
need for this specific data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.model_comparison import ChallengerEvaluation
from modules.predictions.domain.value_objects import MarketId, ModelId


@dataclass
class InMemoryModelComparisonRepository:
    _store: list = field(default_factory=list)  # list[ChallengerEvaluation], insertion order

    async def record(self, evaluation: ChallengerEvaluation) -> ChallengerEvaluation:
        self._store.append(evaluation)
        return evaluation

    async def get_latest(self, market_id: MarketId) -> ChallengerEvaluation | None:
        matches = [e for e in self._store if e.market_id == market_id]
        if not matches:
            return None
        return max(matches, key=lambda e: e.evaluated_at)

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[ChallengerEvaluation]:
        matches = sorted(
            (e for e in self._store if e.market_id == market_id), key=lambda e: e.evaluated_at, reverse=True
        )
        return matches[:limit]

    async def get_for_challenger(self, market_id: MarketId, challenger_model_id: ModelId) -> ChallengerEvaluation | None:
        matches = [
            e for e in self._store if e.market_id == market_id and e.challenger_model_id == challenger_model_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda e: e.evaluated_at)
