from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
)
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.training_preflight_service import TrainingPreflightService
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    FeatureMarketMapping,
    MarketDefinition,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.value_objects import (
    FeatureMarketMappingId,
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)

T0 = datetime(2026, 8, 12, tzinfo=timezone.utc)
MARKET_KEY = "football.preflight_test_market"


@pytest.fixture
def builder(market_repo, prediction_repo, prediction_outcome_repo):
    return DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo)


@pytest.fixture
def service(market_repo, feature_mapping_repo, feature_definition_repo, builder, dataset_repo):
    return TrainingPreflightService(
        markets=market_repo,
        mappings=feature_mapping_repo,
        feature_definitions=feature_definition_repo,
        dataset_builder=builder,
        dataset_repo=dataset_repo,
    )


async def _market(market_repo, key: str = MARKET_KEY) -> MarketDefinition:
    market = MarketDefinition(
        id=MarketId(uuid4()),
        market_key=key,
        sport_code="football",
        name="Preflight Test Market",
        category="match_outcome",
        market_kind=MarketKind.TOTAL,
        target_type=TargetType.REGRESSION,
        status=MarketStatus.PRODUCTION,
    )
    return await market_repo.upsert(market)


def _prediction(market_id, feature_snapshot, value):
    return Prediction(
        id=PredictionId(uuid4()),
        market_id=market_id,
        model_id=ModelId(uuid4()),
        subject_ref="fixture-1",
        value=value,
        probability=0.6,
        confidence=ConfidenceBreakdown(*([0.7] * 9)),
        explanation=ExplanationBundle(),
        feature_snapshot=feature_snapshot,
        model_version="1",
        status=PredictionStatus.PUBLISHED,
        generated_at=T0,
    )


async def _seed(market, prediction_repo, prediction_outcome_repo, n, feature_fn, ref_time_fn=None):
    ref_time_fn = ref_time_fn or (lambda i: T0)
    for i in range(n):
        prediction = await prediction_repo.record(
            _prediction(market.id, feature_fn(i), value=f"{float(i):.4f}")
        )
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                actual_value=f"{float(i):.4f}", error=0.0, evaluated_at=ref_time_fn(i),
            )
        )


async def _feature(
    feature_definition_repo, key: str, status: FeatureStatus = FeatureStatus.ACTIVE,
    leakage_classification: str = "PRE_MATCH_SAFE",
) -> FeatureDefinition:
    definition = FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey(key),
        name=key,
        description="test feature",
        sport_code="football",
        category=FeatureCategory.ENGINEERED,
        formula="test",
        data_type=FeatureDataType.FLOAT,
        owner="data-team",
        entity_type=EntityType.FIXTURE,
        status=status,
        leakage_classification=leakage_classification,
    )
    return await feature_definition_repo.upsert(definition)


async def _map(feature_mapping_repo, market_id, feature_key: str, is_required: bool = True):
    mapping = FeatureMarketMapping(
        id=FeatureMarketMappingId(uuid4()), market_id=market_id, feature_key=feature_key, is_required=is_required,
    )
    return await feature_mapping_repo.upsert(mapping)


class TestMarketNotFound:
    async def test_reports_single_blocking_check(self, service):
        report = await service.check("football.does_not_exist", T0)

        assert report.ready is False
        assert [c.name for c in report.checks] == ["market_exists"]
        assert report.blocking()[0].name == "market_exists"


