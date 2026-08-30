"""Repository ports for the Prediction Intelligence Platform's persistence store (Milestone 9).

Concrete implementations live in modules/predictions/infrastructure/persistence — application
code depends only on these Protocols (docs/architecture.md §3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from modules.predictions.domain.entities import (
    Experiment,
    FeatureMarketMapping,
    MarketDefinition,
    ModelDefinition,
    ModelEvaluation,
    Prediction,
    PredictionAudit,
    PredictionCredit,
    PredictionOutcome,
    PredictionRewardEvent,
)
from modules.predictions.domain.calibration import CalibrationReport
from modules.predictions.domain.model_comparison import ChallengerEvaluation
from modules.predictions.domain.value_objects import (
    ExperimentId,
    MarketId,
    MarketStatus,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionStatus,
)


class MarketRepositoryPort(Protocol):
    async def get(self, market_id: MarketId) -> MarketDefinition | None: ...
    async def get_by_key(self, market_key: str) -> MarketDefinition | None: ...
    async def list_by_sport(self, sport_code: str) -> list[MarketDefinition]: ...
    async def list_by_status(self, status: MarketStatus) -> list[MarketDefinition]: ...
    async def list_all(self) -> list[MarketDefinition]: ...
    async def upsert(self, market: MarketDefinition) -> MarketDefinition: ...


class FeatureMarketMappingRepositoryPort(Protocol):
    async def list_by_market(self, market_id: MarketId) -> list[FeatureMarketMapping]: ...
    async def list_by_feature(self, feature_key: str) -> list[FeatureMarketMapping]: ...
    async def upsert(self, mapping: FeatureMarketMapping) -> FeatureMarketMapping: ...


class ModelRepositoryPort(Protocol):
    async def get(self, model_id: ModelId) -> ModelDefinition | None: ...
    async def get_by_key_version(self, model_key: str, version: int) -> ModelDefinition | None: ...
    async def list_by_market(self, market_id: MarketId) -> list[ModelDefinition]: ...
    async def get_champion(self, market_id: MarketId) -> ModelDefinition | None: ...
    async def list_by_status(self, market_id: MarketId, status: ModelStatus) -> list[ModelDefinition]: ...
    async def get_by_market_and_algorithm(self, market_id: MarketId, algorithm: str) -> ModelDefinition | None:
        """Newest model for `(market_id, algorithm)` regardless of CHAMPION/CHALLENGER/RETIRED
        status — a live statistical-baseline lookup (e.g. `StatisticalBaselineProvider`) needs
        the standing Poisson model for a market even when it isn't the current Champion, which
        `get_champion` can't answer."""
        ...
    async def upsert(self, model: ModelDefinition) -> ModelDefinition: ...


class PredictionRepositoryPort(Protocol):
    async def get(self, prediction_id: PredictionId) -> Prediction | None: ...
    async def record(self, prediction: Prediction) -> Prediction: ...
    async def update_status(self, prediction_id: PredictionId, status: PredictionStatus) -> Prediction: ...
    async def list_by_subject(self, subject_ref: str, market_id: MarketId | None = None) -> list[Prediction]: ...
    async def list_by_market(
        self, market_id: MarketId, status: PredictionStatus | None = None, limit: int = 100
    ) -> list[Prediction]: ...
    async def list_recent(self, limit: int = 100) -> list[Prediction]: ...
    async def get_latest_for_subject(self, subject_ref: str, market_id: MarketId) -> Prediction | None: ...
    async def count_by_market(self, market_id: MarketId, status: PredictionStatus | None = None) -> int: ...


class PredictionOutcomeRepositoryPort(Protocol):
    async def record(self, outcome: PredictionOutcome) -> PredictionOutcome: ...

    async def update(self, outcome: PredictionOutcome) -> PredictionOutcome:
        """Corrects an already-resolved outcome in place — real gap found live (2026-08-25): a
        provider can correct a fixture's score after `OutcomeResolutionService` already resolved
        it against the earlier (live/provisional) score, and the service's idempotency guard
        previously skipped re-resolution unconditionally once any outcome existed, permanently
        freezing the wrong `actual_value`/`error` for that prediction. Updates the existing row
        (by `outcome.prediction_id`, a UNIQUE column) rather than inserting a second one."""
        ...

    async def get_for_prediction(self, prediction_id: PredictionId) -> PredictionOutcome | None: ...
    async def list_by_market(self, market_id: MarketId, limit: int = 500) -> list[PredictionOutcome]: ...
    async def count_by_market(self, market_id: MarketId) -> int: ...


