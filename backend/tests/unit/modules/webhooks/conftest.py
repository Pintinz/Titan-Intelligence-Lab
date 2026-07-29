from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.webhooks.domain.entities import WebhookDelivery, WebhookEndpoint
from modules.webhooks.domain.value_objects import DeliveryStatus, WebhookDeliveryId, WebhookEndpointId
from modules.webhooks.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"webhooks": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@dataclass
class InMemoryWebhookEndpointRepository:
    store: dict[WebhookEndpointId, WebhookEndpoint] = field(default_factory=dict)

    async def get(self, endpoint_id):
        return self.store.get(endpoint_id)

    async def list_by_organization(self, organization_id):
        return [e for e in self.store.values() if e.organization_id == organization_id]

    async def list_subscribed_to(self, event_type):
        return [e for e in self.store.values() if e.is_active and e.is_subscribed(event_type)]

    async def upsert(self, endpoint):
        self.store[endpoint.id] = endpoint
        return endpoint

    async def delete(self, endpoint_id):
        self.store.pop(endpoint_id, None)


@dataclass
class InMemoryWebhookDeliveryRepository:
    store: dict[WebhookDeliveryId, WebhookDelivery] = field(default_factory=dict)

    async def get(self, delivery_id):
        return self.store.get(delivery_id)

    async def list_by_endpoint(self, endpoint_id, limit=100):
        return [d for d in self.store.values() if d.endpoint_id == endpoint_id][:limit]

    async def list_pending_retries(self):
        return [d for d in self.store.values() if d.status is DeliveryStatus.FAILED]

    async def upsert(self, delivery):
        self.store[delivery.id] = delivery
        return delivery


class InMemoryVault:
    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext}"

    def decrypt(self, ciphertext: str) -> str:
        assert ciphertext.startswith("enc:")
        return ciphertext[len("enc:") :]


@pytest.fixture
def endpoint_repo():
    return InMemoryWebhookEndpointRepository()


@pytest.fixture
def delivery_repo():
    return InMemoryWebhookDeliveryRepository()


@pytest.fixture
def vault():
    return InMemoryVault()
