import pytest
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)


def test_password_hash_and_verify():
    password = "SecurePass@123"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)


def test_access_token_roundtrip():
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    token = create_access_token(subject=user_id, extra={"role": "customer"})
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "customer"
    assert payload["type"] == "access"


def test_refresh_token_type():
    token = create_refresh_token(subject="user-001")
    payload = decode_token(token)
    assert payload["type"] == "refresh"


def test_invalid_token_raises():
    with pytest.raises(ValueError):
        decode_token("not.a.valid.token")
