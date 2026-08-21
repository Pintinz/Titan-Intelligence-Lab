"""Flutterwave V4 card-field encryption — AES-256-GCM, verified against Flutterwave's official
documentation (developer.flutterwave.com/docs/encryption, checked 2026-08-20) rather than
assumed, since guessing a crypto scheme for real card data is not acceptable.

Spec, as documented: the dashboard `encryption_key` is base64-decoded to raw key bytes; a single
12-character alphanumeric nonce is generated once per charge and shared across all four card
fields (encrypted_card_number, encrypted_expiry_month, encrypted_expiry_year, encrypted_cvv);
each field is independently AES-256-GCM encrypted with that nonce as the IV and no associated
data, and the ciphertext+tag is base64-encoded. Uses `cryptography` (already a project
dependency via `FernetCredentialVault`) — no new dependency added.
"""

from __future__ import annotations

import base64
import secrets
import string
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from modules.billing.domain.payment import CardDetails

_NONCE_LENGTH = 12
_NONCE_ALPHABET = string.ascii_letters + string.digits


def generate_nonce() -> str:
    return "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(_NONCE_LENGTH))


@dataclass
class EncryptedCard:
    nonce: str
    encrypted_card_number: str
    encrypted_expiry_month: str
    encrypted_expiry_year: str
    encrypted_cvv: str

    def to_payload(self) -> dict:
        return {
            "nonce": self.nonce,
            "encrypted_card_number": self.encrypted_card_number,
            "encrypted_expiry_month": self.encrypted_expiry_month,
            "encrypted_expiry_year": self.encrypted_expiry_year,
            "encrypted_cvv": self.encrypted_cvv,
        }


@dataclass
class FlutterwaveCardEncryptor:
    encryption_key: str  # plaintext, base64-encoded dashboard value — decoded per instance below

    def __post_init__(self) -> None:
        self._aes_key = base64.b64decode(self.encryption_key)

    def _encrypt_field(self, plaintext: str, nonce_bytes: bytes) -> str:
        aes_gcm = AESGCM(self._aes_key)
        ciphertext = aes_gcm.encrypt(nonce_bytes, plaintext.encode(), None)
        return base64.b64encode(ciphertext).decode()

    def encrypt(self, card: CardDetails) -> EncryptedCard:
        nonce = generate_nonce()
        nonce_bytes = nonce.encode()
        return EncryptedCard(
            nonce=nonce,
            encrypted_card_number=self._encrypt_field(card.number, nonce_bytes),
            encrypted_expiry_month=self._encrypt_field(card.expiry_month, nonce_bytes),
            encrypted_expiry_year=self._encrypt_field(card.expiry_year, nonce_bytes),
            encrypted_cvv=self._encrypt_field(card.cvv, nonce_bytes),
        )
