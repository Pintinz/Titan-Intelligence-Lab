from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.admin.domain.entities import (
    ProviderCredential,
    ProviderDefinition,
    ProviderHealthState,
    ProviderIncident,
    ProviderUsageRecord,
)
from modules.admin.domain.value_objects import CredentialId, IncidentId, ProviderId, QuotaPeriod
from modules.admin.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"admin": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryProviderRepository:
    store: dict[ProviderId, ProviderDefinition] = field(default_factory=dict)

    async def get(self, provider_id):
        return self.store.get(provider_id)

    async def get_by_key(self, key):
        return next((p for p in self.store.values() if p.key == key), None)

    async def list_all(self):
        return list(self.store.values())

    async def upsert(self, provider):
        self.store[provider.id] = provider
        return provider

    async def delete(self, provider_id):
        self.store.pop(provider_id, None)


@dataclass
class InMemoryCredentialRepository:
    store: dict[CredentialId, ProviderCredential] = field(default_factory=dict)

    async def get(self, credential_id):
        return self.store.get(credential_id)

    async def list_by_provider(self, provider_id):
        return [c for c in self.store.values() if c.provider_id == provider_id]

    async def upsert(self, credential):
        self.store[credential.id] = credential
        return credential

    async def delete(self, credential_id):
        self.store.pop(credential_id, None)


@dataclass
class InMemoryUsageRepository:
    store: dict[tuple, ProviderUsageRecord] = field(default_factory=dict)

    def _key(self, provider_id, period, window_key, credential_id):
        return (provider_id, period, window_key, credential_id)

    async def get(self, provider_id, period, window_key, credential_id=None):
        return self.store.get(self._key(provider_id, period, window_key, credential_id))

    async def upsert(self, record):
        self.store[
            self._key(record.provider_id, record.period, record.window_key, record.credential_id)
        ] = record
        return record

    async def list_by_provider(self, provider_id, period, limit=30):
        matching = [
            r for r in self.store.values() if r.provider_id == provider_id and r.period == period
        ]
        return sorted(matching, key=lambda r: r.window_key, reverse=True)[:limit]


@dataclass
class InMemoryHealthRepository:
    checks: list = field(default_factory=list)

    async def record(self, check):
        self.checks.append(check)
        return check

    async def list_recent(self, provider_id, limit=20):
        matching = [c for c in self.checks if c.provider_id == provider_id]
        return sorted(matching, key=lambda c: c.checked_at, reverse=True)[:limit]

    async def list_since(self, provider_id, since):
        return [c for c in self.checks if c.provider_id == provider_id and c.checked_at >= since]


@dataclass
class InMemoryHealthStateRepository:
    store: dict[ProviderId, ProviderHealthState] = field(default_factory=dict)

    async def get(self, provider_id):
        return self.store.get(provider_id)

    async def upsert(self, state):
        self.store[state.provider_id] = state
        return state


@dataclass
class InMemoryIncidentRepository:
    store: dict[IncidentId, ProviderIncident] = field(default_factory=dict)

    async def get(self, incident_id):
        return self.store.get(incident_id)

    async def list_by_provider(self, provider_id):
        return [i for i in self.store.values() if i.provider_id == provider_id]

    async def list_open(self, provider_id):
        return [i for i in self.store.values() if i.provider_id == provider_id and i.is_open]

    async def upsert(self, incident):
        self.store[incident.id] = incident
        return incident


class InMemoryVault:
    """Reversible-but-obviously-fake vault for tests that don't need real crypto."""

    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext}"

    def decrypt(self, ciphertext: str) -> str:
        assert ciphertext.startswith("enc:")
        return ciphertext[len("enc:") :]


@pytest.fixture
def provider_repo():
    return InMemoryProviderRepository()


@pytest.fixture
def credential_repo():
    return InMemoryCredentialRepository()


@pytest.fixture
def usage_repo():
    return InMemoryUsageRepository()


@pytest.fixture
def vault():
    return InMemoryVault()


@pytest.fixture
def health_repo():
    return InMemoryHealthRepository()


@pytest.fixture
def health_state_repo():
    return InMemoryHealthStateRepository()


@pytest.fixture
def incident_repo():
    return InMemoryIncidentRepository()
