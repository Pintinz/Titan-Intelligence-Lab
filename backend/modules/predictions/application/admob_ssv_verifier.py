"""Google AdMob rewarded-ad Server-Side Verification (SSV) — proves a reward callback genuinely
came from Google, not a forged client request (spec Phase 5: "the reward must only occur after
the AdMob SDK reports the rewarded event... do not trust arbitrary frontend requests").

Mechanism, quoted from https://developers.google.com/admob/android/ssv (fetched and confirmed
2026-08-23 — this is the published spec, not reconstructed from memory):
  - The callback's last two query params are always `signature` then `key_id`, in that order.
  - The signed message is the raw query string UP TO (not including) `&signature=...`, as UTF-8
    bytes — every other param (ad_network, ad_unit, reward_amount, reward_item, timestamp,
    transaction_id, user_id, custom_data) is part of the signed content, in the order Google sent
    them — never re-sorted or reconstructed from a parsed dict, which could silently reorder them
    and break verification.
  - Signature algorithm: ECDSA, SHA-256, DER-encoded (`EcdsaVerifyJce(..., SHA256, DER)` per
    Google's own Java reference implementation on that page).
  - Public keys: GET https://www.gstatic.com/admob/reward/verifier-keys.json (the bare
    `gstatic.com` host 301-redirects here — confirmed live; use this URL directly rather than
    eating a redirect on every key refresh) ->
    `{"keys": [{"keyId": <int>, "pem": "<PEM>", "base64": "..."}]}` — the callback's `key_id`
    selects which entry to verify against; Google rotates these periodically.

NOT independently verified against a real Google-signed callback in this environment — there is
no AdMob account or real served ad here to produce one. This implements the published spec
faithfully; the AdMob console's own SSV callback URL configuration (pointing it at the endpoint
that calls this) is the external, credentialed step that proves it end-to-end, and that step is
explicitly out of reach in this environment.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ADMOB_VERIFIER_KEYS_URL = "https://www.gstatic.com/admob/reward/verifier-keys.json"


class AdMobSsvVerificationError(Exception):
    """Raised for any reason a callback cannot be trusted — missing params, unknown key_id,
    malformed signature, or a genuine signature mismatch. Every one of these must be treated
    identically by callers: refuse the reward. There is no "partially trusted" callback."""


@dataclass
class AdMobSsvKeyProvider:
    """Fetches and caches Google's published verification keys. A real, process-wide cache (not
    per-request) avoids hitting gstatic.com on every callback; a cache miss triggers exactly one
    refresh before giving up, since Google's periodic key rotation is a legitimate reason a
    known-good `key_id` might not be in a stale cache yet."""

    client: httpx.AsyncClient = field(default_factory=lambda: httpx.AsyncClient())
    _cache: dict[int, ec.EllipticCurvePublicKey] | None = field(default=None, init=False, repr=False)

    async def get_key(self, key_id: int) -> ec.EllipticCurvePublicKey:
        if self._cache is None:
            await self._refresh()
        key = (self._cache or {}).get(key_id)
        if key is None:
            await self._refresh()
            key = (self._cache or {}).get(key_id)
        if key is None:
            raise AdMobSsvVerificationError(f"unknown AdMob SSV key_id: {key_id}")
        return key

    async def _refresh(self) -> None:
        try:
            response = await self.client.get(ADMOB_VERIFIER_KEYS_URL, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 — every failure mode collapses to "can't verify"
            raise AdMobSsvVerificationError(f"could not fetch AdMob verification keys: {exc}") from exc
        self._cache = {
            int(entry["keyId"]): serialization.load_pem_public_key(entry["pem"].encode("utf-8"))
            for entry in payload.get("keys", [])
        }


async def verify_admob_ssv_callback(raw_query_string: str, keys: AdMobSsvKeyProvider) -> dict[str, str]:
    """`raw_query_string` must be the exact, unmodified query string as received (e.g. FastAPI's
    `request.url.query`, which preserves parameter order) — never re-serialized from a parsed
    dict first, which could reorder params and make a genuinely valid signature fail to verify.
    Returns the parsed, verified params on success; raises `AdMobSsvVerificationError` on any
    failure. All-or-nothing — never returns a partial result."""
    if "&signature=" not in f"&{raw_query_string}":
        raise AdMobSsvVerificationError("callback missing 'signature' parameter")

    signed_message, _, remainder = raw_query_string.partition("&signature=")
    signature_b64, sep, key_id_raw = remainder.partition("&key_id=")
    if not sep or not signature_b64 or not key_id_raw:
        raise AdMobSsvVerificationError("callback missing 'signature' or 'key_id' parameter")

    try:
        key_id = int(key_id_raw)
    except ValueError as exc:
        raise AdMobSsvVerificationError(f"malformed key_id: {key_id_raw!r}") from exc

    try:
        signature = base64.urlsafe_b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
    except Exception as exc:  # noqa: BLE001
        raise AdMobSsvVerificationError(f"malformed signature encoding: {exc}") from exc

    key = await keys.get_key(key_id)
    try:
        key.verify(signature, signed_message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise AdMobSsvVerificationError("signature verification failed") from exc

    params: dict[str, str] = {}
    for pair in signed_message.split("&"):
        if "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        params[k] = v
    return params
