import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def fixed_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", key)
    # Force module re-import so it picks up the new env var
    import importlib
    import src.auth.encryption as mod
    importlib.reload(mod)
    return mod


def test_roundtrip(fixed_key):
    plaintext = "pk_1234567890_OAUTHTOKEN"
    encrypted = fixed_key.encrypt_token(plaintext)
    assert encrypted != plaintext
    assert fixed_key.decrypt_token(encrypted) == plaintext


def test_different_ciphertexts_each_call(fixed_key):
    """Fernet uses random IV → encrypting same plaintext twice yields different ciphertext."""
    a = fixed_key.encrypt_token("same")
    b = fixed_key.encrypt_token("same")
    assert a != b
    assert fixed_key.decrypt_token(a) == "same"
    assert fixed_key.decrypt_token(b) == "same"


def test_decrypt_with_wrong_key_raises(monkeypatch):
    import importlib
    import src.auth.encryption as mod
    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    importlib.reload(mod)
    encrypted = mod.encrypt_token("secret")

    monkeypatch.setenv("SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    importlib.reload(mod)
    with pytest.raises(Exception):  # cryptography.fernet.InvalidToken
        mod.decrypt_token(encrypted)


def test_missing_env_var_raises_at_import(monkeypatch):
    import importlib
    import src.auth.encryption as mod
    monkeypatch.delenv("SESSION_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_ENCRYPTION_KEY"):
        importlib.reload(mod)
