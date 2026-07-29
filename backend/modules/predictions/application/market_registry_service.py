"""Market Registry lifecycle service (Milestone 9 Part 2 "Feature Lifecycle" applied to markets;
docs/prediction_markets.md §1 lifecycle: Draft -> Review -> Approved -> Production -> Deprecated
-> Archived -> Removed). Only a PRODUCTION market may participate in prediction generation
(`MarketDefinition.is_production`) — `PredictionEngine` enforces that at generation time, this
service enforces the lifecycle gate that gets a market there in the first place.

Mirrors modules.features.application.feature_registration_service's human-gated review shape:
nothing here auto-approves a market, and promotion to PRODUCTION is additionally gated on the
market having at least one registered required feature (docs/prediction_markets.md: a market
needs "at least one registered, non-leaking feature set" before it can go live — no market may
enter production with zero engineered features backing it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.domain.entities import MarketDefinition
from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, TargetType
from modules.predictions.ports.repositories import FeatureMarketMappingRepositoryPort, MarketRepositoryPort

_TRANSITIONS: dict[MarketStatus, tuple[MarketStatus, ...]] = {
    MarketStatus.DRAFT: (MarketStatus.IN_REVIEW,),
    MarketStatus.IN_REVIEW: (MarketStatus.APPROVED, MarketStatus.DRAFT),
    MarketStatus.APPROVED: (MarketStatus.PRODUCTION,),
    MarketStatus.PRODUCTION: (MarketStatus.DEPRECATED,),
    MarketStatus.DEPRECATED: (MarketStatus.ARCHIVED,),
    MarketStatus.ARCHIVED: (MarketStatus.REMOVED,),
    MarketStatus.REMOVED: (),
}


class MarketAlreadyRegisteredError(ValueError):
    pass


class MarketNotFoundError(KeyError):
    pass


class InvalidMarketLifecycleTransitionError(ValueError):
    pass


class MarketNotReadyForProductionError(ValueError):
    pass


@dataclass
class MarketRegistryService:
    markets: MarketRepositoryPort
    feature_mappings: FeatureMarketMappingRepositoryPort

    async def register(
        self,
        market_key: str,
        sport_code: str,
        name: str,
        category: str,
        market_kind: MarketKind,
        target_type: TargetType,
        description: str = "",
        min_historical_window_days: int = 0,
        required_data_quality: float = 0.0,
        explainability_required: bool = True,
        confidence_threshold: float = 0.5,
        owner: str = "",
        now: datetime | None = None,
    ) -> MarketDefinition:
        if await self.markets.get_by_key(market_key) is not None:
            raise MarketAlreadyRegisteredError(f"market '{market_key}' is already registered")

        market = MarketDefinition(
            id=MarketId(uuid4()),
            market_key=market_key,
            sport_code=sport_code,
            name=name,
            category=category,
            market_kind=market_kind,
            target_type=target_type,
            description=description,
            min_historical_window_days=min_historical_window_days,
            required_data_quality=required_data_quality,
            explainability_required=explainability_required,
            confidence_threshold=confidence_threshold,
            status=MarketStatus.DRAFT,
            owner=owner,
            version=1,
            created_at=now,
            updated_at=now,
        )
        return await self.markets.upsert(market)

    async def submit_for_review(self, market_key: str) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.IN_REVIEW)
        market.status = MarketStatus.IN_REVIEW
        return await self.markets.upsert(market)

    async def approve(self, market_key: str, reviewer: str, now: datetime) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.APPROVED)
        market.status = MarketStatus.APPROVED
        market.reviewed_by = reviewer
        market.reviewed_at = now
        market.rejection_reason = None
        market.updated_at = now
        return await self.markets.upsert(market)

    async def reject(self, market_key: str, reviewer: str, reason: str, now: datetime) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.DRAFT)
        market.status = MarketStatus.DRAFT
        market.reviewed_by = reviewer
        market.reviewed_at = now
        market.rejection_reason = reason
        market.updated_at = now
        return await self.markets.upsert(market)

    async def promote_to_production(self, market_key: str, now: datetime) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.PRODUCTION)

        mappings = await self.feature_mappings.list_by_market(market.id)
        if not any(mapping.is_required for mapping in mappings):
            raise MarketNotReadyForProductionError(
                f"market '{market_key}' has no registered required features — cannot enter production"
            )

        market.status = MarketStatus.PRODUCTION
        market.updated_at = now
        return await self.markets.upsert(market)

    async def deprecate(self, market_key: str, now: datetime) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.DEPRECATED)
        market.status = MarketStatus.DEPRECATED
        market.deprecated_at = now
        market.updated_at = now
        return await self.markets.upsert(market)

    async def archive(self, market_key: str, now: datetime) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.ARCHIVED)
        market.status = MarketStatus.ARCHIVED
        market.updated_at = now
        return await self.markets.upsert(market)

    async def remove(self, market_key: str, now: datetime) -> MarketDefinition:
        market = await self._require(market_key)
        self._check_transition(market, MarketStatus.REMOVED)
        market.status = MarketStatus.REMOVED
        market.updated_at = now
        return await self.markets.upsert(market)

    async def _require(self, market_key: str) -> MarketDefinition:
        market = await self.markets.get_by_key(market_key)
        if market is None:
            raise MarketNotFoundError(market_key)
        return market

    def _check_transition(self, market: MarketDefinition, to: MarketStatus) -> None:
        allowed = _TRANSITIONS[market.status]
        if to not in allowed:
            raise InvalidMarketLifecycleTransitionError(
                f"cannot move market '{market.market_key}' from {market.status.value} to {to.value}"
            )
