from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.ingestion.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"ingestion": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemorySyncRunRepository:
    store: dict = field(default_factory=dict)

    async def record(self, run):
        self.store[run.id] = run
        return run

    async def update(self, run):
        self.store[run.id] = run
        return run

    async def get(self, run_id):
        return self.store.get(run_id)

    async def list_recent(self, sport_code=None, entity_kind=None, limit=50):
        matches = [
            r for r in self.store.values()
            if (sport_code is None or r.sport_code == sport_code)
            and (entity_kind is None or r.entity_kind == entity_kind)
        ]
        return sorted(matches, key=lambda r: r.started_at, reverse=True)[:limit]


@dataclass
class InMemorySyncCheckpointRepository:
    store: dict = field(default_factory=dict)

    async def get(self, sport_code, entity_kind, scope_key):
        return self.store.get((sport_code, entity_kind, scope_key))

    async def upsert(self, checkpoint):
        self.store[(checkpoint.sport_code, checkpoint.entity_kind, checkpoint.scope_key)] = checkpoint
        return checkpoint


@dataclass
class InMemoryTimelineEventRepository:
    store: list = field(default_factory=list)

    async def record(self, event):
        self.store.append(event)
        return event

    async def list_recent(self, entity_kind=None, entity_id=None, since=None, limit=100):
        matches = [
            e for e in self.store
            if (entity_kind is None or e.entity_kind == entity_kind)
            and (entity_id is None or e.entity_id == entity_id)
            and (since is None or e.occurred_at >= since)
        ]
        return sorted(matches, key=lambda e: e.occurred_at, reverse=True)[:limit]


@dataclass
class InMemoryDataQualityReportRepository:
    store: list = field(default_factory=list)

    async def record(self, report):
        self.store.append(report)
        return report

    async def get_latest(self, sport_code, entity_kind):
        matches = [r for r in self.store if r.sport_code == sport_code and r.entity_kind == entity_kind]
        return max(matches, key=lambda r: r.generated_at) if matches else None

    async def list_by_entity_kind(self, sport_code, entity_kind, limit=50):
        matches = [r for r in self.store if r.sport_code == sport_code and r.entity_kind == entity_kind]
        return sorted(matches, key=lambda r: r.generated_at, reverse=True)[:limit]


class FakeProviderReliabilityPort:
    def __init__(self, scores: dict | None = None):
        self.scores = scores or {}

    async def reliability_score(self, provider_key, now):
        return self.scores.get(provider_key)


@pytest.fixture
def sync_run_repo():
    return InMemorySyncRunRepository()


@pytest.fixture
def sync_checkpoint_repo():
    return InMemorySyncCheckpointRepository()


@pytest.fixture
def timeline_repo():
    return InMemoryTimelineEventRepository()


@pytest.fixture
def quality_report_repo():
    return InMemoryDataQualityReportRepository()


@pytest.fixture
def provider_reliability_port():
    return FakeProviderReliabilityPort()
