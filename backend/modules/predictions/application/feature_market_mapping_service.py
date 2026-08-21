"""Feature-to-Market Registry (Milestone 9 Part 3 "Cross-Sport Rules": "No prediction model may
consume features outside its registered Feature-to-Market mapping."). This service is the single
place a (market, feature) edge gets created, and the single place a market's resolved feature
snapshot gets filtered down to exactly that mapping before it ever reaches a `PredictorPort`.

Depends on modules.features' `FeatureDefinitionRepositoryPort` to enforce a second rule implied
by docs/prediction_markets.md: a market may only be mapped to a feature that is itself an
approved, ACTIVE `FeatureDefinition` (`FeatureDefinition.is_consumable()`) — a DRAFT or
DEPRECATED feature can never back a live prediction market.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from modules.features.domain.value_objects import FeatureKey
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort
from modules.predictions.domain.entities import FeatureMarketMapping
from modules.predictions.domain.value_objects import FeatureMarketMappingId
from modules.predictions.ports.repositories import FeatureMarketMappingRepositoryPort, MarketRepositoryPort


class MarketNotFoundError(KeyError):
    pass


class FeatureNotApprovedError(ValueError):
    pass


class FeatureLeakageRiskError(ValueError):
    """Milestone 4 Rule 8: a feature classified POST_MATCH_ONLY must never enter a market's
    live prediction/training feature set — raised before the mapping is ever created, not
    caught later at training time."""


class MappingAlreadyExistsError(ValueError):
    pass


class MissingRequiredFeatureError(ValueError):
    pass


def _as_key(feature_key: str | FeatureKey) -> FeatureKey:
    return feature_key if isinstance(feature_key, FeatureKey) else FeatureKey(feature_key)


@dataclass
class FeatureMarketMappingService:
    mappings: FeatureMarketMappingRepositoryPort
    markets: MarketRepositoryPort
    feature_definitions: FeatureDefinitionRepositoryPort

    async def map_feature(
        self,
        market_key: str,
        feature_key: str,
        is_required: bool = True,
        importance: float = 0.0,
        confidence_contribution: float = 0.0,
        weight: float = 1.0,
    ) -> FeatureMarketMapping:
        market = await self._require_market(market_key)

        fkey = _as_key(feature_key)
        definition = await self.feature_definitions.get(fkey)
        if definition is None or not definition.is_consumable():
            raise FeatureNotApprovedError(
                f"feature '{feature_key}' is not an ACTIVE registered feature — cannot map it to a market"
            )
        if not definition.is_market_safe():
            raise FeatureLeakageRiskError(
                f"feature '{feature_key}' is classified {definition.leakage_classification} — "
                "POST_MATCH_ONLY features can never back a prediction/training feature set"
            )

        existing = await self.mappings.list_by_market(market.id)
        if any(m.feature_key == str(fkey) for m in existing):
            raise MappingAlreadyExistsError(f"feature '{feature_key}' is already mapped to market '{market_key}'")

        mapping = FeatureMarketMapping(
            id=FeatureMarketMappingId(uuid4()),
            market_id=market.id,
            feature_key=str(fkey),
            is_required=is_required,
            importance=importance,
            confidence_contribution=confidence_contribution,
            weight=weight,
        )
        return await self.mappings.upsert(mapping)

    async def set_required(self, market_key: str, feature_key: str, is_required: bool) -> FeatureMarketMapping:
        """Updates an existing (market, feature) mapping's `is_required` flag in place — the
        update counterpart `map_feature` deliberately lacks (it only ever creates, raising
        `MappingAlreadyExistsError` on a duplicate). Needed because `_seed_market`'s own
        create-only `except MappingAlreadyExistsError: continue` means a market_seeding.py spec
        change never retroactively reaches an already-seeded market's persisted mapping — see
        docs/post_m24_phase17_football_prediction_recovery_report.md."""
        market = await self._require_market(market_key)
        fkey = _as_key(feature_key)
        existing = await self.mappings.list_by_market(market.id)
        mapping = next((m for m in existing if m.feature_key == str(fkey)), None)
        if mapping is None:
            raise KeyError(f"feature '{feature_key}' is not mapped to market '{market_key}' yet")
        updated = FeatureMarketMapping(
            id=mapping.id,
            market_id=mapping.market_id,
            feature_key=mapping.feature_key,
            is_required=is_required,
            importance=mapping.importance,
            confidence_contribution=mapping.confidence_contribution,
            weight=mapping.weight,
        )
        return await self.mappings.upsert(updated)

    async def list_for_market(self, market_key: str) -> list[FeatureMarketMapping]:
        market = await self._require_market(market_key)
        return await self.mappings.list_by_market(market.id)

    async def resolve_feature_snapshot(
        self, market_key: str, available_features: dict[str, float]
    ) -> dict[str, float]:
        """Filters ``available_features`` down to exactly this market's registered mapping — the
        enforcement point for "no prediction model may consume features outside its registered
        Feature-to-Market mapping." Raises if a required feature is absent."""
        mappings = await self.list_for_market(market_key)

        resolved: dict[str, float] = {}
        missing_required: list[str] = []
        for mapping in mappings:
            if mapping.feature_key in available_features:
                resolved[mapping.feature_key] = available_features[mapping.feature_key]
            elif mapping.is_required:
                missing_required.append(mapping.feature_key)

        if missing_required:
            raise MissingRequiredFeatureError(
                f"market '{market_key}' is missing required features: {', '.join(missing_required)}"
            )
        return resolved

    async def _require_market(self, market_key: str):
        market = await self.markets.get_by_key(market_key)
        if market is None:
            raise MarketNotFoundError(market_key)
        return market
