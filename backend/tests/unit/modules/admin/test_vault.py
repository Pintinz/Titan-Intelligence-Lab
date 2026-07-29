import pytest
from cryptography.fernet import Fernet

from modules.admin.infrastructure.vault import DecryptionError, FernetCredentialVault


def test_encrypt_then_decrypt_round_trips():
    vault = FernetCredentialVault(key=Fernet.generate_key().decode())

    ciphertext = vault.encrypt("super-secret-api-key")

    assert ciphertext != "super-secret-api-key"
    assert vault.decrypt(ciphertext) == "super-secret-api-key"


def test_decrypt_with_wrong_key_raises():
    vault_a = FernetCredentialVault(key=Fernet.generate_key().decode())
    vault_b = FernetCredentialVault(key=Fernet.generate_key().decode())

    ciphertext = vault_a.encrypt("super-secret-api-key")

    with pytest.raises(DecryptionError):
        vault_b.decrypt(ciphertext)


def test_ciphertext_never_contains_plaintext():
    vault = FernetCredentialVault(key=Fernet.generate_key().decode())

    ciphertext = vault.encrypt("MY-VERY-SECRET-VALUE")

    assert "MY-VERY-SECRET-VALUE" not in ciphertext