class ModelEvaluationRepositoryPort(Protocol):
    async def record(self, evaluation: ModelEvaluation) -> ModelEvaluation: ...
    async def list_by_model(self, model_id: ModelId, limit: int = 50) -> list[ModelEvaluation]: ...
    async def get_latest(self, model_id: ModelId) -> ModelEvaluation | None: ...


class CalibrationReportRepositoryPort(Protocol):
    """Phase 3 (Champion Validation + Calibration) — the missing persistence layer for
    `CalibrationReportBuilder.build()` output. `CalibrationReportModel`/`calibration_reports` has
    existed in the schema since Milestone 9.1 but, until Phase 3, nothing ever wrote a row to it —
    every candidate a calibration comparison evaluates (uncalibrated, sigmoid, isotonic) is
    recorded here, not just the winner, so the comparison itself stays auditable."""

    async def record(self, model_id: ModelId, report: CalibrationReport) -> CalibrationReport: ...
    async def list_by_model(self, model_id: ModelId) -> list[CalibrationReport]: ...


class ExperimentRepositoryPort(Protocol):
    async def get(self, experiment_id: ExperimentId) -> Experiment | None: ...
    async def record(self, experiment: Experiment) -> Experiment: ...
    async def update(self, experiment: Experiment) -> Experiment: ...
    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Experiment]: ...


class PredictionAuditRepositoryPort(Protocol):
    async def record(self, audit: PredictionAudit) -> PredictionAudit: ...
    async def list_by_prediction(self, prediction_id: PredictionId) -> list[PredictionAudit]: ...
    async def list_recent(self, since: datetime | None = None, limit: int = 200) -> list[PredictionAudit]: ...


class PredictionCreditRepositoryPort(Protocol):
    """Mobile V1 monetization. `consume`/`grant` are atomic at the SQL layer (a single guarded
    UPDATE, portable across the Postgres production dialect and the SQLite test dialect — no
    dialect-specific UPSERT), lazily initializing a user's row on first access rather than
    requiring a separate provisioning step."""

    async def get(self, user_id: UUID) -> PredictionCredit | None: ...

    async def get_or_initialize(self, user_id: UUID, initial_free: int, now: datetime) -> PredictionCredit: ...

    async def consume(self, user_id: UUID, initial_free: int, now: datetime) -> PredictionCredit:
        """Raises `PredictionCreditExhaustedError` (never returns a negative balance) when the
        user has 0 available predictions."""
        ...

    async def grant(self, user_id: UUID, credits: int, initial_free: int, now: datetime) -> PredictionCredit: ...


class PredictionRewardEventRepositoryPort(Protocol):
    async def record(self, event: PredictionRewardEvent) -> tuple[PredictionRewardEvent, bool]:
        """Returns `(event, created)` — `created=False` (the pre-existing row is returned
        unchanged) when `provider_event_id` already exists, so a duplicate/replayed reward
        callback is always safe to call this with."""
        ...


class ModelComparisonRepositoryPort(Protocol):
    """Continuous Outcome Learning Engine (2026-08-08) — one row per `ChallengerEvaluationService.evaluate()`
    call, the record a human reviewing a CHALLENGER_BETTER verdict in the Ops Center confirms
    rather than re-derives by hand."""

    async def record(self, evaluation: ChallengerEvaluation) -> ChallengerEvaluation: ...
    async def get_latest(self, market_id: MarketId) -> ChallengerEvaluation | None: ...
    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[ChallengerEvaluation]: ...

    async def get_for_challenger(
        self, market_id: MarketId, challenger_model_id: ModelId
    ) -> ChallengerEvaluation | None:
        """Phase 7 audit fix (2026-08-25): the promotion gate (`ModelRegistryService.
        _require_favorable_comparison`) needs THIS candidate's own comparison, not just "the
        market's most recent N" — `list_by_market(limit=50)` + a client-side filter by
        `challenger_model_id` silently produces a false `COMPARISON_MISSING` once 50+ *other*
        comparisons have been recorded for the same market since this candidate's own (a real risk
        for a market with a fast retraining cadence and a delayed human promotion decision). A
        direct, unbounded lookup by `(market_id, challenger_model_id)` has no such window."""
        ...
