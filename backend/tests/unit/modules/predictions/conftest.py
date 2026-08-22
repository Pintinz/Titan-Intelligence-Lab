from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.features.application.feature_lineage_service import FeatureLineageService
from modules.features.application.feature_registration_service import FeatureRegistrationService
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.entities import FeatureDefinition, FeatureValue
from modules.predictions.domain.entities import FeatureMarketMapping, MarketDefinition, ModelDefinition
from modules.predictions.infrastructure.persistence.models import Base
from modules.sports.domain.entities import TeamStatistics
from modules.sports.domain.value_objects import EntityId, MatchId


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"predictions": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryMarketRepository:
    store: dict = field(default_factory=dict)  # market_key -> MarketDefinition

    async def get(self, market_id):
        return next((m for m in self.store.values() if m.id == market_id), None)

    async def get_by_key(self, market_key):
        return self.store.get(market_key)

    async def list_by_sport(self, sport_code):
        return [m for m in self.store.values() if m.sport_code == sport_code]

    async def list_by_status(self, status):
        return [m for m in self.store.values() if m.status == status]

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, market: MarketDefinition) -> MarketDefinition:
        self.store[market.market_key] = market
        return market


@dataclass
class InMemoryFeatureMarketMappingRepository:
    store: list = field(default_factory=list)

    async def list_by_market(self, market_id):
        return [m for m in self.store if m.market_id == market_id]

    async def list_by_feature(self, feature_key):
        return [m for m in self.store if m.feature_key == feature_key]

    async def upsert(self, mapping: FeatureMarketMapping) -> FeatureMarketMapping:
        for i, existing in enumerate(self.store):
            if existing.id == mapping.id:
                self.store[i] = mapping
                return mapping
        self.store.append(mapping)
        return mapping


@dataclass
class InMemoryModelRepository:
    store: dict = field(default_factory=dict)  # (model_key, version) -> ModelDefinition

    async def get(self, model_id):
        return next((m for m in self.store.values() if m.id == model_id), None)

    async def get_by_key_version(self, model_key, version):
        return self.store.get((model_key, version))

    async def list_by_market(self, market_id):
        return [m for m in self.store.values() if m.market_id == market_id]

    async def get_champion(self, market_id):
        from modules.predictions.domain.value_objects import ModelStatus

        return next(
            (m for m in self.store.values() if m.market_id == market_id and m.status == ModelStatus.CHAMPION), None
        )

    async def list_by_status(self, market_id, status):
        return [m for m in self.store.values() if m.market_id == market_id and m.status == status]

    async def get_by_market_and_algorithm(self, market_id, algorithm):
        candidates = [m for m in self.store.values() if m.market_id == market_id and m.algorithm == algorithm]
        return max(candidates, key=lambda m: m.version) if candidates else None

    async def upsert(self, model: ModelDefinition) -> ModelDefinition:
        self.store[(model.model_key, model.version)] = model
        return model


@dataclass
class InMemoryFeatureDefinitionRepository:
    store: dict = field(default_factory=dict)  # FeatureKey -> FeatureDefinition

    async def get(self, feature_key):
        return self.store.get(feature_key)

    async def list_by_sport(self, sport_code):
        return [d for d in self.store.values() if d.sport_code == sport_code]

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, definition: FeatureDefinition) -> FeatureDefinition:
        self.store[definition.feature_key] = definition
        return definition


@pytest.fixture
def market_repo():
    return InMemoryMarketRepository()


@pytest.fixture
def feature_mapping_repo():
    return InMemoryFeatureMarketMappingRepository()


@pytest.fixture
def model_repo():
    return InMemoryModelRepository()


