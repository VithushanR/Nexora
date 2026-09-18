"""
backend/auth/encryption.py

Part D — Security Core: encryption at rest.

Owned by: Part D
Used by: backend/routers/documents.py (uploaded PDF files)

Public surface:
    encrypt_bytes(data: bytes) -> bytes
    decrypt_bytes(data: bytes) -> bytes

Uses Fernet (symmetric encryption from the `cryptography` package) --
simple, authenticated encryption, exactly what the handoff doc (§D.3)
names as the intended approach: "encrypt the SQLite checkpointer DB
contents and uploaded files using ENCRYPTION_KEY (e.g. cryptography.fernet)".

Fails loudly at import if ENCRYPTION_KEY is missing, matching the same
"no silent fallback" pattern used in auth/jwt.py for JWT_SECRET_KEY.

Generating a key (one-time, per environment):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

This produces a base64-encoded 32-byte key already in the exact format
Fernet expects -- paste the output directly into ENCRYPTION_KEY in .env.
Do NOT hand-write or reuse a JWT_SECRET_KEY-style hex string here; Fernet
requires its own specific key format, not an arbitrary secret string.

Scope note: this module encrypts/decrypts arbitrary bytes -- it is used
today for uploaded PDF file contents (documents.py), and is written
generically enough to also be handed to Part A if they want to encrypt
SQLite checkpointer DB contents with the same key/utility, per D.3's
wording that both are Part D's encryption responsibility. Whether Part D
directly touches Part A's DB file, or just supplies this utility for
Part A to call, is a coordination question for the team -- this module
does not assume either answer.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

# ---------------------------------------------------------------------------
# Config — fail loudly, no silent fallback key
# ---------------------------------------------------------------------------

_ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not _ENCRYPTION_KEY:
    raise RuntimeError(
        "ENCRYPTION_KEY is not set. Refusing to start with no encryption key. "
        "Generate one with: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
        "and set ENCRYPTION_KEY in your environment or .env file."
    )

try:
    _fernet = Fernet(_ENCRYPTION_KEY.encode() if isinstance(_ENCRYPTION_KEY, str) else _ENCRYPTION_KEY)
except (ValueError, TypeError) as e:
    raise RuntimeError(
        "ENCRYPTION_KEY is set but is not a valid Fernet key. Generate one with: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    ) from e


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def encrypt_bytes(data: bytes) -> bytes:
    """
    Encrypts raw bytes for storage at rest.

    Args:
        data: plaintext bytes (e.g. an uploaded PDF's file content).

    Returns:
        Encrypted bytes, safe to write directly to disk. The output
        includes Fernet's built-in timestamp and authentication tag --
        it is NOT the same length as the input, and is not meant to be
        human-readable or further processed except via decrypt_bytes().
    """
    if not isinstance(data, bytes):
        raise TypeError("encrypt_bytes() requires bytes input")
    return _fernet.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """
    Decrypts bytes previously produced by encrypt_bytes().

    Args:
        data: encrypted bytes, as read back from disk.

    Returns:
        The original plaintext bytes.

    Raises:
        ValueError: if `data` is not valid ciphertext for this key (wrong
            key, corrupted file, or the data was never encrypted with
            encrypt_bytes() in the first place). Raised as ValueError
            rather than letting cryptography's InvalidToken leak out
            directly, so callers don't need to import cryptography
            themselves just to catch this.
    """
    if not isinstance(data, bytes):
        raise TypeError("decrypt_bytes() requires bytes input")
    try:
        return _fernet.decrypt(data)
    except InvalidToken as e:
        raise ValueError(
            "Could not decrypt data: wrong ENCRYPTION_KEY, corrupted file, "
            "or the data was never encrypted with this module."
        ) from e
