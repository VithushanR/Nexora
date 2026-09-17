"""
backend/tests/test_encryption.py

Part D — tests for auth/encryption.py
"""

import pytest

from auth.encryption import encrypt_bytes, decrypt_bytes


class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_original(self):
        original = b"%PDF-1.4 fake pdf content for testing"
        encrypted = encrypt_bytes(original)
        decrypted = decrypt_bytes(encrypted)
        assert decrypted == original

    def test_encrypted_output_differs_from_input(self):
        original = b"some plaintext bytes"
        encrypted = encrypt_bytes(original)
        assert encrypted != original

    def test_encrypting_same_input_twice_gives_different_ciphertext(self):
        # Fernet includes a timestamp + random IV, so encrypting the same
        # plaintext twice should NOT produce identical ciphertext -- this
        # is expected behavior, not a bug, and worth asserting so nobody
        # "fixes" it later thinking it's a determinism issue.
        original = b"identical content"
        first = encrypt_bytes(original)
        second = encrypt_bytes(original)
        assert first != second
        # But both still decrypt back to the same original.
        assert decrypt_bytes(first) == original
        assert decrypt_bytes(second) == original

    def test_large_file_bytes_round_trip(self):
        # Simulate a larger PDF-sized payload.
        original = b"%PDF-1.4" + os_urandom_stub(500_000)
        encrypted = encrypt_bytes(original)
        decrypted = decrypt_bytes(encrypted)
        assert decrypted == original


def os_urandom_stub(n: int) -> bytes:
    import os
    return os.urandom(n)


class TestInvalidInput:
    def test_decrypt_garbage_raises_value_error(self):
        with pytest.raises(ValueError):
            decrypt_bytes(b"this is not valid encrypted data")

    def test_decrypt_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            decrypt_bytes(b"")

    def test_encrypt_rejects_non_bytes(self):
        with pytest.raises(TypeError):
            encrypt_bytes("not bytes, a string")

    def test_decrypt_rejects_non_bytes(self):
        with pytest.raises(TypeError):
            decrypt_bytes("not bytes, a string")


class TestTamperDetection:
    def test_tampered_ciphertext_fails_to_decrypt(self):
        """
        Fernet is authenticated encryption -- flipping a byte in the
        ciphertext must be detected, not silently decrypt to garbage.
        This matters for the D.4 checklist's spirit (integrity of stored
        files), even though D.4 doesn't name this test explicitly.
        """
        original = b"important document content"
        encrypted = encrypt_bytes(original)

        tampered = bytearray(encrypted)
        tampered[-5] ^= 0xFF  # flip bits near the end (inside the auth tag)
        tampered = bytes(tampered)

        with pytest.raises(ValueError):
            decrypt_bytes(tampered)