@dataclass
class InMemoryFeatureValueRepository:
    """Mirrors SqlAlchemyFeatureValueRepository's real semantics — `record()` appends (this is
    "the audited historical record", never an overwrite-in-place), so multiple values can exist
    for the same (feature_key, entity_type, entity_id) at different `as_of` times. Needed for
    get_as_of() to mean anything real in a test — a single-value-per-key store can't distinguish
    "the latest value" from "the value as of some earlier cutoff"."""

    store: dict = field(default_factory=dict)  # (feature_key, entity_type, entity_id) -> list[FeatureValue]

    async def record(self, value: FeatureValue) -> FeatureValue:
        self.store.setdefault((value.feature_key, value.entity_type, value.entity_id), []).append(value)
        return value

    def _history(self, feature_key, entity_type, entity_id):
        return sorted(self.store.get((feature_key, entity_type, entity_id), []), key=lambda v: v.as_of)

    async def get_latest(self, feature_key, entity_type, entity_id):
        history = self._history(feature_key, entity_type, entity_id)
        return history[-1] if history else None

    async def get_as_of(self, feature_key, entity_type, entity_id, as_of):
        eligible = [v for v in self._history(feature_key, entity_type, entity_id) if v.as_of <= as_of]
        return eligible[-1] if eligible else None

    async def list_history(self, feature_key, entity_type, entity_id, limit=100):
        return list(reversed(self._history(feature_key, entity_type, entity_id)))[:limit]

    async def list_all_recent(self, feature_key, since=None, limit=5000):
        values = [v for k, vs in self.store.items() if k[0] == feature_key for v in vs]
        if since is not None:
            values = [v for v in values if v.as_of >= since]
        return values[:limit]


@pytest.fixture
def feature_definition_repo():
    return InMemoryFeatureDefinitionRepository()


@dataclass
class InMemoryPredictionOutcomeRepository:
    store: list = field(default_factory=list)

    async def record(self, outcome):
        self.store.append(outcome)
        return outcome

    async def get_for_prediction(self, prediction_id):
        return next((o for o in self.store if o.prediction_id == prediction_id), None)

    async def list_by_market(self, market_id, limit=500):
        return self.store[:limit]

    async def count_by_market(self, market_id):
        # Mirrors list_by_market's pre-existing simplification: this fake never filters by
        # market_id (tests only ever populate one market per test), so this is just len(store).
        return len(self.store)


@dataclass
class InMemoryModelEvaluationRepository:
    store: list = field(default_factory=list)

    async def record(self, evaluation):
        self.store.append(evaluation)
        return evaluation

    async def list_by_model(self, model_id, limit=50):
        return [e for e in self.store if e.model_id == model_id][:limit]

    async def get_latest(self, model_id):
        matches = [e for e in self.store if e.model_id == model_id]
        return max(matches, key=lambda e: e.evaluated_at) if matches else None


@dataclass
class InMemoryPredictionRepository:
    store: dict = field(default_factory=dict)  # PredictionId -> Prediction
    by_subject: list = field(default_factory=list)

    async def get(self, prediction_id):
        return self.store.get(prediction_id)

    async def record(self, prediction):
        self.store[prediction.id] = prediction
        self.by_subject.append(prediction)
        return prediction

    async def update(self, prediction):
        self.store[prediction.id] = prediction
        return prediction

    async def list_by_subject(self, subject_ref, market_id=None):
        matches = [p for p in self.by_subject if p.subject_ref == subject_ref]
        if market_id is not None:
            matches = [p for p in matches if p.market_id == market_id]
        return list(reversed(matches))

    async def list_by_market(self, market_id, status=None, limit=100):
        matches = [p for p in self.store.values() if p.market_id == market_id]
        if status is not None:
            matches = [p for p in matches if p.status == status]
        return matches[:limit]

    async def list_recent(self, limit=100):
        return list(self.store.values())[:limit]

    async def get_latest_for_subject(self, subject_ref, market_id):
        matches = await self.list_by_subject(subject_ref, market_id)
        return matches[0] if matches else None

    async def count_by_market(self, market_id, status=None):
        matches = [p for p in self.store.values() if p.market_id == market_id]
        if status is not None:
            matches = [p for p in matches if p.status == status]
        return len(matches)


@pytest.fixture
def feature_value_repo():
    return InMemoryFeatureValueRepository()


@pytest.fixture
def prediction_outcome_repo():
    return InMemoryPredictionOutcomeRepository()


@pytest.fixture
def model_evaluation_repo():
    return InMemoryModelEvaluationRepository()


@dataclass
class InMemoryPredictionAuditRepository:
    store: list = field(default_factory=list)

    async def record(self, audit):
        self.store.append(audit)
        return audit

    async def list_by_prediction(self, prediction_id):
        return [a for a in self.store if a.prediction_id == prediction_id]

    async def list_recent(self, since=None, limit=200):
        matches = self.store
        if since is not None:
            matches = [a for a in matches if a.occurred_at >= since]
        return matches[:limit]


@pytest.fixture
def prediction_repo():
    return InMemoryPredictionRepository()


@dataclass
class InMemoryFeatureVersionRepository:
    store: list = field(default_factory=list)

    async def record(self, snapshot):
        self.store.append(snapshot)
        return snapshot

    async def list_by_feature(self, feature_key):
        return [s for s in self.store if s.feature_key == feature_key]


