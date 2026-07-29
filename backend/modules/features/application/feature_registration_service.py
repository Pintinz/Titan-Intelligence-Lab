"""Feature registration workflow with a human-gated leakage-review checkpoint
(docs/feature_catalog.md §1, §6). Lifecycle: DRAFT -> IN_REVIEW -> ACTIVE -> DEPRECATED, with
REMOVED as a terminal end-of-life state. Only ACTIVE features are consumable
(FeatureDefinition.is_consumable) — nothing here auto-approves a feature into ACTIVE; that
always requires an explicit `approve()` call naming a human reviewer, mirroring the
Champion/Challenger human-gated promotion pattern used for models (docs/architecture.md
"AI Governance").
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.domain.entities import FeatureDefinition, FeatureDefinitionVersionSnapshot
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort, FeatureVersionRepositoryPort


class FeatureAlreadyRegisteredError(ValueError):
    pass


class FeatureNotFoundError(KeyError):
    pass


class InvalidFeatureDefinitionError(ValueError):
    pass


class InvalidLifecycleTransitionError(ValueError):
    pass


def _as_key(feature_key: str | FeatureKey) -> FeatureKey:
    return feature_key if isinstance(feature_key, FeatureKey) else FeatureKey(feature_key)


@dataclass
class FeatureRegistrationService:
    definitions: FeatureDefinitionRepositoryPort
    versions: FeatureVersionRepositoryPort
    lineage: FeatureLineageService

    async def register(
        self,
        feature_key: str,
        name: str,
        description: str,
        sport_code: str,
        category: FeatureCategory,
        formula: str,
        data_type: FeatureDataType,
        owner: str,
        entity_type: EntityType,
        unit: str | None = None,
        expected_range: tuple[float, float] | None = None,
        update_frequency: str = "unspecified",
        online_ttl_seconds: int = 3600,
        source_provider_key: str | None = None,
        dependencies: tuple[str, ...] = (),
    ) -> FeatureDefinition:
        key = _as_key(feature_key)
        if await self.definitions.get(key) is not None:
            raise FeatureAlreadyRegisteredError(f"feature '{key}' is already registered")
        if not formula.strip():
            raise InvalidFeatureDefinitionError("formula is required — a feature must be reproducible")

        dep_keys = tuple(_as_key(d) for d in dependencies)
        errors = await self.lineage.validate_dependencies(key, dep_keys)
        if errors:
            raise InvalidFeatureDefinitionError("; ".join(errors))

        definition = FeatureDefinition(
            id=FeatureDefinitionId(uuid4()),
            feature_key=key,
            name=name,
            description=description,
            sport_code=sport_code,
            category=category,
            formula=formula,
            data_type=data_type,
            owner=owner,
            entity_type=entity_type,
            unit=unit,
            expected_range=expected_range,
            update_frequency=update_frequency,
            online_ttl_seconds=online_ttl_seconds,
            source_provider_key=source_provider_key,
            dependencies=dep_keys,
            status=FeatureStatus.DRAFT,
            version=1,
        )
        await self.definitions.upsert(definition)
        await self.lineage.record_dependencies(key, dep_keys)
        return definition

    async def submit_for_review(self, feature_key: str) -> FeatureDefinition:
        definition = await self._require(feature_key)
        if definition.status is not FeatureStatus.DRAFT:
            raise InvalidLifecycleTransitionError(
                f"cannot submit '{feature_key}' for review from status {definition.status.value}"
            )
        definition.status = FeatureStatus.IN_REVIEW
        return await self.definitions.upsert(definition)

    async def approve(self, feature_key: str, reviewer: str, now: datetime) -> FeatureDefinition:
        definition = await self._require(feature_key)
        if definition.status is not FeatureStatus.IN_REVIEW:
            raise InvalidLifecycleTransitionError(
                f"cannot approve '{feature_key}' from status {definition.status.value} — must be IN_REVIEW"
            )
        definition.status = FeatureStatus.ACTIVE
        definition.leakage_reviewed = True
        definition.reviewed_by = reviewer
        definition.reviewed_at = now
        definition.rejection_reason = None
        return await self.definitions.upsert(definition)

    async def reject(self, feature_key: str, reviewer: str, reason: str, now: datetime) -> FeatureDefinition:
        definition = await self._require(feature_key)
        if definition.status is not FeatureStatus.IN_REVIEW:
            raise InvalidLifecycleTransitionError(
                f"cannot reject '{feature_key}' from status {definition.status.value} — must be IN_REVIEW"
            )
        definition.status = FeatureStatus.DRAFT
        definition.reviewed_by = reviewer
        definition.reviewed_at = now
        definition.rejection_reason = reason
        return await self.definitions.upsert(definition)

    async def deprecate(self, feature_key: str, now: datetime) -> FeatureDefinition:
        definition = await self._require(feature_key)
        if definition.status is not FeatureStatus.ACTIVE:
            raise InvalidLifecycleTransitionError(
                f"cannot deprecate '{feature_key}' from status {definition.status.value} — must be ACTIVE"
            )
        definition.status = FeatureStatus.DEPRECATED
        definition.deprecated_at = now
        return await self.definitions.upsert(definition)

    async def remove(self, feature_key: str) -> FeatureDefinition:
        definition = await self._require(feature_key)
        if definition.status is not FeatureStatus.DEPRECATED:
            raise InvalidLifecycleTransitionError(
                f"cannot remove '{feature_key}' from status {definition.status.value} — must be DEPRECATED first"
            )
        definition.status = FeatureStatus.REMOVED
        return await self.definitions.upsert(definition)

    async def update_formula(
        self, feature_key: str, new_formula: str, new_dependencies: tuple[str, ...], now: datetime
    ) -> FeatureDefinition:
        """Any formula/dependency change is a new version and resets review to DRAFT — an
        ACTIVE feature's behavior can never silently change under models already trained
        against it."""
        definition = await self._require(feature_key)
        if not new_formula.strip():
            raise InvalidFeatureDefinitionError("formula is required")
        await self._snapshot(definition, now)

        dep_keys = tuple(_as_key(d) for d in new_dependencies)
        errors = await self.lineage.validate_dependencies(definition.feature_key, dep_keys)
        if errors:
            raise InvalidFeatureDefinitionError("; ".join(errors))

        definition.formula = new_formula
        definition.dependencies = dep_keys
        definition.version += 1
        definition.status = FeatureStatus.DRAFT
        definition.leakage_reviewed = False
        definition.reviewed_by = None
        definition.reviewed_at = None
        definition.rejection_reason = None
        await self.lineage.record_dependencies(definition.feature_key, dep_keys)
        return await self.definitions.upsert(definition)

    async def _require(self, feature_key: str) -> FeatureDefinition:
        key = _as_key(feature_key)
        definition = await self.definitions.get(key)
        if definition is None:
            raise FeatureNotFoundError(str(key))
        return definition

    async def _snapshot(self, definition: FeatureDefinition, now: datetime) -> None:
        # `replace()` copies the current field values into a new instance — without this, the
        # snapshot would hold a live reference and silently "rewrite history" the moment the
        # caller mutates `definition` afterward (see update_formula, which snapshots then
        # changes formula/version/status on the same object).
        frozen_copy = replace(definition)
        await self.versions.record(
            FeatureDefinitionVersionSnapshot(
                feature_key=frozen_copy.feature_key, version=frozen_copy.version, snapshot=frozen_copy, recorded_at=now
            )
        )
