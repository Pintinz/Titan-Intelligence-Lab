"""Prediction Context Builder (Milestone 9 Part 4 pipeline stage: Feature Store -> Feature
Selection -> Market Selection -> Market Feature Retrieval). Given a market and a subject entity,
assembles everything `PredictionEngine` needs to run a `PredictorPort` and score a
`ConfidenceBreakdown`'s per-feature factors: the PRODUCTION `MarketDefinition`, its CHAMPION
`ModelDefinition`, the resolved feature snapshot (filtered through the market's registered
Feature-to-Market mapping via `FeatureMarketMappingService`), the corresponding mapping weights,
and a per-feature `FeatureConfidenceInput` derived from each `FeatureValue`'s own
`quality_flags`/`as_of` freshness — real signals already recorded at write time by Milestone 4's
Feature Store, not re-derived here.

The six cross-module confidence factors this builder does *not* gather
(`historical_accuracy`, `knowledge_graph_completeness`, `news_reliability`,
`community_reliability`, `model_reliability`, `prediction_stability`) are `PredictionEngine`'s
job (Milestone 9 task #133) — it holds the broader set of service dependencies (Model Registry
history, Knowledge Graph, Source Reliability) this builder deliberately doesn't reach for,
keeping this class scoped to "market + feature store retrieval" only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureKey, QualityFlag
from modules.features.ports.repositories import FeatureValueRepositoryPort
from modules.predictions.application.confidence_engine import FeatureConfidenceInput
from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.ports.repositories import MarketRepositoryPort, ModelRepositoryPort

def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


_QUALITY_SCORES: dict[QualityFlag, float] = {
    QualityFlag.OK: 1.0,
    QualityFlag.STALE: 0.5,
    QualityFlag.MISSING_IMPUTED: 0.4,
    QualityFlag.OUT_OF_RANGE: 0.2,
    QualityFlag.TYPE_MISMATCH: 0.2,
}


class MarketNotFoundError(KeyError):
    pass


class MarketNotInProductionError(ValueError):
    pass


class NoChampionModelError(ValueError):
    pass


@dataclass(frozen=True)
class PredictionContext:
    market: MarketDefinition
    model: ModelDefinition
    resolved_features: dict[str, float]
    mapping_weights: dict[str, float]
    feature_confidence_inputs: tuple[FeatureConfidenceInput, ...]


@dataclass
class PredictionContextBuilder:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    mapping_service: FeatureMarketMappingService
    feature_values: FeatureValueRepositoryPort
    freshness_half_life_seconds: float = 3600.0

    async def build(
        self, market_key: str, entity_type: EntityType, entity_id: str, now: datetime
    ) -> PredictionContext:
        market = await self.markets.get_by_key(market_key)
        if market is None:
            raise MarketNotFoundError(market_key)
        if not market.is_production():
            raise MarketNotInProductionError(
                f"market '{market_key}' is not in PRODUCTION (status={market.status.value})"
            )

        model = await self.models.get_champion(market.id)
        if model is None:
            raise NoChampionModelError(f"market '{market_key}' has no CHAMPION model")

        mappings = await self.mapping_service.list_for_market(market_key)

        available_features: dict[str, float] = {}
        confidence_inputs: list[FeatureConfidenceInput] = []
        for mapping in mappings:
            feature_value = await self.feature_values.get_latest(
                FeatureKey(mapping.feature_key), entity_type, entity_id
            )
            is_present = feature_value is not None and isinstance(feature_value.value, (int, float)) and not isinstance(
                feature_value.value, bool
            )
            if is_present:
                available_features[mapping.feature_key] = float(feature_value.value)

            confidence_inputs.append(
                FeatureConfidenceInput(
                    feature_key=mapping.feature_key,
                    quality_score=self._quality_score(feature_value),
                    freshness_score=self._freshness_score(feature_value, now),
                    is_present=is_present,
                )
            )

        resolved_features = await self.mapping_service.resolve_feature_snapshot(market_key, available_features)
        mapping_weights = {mapping.feature_key: mapping.weight for mapping in mappings}

        return PredictionContext(
            market=market,
            model=model,
            resolved_features=resolved_features,
            mapping_weights=mapping_weights,
            feature_confidence_inputs=tuple(confidence_inputs),
        )

    def _quality_score(self, feature_value: FeatureValue | None) -> float:
        if feature_value is None:
            return 0.0
        return min((_QUALITY_SCORES[flag] for flag in feature_value.quality_flags), default=0.2)

    def _freshness_score(self, feature_value: FeatureValue | None, now: datetime) -> float:
        """Exponential decay against ``freshness_half_life_seconds`` — 1.0 for a value computed
        right now, decaying toward 0 the older ``as_of`` gets."""
        if feature_value is None:
            return 0.0
        as_of = _ensure_aware(feature_value.as_of, now)
        age_seconds = max((now - as_of).total_seconds(), 0.0)
        return math.exp(-age_seconds / self.freshness_half_life_seconds)
