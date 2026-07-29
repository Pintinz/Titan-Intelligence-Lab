from __future__ import annotations

from datetime import datetime, timezone

import pytest

from modules.webhooks.application.webhook_service import WebhookService
from modules.webhooks.domain.value_objects import DeliveryStatus


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def service(endpoint_repo, delivery_repo, vault):
    return WebhookService(endpoints=endpoint_repo, deliveries=delivery_repo, vault=vault, max_delivery_attempts=3)


async def test_register_endpoint_returns_raw_secret_once(service):
    endpoint, raw_secret = await service.register_endpoint("org-1", "https://example.com/hook", ["payment.succeeded"], now())

    assert endpoint.organization_id == "org-1"
    assert endpoint.signing_secret_encrypted != raw_secret
    assert endpoint.signing_secret_encrypted.startswith("enc:")


async def test_sign_and_verify_payload(service):
    endpoint, _ = await service.register_endpoint("org-1", "https://example.com/hook", ["*"], now())
    payload = {"event": "payment.succeeded", "amount": 100}

    signature = service.sign_payload(endpoint, payload)

    assert service.verify_signature(endpoint, payload, signature) is True
    assert service.verify_signature(endpoint, {**payload, "amount": 200}, signature) is False


async def test_rotate_secret_changes_signature(service):
    endpoint, _ = await service.register_endpoint("org-1", "https://example.com/hook", ["*"], now())
    payload = {"event": "x"}
    old_signature = service.sign_payload(endpoint, payload)

    rotated, new_raw = await service.rotate_secret(endpoint.id, now())

    assert rotated.rotated_at is not None
    new_signature = service.sign_payload(rotated, payload)
    assert new_signature != old_signature


async def test_deactivate_endpoint(service, endpoint_repo):
    endpoint, _ = await service.register_endpoint("org-1", "https://example.com/hook", ["*"], now())

    await service.deactivate_endpoint(endpoint.id)

    stored = await endpoint_repo.get(endpoint.id)
    assert stored.is_active is False


async def test_delivery_retry_lifecycle(service):
    endpoint, _ = await service.register_endpoint("org-1", "https://example.com/hook", ["*"], now())
    delivery = await service.enqueue_delivery(endpoint.id, "payment.succeeded", {"amount": 100}, now())

    failed = await service.record_attempt(delivery.id, now(), success=False, response_status_code=500)
    assert failed.status is DeliveryStatus.FAILED
    assert failed.attempt_count == 1

    due = await service.deliveries_due_for_retry()
    assert due[0].id == delivery.id

    succeeded = await service.record_attempt(delivery.id, now(), success=True, response_status_code=200)
    assert succeeded.status is DeliveryStatus.SUCCEEDED


async def test_delivery_exhausts_after_max_attempts(service):
    endpoint, _ = await service.register_endpoint("org-1", "https://example.com/hook", ["*"], now())
    delivery = await service.enqueue_delivery(endpoint.id, "payment.failed", {}, now())

    for _ in range(service.max_delivery_attempts):
        delivery = await service.record_attempt(delivery.id, now(), success=False)

    assert delivery.status is DeliveryStatus.EXHAUSTED
    assert delivery.can_retry(service.max_delivery_attempts) is False


async def test_endpoint_subscription_matching(service):
    specific, _ = await service.register_endpoint("org-1", "https://a.example.com", ["payment.succeeded"], now())
    wildcard, _ = await service.register_endpoint("org-1", "https://b.example.com", ["*"], now())

    subscribed = await service.endpoints.list_subscribed_to("payment.succeeded")
    subscribed_ids = {e.id for e in subscribed}
    assert specific.id in subscribed_ids
    assert wildcard.id in subscribed_ids

    subscribed_other = await service.endpoints.list_subscribed_to("payment.refunded")
    assert specific.id not in {e.id for e in subscribed_other}
    assert wildcard.id in {e.id for e in subscribed_other}
