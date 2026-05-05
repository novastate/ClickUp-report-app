"""Fernet-based symmetric encryption for OAuth tokens stored in the DB.

The master key is read from SESSION_ENCRYPTION_KEY env var at import time.
If the key is rotated, all existing tokens become unreadable and users
must re-login. Generate a key with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from cryptography.fernet import Fernet

_key = os.environ.get("SESSION_ENCRYPTION_KEY")
if not _key:
    raise RuntimeError(
        "SESSION_ENCRYPTION_KEY env var is required. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

_fernet = Fernet(_key.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
