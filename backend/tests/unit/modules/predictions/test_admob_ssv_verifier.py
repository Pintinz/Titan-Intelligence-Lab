"""Real cryptographic tests for the AdMob rewarded-ad SSV verifier — a local EC P-256 keypair
signs a query string exactly the way Google's docs describe (ECDSA/SHA-256/DER over the raw query
string up to, not including, `&signature=`), and `verify_admob_ssv_callback` is exercised against
real signature bytes, not mocked crypto. This proves the verifier's own logic is internally
correct; it does NOT prove Google's real callback format matches this byte-for-byte (no AdMob
account exists in this environment to produce a real signed callback) — see the module docstring
on `admob_ssv_verifier.py` for what was independently confirmed against Google's published docs.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from modules.predictions.application.admob_ssv_verifier import (
    AdMobSsvKeyProvider,
    AdMobSsvVerificationError,
    verify_admob_ssv_callback,
)

KEY_ID = 1268887


def _keypair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


def _signed_query_string(private_key: ec.EllipticCurvePrivateKey, message: str, key_id: int = KEY_ID) -> str:
    signature = private_key.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{message}&signature={signature_b64}&key_id={key_id}"


@pytest.fixture
def key_provider_factory():
    """Returns a function that builds an `AdMobSsvKeyProvider` pre-seeded with a real public key —
    bypassing the real gstatic.com network fetch, which this test environment can't rely on."""

    def _make(public_key: ec.EllipticCurvePublicKey, key_id: int = KEY_ID) -> AdMobSsvKeyProvider:
        provider = AdMobSsvKeyProvider()
        provider._cache = {key_id: public_key}  # noqa: SLF001 — deliberate test seam, real field
        return provider

    return _make


async def test_valid_signature_verifies_and_returns_parsed_params(key_provider_factory):
    private_key, public_key = _keypair()
    message = (
        "ad_network=5450213213286189855&ad_unit=1234567890&reward_amount=2"
        "&reward_item=prediction_unlock&timestamp=1500000000&transaction_id=abc123"
        "&user_id=11111111-1111-1111-1111-111111111111"
    )
    query = _signed_query_string(private_key, message)

    params = await verify_admob_ssv_callback(query, key_provider_factory(public_key))

    assert params["transaction_id"] == "abc123"
    assert params["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert params["reward_amount"] == "2"


async def test_tampered_message_fails_verification(key_provider_factory):
    """A forged client request that copies a real signature but edits a param (e.g. swapping in
    a different user_id to steal someone else's reward) must be rejected — this is the exact
    attack Phase 5's "do not trust arbitrary frontend requests" rule exists to prevent."""
    private_key, public_key = _keypair()
    genuine = _signed_query_string(private_key, "user_id=victim&transaction_id=abc123")
    forged = genuine.replace("user_id=victim", "user_id=attacker")

    with pytest.raises(AdMobSsvVerificationError, match="signature verification failed"):
        await verify_admob_ssv_callback(forged, key_provider_factory(public_key))


async def test_signature_from_a_different_key_fails_verification(key_provider_factory):
    """Simulates a forged callback signed with an attacker-controlled key rather than Google's
    real one — must fail even though the message and key_id "look" well-formed."""
    attacker_key, _ = _keypair()
    _, real_public_key = _keypair()
    query = _signed_query_string(attacker_key, "user_id=x&transaction_id=abc123")

    with pytest.raises(AdMobSsvVerificationError, match="signature verification failed"):
        await verify_admob_ssv_callback(query, key_provider_factory(real_public_key))


async def test_unknown_key_id_fails_verification(key_provider_factory, monkeypatch):
    private_key, public_key = _keypair()
    query = _signed_query_string(private_key, "user_id=x&transaction_id=abc123", key_id=999999)
    provider = key_provider_factory(public_key, key_id=KEY_ID)
    # A genuine cache miss triggers one real refresh — stub it to an async no-op so this test
    # exercises only "still unknown after a miss", not a real gstatic.com round trip.
    async def _no_op_refresh():
        return None

    monkeypatch.setattr(provider, "_refresh", _no_op_refresh)

    with pytest.raises(AdMobSsvVerificationError, match="unknown AdMob SSV key_id"):
        await verify_admob_ssv_callback(query, provider)


async def test_missing_signature_parameter_fails_verification(key_provider_factory):
    _, public_key = _keypair()
    with pytest.raises(AdMobSsvVerificationError, match="missing 'signature'"):
        await verify_admob_ssv_callback("user_id=x&transaction_id=abc123", key_provider_factory(public_key))


async def test_key_provider_refreshes_once_on_cache_miss_before_giving_up(monkeypatch):
    """A real key rotation (Google publishes a new key_id) shouldn't be indistinguishable from a
    forged key_id — one refresh gives a legitimately-rotated key a chance to be picked up."""
    provider = AdMobSsvKeyProvider()
    calls = {"count": 0}

    async def fake_refresh():
        calls["count"] += 1
        provider._cache = {}  # still nothing — simulates a key_id that's genuinely never existed

    monkeypatch.setattr(provider, "_refresh", fake_refresh)

    with pytest.raises(AdMobSsvVerificationError, match="unknown AdMob SSV key_id"):
        await provider.get_key(42)

    assert calls["count"] == 2  # initial fetch (cache was None) + one retry on miss, not more
