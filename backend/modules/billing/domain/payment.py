"""Payment-provider domain types (Milestone 6 follow-on) — kept separate from ``entities.py``
because ``CardDetails``/``ChargeResult`` are transient values that exist only for the duration
of one checkout request and are never persisted, unlike the aggregate roots in that module.

``PendingCheckout`` *is* persisted — it correlates a Flutterwave charge reference to what should
happen once the webhook confirms payment. It is the only mechanism that turns a real, verified
payment into an active ``Subscription``; the synchronous checkout response is never trusted for
that (docs constitution: "never trust frontend payment callbacks").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.billing.domain.value_objects import ChargeStatus, PendingCheckoutId, PlanId


@dataclass(frozen=True)
class CardDetails:
    """Raw card fields for the duration of one encrypt-and-forward request — never persisted,
    never logged. ``__repr__`` is overridden so an accidental ``logger.info(card)`` or an
    uncaught-exception traceback can never leak these into a log line."""

    number: str
    expiry_month: str
    expiry_year: str
    cvv: str

    def __repr__(self) -> str:
        return "CardDetails(<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True)
class CustomerInfo:
    email: str
    first_name: str
    last_name: str
    phone_country_code: str
    phone_number: str
    address_line1: str
    city: str
    state: str
    postal_code: str
    country: str
    middle_name: str = ""


@dataclass(frozen=True)
class ChargeResult:
    provider_charge_id: str
    status: ChargeStatus
    redirect_url: str | None = None  # set when the provider requires a 3DS/OTP browser redirect
    message: str = ""


@dataclass
class PendingCheckout:
    id: PendingCheckoutId
    reference: str  # our own generated reference — sent to the provider, echoed back on webhook
    subject_type: str
    subject_id: str
    plan_id: PlanId
    provider_charge_id: str | None = None
    status: ChargeStatus = ChargeStatus.PENDING
    created_at: datetime | None = None
    resolved_at: datetime | None = None
