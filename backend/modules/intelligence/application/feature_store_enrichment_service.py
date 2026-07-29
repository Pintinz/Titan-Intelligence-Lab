"""Feature Store Enrichment (Milestone 8 "FEATURE STORE ENRICHMENT": "Publish structured
outputs to the Feature Store. Examples: Injury Impact, Transfer Stability, Manager Stability,
Community Momentum, News Momentum, Squad Availability, Media Pressure, Travel Fatigue, Weather
Impact, Source Reliability. Do NOT compute sport-specific engineered features yet.").

Every feature here is registered with ``sport_code="generic"`` and
``category=FeatureCategory.CONTEXTUAL`` — cross-sport contextual signals derived from news/
community intelligence, not the sport-specific engineered features Milestone 4's Feature
Intelligence Platform builds toward (explicitly out of scope this milestone). Registration goes
through the real DRAFT -> IN_REVIEW -> ACTIVE workflow every other feature uses
(`FeatureRegistrationService`, Milestone 4) rather than bypassing governance with
``require_active=False`` — a "system" reviewer approves them since no human authored these
definitions, but they're consumable exactly like any other ACTIVE feature.

One generic `publish()` plus ten named thin wrappers (one per constitution example) — the same
"one operation, many named callers" shape `ContextEngine`/`SummarizationService` already use.
Each wrapper only pins the correct feature key and `EntityType`; computing the actual value from
an `ImpactScore`/`SentimentResult`/`SourceReliabilityScore` is the caller's job, since each of
those upstream shapes already carries whatever specific number is appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureRegistrationService,
)
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey

GENERIC_SPORT_CODE = "generic"
SYSTEM_REVIEWER = "intelligence-platform"

# feature_key -> (name, description, entity_type)
FEATURE_CATALOG: dict[str, tuple[str, str, EntityType]] = {
    "intelligence.injury_impact": (
        "Injury Impact", "News Impact Engine's injury-severity-weighted impact score.", EntityType.PLAYER,
    ),
    "intelligence.transfer_stability": (
        "Transfer Stability", "Inverse of recent transfer-related news impact for the squad.", EntityType.TEAM,
    ),
    "intelligence.manager_stability": (
        "Manager Stability", "Inverse of recent manager-change-related news impact for the team.", EntityType.TEAM,
    ),
    "intelligence.community_momentum": (
        "Community Momentum", "Recent community sentiment momentum for the entity.", EntityType.TEAM,
    ),
    "intelligence.news_momentum": (
        "News Momentum", "Recent news sentiment momentum for the entity.", EntityType.TEAM,
    ),
    "intelligence.squad_availability": (
        "Squad Availability", "Fraction of the squad without an open injury/suspension/availability concern.",
        EntityType.TEAM,
    ),
    "intelligence.media_pressure": (
        "Media Pressure", "Volume-weighted recent news attention on the entity.", EntityType.TEAM,
    ),
    "intelligence.travel_fatigue": (
        "Travel Fatigue", "Recent travel-delay-related news impact for the team.", EntityType.TEAM,
    ),
    "intelligence.weather_impact": (
        "Weather Impact", "Recent weather-report-related news impact for the fixture/venue.", EntityType.VENUE,
    ),
    "intelligence.source_reliability": (
        "Source Reliability", "Reliability score of the news source reporting on the entity.", EntityType.TEAM,
    ),
}


@dataclass
class FeatureStoreEnrichmentService:
    registration: FeatureRegistrationService
    store: FeatureStoreService

    async def ensure_registered(self, now: datetime) -> None:
        """Idempotent — registers and approves every catalog feature that doesn't already
        exist. Safe to call on every enrichment run/startup."""
        for feature_key, (name, description, entity_type) in FEATURE_CATALOG.items():
            existing = await self.registration.definitions.get(FeatureKey(feature_key))
            if existing is not None:
                continue
            try:
                await self.registration.register(
                    feature_key, name, description, GENERIC_SPORT_CODE, FeatureCategory.CONTEXTUAL,
                    formula="external (news/community intelligence pipeline)", data_type=FeatureDataType.FLOAT,
                    owner=SYSTEM_REVIEWER, entity_type=entity_type,
                )
            except FeatureAlreadyRegisteredError:
                continue
            await self.registration.submit_for_review(feature_key)
            await self.registration.approve(feature_key, SYSTEM_REVIEWER, now)

    async def publish(
        self, feature_key: str, entity_type: EntityType, entity_ref: str, value: float, now: datetime
    ) -> FeatureValue:
        return await self.store.write(feature_key, entity_type, entity_ref, value, now)

    async def publish_injury_impact(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.injury_impact", EntityType.PLAYER, entity_ref, value, now)

    async def publish_transfer_stability(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.transfer_stability", EntityType.TEAM, entity_ref, value, now)

    async def publish_manager_stability(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.manager_stability", EntityType.TEAM, entity_ref, value, now)

    async def publish_community_momentum(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.community_momentum", EntityType.TEAM, entity_ref, value, now)

    async def publish_news_momentum(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.news_momentum", EntityType.TEAM, entity_ref, value, now)

    async def publish_squad_availability(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.squad_availability", EntityType.TEAM, entity_ref, value, now)

    async def publish_media_pressure(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.media_pressure", EntityType.TEAM, entity_ref, value, now)

    async def publish_travel_fatigue(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.travel_fatigue", EntityType.TEAM, entity_ref, value, now)

    async def publish_weather_impact(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.weather_impact", EntityType.VENUE, entity_ref, value, now)

    async def publish_source_reliability(self, entity_ref: str, value: float, now: datetime) -> FeatureValue:
        return await self.publish("intelligence.source_reliability", EntityType.TEAM, entity_ref, value, now)
