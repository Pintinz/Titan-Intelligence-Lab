"""WebhookService — endpoint registration, HMAC signing, and delivery/retry bookkeeping
(Milestone 6). Reuses ``modules.admin.ports.vault.CredentialVaultPort`` for signing-secret
encryption at rest — same contract as provider credentials, no need for a second vault port.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.admin.ports.vault import CredentialVaultPort
from modules.webhooks.domain.entities import WebhookDelivery, WebhookEndpoint
from modules.webhooks.domain.value_objects import DeliveryStatus, WebhookDeliveryId, WebhookEndpointId
from modules.webhooks.ports.repositories import WebhookDeliveryRepositoryPort, WebhookEndpointRepositoryPort


@dataclass
class WebhookService:
    endpoints: WebhookEndpointRepositoryPort
    deliveries: WebhookDeliveryRepositoryPort
    vault: CredentialVaultPort
    max_delivery_attempts: int = 5

    # -- endpoint registration --------------------------------------------------------------------

    async def register_endpoint(
        self, organization_id: str, url: str, subscribed_events: list[str], now: datetime
    ) -> tuple[WebhookEndpoint, str]:
        raw_secret = secrets.token_urlsafe(32)
        endpoint = WebhookEndpoint(
            id=WebhookEndpointId(uuid4()),
            organization_id=organization_id,
            url=url,
            signing_secret_encrypted=self.vault.encrypt(raw_secret),
            subscribed_events=subscribed_events,
            created_at=now,
        )
        await self.endpoints.upsert(endpoint)
        return endpoint, raw_secret

    async def rotate_secret(self, endpoint_id: WebhookEndpointId, now: datetime) -> tuple[WebhookEndpoint, str]:
        endpoint = await self.endpoints.get(endpoint_id)
        if endpoint is None:
            raise ValueError("No such webhook endpoint")
        raw_secret = secrets.token_urlsafe(32)
        endpoint.signing_secret_encrypted = self.vault.encrypt(raw_secret)
        endpoint.rotated_at = now
        await self.endpoints.upsert(endpoint)
        return endpoint, raw_secret

    async def deactivate_endpoint(self, endpoint_id: WebhookEndpointId) -> None:
        endpoint = await self.endpoints.get(endpoint_id)
        if endpoint is not None:
            endpoint.is_active = False
            await self.endpoints.upsert(endpoint)

    # -- signing ------------------------------------------------------------------------------------

    def sign_payload(self, endpoint: WebhookEndpoint, payload: dict) -> str:
        secret = self.vault.decrypt(endpoint.signing_secret_encrypted)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def verify_signature(self, endpoint: WebhookEndpoint, payload: dict, signature: str) -> bool:
        return hmac.compare_digest(self.sign_payload(endpoint, payload), signature)

    # -- dispatch bookkeeping (actual HTTP send is an infrastructure-layer concern; this records
    # intent + outcome so retries/observability work the same regardless of transport) -----------

    async def enqueue_delivery(self, endpoint_id: WebhookEndpointId, event_type: str, payload: dict, now: datetime) -> WebhookDelivery:
        delivery = WebhookDelivery(
            id=WebhookDeliveryId(uuid4()), endpoint_id=endpoint_id, event_type=event_type, payload=payload, created_at=now
        )
        return await self.deliveries.upsert(delivery)

    async def record_attempt(
        self, delivery_id: WebhookDeliveryId, now: datetime, success: bool, response_status_code: int | None = None
    ) -> WebhookDelivery:
        delivery = await self.deliveries.get(delivery_id)
        if delivery is None:
            raise ValueError("No such delivery")
        delivery.attempt_count += 1
        delivery.last_attempted_at = now
        delivery.response_status_code = response_status_code
        if success:
            delivery.status = DeliveryStatus.SUCCEEDED
        elif delivery.attempt_count >= self.max_delivery_attempts:
            delivery.status = DeliveryStatus.EXHAUSTED
        else:
            delivery.status = DeliveryStatus.FAILED
        return await self.deliveries.upsert(delivery)

    async def deliveries_due_for_retry(self) -> list[WebhookDelivery]:
        pending = await self.deliveries.list_pending_retries()
        return [d for d in pending if d.can_retry(self.max_delivery_attempts)]
