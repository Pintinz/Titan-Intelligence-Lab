from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.features.domain.entities import FeatureDefinition, FeatureLineageEdge, FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureKey
from modules.features.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"features": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryFeatureDefinitionRepository:
    store: dict[FeatureKey, FeatureDefinition] = field(default_factory=dict)

    async def get(self, feature_key):
        return self.store.get(feature_key)

    async def list_by_sport(self, sport_code):
        return [d for d in self.store.values() if d.sport_code == sport_code]

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, definition):
        self.store[definition.feature_key] = definition
        return definition


@dataclass
class InMemoryFeatureVersionRepository:
    store: list = field(default_factory=list)

    async def record(self, snapshot):
        self.store.append(snapshot)
        return snapshot

    async def list_by_feature(self, feature_key):
        return [s for s in self.store if s.feature_key == feature_key]


@dataclass
class InMemoryFeatureValueRepository:
    store: list = field(default_factory=list)

    async def record(self, value: FeatureValue):
        self.store.append(value)
        return value

    async def get_latest(self, feature_key, entity_type, entity_id):
        matches = [
            v for v in self.store
            if v.feature_key == feature_key and v.entity_type == entity_type and v.entity_id == entity_id
        ]
        return max(matches, key=lambda v: v.as_of) if matches else None

    async def list_history(self, feature_key, entity_type, entity_id, limit=100):
        matches = [
            v for v in self.store
            if v.feature_key == feature_key and v.entity_type == entity_type and v.entity_id == entity_id
        ]
        return sorted(matches, key=lambda v: v.as_of, reverse=True)[:limit]

    async def get_as_of(self, feature_key, entity_type, entity_id, as_of):
        # Mirrors SqlAlchemyFeatureValueRepository.get_as_of's WHERE as_of <= cutoff ORDER BY
        # as_of DESC LIMIT 1 — the most recent value that was already true at `as_of`, ignoring
        # insertion order (list position) entirely, same as the real SQL query would.
        matches = [
            v for v in self.store
            if v.feature_key == feature_key and v.entity_type == entity_type and v.entity_id == entity_id
            and v.as_of <= as_of
        ]
        return max(matches, key=lambda v: v.as_of) if matches else None

    async def list_all_recent(self, feature_key, since=None, limit=5000):
        matches = [
            v for v in self.store
            if v.feature_key == feature_key and (since is None or v.as_of >= since)
        ]
        return sorted(matches, key=lambda v: v.as_of, reverse=True)[:limit]


@dataclass
class InMemoryFeatureLineageRepository:
    edges: list = field(default_factory=list)

    async def add_edge(self, edge: FeatureLineageEdge):
        if edge not in self.edges:
            self.edges.append(edge)
        return edge

    async def list_dependencies(self, feature_key):
        return [e.depends_on_feature_key for e in self.edges if e.feature_key == feature_key]

    async def list_dependents(self, feature_key):
        return [e.feature_key for e in self.edges if e.depends_on_feature_key == feature_key]


@dataclass
class InMemoryOnlineFeatureStore:
    store: dict = field(default_factory=dict)

    def _key(self, feature_key, entity_type, entity_id):
        return (feature_key, entity_type, entity_id)

    async def get(self, feature_key, entity_type, entity_id):
        return self.store.get(self._key(feature_key, entity_type, entity_id))

    async def set(self, value, ttl_seconds):
        self.store[self._key(value.feature_key, value.entity_type, value.entity_id)] = value

    async def delete(self, feature_key, entity_type, entity_id):
        self.store.pop(self._key(feature_key, entity_type, entity_id), None)


@pytest.fixture
def definition_repo():
    return InMemoryFeatureDefinitionRepository()


@pytest.fixture
def version_repo():
    return InMemoryFeatureVersionRepository()


@pytest.fixture
def value_repo():
    return InMemoryFeatureValueRepository()


@pytest.fixture
def lineage_repo():
    return InMemoryFeatureLineageRepository()


@dataclass
class InMemoryFeatureValidationReportRepository:
    store: list = field(default_factory=list)

    async def record(self, report):
        self.store.append(report)
        return report

    async def get_latest(self, feature_key):
        matches = [r for r in self.store if r.feature_key == feature_key]
        return max(matches, key=lambda r: r.validated_at) if matches else None

    async def list_by_feature(self, feature_key, limit=50):
        matches = [r for r in self.store if r.feature_key == feature_key]
        return sorted(matches, key=lambda r: r.validated_at, reverse=True)[:limit]


@dataclass
class InMemoryFeatureComputationLogRepository:
    store: list = field(default_factory=list)

    async def record(self, log):
        self.store.append(log)
        return log

    async def list_since(self, feature_key, since):
        return [l for l in self.store if l.feature_key == feature_key and l.recorded_at >= since]


@dataclass
class InMemoryFeatureConsumerRepository:
    store: list = field(default_factory=list)

    async def register(self, consumer):
        existing = [
            c for c in self.store if c.feature_key == consumer.feature_key and c.consumer_key == consumer.consumer_key
        ]
        if existing:
            return existing[0]
        self.store.append(consumer)
        return consumer

    async def list_by_feature(self, feature_key):
        return [c for c in self.store if c.feature_key == feature_key]


@dataclass
class InMemoryFeatureUsageRepository:
    store: dict = field(default_factory=dict)

    async def get(self, feature_key, window_key):
        return self.store.get((feature_key, window_key))

    async def upsert(self, record):
        self.store[(record.feature_key, record.window_key)] = record
        return record

    async def list_since(self, feature_key, since_window_key):
        return [
            r for (fk, wk), r in self.store.items()
            if fk == feature_key and wk >= since_window_key
        ]


class FakeProviderReliabilityPort:
    def __init__(self, scores: dict | None = None):
        self.scores = scores or {}

    async def reliability_score(self, provider_key, now):
        return self.scores.get(provider_key)


@pytest.fixture
def online_store():
    return InMemoryOnlineFeatureStore()


@pytest.fixture
def validation_report_repo():
    return InMemoryFeatureValidationReportRepository()


@pytest.fixture
def computation_log_repo():
    return InMemoryFeatureComputationLogRepository()


@pytest.fixture
def consumer_repo():
    return InMemoryFeatureConsumerRepository()


@pytest.fixture
def usage_repo():
    return InMemoryFeatureUsageRepository()


@pytest.fixture
def provider_reliability_port():
    return FakeProviderReliabilityPort()
