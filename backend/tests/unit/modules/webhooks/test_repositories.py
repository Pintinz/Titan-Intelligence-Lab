from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.webhooks.domain.entities import WebhookDelivery, WebhookEndpoint
from modules.webhooks.domain.value_objects import DeliveryStatus, WebhookDeliveryId, WebhookEndpointId
from modules.webhooks.infrastructure.persistence.repositories import (
    SqlAlchemyWebhookDeliveryRepository,
    SqlAlchemyWebhookEndpointRepository,
)


def now():
    return datetime.now(timezone.utc)


async def test_endpoint_repository_round_trip(sqlite_session):
    repo = SqlAlchemyWebhookEndpointRepository(session=sqlite_session)
    endpoint = WebhookEndpoint(
        id=WebhookEndpointId(uuid4()), organization_id="org-1", url="https://example.com/hook",
        signing_secret_encrypted="enc:secret", subscribed_events=["payment.succeeded"],
    )

    await repo.upsert(endpoint)
    await sqlite_session.commit()

    fetched = list(await repo.list_by_organization("org-1"))
    assert len(fetched) == 1 and fetched[0].id == endpoint.id

    matching = await repo.list_subscribed_to("payment.succeeded")
    assert len(matching) == 1

    await repo.delete(endpoint.id)
    await sqlite_session.commit()
    assert await repo.get(endpoint.id) is None


async def test_delivery_repository_round_trip(sqlite_session):
    endpoint_repo = SqlAlchemyWebhookEndpointRepository(session=sqlite_session)
    endpoint = await endpoint_repo.upsert(
        WebhookEndpoint(id=WebhookEndpointId(uuid4()), organization_id="org-1", url="https://example.com/hook", signing_secret_encrypted="enc:x")
    )
    await sqlite_session.commit()

    delivery_repo = SqlAlchemyWebhookDeliveryRepository(session=sqlite_session)
    delivery = await delivery_repo.upsert(
        WebhookDelivery(id=WebhookDeliveryId(uuid4()), endpoint_id=endpoint.id, event_type="payment.succeeded", payload={"amount": 100})
    )
    await sqlite_session.commit()

    fetched = list(await delivery_repo.list_by_endpoint(endpoint.id))
    assert len(fetched) == 1 and fetched[0].payload == {"amount": 100}

    delivery.status = DeliveryStatus.FAILED
    delivery.attempt_count = 1
    await delivery_repo.upsert(delivery)
    await sqlite_session.commit()

    pending = await delivery_repo.list_pending_retries()
    assert len(pending) == 1 and pending[0].id == delivery.id
