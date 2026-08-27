"""News Intelligence audit (2026-08-27) — the first genuinely TEAM-level (not player-role-scoped)
context feature consuming a real extracted `NewsEventType.MANAGER_CHANGE` event: how recently a
team changed its manager, per the master prompt's own Section 13 feature list
(`days_since_manager_change`).

Deliberately NOT built on `NewsMarketImpactEngine`/`MARKET_IMPACT_RULES` (`news_market_impact_
engine.py`, `news_market_impact_registry.py`): that machinery is shaped for a signed,
magnitude-weighted probability *adjustment* (an injury reduces expected goals by some weighted
amount) scanned per player-role across a team's roster. A manager change has no comparable
direction/magnitude to assign — it is a plain elapsed-time signal a model can learn its own
relationship to, the same "let the model determine the numerical consequence, never a hand-picked
adjustment" posture every other real feature in this codebase already takes (see market_seeding.py's
own comment on why fabricated weights are avoided). This calculator is a genuinely new, separate
shape, matching this module's own `TransferActivityCalculator`/`FixtureVenueStrengthCalculator`
convention (registration/store deps, `ensure_registered`, `compute_and_write`) rather than forced
into the injury-shaped engine.

Never assumes "new manager = better/worse" (the master prompt's own explicit warning) — writes
only the honest elapsed time since the most recent feature-eligible, still-valid manager-change
event for this team; the model learns whatever real correlation exists, if any.
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
from modules.intelligence.application.news_provenance import is_information_available_before_kickoff
from modules.intelligence.application.news_validity_policy import validity_window_hours
from modules.intelligence.domain.value_objects import NewsEventType
from modules.intelligence.ports.repositories import NewsEventRepositoryPort
from modules.knowledge_graph.domain.value_objects import NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.sports.domain.value_objects import TeamId

SYSTEM_REVIEWER = "prediction-platform"
ENGINEERED_FEATURE_TTL_SECONDS = 24 * 3600


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as every other duplicate of this helper across this codebase (SQLite/aiosqlite
    drops tzinfo on read-back, docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class ManagerChangeContextCalculator:
    registration: FeatureRegistrationService
    store: FeatureStoreService
    events: NewsEventRepositoryPort
    kg_nodes: KGNodeRepositoryPort
    sport_code: str = "football"

    def feature_key(self, side: str) -> str:
        return f"news.{self.sport_code}.{side}_days_since_manager_change"

    async def ensure_registered(self, now: datetime) -> None:
        for side in ("home", "away"):
            feature_key = self.feature_key(side)
            existing = await self.registration.definitions.get(FeatureKey(feature_key))
            if existing is not None:
                continue
            try:
                await self.registration.register(
                    feature_key,
                    f"{self.sport_code.title()} Days Since Manager Change ({side.title()})",
                    "Elapsed days since this team's most recent verified, still-valid manager-change "
                    "news event — an honest elapsed-time signal, never a hand-picked 'new manager "
                    "effect' adjustment; the model learns whatever real correlation exists.",
                    self.sport_code,
                    FeatureCategory.AI_EXTRACTED,
                    formula="(now - most_recent_feature_eligible_manager_change.occurred_at) in days",
                    data_type=FeatureDataType.FLOAT,
                    owner=SYSTEM_REVIEWER,
                    entity_type=EntityType.FIXTURE,
                    online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
                )
            except FeatureAlreadyRegisteredError:
                continue
            await self.registration.submit_for_review(feature_key)
            await self.registration.approve(feature_key, SYSTEM_REVIEWER, now)
            definition = await self.registration.definitions.get(FeatureKey(feature_key))
            if definition is not None:
                # Same leakage classification every other feature gated on is_feature_eligible()
                # (VERIFIED_PRE_MATCH) already earns — see news_market_impact_engine.py's own comment.
                definition.leakage_classification = "PRE_MATCH_SAFE"
                await self.registration.definitions.upsert(definition)

    async def _most_recent_manager_change(
        self, team_id: TeamId, now: datetime, kickoff: datetime | None,
    ) -> datetime | None:
        node = await self.kg_nodes.get_by_entity_ref(NodeType.TEAM, str(team_id.value))
        if node is None:
            return None

        ttl_hours = validity_window_hours(NewsEventType.MANAGER_CHANGE)
        most_recent: datetime | None = None
        for event in await self.events.list_for_entity(str(node.id)):
            if event.event_type is not NewsEventType.MANAGER_CHANGE:
                continue
            if not event.is_feature_eligible():
                continue
            if kickoff is not None and event.information_available_at is not None:
                available_at = _ensure_aware(event.information_available_at, now)
                if not is_information_available_before_kickoff(available_at, _ensure_aware(kickoff, now)):
                    continue
            occurred_at = _ensure_aware(event.occurred_at, now)
            age_hours = (now - occurred_at).total_seconds() / 3600
            if age_hours < 0 or age_hours > ttl_hours:
                continue  # expired, or (defensively) dated after `now`
            if most_recent is None or occurred_at > most_recent:
                most_recent = occurred_at
        return most_recent

    async def compute_and_write(
        self, fixture_id: str, team_id: TeamId, side: str, now: datetime, kickoff: datetime | None = None,
    ) -> FeatureValue | None:
        """Honest null semantics, matching every other calculator in this module: no feature-
        eligible manager-change event within its own validity window -> writes nothing (`None`,
        genuinely unavailable) — never a fabricated 'stable, no change' default."""
        most_recent = await self._most_recent_manager_change(team_id, now, kickoff)
        if most_recent is None:
            return None
        days_elapsed = (now - most_recent).total_seconds() / 86400
        return await self.store.write(self.feature_key(side), EntityType.FIXTURE, fixture_id, days_elapsed, now)


def football_manager_change_context_calculator(
    registration: FeatureRegistrationService, store: FeatureStoreService,
    events: NewsEventRepositoryPort, kg_nodes: KGNodeRepositoryPort,
) -> ManagerChangeContextCalculator:
    return ManagerChangeContextCalculator(registration=registration, store=store, events=events, kg_nodes=kg_nodes, sport_code="football")
