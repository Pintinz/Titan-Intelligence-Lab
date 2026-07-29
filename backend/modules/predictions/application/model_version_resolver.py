"""Version Resolver (Milestone 9.1 Model Serving) — resolves which `ModelDefinition` version to
serve for a market: the current CHAMPION by default (the same resolution
`PredictionContextBuilder` already performs, Milestone 9), or a specific pinned version for
reproducibility/shadow-comparison/debugging use cases the champion resolver alone can't serve.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.value_objects import MarketId
from modules.predictions.ports.repositories import ModelRepositoryPort


class ModelVersionNotFoundError(KeyError):
    pass


class PinnedVersionRequiresModelKeyError(ValueError):
    pass


@dataclass
class ModelVersionResolver:
    models: ModelRepositoryPort

    async def resolve(
        self, market_id: MarketId, model_key: str | None = None, pinned_version: int | None = None
    ) -> ModelDefinition:
        if pinned_version is not None:
            if model_key is None:
                raise PinnedVersionRequiresModelKeyError("model_key is required when pinned_version is set")
            model = await self.models.get_by_key_version(model_key, pinned_version)
            if model is None:
                raise ModelVersionNotFoundError(f"'{model_key}' v{pinned_version} not found")
            return model

        champion = await self.models.get_champion(market_id)
        if champion is None:
            raise ModelVersionNotFoundError(f"no champion model for market {market_id}")
        return champion
