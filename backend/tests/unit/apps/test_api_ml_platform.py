from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import get_dataset_repo, get_jwt_validator, get_session
from apps.api.main import app
from modules.identity.domain.value_objects import Email, Role
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.identity.infrastructure.persistence.repositories import SqlAlchemyUserRepository
from modules.identity.infrastructure.security import MockJWTValidator
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.value_objects import MarketId, MarketKind, MarketStatus, ModelId, ModelStatus, TargetType
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository, SqlAlchemyModelRepository
from modules.sports.infrastructure.persistence.models import Base as SportsBase

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={
            "schema_translate_map": {
                "identity": None, "predictions": None, "features": None, "sports": None,
                "intelligence": None, "knowledge_graph": None,
            }
        },
    )
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all)
        await conn.run_sync(PredictionsBase.metadata.create_all)
        await conn.run_sync(FeaturesBase.metadata.create_all)
        await conn.run_sync(SportsBase.metadata.create_all)
        await conn.run_sync(IntelligenceBase.metadata.create_all)
        await conn.run_sync(KnowledgeGraphBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(db_session_factory):
    async def override_get_session():
        async with db_session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_validator] = lambda: MockJWTValidator()
    get_dataset_repo.cache_clear()  # process-wide singleton — start each test with an empty registry
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_dataset_repo.cache_clear()


async def _promote_to_admin(db_session_factory, email: str) -> None:
    async with db_session_factory() as session:
        users = SqlAlchemyUserRepository(session=session)
        user = await users.get_by_email(Email(email))
        user.role = Role.ADMINISTRATOR
        await users.upsert(user)
        await session.commit()


