"""Value objects for the Webhook Infrastructure bounded context (Milestone 6).

Built for future payment/integration providers (Stripe-style webhooks, org integrations) — no
real provider is wired yet, only the endpoint-registration/delivery/retry machinery.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXHAUSTED = "exhausted"  # retries exhausted, will not be attempted again


@dataclass(frozen=True)
class WebhookEndpointId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class WebhookDeliveryId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
