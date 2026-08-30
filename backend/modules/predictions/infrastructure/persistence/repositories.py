"""Concrete SQLAlchemy repository implementations of modules.predictions.ports.repositories.

Application-layer code depends only on the ports, never on these classes directly — they're
wired up only in each app's composition module (docs/architecture.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.predictions.domain.calibration import CalibrationReport
from modules.predictions.domain.dataset import Dataset, DatasetId
from modules.predictions.domain.entities import (
    Experiment,
    FeatureMarketMapping,
    MarketDefinition,
    ModelDefinition,
    ModelEvaluation,
    Prediction,
    PredictionAudit,
    PredictionCreditExhaustedError,
    PredictionOutcome,
    PredictionRewardEvent,
)
from modules.predictions.domain.calibration import PlattCalibrationParameters
from modules.predictions.domain.model_comparison import ChallengerEvaluation
from modules.predictions.domain.training_run import TrainingRun, TrainingRunId
from modules.predictions.domain.value_objects import (
    ExperimentId,
    MarketId,
    MarketStatus,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionStatus,
)
from modules.predictions.infrastructure.persistence import mappers
from modules.predictions.infrastructure.persistence import context_review_mapper
from modules.predictions.infrastructure.persistence import football_explanation_mapper
from modules.predictions.infrastructure.persistence.models import (
    CalibrationReportModel,
    ChallengerEvaluationModel,
    DatasetModel,
    ExperimentModel,
    FeatureMarketMappingModel,
    FootballExplanationModel,
    MarketDefinitionModel,
    ModelDefinitionModel,
    ModelEvaluationModel,
    PredictionAuditModel,
    PredictionContextReviewModel,
    PredictionCreditModel,
    CalibrationParametersModel,
    PredictionModel,
    PredictionOutcomeModel,
    PredictionRewardEventModel,
    TrainingRunModel,
)


@dataclass
class SqlAlchemyMarketRepository:
    session: AsyncSession

    async def get(self, market_id: MarketId) -> MarketDefinition | None:
        model = await self.session.get(MarketDefinitionModel, market_id.value)
        return mappers.market_to_domain(model) if model else None

    async def get_by_key(self, market_key: str) -> MarketDefinition | None:
        result = await self.session.execute(
            select(MarketDefinitionModel).where(MarketDefinitionModel.market_key == market_key)
        )
        model = result.scalar_one_or_none()
        return mappers.market_to_domain(model) if model else None

    async def list_by_sport(self, sport_code: str) -> list[MarketDefinition]:
        result = await self.session.execute(
            select(MarketDefinitionModel).where(MarketDefinitionModel.sport_code == sport_code)
        )
        return [mappers.market_to_domain(row) for row in result.scalars().all()]

    async def list_by_status(self, status: MarketStatus) -> list[MarketDefinition]:
        result = await self.session.execute(
            select(MarketDefinitionModel).where(MarketDefinitionModel.status == status.value)
        )
        return [mappers.market_to_domain(row) for row in result.scalars().all()]

    async def list_all(self) -> list[MarketDefinition]:
        result = await self.session.execute(select(MarketDefinitionModel))
        return [mappers.market_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, market: MarketDefinition) -> MarketDefinition:
        existing = await self.session.get(MarketDefinitionModel, market.id.value)
        model = mappers.market_to_model(market, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.market_to_domain(model)


@dataclass
class SqlAlchemyFeatureMarketMappingRepository:
    session: AsyncSession

    async def list_by_market(self, market_id: MarketId) -> list[FeatureMarketMapping]:
        result = await self.session.execute(
            select(FeatureMarketMappingModel).where(FeatureMarketMappingModel.market_id == market_id.value)
        )
        return [mappers.feature_mapping_to_domain(row) for row in result.scalars().all()]

    async def list_by_feature(self, feature_key: str) -> list[FeatureMarketMapping]:
        result = await self.session.execute(
            select(FeatureMarketMappingModel).where(FeatureMarketMappingModel.feature_key == feature_key)
        )
        return [mappers.feature_mapping_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, mapping: FeatureMarketMapping) -> FeatureMarketMapping:
        existing = await self.session.get(FeatureMarketMappingModel, mapping.id.value)
        model = mappers.feature_mapping_to_model(mapping, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.feature_mapping_to_domain(model)


@dataclass
class SqlAlchemyModelRepository:
    session: AsyncSession

    async def get(self, model_id: ModelId) -> ModelDefinition | None:
        model = await self.session.get(ModelDefinitionModel, model_id.value)
        return mappers.model_definition_to_domain(model) if model else None

    async def get_by_key_version(self, model_key: str, version: int) -> ModelDefinition | None:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(
                ModelDefinitionModel.model_key == model_key, ModelDefinitionModel.version == version
            )
        )
        model = result.scalar_one_or_none()
        return mappers.model_definition_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId) -> list[ModelDefinition]:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(ModelDefinitionModel.market_id == market_id.value)
        )
        return [mappers.model_definition_to_domain(row) for row in result.scalars().all()]

    async def get_champion(self, market_id: MarketId) -> ModelDefinition | None:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(
                ModelDefinitionModel.market_id == market_id.value,
                ModelDefinitionModel.status == ModelStatus.CHAMPION.value,
            )
        )
        model = result.scalar_one_or_none()
        return mappers.model_definition_to_domain(model) if model else None

    async def list_by_status(self, market_id: MarketId, status: ModelStatus) -> list[ModelDefinition]:
        result = await self.session.execute(
            select(ModelDefinitionModel).where(
                ModelDefinitionModel.market_id == market_id.value, ModelDefinitionModel.status == status.value
            )
        )
        return [mappers.model_definition_to_domain(row) for row in result.scalars().all()]

    async def get_by_market_and_algorithm(self, market_id: MarketId, algorithm: str) -> ModelDefinition | None:
        result = await self.session.execute(
            select(ModelDefinitionModel)
            .where(ModelDefinitionModel.market_id == market_id.value, ModelDefinitionModel.algorithm == algorithm)
            .order_by(ModelDefinitionModel.version.desc())
        )
        model = result.scalars().first()
        return mappers.model_definition_to_domain(model) if model else None

    async def upsert(self, model: ModelDefinition) -> ModelDefinition:
        existing = await self.session.get(ModelDefinitionModel, model.id.value)
        row = mappers.model_definition_to_model(model, existing)
        self.session.add(row)
        await self.session.flush()
        return mappers.model_definition_to_domain(row)


@dataclass
class SqlAlchemyPredictionRepository:
    session: AsyncSession

    async def get(self, prediction_id: PredictionId) -> Prediction | None:
        model = await self.session.get(PredictionModel, prediction_id.value)
        return mappers.prediction_to_domain(model) if model else None

    async def record(self, prediction: Prediction) -> Prediction:
        model = mappers.prediction_to_model(prediction)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_to_domain(model)

    async def update_status(self, prediction_id: PredictionId, status: PredictionStatus) -> Prediction:
        """The only mutation this repository allows once a prediction has been `record()`ed —
        forensic audit finding #10 (2026-08-30). The generic `update(prediction)` this replaced
        could silently overwrite ANY field, including `value`/`probability`/`feature_snapshot`,
        even though every real caller (`PredictionCacheService.approve`/`reject`/`void`/the
        supersede step in `_persist_new_version`) only ever changed `status`. That was an
        application-layer convention, not something the repository enforced — restricting the
        port to a status-only method makes it structural: there is no longer a method available
        to change a served prediction's numbers after the fact. A new prediction is always a new
        `record()`ed row; the prior one is marked SUPERSEDED, never rewritten."""
        model = await self.session.get(PredictionModel, prediction_id.value)
        if model is None:
            raise KeyError(str(prediction_id))
        model.status = status.value
        await self.session.flush()
        return mappers.prediction_to_domain(model)

    async def list_by_subject(self, subject_ref: str, market_id: MarketId | None = None) -> list[Prediction]:
        stmt = select(PredictionModel).where(PredictionModel.subject_ref == subject_ref)
        if market_id is not None:
            stmt = stmt.where(PredictionModel.market_id == market_id.value)
        stmt = stmt.order_by(PredictionModel.generated_at.desc())
        result = await self.session.execute(stmt)
        return [mappers.prediction_to_domain(row) for row in result.scalars().all()]

    async def list_by_market(
        self, market_id: MarketId, status: PredictionStatus | None = None, limit: int = 100
    ) -> list[Prediction]:
        stmt = select(PredictionModel).where(PredictionModel.market_id == market_id.value)
        if status is not None:
            stmt = stmt.where(PredictionModel.status == status.value)
        stmt = stmt.order_by(PredictionModel.generated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.prediction_to_domain(row) for row in result.scalars().all()]

    async def list_recent(self, limit: int = 100) -> list[Prediction]:
        stmt = select(PredictionModel).order_by(PredictionModel.generated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.prediction_to_domain(row) for row in result.scalars().all()]

    async def get_latest_for_subject(self, subject_ref: str, market_id: MarketId) -> Prediction | None:
        stmt = (
            select(PredictionModel)
            .where(PredictionModel.subject_ref == subject_ref, PredictionModel.market_id == market_id.value)
            .order_by(PredictionModel.generated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.prediction_to_domain(model) if model else None

    async def count_by_market(self, market_id: MarketId, status: PredictionStatus | None = None) -> int:
        stmt = select(func.count()).select_from(PredictionModel).where(PredictionModel.market_id == market_id.value)
        if status is not None:
            stmt = stmt.where(PredictionModel.status == status.value)
        return int((await self.session.execute(stmt)).scalar_one())


@dataclass
class SqlAlchemyPredictionOutcomeRepository:
    session: AsyncSession

    async def record(self, outcome: PredictionOutcome) -> PredictionOutcome:
        model = mappers.prediction_outcome_to_model(outcome)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_outcome_to_domain(model)

    async def update(self, outcome: PredictionOutcome) -> PredictionOutcome:
        result = await self.session.execute(
            select(PredictionOutcomeModel).where(PredictionOutcomeModel.prediction_id == outcome.prediction_id.value)
        )
        model = result.scalar_one()  # caller's responsibility to only update an outcome that exists
        mappers.prediction_outcome_to_model(outcome, model)
        await self.session.flush()
        return mappers.prediction_outcome_to_domain(model)

    async def get_for_prediction(self, prediction_id: PredictionId) -> PredictionOutcome | None:
        result = await self.session.execute(
            select(PredictionOutcomeModel).where(PredictionOutcomeModel.prediction_id == prediction_id.value)
        )
        model = result.scalar_one_or_none()
        return mappers.prediction_outcome_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId, limit: int = 500) -> list[PredictionOutcome]:
        stmt = (
            select(PredictionOutcomeModel)
            .join(PredictionModel, PredictionModel.id == PredictionOutcomeModel.prediction_id)
            .where(PredictionModel.market_id == market_id.value)
            .order_by(PredictionOutcomeModel.evaluated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.prediction_outcome_to_domain(row) for row in result.scalars().all()]

    async def count_by_market(self, market_id: MarketId) -> int:
        stmt = (
            select(func.count())
            .select_from(PredictionOutcomeModel)
            .join(PredictionModel, PredictionModel.id == PredictionOutcomeModel.prediction_id)
            .where(PredictionModel.market_id == market_id.value)
        )
        return int((await self.session.execute(stmt)).scalar_one())


@dataclass
class SqlAlchemyModelEvaluationRepository:
    session: AsyncSession

    async def record(self, evaluation: ModelEvaluation) -> ModelEvaluation:
        model = mappers.model_evaluation_to_model(evaluation)
        self.session.add(model)
        await self.session.flush()
        return mappers.model_evaluation_to_domain(model)

    async def list_by_model(self, model_id: ModelId, limit: int = 50) -> list[ModelEvaluation]:
        stmt = (
            select(ModelEvaluationModel)
            .where(ModelEvaluationModel.model_id == model_id.value)
            .order_by(ModelEvaluationModel.evaluated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.model_evaluation_to_domain(row) for row in result.scalars().all()]

    async def get_latest(self, model_id: ModelId) -> ModelEvaluation | None:
        stmt = (
            select(ModelEvaluationModel)
            .where(ModelEvaluationModel.model_id == model_id.value)
            .order_by(ModelEvaluationModel.evaluated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.model_evaluation_to_domain(model) if model else None


@dataclass
class SqlAlchemyCalibrationReportRepository:
    """Phase 3 — the first real writer `calibration_reports` has ever had (audit finding: the
    table and its ORM class existed since Milestone 9.1 but nothing ever inserted a row)."""

    session: AsyncSession

    async def record(self, model_id: ModelId, report: CalibrationReport) -> CalibrationReport:
        row = CalibrationReportModel(
            model_id=model_id.value,
            method=report.method.value,
            sample_count=report.sample_count,
            expected_calibration_error=report.expected_calibration_error,
            brier_score=report.brier_score,
            reliability_curve={
                "bins": [
                    {
                        "bin_index": b.bin_index,
                        "predicted_mean": b.predicted_mean,
                        "actual_rate": b.actual_rate,
                        "sample_count": b.sample_count,
                    }
                    for b in report.reliability_curve.bins
                ]
            },
            generated_at=report.generated_at,
        )
        self.session.add(row)
        await self.session.flush()
        return report

    async def list_by_model(self, model_id: ModelId) -> list[CalibrationReport]:
        stmt = (
            select(CalibrationReportModel)
            .where(CalibrationReportModel.model_id == model_id.value)
            .order_by(CalibrationReportModel.generated_at.desc())
        )
        result = await self.session.execute(stmt)
        return [mappers.calibration_report_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyContextReviewRepository:
    """Gemini Prediction Reasoning Engine persistence — `record()` overwrites the existing row
    for `prediction_id` if one exists (a fresh review supersedes the prior one for the same
    prediction, per `PredictionContextReviewModel`'s own docstring), rather than accumulating a
    growing history the way `PredictionAuditModel` deliberately does."""

    session: AsyncSession

    async def record(self, prediction_id: PredictionId, review) -> None:
        existing_stmt = select(PredictionContextReviewModel).where(
            PredictionContextReviewModel.prediction_id == prediction_id.value
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        model = context_review_mapper.context_review_to_model(prediction_id, review, existing)
        self.session.add(model)
        await self.session.flush()

    async def get_for_prediction(self, prediction_id: PredictionId):
        stmt = select(PredictionContextReviewModel).where(
            PredictionContextReviewModel.prediction_id == prediction_id.value
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return context_review_mapper.context_review_to_domain(model) if model else None


@dataclass
class SqlAlchemyFootballExplanationRepository:
    """Sports-Analyst Explainability persistence — `record()` overwrites the existing row for
    `prediction_id`, same "current assessment" posture as `SqlAlchemyContextReviewRepository`."""

    session: AsyncSession

    async def record(self, prediction_id: PredictionId, explanation) -> None:
        existing_stmt = select(FootballExplanationModel).where(
            FootballExplanationModel.prediction_id == prediction_id.value
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        model = football_explanation_mapper.football_explanation_to_model(prediction_id, explanation, existing)
        self.session.add(model)
        await self.session.flush()

    async def get_for_prediction(self, prediction_id: PredictionId):
        stmt = select(FootballExplanationModel).where(FootballExplanationModel.prediction_id == prediction_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return football_explanation_mapper.football_explanation_to_domain(model) if model else None


@dataclass
class SqlAlchemyModelComparisonRepository:
    """Continuous Outcome Learning Engine persistence — Phase 3 audit fix: replaces
    `InMemoryModelComparisonRepository` (process-wide, lost on every worker restart) so a
    CHALLENGER_BETTER/CHAMPION_BETTER verdict survives past the process that computed it."""

    session: AsyncSession

    async def record(self, evaluation: ChallengerEvaluation) -> ChallengerEvaluation:
        model = mappers.challenger_evaluation_to_model(evaluation)
        self.session.add(model)
        await self.session.flush()
        return evaluation

    async def get_latest(self, market_id: MarketId) -> ChallengerEvaluation | None:
        stmt = (
            select(ChallengerEvaluationModel)
            .where(ChallengerEvaluationModel.market_id == market_id.value)
            .order_by(ChallengerEvaluationModel.evaluated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.challenger_evaluation_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[ChallengerEvaluation]:
        stmt = (
            select(ChallengerEvaluationModel)
            .where(ChallengerEvaluationModel.market_id == market_id.value)
            .order_by(ChallengerEvaluationModel.evaluated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.challenger_evaluation_to_domain(row) for row in result.scalars().all()]

    async def get_for_challenger(
        self, market_id: MarketId, challenger_model_id: ModelId
    ) -> ChallengerEvaluation | None:
        stmt = (
            select(ChallengerEvaluationModel)
            .where(
                ChallengerEvaluationModel.market_id == market_id.value,
                ChallengerEvaluationModel.challenger_model_id == challenger_model_id.value,
            )
            .order_by(ChallengerEvaluationModel.evaluated_at.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.challenger_evaluation_to_domain(model) if model else None


@dataclass
class SqlAlchemyTrainingRunRepository:
    """The audit trail behind `ModelDefinition.training_run_ref` — one row per
    `AutomaticModelSelectionService.select_and_register_challenger()` call's winning candidate."""

    session: AsyncSession

    async def record(self, run: TrainingRun) -> TrainingRun:
        model = mappers.training_run_to_model(run)
        self.session.add(model)
        await self.session.flush()
        return run

    async def get(self, run_id: TrainingRunId) -> TrainingRun | None:
        stmt = select(TrainingRunModel).where(TrainingRunModel.id == run_id.value)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.training_run_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[TrainingRun]:
        stmt = (
            select(TrainingRunModel)
            .where(TrainingRunModel.market_id == market_id.value)
            .order_by(TrainingRunModel.completed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.training_run_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyCalibrationParametersRepository:
    """The durable store behind `PlattScalingCalibrator` — one row per model, upserted on every
    `fit()` and read through on a `calibrate()` cache miss, so a fit reaches every process
    regardless of which one ran it (Phase 3 audit fix)."""

    session: AsyncSession

    async def get(self, model_id: ModelId) -> PlattCalibrationParameters | None:
        model = await self.session.get(CalibrationParametersModel, model_id.value)
        return mappers.platt_calibration_parameters_to_domain(model) if model else None

    async def upsert(self, params: PlattCalibrationParameters) -> PlattCalibrationParameters:
        existing = await self.session.get(CalibrationParametersModel, params.model_id.value)
        model = mappers.platt_calibration_parameters_to_model(params, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.platt_calibration_parameters_to_domain(model)


@dataclass
class SqlAlchemyExperimentRepository:
    session: AsyncSession

    async def get(self, experiment_id: ExperimentId) -> Experiment | None:
        model = await self.session.get(ExperimentModel, experiment_id.value)
        return mappers.experiment_to_domain(model) if model else None

    async def record(self, experiment: Experiment) -> Experiment:
        model = mappers.experiment_to_model(experiment)
        self.session.add(model)
        await self.session.flush()
        return mappers.experiment_to_domain(model)

    async def update(self, experiment: Experiment) -> Experiment:
        existing = await self.session.get(ExperimentModel, experiment.id.value)
        model = mappers.experiment_to_model(experiment, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.experiment_to_domain(model)

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Experiment]:
        stmt = (
            select(ExperimentModel)
            .where(ExperimentModel.market_id == market_id.value)
            .order_by(ExperimentModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.experiment_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyPredictionAuditRepository:
    session: AsyncSession

    async def record(self, audit: PredictionAudit) -> PredictionAudit:
        model = mappers.prediction_audit_to_model(audit)
        self.session.add(model)
        await self.session.flush()
        return mappers.prediction_audit_to_domain(model)

    async def list_by_prediction(self, prediction_id: PredictionId) -> list[PredictionAudit]:
        stmt = (
            select(PredictionAuditModel)
            .where(PredictionAuditModel.prediction_id == prediction_id.value)
            .order_by(PredictionAuditModel.occurred_at.asc())
        )
        result = await self.session.execute(stmt)
        return [mappers.prediction_audit_to_domain(row) for row in result.scalars().all()]

    async def list_recent(self, since: datetime | None = None, limit: int = 200) -> list[PredictionAudit]:
        stmt = select(PredictionAuditModel)
        if since is not None:
            stmt = stmt.where(PredictionAuditModel.occurred_at >= since)
        stmt = stmt.order_by(PredictionAuditModel.occurred_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return [mappers.prediction_audit_to_domain(row) for row in result.scalars().all()]


@dataclass
class SqlAlchemyDatasetRepository:
    """Milestone 20: closes the `dataset_provenance_persisted` gap `TrainingPreflightService`
    (Milestone 19) surfaced — the `datasets` table has existed since Milestone 4/9
    (`DatasetModel`); this is the first repository to actually read/write it."""

    session: AsyncSession

    async def get(self, dataset_id: DatasetId) -> Dataset | None:
        model = await self.session.get(DatasetModel, dataset_id.value)
        return mappers.dataset_to_domain(model) if model else None

    async def get_latest_version(self, market_id: MarketId) -> Dataset | None:
        stmt = (
            select(DatasetModel)
            .where(DatasetModel.market_id == market_id.value)
            .order_by(DatasetModel.version.desc())
            .limit(1)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return mappers.dataset_to_domain(model) if model else None

    async def list_by_market(self, market_id: MarketId, limit: int = 50) -> list[Dataset]:
        stmt = (
            select(DatasetModel)
            .where(DatasetModel.market_id == market_id.value)
            .order_by(DatasetModel.version.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [mappers.dataset_to_domain(row) for row in result.scalars().all()]

    async def upsert(self, dataset: Dataset) -> Dataset:
        existing = await self.session.get(DatasetModel, dataset.id.value)
        model = mappers.dataset_to_model(dataset, existing)
        self.session.add(model)
        await self.session.flush()
        return mappers.dataset_to_domain(model)


@dataclass
class SqlAlchemyPredictionCreditRepository:
    """`consume`/`grant` use a Core-level guarded `UPDATE` (never read-modify-write in Python) so
    concurrent requests for the same user serialize correctly on Postgres's row lock — the second
    of two simultaneous `consume` calls re-evaluates `available_predictions > 0` against the
    first's already-committed result, never against a value read before the first's write landed.
    `begin_nested()` (a SAVEPOINT) wraps the lazy-init INSERT so a concurrent duplicate-insert race
    only rolls back that one INSERT, never the rest of the caller's transaction."""

    session: AsyncSession

    async def _get_model(self, user_id: UUID) -> PredictionCreditModel | None:
        stmt = select(PredictionCreditModel).where(PredictionCreditModel.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_or_initialize_model(self, user_id: UUID, initial_free: int, now: datetime) -> PredictionCreditModel:
        existing = await self._get_model(user_id)
        if existing is not None:
            return existing
        model = PredictionCreditModel(
            user_id=user_id,
            available_predictions=initial_free,
            lifetime_free_predictions_used=0,
            rewarded_predictions_granted=0,
            rewarded_ads_completed=0,
            created_at=now,
            updated_at=now,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(model)
                await self.session.flush()
        except IntegrityError:
            existing = await self._get_model(user_id)
            if existing is None:
                raise  # not a duplicate-user_id race after all — a real, unexpected failure
            return existing
        return model

    async def get(self, user_id: UUID) -> PredictionCredit | None:
        model = await self._get_model(user_id)
        return mappers.prediction_credit_to_domain(model) if model else None

    async def get_or_initialize(self, user_id: UUID, initial_free: int, now: datetime) -> PredictionCredit:
        return mappers.prediction_credit_to_domain(await self._get_or_initialize_model(user_id, initial_free, now))

    async def consume(self, user_id: UUID, initial_free: int, now: datetime) -> PredictionCredit:
        credit_model = await self._get_or_initialize_model(user_id, initial_free, now)
        stmt = (
            update(PredictionCreditModel)
            .where(PredictionCreditModel.user_id == user_id, PredictionCreditModel.available_predictions > 0)
            .values(
                available_predictions=PredictionCreditModel.available_predictions - 1,
                lifetime_free_predictions_used=PredictionCreditModel.lifetime_free_predictions_used + 1,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            raise PredictionCreditExhaustedError(f"user {user_id} has no available prediction credits")
        await self.session.refresh(credit_model)
        return mappers.prediction_credit_to_domain(credit_model)

    async def grant(self, user_id: UUID, credits: int, initial_free: int, now: datetime) -> PredictionCredit:
        credit_model = await self._get_or_initialize_model(user_id, initial_free, now)
        stmt = (
            update(PredictionCreditModel)
            .where(PredictionCreditModel.user_id == user_id)
            .values(
                available_predictions=PredictionCreditModel.available_predictions + credits,
                rewarded_predictions_granted=PredictionCreditModel.rewarded_predictions_granted + credits,
                rewarded_ads_completed=PredictionCreditModel.rewarded_ads_completed + 1,
                updated_at=now,
            )
        )
        await self.session.execute(stmt)
        await self.session.refresh(credit_model)
        return mappers.prediction_credit_to_domain(credit_model)


@dataclass
class SqlAlchemyPredictionRewardEventRepository:
    session: AsyncSession

    async def record(self, event: PredictionRewardEvent) -> tuple[PredictionRewardEvent, bool]:
        model = PredictionRewardEventModel(
            id=event.id.value,
            user_id=event.user_id,
            provider=event.provider,
            reward_type=event.reward_type,
            credits_granted=event.credits_granted,
            provider_event_id=event.provider_event_id,
            status=event.status,
            created_at=event.created_at,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(model)
                await self.session.flush()
        except IntegrityError:
            stmt = select(PredictionRewardEventModel).where(
                PredictionRewardEventModel.provider_event_id == event.provider_event_id
            )
            existing = (await self.session.execute(stmt)).scalar_one_or_none()
            if existing is None:
                raise  # not a duplicate-event race after all — a real, unexpected failure
            return mappers.prediction_reward_event_to_domain(existing), False
        return mappers.prediction_reward_event_to_domain(model), True