def _admin_headers(client, db_session_factory, email="ml-admin@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    asyncio.run(_promote_to_admin(db_session_factory, email))
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _regular_headers(client, email="ml-regular@titaniq.test", password="correct-horse-battery"):
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _seed_market(db_session_factory, market_key: str, with_champion: bool = True) -> MarketId:
    async with db_session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        from modules.predictions.domain.entities import MarketDefinition

        market = MarketDefinition(
            id=MarketId(uuid4()), market_key=market_key, sport_code="football", name="Test Market",
            category="match_outcome", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
            status=MarketStatus.PRODUCTION,
        )
        await markets.upsert(market)

        if with_champion:
            models = SqlAlchemyModelRepository(session=session)
            model = ModelDefinition(
                id=ModelId(uuid4()), market_id=market.id, model_key=f"{market_key}.heuristic", version=1,
                algorithm="heuristic_logistic_v1", status=ModelStatus.CHAMPION,
            )
            await models.upsert(model)

        await session.commit()
        return market.id


class TestRoleGating:
    def test_non_admin_is_forbidden_from_mutation_endpoints(self, client, db_session_factory):
        headers = _regular_headers(client)
        response = client.get("/api/v1/admin/ml/experiments/does.not.exist", headers=headers)
        assert response.status_code == 403

    def test_non_admin_is_forbidden_from_monitoring_endpoints(self, client, db_session_factory):
        headers = _regular_headers(client)
        response = client.get("/api/v1/admin/ml/monitoring/does.not.exist/health", headers=headers)
        assert response.status_code == 403

    def test_non_admin_can_read_the_four_end_user_learning_endpoints(self, client, db_session_factory):
        """`list_models`, `resolve_champion`, `champion_feature_importance`, and
        `list_model_evaluations` back the public Learning Intelligence page — they're
        deliberately gated at plain authentication, not Role.ADMINISTRATOR, matching every
        other read-only router in the app. A 404 here (not 403) proves the request cleared
        auth and only failed on "market not found", which is what a regular authenticated
        user hitting an unknown market should see."""
        headers = _regular_headers(client)

        assert client.get("/api/v1/admin/ml/models/does.not.exist", headers=headers).status_code == 404
        assert client.get("/api/v1/admin/ml/champion/does.not.exist", headers=headers).status_code == 404
        assert client.get("/api/v1/admin/ml/feature-importance/does.not.exist", headers=headers).status_code == 404
        assert client.get(f"/api/v1/admin/ml/evaluation/{uuid4()}", headers=headers).status_code == 200


class TestTrainingDatasets:
    def test_build_dataset_for_unknown_market_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        response = client.post("/api/v1/admin/ml/training/datasets/does.not.exist/build", headers=headers)
        assert response.status_code == 404

    def test_build_dataset_reports_too_few_samples(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_dataset_market"))

        response = client.post("/api/v1/admin/ml/training/datasets/football.ml_dataset_market/build", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"]["sample_count"] == 0
        assert "too_few_samples" in response.json()["data"]["quality_issues"]

    def test_validate_dataset_with_too_few_samples_returns_409(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_validate_market"))
        built = client.post("/api/v1/admin/ml/training/datasets/football.ml_validate_market/build", headers=headers).json()["data"]

        response = client.post(f"/api/v1/admin/ml/training/datasets/{built['id']}/validate", headers=headers)

        assert response.status_code == 409

    def test_validate_unknown_dataset_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        response = client.post(f"/api/v1/admin/ml/training/datasets/{uuid4()}/validate", headers=headers)
        assert response.status_code == 404

    def test_select_champion_without_approved_dataset_returns_409(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_select_champion_market"))

        response = client.post(
            "/api/v1/admin/ml/training/select-champion",
            json={"market_key": "football.ml_select_champion_market", "model_key_prefix": "football.match_result"},
            headers=headers,
        )

        assert response.status_code == 409


class TestExperiments:
    def test_list_experiments_for_unknown_market_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        response = client.get("/api/v1/admin/ml/experiments/does.not.exist", headers=headers)
        assert response.status_code == 404

    def test_list_experiments_for_market_with_none_returns_empty(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_experiments_market"))

        response = client.get("/api/v1/admin/ml/experiments/football.ml_experiments_market", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_decide_unknown_experiment_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        response = client.post(f"/api/v1/admin/ml/experiments/{uuid4()}/decide", json={"decision": "promoted"}, headers=headers)
        assert response.status_code == 404


class TestModelRegistry:
    def test_list_models_for_market(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_models_market"))

        response = client.get("/api/v1/admin/ml/models/football.ml_models_market", headers=headers)

        assert response.status_code == 200
        assert response.json()["meta"]["count"] == 1
        assert response.json()["data"][0]["status"] == "champion"

    def test_set_deployment_mode(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_deployment_market"))
        model_id = client.get("/api/v1/admin/ml/models/football.ml_deployment_market", headers=headers).json()["data"][0]["id"]

        response = client.post(f"/api/v1/admin/ml/models/{model_id}/deployment-mode", json={"mode": "shadow"}, headers=headers)

        assert response.status_code == 200
        assert response.json()["data"]["deployment_mode"] == "shadow"

    def test_set_invalid_deployment_mode_returns_422(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_bad_deployment_market"))
        model_id = client.get("/api/v1/admin/ml/models/football.ml_bad_deployment_market", headers=headers).json()["data"][0]["id"]

        response = client.post(f"/api/v1/admin/ml/models/{model_id}/deployment-mode", json={"mode": "not-a-mode"}, headers=headers)

        assert response.status_code == 422


class TestChampion:
    def test_resolve_champion(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_champion_market"))

        response = client.get("/api/v1/admin/ml/champion/football.ml_champion_market", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "champion"

    def test_resolve_champion_missing_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_no_champion_market", with_champion=False))

        response = client.get("/api/v1/admin/ml/champion/football.ml_no_champion_market", headers=headers)

        assert response.status_code == 404

    def test_promote_champion_requires_challenger_status(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_promote_market"))
        model_id = client.get("/api/v1/admin/ml/models/football.ml_promote_market", headers=headers).json()["data"][0]["id"]

        response = client.post(f"/api/v1/admin/ml/champion/{model_id}/promote", json={"approved_by": "cto"}, headers=headers)

        assert response.status_code == 409  # already CHAMPION, not CHALLENGER


class TestFeatureImportance:
    def test_weighted_champion_has_no_model_to_explain(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_feature_importance_market"))

        response = client.get("/api/v1/admin/ml/feature-importance/football.ml_feature_importance_market", headers=headers)

        assert response.status_code == 409

    def test_unknown_market_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        response = client.get("/api/v1/admin/ml/feature-importance/does.not.exist", headers=headers)
        assert response.status_code == 404

    def test_market_with_no_champion_returns_404(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_no_champion_importance_market", with_champion=False))

        response = client.get("/api/v1/admin/ml/feature-importance/football.ml_no_champion_importance_market", headers=headers)

        assert response.status_code == 404


class TestCalibration:
    def test_build_calibration_report(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)

        response = client.post(
            "/api/v1/admin/ml/calibration/reports",
            json={"method": "platt_scaling", "samples": [[0.9, True]] * 90 + [[0.9, False]] * 10},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["data"]["sample_count"] == 100
        assert response.json()["data"]["expected_calibration_error"] == pytest.approx(0.0, abs=1e-6)

    def test_unrecognized_method_returns_422(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        response = client.post(
            "/api/v1/admin/ml/calibration/reports", json={"method": "not-a-method", "samples": []}, headers=headers
        )
        assert response.status_code == 422


class TestBenchmark:
    def test_benchmark_without_approved_dataset_returns_409(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_benchmark_market"))

        response = client.post(
            "/api/v1/admin/ml/benchmark",
            json={"market_key": "football.ml_benchmark_market", "algorithm": "random_forest", "framework": "sklearn"},
            headers=headers,
        )

        assert response.status_code == 409


class TestMonitoring:
    def test_model_health(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_health_market"))

        response = client.get("/api/v1/admin/ml/monitoring/football.ml_health_market/health", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"

    def test_record_and_read_latency(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_latency_market"))

        record = client.post(
            "/api/v1/admin/ml/monitoring/football.ml_latency_market/latency", json={"duration_ms": 123.0}, headers=headers
        )
        stats = client.get("/api/v1/admin/ml/monitoring/football.ml_latency_market/latency", headers=headers)

        assert record.status_code == 200
        assert stats.status_code == 200
        assert stats.json()["data"]["sample_size"] == 1


class TestRetraining:
    def test_check_retraining_with_no_dataset(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_retraining_market"))

        response = client.post("/api/v1/admin/ml/retraining/football.ml_retraining_market/check", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"]["should_retrain"] is False

    def test_latest_comparison_with_none_recorded_returns_none(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_comparison_market"))

        response = client.get("/api/v1/admin/ml/retraining/football.ml_comparison_market/comparison", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"] is None

    def test_latest_comparison_returns_the_recorded_verdict(self, client, db_session_factory):
        from datetime import datetime, timezone
        from uuid import uuid4

        from apps.api.composition import get_model_comparison_repo
        from modules.predictions.domain.model_comparison import ChallengerEvaluation, ComparisonMetrics, ComparisonVerdict
        from modules.predictions.domain.value_objects import ChallengerEvaluationId

        headers = _admin_headers(client, db_session_factory)
        market_id = asyncio.run(_seed_market(db_session_factory, "football.ml_comparison_market2"))

        evaluation = ChallengerEvaluation(
            id=ChallengerEvaluationId(uuid4()), market_id=market_id,
            challenger_model_id=ModelId(uuid4()), champion_model_id=ModelId(uuid4()),
            challenger_metrics=ComparisonMetrics(log_loss=0.4, brier_score=0.15, expected_calibration_error=0.02),
            champion_metrics=ComparisonMetrics(log_loss=0.6, brier_score=0.2, expected_calibration_error=0.05),
            verdict=ComparisonVerdict.CHALLENGER_BETTER, decisive_metric="log_loss",
            holdout_sample_count=12, evaluated_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        )
        asyncio.run(get_model_comparison_repo().record(evaluation))

        response = client.get("/api/v1/admin/ml/retraining/football.ml_comparison_market2/comparison", headers=headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["verdict"] == "challenger_better"
        assert data["decisive_metric"] == "log_loss"
        assert data["holdout_sample_count"] == 12
        assert data["challenger_metrics"]["log_loss"] == 0.4
        assert data["champion_metrics"]["brier_score"] == 0.2


class TestBacktest:
    def test_backtest_with_no_outcomes_returns_409_not_a_fabricated_report(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_backtest_market", with_champion=False))

        response = client.post(
            "/api/v1/admin/ml/backtest",
            json={"market_key": "football.ml_backtest_market"},
            headers=headers,
        )

        assert response.status_code == 409

    def test_backtest_rejects_unknown_algorithm(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_backtest_market2", with_champion=False))

        response = client.post(
            "/api/v1/admin/ml/backtest",
            json={"market_key": "football.ml_backtest_market2", "algorithm": "not_a_real_algorithm"},
            headers=headers,
        )

        assert response.status_code == 422


class TestErrorMemory:
    def test_market_ranking_with_no_data_returns_empty_ranking(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_error_memory_market", with_champion=False))

        response = client.get("/api/v1/admin/ml/error-memory/market-ranking", headers=headers)

        assert response.status_code == 200
        keys = [m["market_key"] for m in response.json()["data"]]
        assert "football.ml_error_memory_market" in keys

    def test_feature_failures_with_no_outcomes_returns_empty_list(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_error_memory_market2", with_champion=False))

        response = client.get("/api/v1/admin/ml/error-memory/football.ml_error_memory_market2/feature-failures", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_overconfidence_with_no_outcomes_returns_honest_empty_summary(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_error_memory_market3", with_champion=False))

        response = client.get("/api/v1/admin/ml/error-memory/football.ml_error_memory_market3/overconfidence", headers=headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["sample_count"] == 0
        assert data["overconfidence_score"] is None

    def test_model_version_ranking_reflects_the_seeded_champion(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_error_memory_market4", with_champion=True))

        response = client.get("/api/v1/admin/ml/error-memory/football.ml_error_memory_market4/model-versions", headers=headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "champion"


class TestEvaluation:
    def test_list_evaluations_for_model_with_none_returns_empty(self, client, db_session_factory):
        headers = _admin_headers(client, db_session_factory)
        asyncio.run(_seed_market(db_session_factory, "football.ml_evaluation_market"))
        model_id = client.get("/api/v1/admin/ml/models/football.ml_evaluation_market", headers=headers).json()["data"][0]["id"]

        response = client.get(f"/api/v1/admin/ml/evaluation/{model_id}", headers=headers)

        assert response.status_code == 200
        assert response.json()["data"] == []
