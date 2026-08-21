from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx
import pytest

from modules.billing.domain.payment import CardDetails, CustomerInfo
from modules.billing.domain.value_objects import ChargeStatus
from modules.billing.infrastructure.flutterwave.flutterwave_provider import (
    FlutterwaveNotConfiguredError,
    FlutterwavePaymentProvider,
    FlutterwaveProviderError,
    TOKEN_URL,
)

CREDENTIALS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "encryption_key": base64.b64encode(b"0" * 32).decode(),
    "webhook_secret_hash": "test-webhook-secret",
}


async def _get_credential(label: str) -> str | None:
    return CREDENTIALS.get(label)


def _card() -> CardDetails:
    return CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")


def _customer() -> CustomerInfo:
    return CustomerInfo(
        email="jane@example.com",
        first_name="Jane",
        last_name="Doe",
        phone_country_code="1",
        phone_number="5551234567",
        address_line1="1 Main St",
        city="Metropolis",
        state="NY",
        postal_code="10001",
        country="US",
    )


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _token_response(request: httpx.Request) -> httpx.Response | None:
    if request.url == httpx.URL(TOKEN_URL):
        return httpx.Response(200, json={"access_token": "fake-access-token", "expires_in": 600, "token_type": "Bearer"})
    return None


async def test_create_charge_succeeds_immediately():
    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _token_response(request)
        if token_response is not None:
            return token_response
        assert request.headers["Authorization"] == "Bearer fake-access-token"
        assert request.headers["X-Idempotency-Key"] == "ref-123"
        body = json.loads(request.content)
        assert body["amount"] == 9.99
        assert body["currency"] == "USD"
        assert body["payment_method"]["card"]["encrypted_card_number"]
        return httpx.Response(200, json={"status": "success", "data": {"id": "chg_abc", "status": "succeeded"}})

    provider = FlutterwavePaymentProvider(get_credential=_get_credential, client=_client_for(handler))

    result = await provider.create_charge(
        amount_cents=999, currency="USD", reference="ref-123", customer=_customer(), card=_card(),
        redirect_url="https://titaniq.test/checkout/return",
    )

    assert result.status is ChargeStatus.SUCCEEDED
    assert result.provider_charge_id == "chg_abc"


async def test_create_charge_returns_pending_with_3ds_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _token_response(request)
        if token_response is not None:
            return token_response
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "id": "chg_pending",
                    "status": "pending",
                    "next_action": {"type": "redirect_url", "redirect_url": {"url": "https://flutterwave.test/3ds"}},
                },
            },
        )

    provider = FlutterwavePaymentProvider(get_credential=_get_credential, client=_client_for(handler))

    result = await provider.create_charge(
        amount_cents=999, currency="USD", reference="ref-456", customer=_customer(), card=_card(),
        redirect_url="https://titaniq.test/checkout/return",
    )

    assert result.status is ChargeStatus.PENDING
    assert result.redirect_url == "https://flutterwave.test/3ds"


async def test_create_charge_maps_declined_to_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _token_response(request)
        if token_response is not None:
            return token_response
        return httpx.Response(
            200, json={"status": "success", "data": {"id": "chg_declined", "status": "declined", "message": "Card declined"}}
        )

    provider = FlutterwavePaymentProvider(get_credential=_get_credential, client=_client_for(handler))

    result = await provider.create_charge(
        amount_cents=999, currency="USD", reference="ref-789", customer=_customer(), card=_card(),
        redirect_url="https://titaniq.test/checkout/return",
    )

    assert result.status is ChargeStatus.FAILED


async def test_create_charge_raises_on_http_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _token_response(request)
        if token_response is not None:
            return token_response
        return httpx.Response(422, json={"status": "failed", "error": {"message": "Invalid card number"}})

    provider = FlutterwavePaymentProvider(get_credential=_get_credential, client=_client_for(handler))

    with pytest.raises(FlutterwaveProviderError):
        await provider.create_charge(
            amount_cents=999, currency="USD", reference="ref-err", customer=_customer(), card=_card(),
            redirect_url="https://titaniq.test/checkout/return",
        )


async def test_create_charge_raises_when_encryption_key_missing():
    async def missing_key(label: str) -> str | None:
        return None if label == "encryption_key" else CREDENTIALS.get(label)

    provider = FlutterwavePaymentProvider(get_credential=missing_key)

    with pytest.raises(FlutterwaveNotConfiguredError):
        await provider.create_charge(
            amount_cents=999, currency="USD", reference="ref-noconf", customer=_customer(), card=_card(),
            redirect_url="https://titaniq.test/checkout/return",
        )


async def test_verify_webhook_signature_accepts_correct_hmac():
    provider = FlutterwavePaymentProvider(get_credential=_get_credential)
    raw_body = b'{"type":"charge.completed","data":{"id":"chg_abc","status":"succeeded"}}'
    expected = base64.b64encode(hmac.new(b"test-webhook-secret", raw_body, hashlib.sha256).digest()).decode()

    assert await provider.verify_webhook_signature(raw_body, expected) is True


async def test_verify_webhook_signature_rejects_tampered_body():
    provider = FlutterwavePaymentProvider(get_credential=_get_credential)
    raw_body = b'{"type":"charge.completed","data":{"id":"chg_abc","status":"succeeded"}}'
    signature_for_different_body = base64.b64encode(hmac.new(b"test-webhook-secret", b"different", hashlib.sha256).digest()).decode()

    assert await provider.verify_webhook_signature(raw_body, signature_for_different_body) is False


async def test_verify_webhook_signature_rejects_when_secret_not_configured():
    async def no_secret(label: str) -> str | None:
        return None if label == "webhook_secret_hash" else CREDENTIALS.get(label)

    provider = FlutterwavePaymentProvider(get_credential=no_secret)

    assert await provider.verify_webhook_signature(b"{}", "anything") is False
