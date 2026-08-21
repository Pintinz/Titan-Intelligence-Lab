from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from modules.billing.domain.payment import CardDetails
from modules.billing.infrastructure.flutterwave.encryption import FlutterwaveCardEncryptor, generate_nonce

TEST_KEY = base64.b64encode(b"0" * 32).decode()  # 32 raw bytes -> AES-256 key


def test_generate_nonce_is_twelve_alphanumeric_chars():
    nonce = generate_nonce()
    assert len(nonce) == 12
    assert nonce.isalnum()


def test_encrypt_produces_base64_ciphertext_for_each_field():
    encryptor = FlutterwaveCardEncryptor(TEST_KEY)
    card = CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")

    encrypted = encryptor.encrypt(card)

    for field in (
        encrypted.encrypted_card_number,
        encrypted.encrypted_expiry_month,
        encrypted.encrypted_expiry_year,
        encrypted.encrypted_cvv,
    ):
        base64.b64decode(field)  # raises if not valid base64


def test_same_nonce_shared_across_all_four_fields():
    encryptor = FlutterwaveCardEncryptor(TEST_KEY)
    card = CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")

    encrypted = encryptor.encrypt(card)

    assert len(encrypted.nonce) == 12
    payload = encrypted.to_payload()
    assert payload["nonce"] == encrypted.nonce


def test_round_trip_decrypts_to_original_plaintext():
    """Verifies the encryptor actually implements AES-256-GCM correctly by decrypting its own
    output with the standard library primitive directly — not just checking shape."""
    encryptor = FlutterwaveCardEncryptor(TEST_KEY)
    card = CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")

    encrypted = encryptor.encrypt(card)

    aes_key = base64.b64decode(TEST_KEY)
    aes_gcm = AESGCM(aes_key)
    nonce_bytes = encrypted.nonce.encode()

    decrypted_number = aes_gcm.decrypt(nonce_bytes, base64.b64decode(encrypted.encrypted_card_number), None)
    decrypted_cvv = aes_gcm.decrypt(nonce_bytes, base64.b64decode(encrypted.encrypted_cvv), None)

    assert decrypted_number.decode() == card.number
    assert decrypted_cvv.decode() == card.cvv


def test_two_encryptions_use_different_random_nonces():
    encryptor = FlutterwaveCardEncryptor(TEST_KEY)
    card = CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")

    first = encryptor.encrypt(card)
    second = encryptor.encrypt(card)

    assert first.nonce != second.nonce
    assert first.encrypted_card_number != second.encrypted_card_number


def test_card_details_repr_never_leaks_raw_values():
    card = CardDetails(number="4242424242424242", expiry_month="12", expiry_year="2030", cvv="123")

    text = repr(card)

    assert "4242424242424242" not in text
    assert "123" not in text
