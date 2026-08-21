"""Flutterwave V4 ``PaymentProviderPort`` implementation.

Every endpoint, request/response shape, and the webhook signature scheme below was verified
against Flutterwave's own official documentation and engineering blog (developer.flutterwave.com,
dev.to/flutterwaveeng — checked 2026-08-20) before being written here — none of it is guessed,
given real card data and live money are involved:
  - OAuth2 token exchange: docs/authentication
  - Live API base URL (f4bexperience.flutterwave.com) vs. sandbox: docs/environments
  - Card encryption scheme: docs/encryption (see ``encryption.py``)
  - /orchestration/direct-charges request/response shape: docs/payment-orchestrator-flow
  - Webhook signature (HMAC-SHA256 -> base64, ``flutterwave-signature`` header): docs/webhooks

V4 has no hosted-checkout product yet (Flutterwave's own engineering blog: "still in work,
coming out very soon") — this is the raw-card orchestrator flow, which means card data
transits our backend for the single encrypt-and-forward step. It is never persisted, never
logged, and discarded immediately after this call returns (docs constitution §5).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

from modules.billing.domain.payment import CardDetails, ChargeResult, CustomerInfo
from modules.billing.domain.value_objects import ChargeStatus
from modules.billing.infrastructure.flutterwave.encryption import FlutterwaveCardEncryptor

TOKEN_URL = "https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token"
LIVE_BASE_URL = "https://f4bexperience.flutterwave.com"
SANDBOX_BASE_URL = "https://developersandbox-api.flutterwave.com"

GetCredential = Callable[[str], Awaitable[str | None]]


class FlutterwaveNotConfiguredError(RuntimeError):
    """Raised when a required credential (client_id/client_secret/encryption_key) is missing —
    never silently falls back to an unauthenticated or unencrypted request."""


class FlutterwaveProviderError(RuntimeError):
    """Wraps a non-2xx response from Flutterwave's API with enough detail to act on, without
    ever including the request's card fields (they were never in the error path to begin with —
    only the response body, which is the provider's own message, is included)."""


def _customer_payload(customer: CustomerInfo) -> dict:
    return {
        "name": {"first": customer.first_name, "middle": customer.middle_name, "last": customer.last_name},
        "email": customer.email,
        "phone": {"country_code": customer.phone_country_code, "number": customer.phone_number},
        "address": {
            "line1": customer.address_line1,
            "city": customer.city,
            "state": customer.state,
            "postal_code": customer.postal_code,
            "country": customer.country,
        },
    }


def _parse_charge_result(data: dict) -> ChargeResult:
    status_raw = data.get("status")
    charge_id = data.get("id", "")
    if status_raw == "succeeded":
        return ChargeResult(provider_charge_id=charge_id, status=ChargeStatus.SUCCEEDED)

    next_action = data.get("next_action") or {}
    if next_action.get("type") == "redirect_url":
        redirect = (next_action.get("redirect_url") or {}).get("url")
        return ChargeResult(
            provider_charge_id=charge_id,
            status=ChargeStatus.PENDING,
            redirect_url=redirect,
            message="Additional customer action required (3DS/OTP).",
        )
    if status_raw in ("pending", "processing"):
        return ChargeResult(provider_charge_id=charge_id, status=ChargeStatus.PENDING, message="Charge is processing.")
    return ChargeResult(provider_charge_id=charge_id, status=ChargeStatus.FAILED, message=str(data.get("message") or "Charge failed."))


@dataclass
class FlutterwavePaymentProvider:
    get_credential: GetCredential  # async fn(label) -> plaintext or None, backed by the vault
    base_url: str = LIVE_BASE_URL
    timeout_seconds: int = 20
    client: httpx.AsyncClient | None = None  # injectable for tests (httpx.MockTransport)

    async def _require_credential(self, label: str) -> str:
        value = await self.get_credential(label)
        if not value:
            raise FlutterwaveNotConfiguredError(f"Flutterwave credential '{label}' is not configured.")
        return value

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        client_id = await self._require_credential("client_id")
        client_secret = await self._require_credential("client_secret")
        response = await client.post(
            TOKEN_URL,
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()["access_token"]

    async def create_charge(
        self,
        *,
        amount_cents: int,
        currency: str,
        reference: str,
        customer: CustomerInfo,
        card: CardDetails,
        redirect_url: str,
    ) -> ChargeResult:
        encryption_key = await self._require_credential("encryption_key")
        encrypted_card = FlutterwaveCardEncryptor(encryption_key).encrypt(card)

        body = {
            "amount": round(amount_cents / 100, 2),
            "currency": currency,
            "reference": reference,
            "payment_method": {"type": "card", "card": encrypted_card.to_payload()},
            "redirect_url": redirect_url,
            "customer": _customer_payload(customer),
        }

        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            access_token = await self._get_access_token(client)
            response = await client.post(
                f"{self.base_url}/orchestration/direct-charges",
                json=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Trace-Id": str(uuid.uuid4()),
                    # Stable per logical charge attempt (not per HTTP call) so a client-side
                    # retry of the same checkout never double-charges the card.
                    "X-Idempotency-Key": reference,
                },
            )
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            raise FlutterwaveProviderError(f"Flutterwave charge request failed ({response.status_code}): {response.text}")

        payload = response.json()
        return _parse_charge_result(payload.get("data") or {})

    async def get_charge_status(self, provider_charge_id: str) -> ChargeResult:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            access_token = await self._get_access_token(client)
            response = await client.get(
                f"{self.base_url}/charges/{provider_charge_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            raise FlutterwaveProviderError(f"Flutterwave charge lookup failed ({response.status_code}): {response.text}")
        return _parse_charge_result(response.json().get("data") or {})

    async def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """HMAC-SHA256 over the raw request body, base64-encoded, compared against the
        ``flutterwave-signature`` header using a constant-time comparison (docs/webhooks:
        "Flutterwave uses the secret hash you specify on your dashboard to hash the webhook
        response using HMAC-SHA256... returned as flutterwave-signature")."""
        secret_hash = await self.get_credential("webhook_secret_hash")
        if not secret_hash or not signature:
            return False
        expected = base64.b64encode(hmac.new(secret_hash.encode(), raw_body, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(expected, signature)
