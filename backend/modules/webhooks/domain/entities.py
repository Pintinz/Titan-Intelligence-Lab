"""Entities for the Webhook Infrastructure bounded context (Milestone 6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.webhooks.domain.value_objects import DeliveryStatus, WebhookDeliveryId, WebhookEndpointId


@dataclass
class WebhookEndpoint:
    """``signing_secret`` is opaque ciphertext (same ``CredentialVaultPort`` pattern as
    ``ProviderCredential.encrypted_value`` in modules.admin) — used to HMAC-sign outbound
    delivery payloads so the receiver can verify authenticity."""

    id: WebhookEndpointId
    organization_id: str
    url: str
    signing_secret_encrypted: str
    subscribed_events: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None
    rotated_at: datetime | None = None

    def is_subscribed(self, event_type: str) -> bool:
        return event_type in self.subscribed_events or "*" in self.subscribed_events


@dataclass
class WebhookDelivery:
    id: WebhookDeliveryId
    endpoint_id: WebhookEndpointId
    event_type: str
    payload: dict
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempt_count: int = 0
    last_attempted_at: datetime | None = None
    response_status_code: int | None = None
    created_at: datetime | None = None

    def can_retry(self, max_attempts: int) -> bool:
        return self.status is DeliveryStatus.FAILED and self.attempt_count < max_attempts