@dataclass
class InMemoryFeatureLineageRepository:
    edges: list = field(default_factory=list)

    async def add_edge(self, edge):
        self.edges.append(edge)
        return edge

    async def list_dependencies(self, feature_key):
        return []

    async def list_dependents(self, feature_key):
        return []


@dataclass
class InMemoryOnlineFeatureStore:
    store: dict = field(default_factory=dict)

    async def get(self, feature_key, entity_type, entity_id):
        return self.store.get((feature_key, entity_type, entity_id))

    async def set(self, value, ttl_seconds):
        self.store[(value.feature_key, value.entity_type, value.entity_id)] = value

    async def delete(self, feature_key, entity_type, entity_id):
        self.store.pop((feature_key, entity_type, entity_id), None)


@dataclass
class InMemoryTeamStatisticsRepository:
    store: list = field(default_factory=list)

    def add(self, team_id, stat_set, started_at):
        self.store.append((team_id, stat_set, started_at))

    async def get_for_match_team(self, match_id, team_id):
        raise NotImplementedError

    async def list_by_match(self, match_id):
        raise NotImplementedError

    async def upsert(self, statistics):
        raise NotImplementedError

    async def list_recent_by_team(self, team_id, before, limit=10):
        matches = [
            TeamStatistics(id=EntityId(uuid4()), match_id=MatchId(uuid4()), team_id=team_id, stat_set=stat_set)
            for tid, stat_set, started_at in sorted(self.store, key=lambda row: row[2], reverse=True)
            if tid == team_id and started_at < before
        ]
        return matches[:limit]


@pytest.fixture
def registration(feature_definition_repo):
    lineage = FeatureLineageService(lineage=InMemoryFeatureLineageRepository(), definitions=feature_definition_repo)
    return FeatureRegistrationService(
        definitions=feature_definition_repo, versions=InMemoryFeatureVersionRepository(), lineage=lineage
    )


@pytest.fixture
def store(feature_definition_repo, feature_value_repo):
    return FeatureStoreService(
        definitions=feature_definition_repo, offline=feature_value_repo, online=InMemoryOnlineFeatureStore()
    )


@pytest.fixture
def team_statistics_repo():
    return InMemoryTeamStatisticsRepository()


@pytest.fixture
def market_registry(market_repo, feature_mapping_repo):
    from modules.predictions.application.market_registry_service import MarketRegistryService

    return MarketRegistryService(markets=market_repo, feature_mappings=feature_mapping_repo)


@pytest.fixture
def mapping_service(feature_mapping_repo, market_repo, feature_definition_repo):
    from modules.predictions.application.feature_market_mapping_service import FeatureMarketMappingService

    return FeatureMarketMappingService(
        mappings=feature_mapping_repo, markets=market_repo, feature_definitions=feature_definition_repo
    )


@pytest.fixture
def prediction_audit_repo():
    return InMemoryPredictionAuditRepository()


@dataclass
class InMemoryDatasetRepository:
    store: dict = field(default_factory=dict)  # DatasetId -> Dataset

    async def get(self, dataset_id):
        return self.store.get(dataset_id)

    async def get_latest_version(self, market_id):
        matches = [d for d in self.store.values() if d.market_id == market_id]
        return max(matches, key=lambda d: d.version) if matches else None

    async def list_by_market(self, market_id, limit=50):
        matches = [d for d in self.store.values() if d.market_id == market_id]
        return sorted(matches, key=lambda d: d.version, reverse=True)[:limit]

    async def upsert(self, dataset):
        self.store[dataset.id] = dataset
        return dataset


@pytest.fixture
def dataset_repo():
    return InMemoryDatasetRepository()


@dataclass
class InMemoryExperimentRepository:
    """Promoted from test_experiment_tracking_service.py's local `_InMemoryExperimentRepository`
    once test_predictive_signal_audit_service.py needed the same fake, to avoid a second source
    of truth for it."""

    store: dict = field(default_factory=dict)

    async def get(self, experiment_id):
        return self.store.get(experiment_id)

    async def record(self, experiment):
        self.store[experiment.id] = experiment
        return experiment

    async def update(self, experiment):
        self.store[experiment.id] = experiment
        return experiment

    async def list_by_market(self, market_id, limit=50):
        matches = [e for e in self.store.values() if e.market_id == market_id]
        return matches[:limit]


@pytest.fixture
def experiment_repo():
    return InMemoryExperimentRepository()
