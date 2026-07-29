"""Model Registry — Champion/Challenger lifecycle (Milestone 9: "Exactly one CHAMPION per market
at a time", docs/prediction_markets.md "Champion-Challenger Requirement": no market's production
model changes without a documented Champion vs. Candidate offline benchmark recorded in
`predictions.experiments`).

This service enforces the *status* gate and the single-champion invariant only. Whether a
CHALLENGER *should* be promoted — the offline benchmark decision itself — is `Experiment`
territory (a separate concern, recorded before `promote_to_champion` is called); this service
does not re-derive that judgment, it only refuses to leave two CHAMPIONs standing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.value_objects import MarketId, ModelId, ModelStatus
from modules.predictions.ports.repositories import ModelRepositoryPort


class ModelAlreadyRegisteredError(ValueError):
    pass


class ModelNotFoundError(KeyError):
    pass


class InvalidModelLifecycleTransitionError(ValueError):
    pass


class InvalidDeploymentModeError(ValueError):
    pass

_VALID_DEPLOYMENT_MODES = {"shadow", "canary", "live", None}


@dataclass
class ModelRegistryService:
    models: ModelRepositoryPort

    async def register(
        self,
        market_id: MarketId,
        model_key: str,
        version: int,
        algorithm: str,
        training_dataset_ref: str | None = None,
        calibration_ref: str | None = None,
        now: datetime | None = None,
        framework: str | None = None,
        dataset_version: int | None = None,
        feature_versions: dict | None = None,
        training_run_ref: str | None = None,
        calibration_report_ref: str | None = None,
        feature_importance_ref: str | None = None,
        artifact_ref: str | None = None,
        trained_at: datetime | None = None,
    ) -> ModelDefinition:
        if await self.models.get_by_key_version(model_key, version) is not None:
            raise ModelAlreadyRegisteredError(f"model '{model_key}' v{version} is already registered")

        model = ModelDefinition(
            id=ModelId(uuid4()),
            market_id=market_id,
            model_key=model_key,
            version=version,
            algorithm=algorithm,
            status=ModelStatus.CANDIDATE,
            training_dataset_ref=training_dataset_ref,
            calibration_ref=calibration_ref,
            created_at=now,
            framework=framework,
            dataset_version=dataset_version,
            feature_versions=feature_versions or {},
            training_run_ref=training_run_ref,
            calibration_report_ref=calibration_report_ref,
            feature_importance_ref=feature_importance_ref,
            artifact_ref=artifact_ref,
            trained_at=trained_at,
        )
        return await self.models.upsert(model)

    async def set_deployment_mode(self, model_id: ModelId, mode: str | None) -> ModelDefinition:
        """Milestone 9.1 "Deployment Status" — shadow deployment/A-B testing/canary rollout are
        finer-grained than the CANDIDATE/CHALLENGER/CHAMPION/RETIRED lifecycle `status` already
        enforces; this tracks *how* a model (typically a CHALLENGER) is currently being exercised,
        independent of that lifecycle gate."""
        if mode not in _VALID_DEPLOYMENT_MODES:
            raise InvalidDeploymentModeError(f"'{mode}' is not one of {sorted(m for m in _VALID_DEPLOYMENT_MODES if m)}")
        model = await self._require(model_id)
        model.deployment_mode = mode
        return await self.models.upsert(model)

    async def promote_to_challenger(self, model_id: ModelId) -> ModelDefinition:
        model = await self._require(model_id)
        if model.status is not ModelStatus.CANDIDATE:
            raise InvalidModelLifecycleTransitionError(
                f"cannot promote model '{model.model_key}' v{model.version} to CHALLENGER "
                f"from {model.status.value} — must be CANDIDATE"
            )
        model.status = ModelStatus.CHALLENGER
        return await self.models.upsert(model)

    async def promote_to_champion(self, model_id: ModelId, approved_by: str, now: datetime) -> ModelDefinition:
        model = await self._require(model_id)
        if model.status is not ModelStatus.CHALLENGER:
            raise InvalidModelLifecycleTransitionError(
                f"cannot promote model '{model.model_key}' v{model.version} to CHAMPION "
                f"from {model.status.value} — must be CHALLENGER"
            )

        current_champion = await self.models.get_champion(model.market_id)
        if current_champion is not None and current_champion.id != model.id:
            current_champion.status = ModelStatus.RETIRED
            current_champion.retired_at = now
            await self.models.upsert(current_champion)

        model.status = ModelStatus.CHAMPION
        model.approved_by = approved_by
        model.approved_at = now
        model.promoted_at = now
        return await self.models.upsert(model)

    async def rollback(self, market_id: MarketId, now: datetime) -> ModelDefinition:
        """Retires the current champion and reinstates the most recently retired model as
        champion — the Admin Action "Rollback" (Milestone 9 Part 6)."""
        current_champion = await self.models.get_champion(market_id)
        if current_champion is None:
            raise ModelNotFoundError(f"no champion set for market {market_id}")

        retired = await self.models.list_by_status(market_id, ModelStatus.RETIRED)
        if not retired:
            raise ModelNotFoundError(f"no retired model to roll back to for market {market_id}")
        previous = max(retired, key=lambda m: m.retired_at)

        current_champion.status = ModelStatus.RETIRED
        current_champion.retired_at = now
        await self.models.upsert(current_champion)

        previous.status = ModelStatus.CHAMPION
        previous.promoted_at = now
        previous.retired_at = None
        return await self.models.upsert(previous)

    async def retire(self, model_id: ModelId, now: datetime) -> ModelDefinition:
        model = await self._require(model_id)
        if model.status is ModelStatus.RETIRED:
            raise InvalidModelLifecycleTransitionError(f"model '{model.model_key}' v{model.version} already retired")
        model.status = ModelStatus.RETIRED
        model.retired_at = now
        return await self.models.upsert(model)

    async def _require(self, model_id: ModelId) -> ModelDefinition:
        model = await self.models.get(model_id)
        if model is None:
            raise ModelNotFoundError(str(model_id))
        return model