class TestFullyReadyMarket:
    async def test_every_check_passes(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo,
        prediction_outcome_repo, dataset_repo,
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _feature(feature_definition_repo, "core.feature_b")
        await _map(feature_mapping_repo, market.id, "core.feature_a", is_required=True)
        await _map(feature_mapping_repo, market.id, "core.feature_b", is_required=False)
        await _seed(
            market, prediction_repo, prediction_outcome_repo, 40,
            feature_fn=lambda i: {"core.feature_a": float(i), "core.feature_b": float(i) * 2},
            ref_time_fn=lambda i: datetime(2026, 8, 1, tzinfo=timezone.utc).replace(hour=i % 24),
        )
        # Simulate a durably persisted dataset (the M19 audit's blocker #2 — not present today in
        # production, but the check must honestly report READY once persistence exists).
        prebuilt = await DatasetBuilder(
            markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo
        ).build(market.id, T0)
        await dataset_repo.upsert(prebuilt)

        report = await service.check(MARKET_KEY, T0)

        failing = [c.name for c in report.blocking()]
        assert failing == [], f"unexpected failing checks: {failing}"
        assert report.ready is True


class TestInsufficientObservations:
    async def test_blocks_readiness(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _map(feature_mapping_repo, market.id, "core.feature_a")
        await _seed(market, prediction_repo, prediction_outcome_repo, 5, feature_fn=lambda i: {"core.feature_a": float(i)})

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        check = next(c for c in report.checks if c.name == "sufficient_labeled_observations")
        assert check.passed is False


class TestMissingTemporalReference:
    async def test_blocks_readiness(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _map(feature_mapping_repo, market.id, "core.feature_a")
        await _seed(
            market, prediction_repo, prediction_outcome_repo, 40,
            feature_fn=lambda i: {"core.feature_a": float(i)},
            ref_time_fn=lambda i: None,  # a defensive edge case — evaluated_at should never be None
        )

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        temporal = next(c for c in report.checks if c.name == "temporal_reference_present")
        assert temporal.passed is False
        split_check = next(c for c in report.checks if c.name == "temporal_split_valid")
        assert split_check.passed is False


class TestTrainingInferenceFeatureParity:
    async def test_required_feature_never_present_in_training_data_blocks_readiness(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        """Mirrors the exact M19 audit finding: a feature declared `is_required=True` for live
        inference that has never once appeared in a historical `feature_snapshot`."""
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _feature(feature_definition_repo, "gated.never_trained")
        await _map(feature_mapping_repo, market.id, "core.feature_a", is_required=True)
        await _map(feature_mapping_repo, market.id, "gated.never_trained", is_required=True)
        await _seed(market, prediction_repo, prediction_outcome_repo, 40, feature_fn=lambda i: {"core.feature_a": float(i)})

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        parity = next(c for c in report.checks if c.name == "training_inference_feature_parity")
        assert parity.passed is False
        assert "gated.never_trained" in parity.detail


class TestRequiredFeatureCoverage:
    async def test_low_coverage_blocks_readiness(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.sometimes_present")
        await _map(feature_mapping_repo, market.id, "core.sometimes_present", is_required=True)
        # Present in only 10 of 40 samples (25% coverage, 75% missing >= 50% threshold).
        await _seed(
            market, prediction_repo, prediction_outcome_repo, 40,
            feature_fn=lambda i: {"core.sometimes_present": float(i)} if i < 10 else {},
        )

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        coverage = next(c for c in report.checks if c.name == "required_feature_coverage_acceptable")
        assert coverage.passed is False
        assert "core.sometimes_present" in coverage.detail


class TestLeakageSafety:
    async def test_post_match_only_required_feature_blocks_readiness(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "unsafe.feature", leakage_classification="POST_MATCH_ONLY")
        await _map(feature_mapping_repo, market.id, "unsafe.feature", is_required=True)
        await _seed(
            market, prediction_repo, prediction_outcome_repo, 40,
            feature_fn=lambda i: {"unsafe.feature": float(i)},
        )

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        leakage = next(c for c in report.checks if c.name == "intelligence_feature_leakage_safe")
        assert leakage.passed is False
        assert "unsafe.feature" in leakage.detail


class TestFeatureVersionsKnown:
    async def test_unregistered_feature_definition_blocks_readiness(
        self, service, market_repo, feature_mapping_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        # Mapped but never registered as a FeatureDefinition — feature_definition_repo stays empty.
        await _map(feature_mapping_repo, market.id, "unregistered.feature", is_required=True)
        await _seed(
            market, prediction_repo, prediction_outcome_repo, 40,
            feature_fn=lambda i: {"unregistered.feature": float(i)},
        )

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        versions = next(c for c in report.checks if c.name == "feature_versions_known")
        assert versions.passed is False


class TestFeatureManifestDeclared:
    async def test_no_mappings_blocks_readiness(
        self, service, market_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _seed(market, prediction_repo, prediction_outcome_repo, 40, feature_fn=lambda i: {"x": float(i)})

        report = await service.check(MARKET_KEY, T0)

        assert report.ready is False
        manifest = next(c for c in report.checks if c.name == "feature_manifest_declared")
        assert manifest.passed is False


class TestDatasetProvenancePersisted:
    async def test_reports_blocked_when_dataset_never_persisted(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _map(feature_mapping_repo, market.id, "core.feature_a")
        await _seed(market, prediction_repo, prediction_outcome_repo, 40, feature_fn=lambda i: {"core.feature_a": float(i)})

        report = await service.check(MARKET_KEY, T0)

        provenance = next(c for c in report.checks if c.name == "dataset_provenance_persisted")
        assert provenance.passed is False
        assert "in-memory-only" in provenance.detail


class TestDatasetReproducibility:
    async def test_content_hash_stable_across_builds(
        self, service, market_repo, feature_mapping_repo, feature_definition_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await _market(market_repo)
        await _feature(feature_definition_repo, "core.feature_a")
        await _map(feature_mapping_repo, market.id, "core.feature_a")
        await _seed(market, prediction_repo, prediction_outcome_repo, 40, feature_fn=lambda i: {"core.feature_a": float(i)})

        report = await service.check(MARKET_KEY, T0)

        reproducible = next(c for c in report.checks if c.name == "dataset_reproducible")
        assert reproducible.passed is True
