"""Checkout endpoints — initiating a card charge and receiving Flutterwave's webhook
confirmation (Milestone 6 follow-on). See ``modules.billing.application.checkout_service`` for
the security model: subscription state changes only from a verified webhook, never from this
router's synchronous checkout response.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth_deps import get_current_user
from apps.api.composition import build_checkout_service, get_session
from modules.billing.application.checkout_service import PlanNotFoundError, WebhookSignatureInvalidError
from modules.billing.domain.payment import CardDetails, ChargeResult, CustomerInfo
from modules.billing.domain.value_objects import SubjectType
from modules.billing.infrastructure.flutterwave.flutterwave_provider import (
    FlutterwaveNotConfiguredError,
    FlutterwaveProviderError,
)
from modules.identity.domain.entities import User

router = APIRouter(prefix="/api/v1/billing", tags=["checkout"])


def envelope(data=None, meta=None, error=None):
    return {"data": data, "meta": meta or {}, "error": error}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CheckoutCardRequest(BaseModel):
    number: str
    expiry_month: str
    expiry_year: str
    cvv: str


class CheckoutCustomerRequest(BaseModel):
    email: str
    first_name: str
    last_name: str
    middle_name: str = ""
    phone_country_code: str
    phone_number: str
    address_line1: str
    city: str
    state: str
    postal_code: str
    country: str


class CheckoutRequest(BaseModel):
    plan_key: str
    card: CheckoutCardRequest
    customer: CheckoutCustomerRequest
    redirect_url: str


def _serialize_charge_result(result: ChargeResult) -> dict:
    return {"status": result.status.value, "redirect_url": result.redirect_url, "message": result.message}


@router.post("/checkout")
async def checkout(
    payload: CheckoutRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    service = build_checkout_service(session)
    card = CardDetails(
        number=payload.card.number,
        expiry_month=payload.card.expiry_month,
        expiry_year=payload.card.expiry_year,
        cvv=payload.card.cvv,
    )
    customer = CustomerInfo(
        email=payload.customer.email,
        first_name=payload.customer.first_name,
        last_name=payload.customer.last_name,
        middle_name=payload.customer.middle_name,
        phone_country_code=payload.customer.phone_country_code,
        phone_number=payload.customer.phone_number,
        address_line1=payload.customer.address_line1,
        city=payload.customer.city,
        state=payload.customer.state,
        postal_code=payload.customer.postal_code,
        country=payload.customer.country,
    )
    try:
        result = await service.initiate_checkout(
            plan_key=payload.plan_key,
            subject_type=SubjectType.USER,
            subject_id=str(user.id),
            card=card,
            customer=customer,
            redirect_url=payload.redirect_url,
            now=_now(),
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except FlutterwaveNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except FlutterwaveProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return envelope(_serialize_charge_result(result))


@router.post("/webhooks/flutterwave")
async def flutterwave_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    raw_body = await request.body()
    signature = request.headers.get("flutterwave-signature", "")
    service = build_checkout_service(session)
    try:
        await service.handle_webhook(raw_body=raw_body, signature=signature, now=_now())
    except WebhookSignatureInvalidError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None
    return envelope({"received": True})
