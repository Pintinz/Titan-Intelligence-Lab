"""``PaymentProviderPort`` — the provider-agnostic contract ``CheckoutService`` depends on.
Deliberately narrow: only what an MVP checkout flow needs today (create a charge, check its
status, verify an inbound webhook's signature). A provider swap (e.g. adding Stripe alongside
Flutterwave) means implementing this Protocol, not touching ``CheckoutService``.
"""

from __future__ import annotations

from typing import Protocol

from modules.billing.domain.payment import CardDetails, ChargeResult, CustomerInfo


class PaymentProviderPort(Protocol):
    async def create_charge(
        self,
        *,
        amount_cents: int,
        currency: str,
        reference: str,
        customer: CustomerInfo,
        card: CardDetails,
        redirect_url: str,
    ) -> ChargeResult: ...

    async def get_charge_status(self, provider_charge_id: str) -> ChargeResult: ...

    async def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool: ...
